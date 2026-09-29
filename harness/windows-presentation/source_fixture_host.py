"""One-shot clean native worker. Original/registered handles own all cleanup."""
import ctypes as c
from ctypes import wintypes as w
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import time

from candidate_mapping import read_json, require, sha
from source_fixture_contract import validate_binding, validate_completed

k = c.WinDLL("kernel32", use_last_error=True)


def api(name, args, result=w.BOOL):
    function = getattr(k, name)
    function.argtypes, function.restype = args, result
    return function


close = api("CloseHandle", [w.HANDLE])
wait = api("WaitForSingleObject", [w.HANDLE, w.DWORD], w.DWORD)
terminate = api("TerminateProcess", [w.HANDLE, w.UINT])
pid_of = api("GetProcessId", [w.HANDLE], w.DWORD)
current = api("GetCurrentProcess", [], w.HANDLE)
process_times = api("GetProcessTimes", [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4)
in_job = api("IsProcessInJob", [w.HANDLE, w.HANDLE, c.POINTER(w.BOOL)])
image_of = api("QueryFullProcessImageNameW", [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)])
resume = api("ResumeThread", [w.HANDLE], w.DWORD)
exit_of = api("GetExitCodeProcess", [w.HANDLE, c.POINTER(w.DWORD)])
open_process = api("OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE)
duplicate = api("DuplicateHandle", [w.HANDLE, w.HANDLE, w.HANDLE, c.POINTER(w.HANDLE),
                w.DWORD, w.BOOL, w.DWORD])


class Startup(c.Structure):
    _fields_ = [("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR),
                ("title", w.LPWSTR)] + [(n, w.DWORD) for n in
                ("x", "y", "xs", "ys", "xc", "yc", "fill", "flags")] + [
                ("show", w.WORD), ("cbres", w.WORD), ("res", w.LPVOID),
                ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE)]


class ProcessInfo(c.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]


class StartupEx(c.Structure):
    _fields_ = [("startup", Startup), ("attributes", w.LPVOID)]


create = api("CreateProcessW", [w.LPCWSTR, w.LPWSTR, w.LPVOID, w.LPVOID, w.BOOL,
             w.DWORD, w.LPVOID, w.LPCWSTR, w.LPVOID, c.POINTER(ProcessInfo)])
init_attributes = api("InitializeProcThreadAttributeList", [w.LPVOID, w.DWORD, w.DWORD,
                       c.POINTER(c.c_size_t)])
update_attributes = api("UpdateProcThreadAttribute", [w.LPVOID, w.DWORD, c.c_size_t,
                         w.LPVOID, c.c_size_t, w.LPVOID, w.LPVOID])
delete_attributes = api("DeleteProcThreadAttributeList", [w.LPVOID], None)


def checked(ok, operation):
    if not ok:
        raise OSError(c.get_last_error(), operation)


def identity(handle):
    fields = [w.FILETIME() for _ in range(4)]
    checked(process_times(handle, *[c.byref(t) for t in fields]), "GetProcessTimes")
    pid = pid_of(handle)
    checked(pid, "GetProcessId")
    member = w.BOOL()
    c.set_last_error(0)
    result = in_job(handle, None, c.byref(member))
    error = c.get_last_error()
    checked(result, "IsProcessInJob")
    require(not member.value, "Native fixture retains a Job")
    return {"pid": pid, "created": (fields[0].dwHighDateTime << 32) | fields[0].dwLowDateTime,
            "queryReturn": result, "lastError": error, "inJob": False}


def image(handle):
    size, text = w.DWORD(32768), c.create_unicode_buffer(32768)
    checked(image_of(handle, 0, text, c.byref(size)), "QueryFullProcessImageNameW")
    return Path(text.value).resolve()


def atomic_json(path, data):
    require(not path.exists(), "Fixture evidence already exists")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.rename(path)


def isolated_env(home, extra):
    # Allowlist avoids consulting account credentials or personal application state.
    allowed = ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROCESSOR_ARCHITECTURE",
               "NUMBER_OF_PROCESSORS")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    for folder in (home, home / ".codex", home / "tmp", home / "roaming", home / "local"):
        folder.mkdir(parents=True, exist_ok=True)
    env.update(HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(home / ".codex"),
               TEMP=str(home / "tmp"), TMP=str(home / "tmp"), APPDATA=str(home / "roaming"),
               LOCALAPPDATA=str(home / "local"), GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL="NUL", GIT_TERMINAL_PROMPT="0")
    env.update(extra)
    return env


def run_host(binary, binding, output, *, timeout=30, synthetic_args=None, fault="normal"):
    synthetic = synthetic_args is not None
    validate_binding(binding, synthetic=synthetic)
    binary, output = Path(binary).resolve(), Path(output).resolve()
    require(binary.is_file() and sha(binary) == binding["binarySha256"], "Worker binary changed")
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "binding.json", binding)
    # Controller may have ambient Jobs; only the worker/child must be independent.
    fields = [w.FILETIME() for _ in range(4)]
    checked(process_times(current(), *[c.byref(t) for t in fields]), "Controller identity")
    controller_created = (fields[0].dwHighDateTime << 32) | fields[0].dwLowDateTime
    env = isolated_env(output / "home", {
        "CODEX_TEST_NATIVE_ROLE": "worker", "CODEX_TEST_NATIVE_DIR": str(output),
        "CODEX_TEST_NATIVE_CONTROLLER_PID": str(os.getpid()),
        "CODEX_TEST_NATIVE_CONTROLLER_CREATED": str(controller_created),
        "CODEX_TEST_NATIVE_FAULT": fault})
    env_buffer = c.create_unicode_buffer("\0".join(f"{key}={value}" for key, value in
                                      sorted(env.items(), key=lambda pair: pair[0].upper())) + "\0\0")
    args = [str(binary)] + (synthetic_args if synthetic else
            ["--exact", binding["testName"], "--nocapture", "--test-threads=1"])
    info, startup = ProcessInfo(), StartupEx()
    startup.startup.cb = c.sizeof(startup)
    child_handle, worker_record, child_record = None, None, None
    fault_observer_handle, fault_observation = None, None
    completed, cleanup_errors = False, []
    try:
        # Restricted handle inheritance: only this fixture's three stdio files.
        with open("NUL", "rb") as stdin, (output / "worker-libtest.log").open("xb") as stdout, \
                (output / "worker-stderr.log").open("xb") as stderr:
            handles = [msvcrt.get_osfhandle(stream.fileno()) for stream in (stdin, stdout, stderr)]
            for handle in handles:
                os.set_handle_inheritable(handle, True)
            startup.startup.flags = 0x100
            startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = handles
            size = c.c_size_t()
            c.set_last_error(0)
            require(not init_attributes(None, 1, 0, c.byref(size)) and c.get_last_error() == 122,
                    "Cannot size restricted handle list")
            attribute_buffer = c.create_string_buffer(size.value)
            startup.attributes = c.cast(attribute_buffer, w.LPVOID)
            checked(init_attributes(startup.attributes, 1, 0, c.byref(size)), "Initialize handle list")
            try:
                handle_list = (w.HANDLE * 3)(*handles)
                checked(update_attributes(startup.attributes, 0, 0x20002, handle_list,
                                          c.sizeof(handle_list), None, None), "Restrict inherited handles")
                checked(create(str(binary), c.create_unicode_buffer(subprocess.list2cmdline(args)),
                               None, None, True, 0x09080404, env_buffer, str(output),
                               c.byref(startup), c.byref(info)), "Launch one-shot breakaway worker")
            finally:
                delete_attributes(startup.attributes)
        worker_record = identity(info.process)
        require(worker_record["pid"] == info.pid and image(info.process) == binary, "Wrong worker image")
        checked(resume(info.thread) != 0xffffffff, "Resume clean worker")
        checked(close(info.thread), "Close original worker thread")
        info.thread = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Harness-only observation proves the kernel crash backstop without
            # registering or terminating this child. Never used for source PASS.
            if synthetic and fault in ("crash-before-debug-check", "crash-before-registration",
                                       "crash-during-registration") and fault_observer_handle is None:
                fault_file = output / "fault-child.json"
                if fault_file.exists():
                    observed = read_json(fault_file)
                    require(wait(info.process, 0) == 258, "Fault worker exited before measurement")
                    handle = open_process(0x1000 | 0x100000, False, observed["pid"])
                    checked(handle, "Open exact synthetic observer child")
                    try:
                        require(identity(handle) == observed and image(handle) == binary,
                                "Synthetic child identity mismatch")
                        fault_observer_handle = handle
                        fault_observation = {"child": observed, "childTerminationUsed": False}
                    except BaseException:
                        close(handle)
                        raise
                    atomic_json(output / "fault-observer-ack.json", {"measurementOnly": True})
            registration = output / "registration.json"
            if child_handle is None and registration.exists():
                record = read_json(registration)
                require(record["binding"] == binding and record["worker"] == worker_record,
                        "Registration binding/worker mismatch")
                source_handle = record["sourceHandle"]
                require(type(source_handle) is int and source_handle > 0, "Invalid source handle")
                # Controller receives its duplicate directly from the API. There
                # is no remote target-handle publication interval on worker death.
                owned = w.HANDLE()
                checked(duplicate(info.process, source_handle, current(), c.byref(owned),
                                  0, False, 2), "Duplicate original worker-owned child handle")
                try:
                    child_record = identity(owned.value)
                    require(record["child"] == child_record and image(owned.value) == binary and
                            child_record["pid"] != info.pid and
                            child_record["created"] >= worker_record["created"], "Wrong registered child")
                except BaseException:
                    # API-created local duplicate is ours to close. Termination
                    # remains prohibited until its fixture identity is verified.
                    checked(close(owned.value), "Close unverified owned duplicate")
                    raise
                child_handle = owned.value
                require(wait(child_handle, 0) == 258, "Child died before real guard")
                atomic_json(output / "registration-ack.json", {"binding": binding, "child": child_record})
            status = wait(info.process, 0)
            require(status in (0, 258), "Worker wait unknown")
            if status == 0:
                break
            time.sleep(.01)
        else:
            raise TimeoutError("Source fixture worker timed out")
        require(child_handle is not None, "Worker exited without cleanup registration")
        worker_exit = w.DWORD()
        checked(exit_of(info.process, c.byref(worker_exit)), "GetExitCodeProcess")
        require(worker_exit.value == 0, "Source fixture worker failed")
        if not synthetic:
            log = (output / "worker-libtest.log").read_text(encoding="utf-8", errors="replace")
            require(binding["testName"] in log and
                    re.search(r"test result: ok\. 1 passed; 0 failed; 0 ignored;", log),
                    "Native re-exec did not pass exactly one selected Rust test")
        require(wait(child_handle, 5000) == 0, "Fixture child not reaped")
        receipt = read_json(output / "worker-receipt.json")
        require(receipt["worker"] == worker_record and receipt["child"] == child_record,
                "Original/registered process identity disagreement")
        require(sha(binary) == binding["binarySha256"], "Binary changed during native phase")
        checked(close(child_handle), "Close registered child handle")
        child_handle = None
        checked(close(info.process), "Close original worker handle")
        info.process = None
        envelope = {"binding": binding, "workerReceipt": receipt, "worker": worker_record,
                    "child": child_record, "workerExit": worker_exit.value, "childWait": 0,
                    "registeredBeforeGuard": True, "workerHandleClosed": True,
                    "childHandleClosed": True, "completed": True}
        validate_completed(envelope, receipt, binding, synthetic=synthetic)
        atomic_json(output / "controller-receipt.json", envelope)
        completed = True
        return envelope
    finally:
        # Terminate worker first: its debug-owner death kills even an unregistered
        # suspended child. A failure path never writes a completed envelope.
        for name, handle in (("worker", info.process), ("child", child_handle)):
            if not handle:
                continue
            try:
                result = wait(handle, 0)
                require(result in (0, 258), f"Unknown {name} cleanup wait")
                if result == 258:
                    checked(terminate(handle, 79), f"Terminate original/registered {name}")
                require(wait(handle, 5000) == 0, f"{name} cleanup incomplete")
            except BaseException as error:
                cleanup_errors.append(str(error))
            finally:
                if not close(handle):
                    cleanup_errors.append(f"Close {name} handle failed")
        if info.thread and not close(info.thread):
            cleanup_errors.append("Close worker thread failed")
        if fault_observer_handle:
            fault_observation["wait"] = wait(fault_observer_handle, 5000)
            fault_observation["handleClosed"] = bool(close(fault_observer_handle))
            if fault_observation["wait"] != 0 or not fault_observation["handleClosed"]:
                cleanup_errors.append("Pre-registration crash backstop failed")
        atomic_json(output / "host-cleanup.json", {"completed": completed,
                    "worker": worker_record, "child": child_record, "errors": cleanup_errors,
                    "faultObservation": fault_observation,
                    "candidateGuardAcceptance": completed and not synthetic,
                    "scope": "synthetic harness only" if synthetic else "native source fixture"})
        require(not cleanup_errors, f"Native cleanup failed: {cleanup_errors}")
