"""Owned Windows process handles; no PID-only termination or ancestor Job mutation."""
import ctypes as c
from ctypes import wintypes as w
import json
import socket
import threading
import time
from pathlib import Path

from candidate_mapping import require

k = c.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
k.OpenProcess.restype = w.HANDLE
k.CloseHandle.argtypes = [w.HANDLE]
k.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4
k.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, c.POINTER(w.BOOL)]
k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
k.WaitForSingleObject.restype = w.DWORD
k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
k.CreateToolhelp32Snapshot.restype = w.HANDLE


def checked(ok, operation):
    if not ok:
        raise OSError(c.get_last_error(), operation)


def lifetime_acceptance(membership):
    # Only a successful query proving no membership satisfies G01R.
    require(membership is False, "REJECT_UNPROVEN_RESIDUAL_JOB_MEMBERSHIP")


class Process:
    def __init__(self, pid):
        self.pid = pid
        self.handle = k.OpenProcess(0x1000 | 0x100000 | 1, False, pid)
        checked(self.handle, "OpenProcess")
        try:
            times = [w.FILETIME() for _ in range(4)]
            checked(k.GetProcessTimes(self.handle, *[c.byref(t) for t in times]), "GetProcessTimes")
            self.created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            size, image = w.DWORD(32768), c.create_unicode_buffer(32768)
            checked(k.QueryFullProcessImageNameW(self.handle, 0, image, c.byref(size)), "QueryFullProcessImageName")
            self.image = image.value
        except BaseException:
            self.close()
            raise

    def alive(self):
        result = k.WaitForSingleObject(self.handle, 0)
        require(result in (0, 258), "Process wait ambiguous")
        return result == 258

    def membership(self):
        inside = w.BOOL()
        checked(k.IsProcessInJob(self.handle, None, c.byref(inside)), "IsProcessInJob")
        return bool(inside.value)

    def terminate(self):
        if self.alive():
            checked(k.TerminateProcess(self.handle, 79), "Terminate owned process")
        require(k.WaitForSingleObject(self.handle, 5000) == 0, "Owned process did not exit")

    def close(self):
        if self.handle:
            k.CloseHandle(self.handle)
            self.handle = None


class Entry(c.Structure):
    _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
                ("heap", c.c_size_t), ("module", w.DWORD), ("threads", w.DWORD),
                ("parent", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD),
                ("exe", w.WCHAR * 260)]


k.Process32FirstW.argtypes = [w.HANDLE, c.POINTER(Entry)]
k.Process32NextW.argtypes = [w.HANDLE, c.POINTER(Entry)]


def snapshot():
    handle = k.CreateToolhelp32Snapshot(2, 0)
    checked(handle and handle != c.c_void_p(-1).value, "Process snapshot")
    entries = []
    try:
        entry = Entry()
        entry.size = c.sizeof(entry)
        ok = k.Process32FirstW(handle, c.byref(entry))
        checked(ok, "Process32First")
        while ok:
            entries.append((entry.pid, entry.parent, entry.exe))
            ok = k.Process32NextW(handle, c.byref(entry))
        require(c.get_last_error() == 18, "Process enumeration incomplete")
        return entries
    finally:
        k.CloseHandle(handle)


class Ledger:
    def __init__(self, root_process, path):
        self.records = {root_process.pid: root_process}
        self.root = root_process.pid
        self.path = Path(path)
        self.errors = []
        self.closed = False
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.watch, daemon=True)

    def watch(self):
        try:
            while not self.stop.is_set():
                entries = snapshot()
                # Iterate to discover children even if parent ordering differs.
                for _ in range(8):
                    added = False
                    for pid, parent, name in entries:
                        if pid in self.records or parent not in self.records:
                            continue
                        owner = self.records[parent]
                        if not owner.alive():
                            continue  # Never trust a reused dead parent's PID.
                        try:
                            child = Process(pid)
                        except OSError as error:
                            # An exited child can disappear before opening. Access denial is ambiguity.
                            if error.errno != 87:
                                raise
                            continue  # A missed short-lived child cannot satisfy functional coverage.
                        if child.created < owner.created:
                            child.close()
                            continue
                        child.parent = parent
                        child.name = name
                        self.records[pid] = child
                        added = True
                    if not added:
                        break
                self.stop.wait(.01)
        except BaseException as error:
            self.errors.append(str(error))

    def finish(self, cleanup=False):
        if self.closed:
            return
        self.stop.set()
        self.thread.join(5)
        require(not self.thread.is_alive(), "Process observer did not stop")
        records = list(self.records.values())
        remaining = [p for p in records if p.alive()]
        report = [{
            "pid": p.pid, "created": p.created, "image": p.image,
            "parent": getattr(p, "parent", None), "aliveAtShutdown": p.alive()
        } for p in records]
        if not cleanup:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            require(not self.errors, f"Process observer failed: {self.errors}")
            require(not remaining, "Owned orphan remains after graceful shutdown")
        if cleanup:
            for process in reversed(remaining):
                try:
                    process.terminate()
                except BaseException as error:
                    self.errors.append(str(error))
            # Evidence failures must not prevent owned-handle termination/closure.
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            except BaseException as error:
                self.errors.append(str(error))
        for process in records:
            process.close()
        self.closed = True
        require(not self.errors, f"Process observer failed: {self.errors}")


def uds_connect(path):
    # CPython on Windows does not expose AF_UNIX address conversion; Winsock does.
    address = str(path).encode("utf-8")
    require(len(address) < 108, "Windows local socket path exceeds supported sockaddr_un")
    class Address(c.Structure):
        _fields_ = [("family", c.c_ushort), ("path", c.c_char * 108)]
    target = Address(1, address)
    sock = socket.socket(1, socket.SOCK_STREAM)
    winsock = c.WinDLL("ws2_32")
    winsock.connect.argtypes = [c.c_size_t, c.c_void_p, c.c_int]
    try:
        if winsock.connect(sock.fileno(), c.byref(target), c.sizeof(target)) != 0:
            raise OSError(winsock.WSAGetLastError(), "Windows local socket connect")
        sock.settimeout(15)
        return sock
    except BaseException:
        sock.close()
        raise
