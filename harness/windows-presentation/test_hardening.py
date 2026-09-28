"""Focused fail-closed checks; no Codex package or account is executed."""
import base64
import hashlib
import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import candidate_mapping as mapping
from daemon_rpc import RPC


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "candidate.json"
        train = mapping.read_json(mapping.ROOT / "goals/WBP-UPSTREAM-0158-PORT-TRAIN-001.manifest.json")
        self.value = dict(schemaVersion=1, kind="UNRELEASED_CANDIDATE", goalId=train["goalId"],
                          upstreamVersion=train["targetUpstream"]["version"], upstreamCommit=train["targetUpstream"]["commit"],
                          downstreamCommit="a" * 40, downstreamTree="b" * 40, target="x86_64-pc-windows-msvc",
                          packageVariant="codex", cargoProfile="release", sourcePath=str(self.root / "source"),
                          packageDir=str(self.root / "package"), outputDir=str(self.root / "evidence"))
        self.dirty = ""
        self.head = self.value["downstreamCommit"]
        self.tree = self.value["downstreamTree"]

    def git(self, _, *args):
        if args[0] == "rev-parse":
            return self.head
        if args[0] == "show":
            return self.tree
        if args[0] == "status":
            return self.dirty
        return ""

    def load(self, mode="build"):
        mapping.write_json(self.file, self.value)
        with patch.object(mapping, "git", self.git):
            return mapping.load(self.file, mode)

    def test_explicit_unreleased_mapping(self):
        original = mapping.sha(mapping.ROOT / "manifest.json")
        value, paths = self.load()
        self.assertEqual(value["kind"], "UNRELEASED_CANDIDATE")
        self.assertEqual(paths["outputDir"], self.root / "evidence")
        self.assertEqual(mapping.sha(mapping.ROOT / "manifest.json"), original)
        self.assertFalse(paths["outputDir"].exists())

    def test_released_unknown_missing_and_wrong_upstream_rejected(self):
        for key, value in (("kind", "RELEASED"), ("upstreamCommit", "c" * 40),
                           ("cargoProfile", "debug"), ("schemaVersion", True),
                           ("downstreamCommit", "main")):
            with self.subTest(key=key):
                before = self.value[key]
                self.value[key] = value
                with self.assertRaises(ValueError):
                    self.load()
                self.value[key] = before
        self.value["downstreamTag"] = "released"
        with self.assertRaises(ValueError):
            self.load()
        self.value.pop("downstreamTag")
        self.value.pop("downstreamTree")
        with self.assertRaises(ValueError):
            self.load()

    def test_dirty_mismatched_and_nonancestor_source_rejected(self):
        self.dirty = " M file.rs"
        with self.assertRaises(ValueError):
            self.load()
        self.dirty = ""
        self.head = "c" * 40
        with self.assertRaises(ValueError):
            self.load()
        self.head = self.value["downstreamCommit"]
        self.tree = "c" * 40
        with self.assertRaises(ValueError):
            self.load()
        self.tree = self.value["downstreamTree"]
        def failing_git(source, *args):
            if args[0] == "merge-base":
                raise ValueError("not descendant")
            return self.git(source, *args)
        mapping.write_json(self.file, self.value)
        with patch.object(mapping, "git", failing_git), self.assertRaises(ValueError):
            mapping.load(self.file, "build")

    def test_path_overlaps_reuse_and_relative_paths_rejected(self):
        for destination in ("source", "source/package", "."):
            self.value["packageDir"] = str(self.root / destination)
            with self.assertRaises(ValueError):
                self.load()
        self.value["packageDir"] = "relative"
        with self.assertRaises(ValueError):
            self.load()
        self.value["packageDir"] = str(self.root / "package")
        Path(self.value["outputDir"]).mkdir()
        with self.assertRaises(ValueError):
            self.load()

    def test_package_provenance_tamper_rejected(self):
        package = Path(self.value["packageDir"])
        for name in mapping.FILES:
            target = package / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture-only")
        mapping.write_json(package / "codex-package.json", {"version": "0.158.0", "target": self.value["target"], "entrypoint": "bin/codex.exe"})
        mapping.write_json(self.file, self.value)
        with patch.object(mapping, "git", self.git):
            mapping.record_build(self.file)
            mapping.load(self.file)
            (package / "bin/codex.exe").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                mapping.load(self.file)

    def test_duplicate_json_rejected(self):
        self.file.write_text('{"kind":"RELEASED","kind":"UNRELEASED_CANDIDATE"}')
        with self.assertRaises(ValueError):
            mapping.read_json(self.file)


class CatalogTests(unittest.TestCase):
    def test_sol_fixture_uses_custom_code_mode_entrypoint(self):
        import mock_responses
        from qualify_candidate import check_sol_tool_requests
        events = [json.loads(line[6:]) for line in mock_responses.function_call(
            "resp-1", "call-1", "bounded", "code_mode_only").decode().splitlines() if line.startswith("data: ")]
        item = events[1]["item"]
        self.assertEqual((item["type"], item["name"]), ("custom_tool_call", "exec"))
        self.assertIn("tools.exec_command", item["input"])
        self.assertNotIn("arguments", item)
        requests = [{"body": {"model": "gpt-6-sol", "tools": [{"type": "custom", "name": "exec"}],
                              "input": [{"type": "custom_tool_call_output", "call_id": f"call-{i}"} for i in range(1, 4)]}}
                    for _ in range(4)]
        check_sol_tool_requests(requests, {"tool_mode": "code_mode_only"})
        requests[0]["body"]["tools"].append({"type": "function", "name": "exec_command"})
        with self.assertRaises(ValueError):
            check_sol_tool_requests(requests, {"tool_mode": "code_mode_only"})
        with self.assertRaises(ValueError):
            check_sol_tool_requests(requests, {"tool_mode": "function"})

    def setUp(self):
        self.expected = {"default_reasoning_level": "medium", "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}], "default_service_tier": "priority"}
        self.actual = {"model": "gpt-6-sol", "defaultReasoningEffort": "medium", "supportedReasoningEfforts": [{"reasoningEffort": "low"}, {"reasoningEffort": "medium"}], "defaultServiceTier": "priority"}

    def test_runtime_sol_exact_contract(self):
        self.assertEqual(mapping.check_runtime_sol([self.actual], self.expected), self.actual)
        for entries in ([], [self.actual, self.actual]):
            with self.assertRaises(ValueError):
                mapping.check_runtime_sol(entries, self.expected)
        for key, value in (("defaultReasoningEffort", "low"), ("supportedReasoningEfforts", []), ("defaultServiceTier", "standard")):
            bad = dict(self.actual, **{key: value})
            with self.assertRaises(ValueError):
                mapping.check_runtime_sol([bad], self.expected)


class ProtocolTests(unittest.TestCase):
    def test_upgrade_masking_pagination_notifications_and_error(self):
        from io import StringIO
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        errors = []
        def server():
            try:
                sock, _ = listener.accept()
                with sock:
                    raw = b""
                    while not raw.endswith(b"\r\n\r\n"):
                        raw += sock.recv(1)
                    key = next(line.split(b": ")[1] for line in raw.split(b"\r\n") if line.startswith(b"Sec-WebSocket-Key"))
                    accept = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
                    sock.sendall(b"HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")
                    for number in (1, 2):
                        header = sock.recv(2)
                        self.assertTrue(header[1] & 128)
                        size = header[1] & 127
                        if size == 126:
                            size = struct.unpack("!H", sock.recv(2))[0]
                        mask = sock.recv(4)
                        body = bytearray()
                        while len(body) < size:
                            body.extend(sock.recv(size - len(body)))
                        request = json.loads(bytes(b ^ mask[i % 4] for i, b in enumerate(body)))
                        self.assertEqual(request["id"], number)
                        messages = [{"method": "thread/started", "params": {}},
                                    {"id": 1, "result": {"data": [], "nextCursor": None}}] if number == 1 else [{"id": 2, "error": {"code": -1}}]
                        for message in messages:
                            payload = json.dumps(message).encode()
                            sock.sendall(bytes([129, len(payload)]) + payload)
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=server)
        thread.start()
        try:
            sock = socket.create_connection(listener.getsockname(), timeout=5)
            rpc = RPC(sock, StringIO())
            self.assertEqual(rpc.call("model/list", {})["nextCursor"], None)
            self.assertEqual(rpc.pending[0]["method"], "thread/started")
            with self.assertRaises(ValueError):
                rpc.call("bad", {})
            sock.close()
        finally:
            listener.close()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors, errors)


@unittest.skipUnless(os.name == "nt", "Windows native APIs")
class WindowsTests(unittest.TestCase):
    def test_account_and_cloud_environment_not_inherited(self):
        import qualify_candidate as gate
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                "OPENAI_API_KEY": "SYNTHETIC_DO_NOT_COPY", "AWS_SECRET_ACCESS_KEY": "SYNTHETIC_DO_NOT_COPY",
                "CODEX_HOME": "SYNTHETIC_DO_NOT_COPY"}):
            environment = gate.isolated_environment(Path(temporary))
            self.assertEqual(environment["OPENAI_API_KEY"], "local-smoke-only")
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
            self.assertNotIn("CODEX_HOME", environment)
            self.assertTrue(Path(environment["USERPROFILE"]).is_relative_to(Path(temporary)))

    def test_structured_cli_stdout_is_separate_from_diagnostics(self):
        import sys
        import qualify_candidate as gate
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "cli.json"
            process = gate.start([sys.executable, "-B", "-c",
                                  "import sys; print('{\\\"status\\\":\\\"stopped\\\"}'); print('diagnostic', file=sys.stderr)"],
                                 gate.isolated_environment(root), output, separate_error=True)
            gate.wait(process, 10)
            self.assertEqual(mapping.read_json(output)["status"], "stopped")
            self.assertEqual(Path(str(output) + ".stderr.log").read_text().strip(), "diagnostic")

    def test_early_mock_failure_cleans_helpers_and_records_failure(self):
        from contextlib import ExitStack
        import qualify_candidate as gate
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, package, source = base / "evidence", base / "package", base / "source"
            package.mkdir()
            for name in mapping.FILES:
                file = package / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"fixture-only")
            class FakeProcess:
                pid = 999
                returncode = 0
                killed = False
                def communicate(self, timeout):
                    (root / "no-daemon").mkdir(parents=True)
                    return b"fixture smoke", None
                def wait(self, timeout=None):
                    return 0
                def poll(self):
                    return 0 if self.killed else None
                def kill(self):
                    self.killed = True
            class FakeLedger:
                def __init__(self, *args):
                    self.thread = type("Thread", (), {"start": lambda _: None})()
                def finish(self, **kwargs):
                    pass
            server = FakeProcess()
            with ExitStack() as stack:
                stack.enter_context(patch.object(gate, "load", return_value=(
                    {"upstreamCommit": "a"*40}, {"outputDir": root, "packageDir": package, "sourcePath": source})))
                stack.enter_context(patch.object(gate, "sha", return_value="hash"))
                stack.enter_context(patch.object(gate, "package_files", return_value={}))
                stack.enter_context(patch.object(gate, "sol_contract", return_value={"tool_mode": "code_mode_only"}))
                stack.enter_context(patch.object(gate.subprocess, "Popen", return_value=FakeProcess()))
                stack.enter_context(patch.object(gate, "Process", return_value=object()))
                stack.enter_context(patch.object(gate, "Ledger", FakeLedger))
                stack.enter_context(patch.object(gate, "isolated_environment", return_value={"PATH": "fixture-only"}))
                stack.enter_context(patch.object(gate, "lifetime_fixture"))
                stack.enter_context(patch.object(gate, "positive_control"))
                stack.enter_context(patch.object(gate, "start", return_value=server))
                stack.enter_context(patch.object(gate, "snapshot", return_value=[]))
                stack.enter_context(patch.object(gate, "ready", side_effect=ValueError("INJECTED_EARLY_FAILURE")))
                with self.assertRaisesRegex(ValueError, "INJECTED_EARLY_FAILURE"):
                    gate.managed_run(base / "mapping.json", "pwsh")
            self.assertTrue(server.killed)
            self.assertFalse(mapping.read_json(root / "failure.json")["qualificationClaimed"])

    def test_failed_graceful_shutdown_preserves_handles_for_cleanup(self):
        import subprocess
        import sys
        from windows_native import Ledger, Process
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "ready"
            child = subprocess.Popen([sys.executable, "-B", "-c",
                                      "import sys,time; from pathlib import Path; Path(sys.argv[1]).write_text('ready'); time.sleep(30)", str(marker)],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(marker.exists(), "Owned fixture did not initialize")
                owned = Process(child.pid)
                ledger = Ledger(owned, Path(temporary) / "not-created/processes.json")
                ledger.thread.start()
                with self.assertRaises(ValueError):
                    ledger.finish()
                self.assertIsNotNone(owned.handle)
                ledger.finish(cleanup=True)
                ledger.finish(cleanup=True)
                self.assertEqual(child.wait(5), 79)
                self.assertIsNone(owned.handle)
                self.assertTrue(ledger.path.exists())
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(5)

    def test_residual_unknown_query_and_harmless_are_rejected(self):
        from windows_native import lifetime_acceptance
        lifetime_acceptance(False)
        for membership in (True, None, "unknown", 0):
            with self.assertRaises(ValueError):
                lifetime_acceptance(membership)

    def test_unknown_visible_console_is_ambiguity(self):
        from datetime import datetime, timezone
        from qualify_candidate import relevant_events
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "windows.tsv"
            path.write_text("win_event\tclass\tprocess_started_utc\tprocess\tpid\n8002\tConsoleWindowClass\t\t\t1\n")
            with self.assertRaises(ValueError):
                relevant_events(path, datetime.now(timezone.utc))

    def test_native_socket_address_transport(self):
        import ctypes as c
        from windows_native import uds_connect
        # Local disposable endpoint; no product daemon involved.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "s"
            address = str(path).encode()
            self.assertLess(len(address), 108)
            class Address(c.Structure):
                _fields_ = [("family", c.c_ushort), ("path", c.c_char * 108)]
            target = Address(1, address)
            listener = socket.socket(1, 1)
            native = c.WinDLL("ws2_32")
            native.bind.argtypes = [c.c_size_t, c.c_void_p, c.c_int]
            self.assertEqual(native.bind(listener.fileno(), c.byref(target), c.sizeof(target)), 0)
            listener.listen()
            try:
                client = uds_connect(path)
                native.accept.argtypes = [c.c_size_t, c.c_void_p, c.c_void_p]
                native.accept.restype = c.c_size_t
                native.recv.argtypes = [c.c_size_t, c.c_void_p, c.c_int, c.c_int]
                native.closesocket.argtypes = [c.c_size_t]
                server = native.accept(listener.fileno(), None, None)
                self.assertNotEqual(server, c.c_size_t(-1).value)
                with client:
                    client.sendall(b"fixture")
                    buffer = c.create_string_buffer(7)
                    self.assertEqual(native.recv(server, buffer, 7, 0), 7)
                    self.assertEqual(buffer.raw, b"fixture")
                native.closesocket(server)
            finally:
                listener.close()


if __name__ == "__main__":
    unittest.main()
