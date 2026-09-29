"""Freeze, release-lock and durable-job rejection regressions."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from candidate_mapping import read_json
import rolling_control as rolling
from release_source_sanity import normalize
from validation_job import validate_request, run, verify_receipt
from candidate_mapping import sha
from source_fixture_host import pid_of


class RollingTests(unittest.TestCase):
    def setUp(self):
        self.control = read_json(rolling.CONTROL)
        self.state = dict(schemaVersion=1, goalId=self.control["goalId"],
                          targetUpstream=self.control["targetUpstream"], edge=None, stable=None, history=[])
        self.edge = dict(status="FAST_EDGE_PASS", goalId=self.state["goalId"],
                         upstreamCommit=self.state["targetUpstream"]["commit"], sourceCommit="a" * 40,
                         sourceTree="b" * 40, maintenanceCommit="c" * 40, maintenanceTree="d" * 40,
                         checks=dict.fromkeys(("deltaAudit", "releaseSourceSanity", "format", "affectedSource",
                                               "nativeNextest68", "solCatalog", "independentReview"), "PASS"))

    def test_admitted_retarget_invalidates_edge(self):
        self.state["edge"] = self.edge
        newer = dict(version="0.160.0", tag="rust-v0.160.0", commit="f" * 40)
        with patch.object(rolling, "read_json", return_value={**self.control, "targetUpstream": newer}):
            result = rolling.transition(self.state, "retarget", newer)
        self.assertEqual(result["targetUpstream"], newer)
        self.assertIsNone(result["edge"])
        self.assertIsNotNone(self.state["edge"])

    def test_started_and_failed_qualification_never_retarget(self):
        frozen = rolling.transition(self.state, "begin-stable", self.edge)
        for status in ("STABLE_QUALIFICATION_STARTED", "FAIL", "PASS"):
            frozen["stable"]["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "frozen"):
                rolling.transition(frozen, "retarget", self.control["targetUpstream"])
        with self.assertRaises(ValueError):
            rolling.transition(frozen, "begin-stable", self.edge)

    def test_missing_or_mismatched_fast_evidence_cannot_freeze(self):
        for key, value in (("status", "RUNNING"), ("upstreamCommit", "f" * 40),
                           ("sourceTree", "main"), ("checks", {"nativeNextest68": "PASS"})):
            invalid = deepcopy(self.edge)
            invalid[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                rolling.transition(self.state, "begin-stable", invalid)

    def test_stable_freezes_maintenance_identity(self):
        frozen = rolling.transition(self.state, "begin-stable", self.edge)["stable"]
        self.assertEqual((frozen["maintenanceCommit"], frozen["maintenanceTree"]),
                         (self.edge["maintenanceCommit"], self.edge["maintenanceTree"]))

    def test_cli_releases_windows_lock_after_success_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            command = [sys.executable, "-S", "-B", rolling.__file__, "init", "--state", str(state)]
            result = subprocess.run(command, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(read_json(state)["stable"])
            self.assertFalse(state.with_suffix(".transition.lock").exists())
            before = state.read_bytes()
            result = subprocess.run(command, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(state.read_bytes(), before)
            self.assertFalse(state.with_suffix(".transition.lock").exists())


class ReleaseLockTests(unittest.TestCase):
    LOCAL = b'[[package]]\nname = "codex-local"\nversion = "0.0.0"\ndependencies = ["external"]\n\n'
    EXTERNAL = b'[[package]]\nname = "external"\nversion = "1.2.3"\nsource = "registry+https://example.invalid"\nchecksum = "abc"\n'

    def test_only_local_version_changes_and_already_normal_is_idempotent(self):
        original = b'version = 4\n\n' + self.LOCAL + self.EXTERNAL
        updated, changed = normalize(original, {"codex-local"}, "0.159.0")
        self.assertEqual(updated, original.replace(b'"0.0.0"', b'"0.159.0"'))
        self.assertTrue(updated.endswith(self.EXTERNAL))
        self.assertEqual(changed, ["codex-local"])
        self.assertEqual(normalize(updated, {"codex-local"}, "0.159.0"), (updated, []))

    def test_unknown_missing_duplicate_and_nonrelease_local_version_rejected(self):
        for lock, names in ((self.LOCAL, set()), (self.EXTERNAL, {"codex-local"}),
                            (self.LOCAL * 2, {"codex-local"}),
                            (self.LOCAL.replace(b'"0.0.0"', b'"0.158.0"'), {"codex-local"})):
            with self.subTest(lock=lock), self.assertRaises(ValueError):
                normalize(lock, names, "0.159.0")


class DurableJobTests(unittest.TestCase):
    def test_completed_receipt_rejects_tampered_identity_hash_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = dict(path=str(root / "source"), commit="a" * 40, tree="b" * 40)
            request = dict(schemaVersion=1, kind="DURABLE_VALIDATION_JOB", lane="FAST_EDGE",
                           env={}, source=binding, maintenance={**binding, "path": str(root / "maintenance")},
                           cwd=str(root), command=[sys.executable, "-I", "-S", "-c", 'print("ok")'])
            (root / "request.json").write_text(json.dumps(request))
            def clean_identity(handle):
                return dict(pid=pid_of(handle), created=1, queryReturn=1, lastError=0, inJob=False)
            with patch("validation_job.verify"), patch("validation_job.identity", side_effect=clean_identity):
                run(root)
            receipt = read_json(root / "receipt.json")
            launch = dict(pid=receipt["pid"], requestSha256=sha(root / "request.json"),
                          workerIdentity=receipt["workerIdentity"], workerSha256=sha(sys.modules["validation_job"].__file__),
                          workerExecutable=sys.executable, workerExecutableSha256=sha(sys.executable))
            (root / "launch.json").write_text(json.dumps(launch))
            with patch("validation_job.validate_request"):
                self.assertEqual(verify_receipt(root, "PASS")[1]["status"], "PASS")
                for field, invalid in (("requestSha256", "0" * 64), ("workerSha256", "0" * 64),
                                       ("childIdentity", {**receipt["childIdentity"], "created": 0}),
                                       ("logSha256", "0" * 64),
                                       ("maintenance", {**binding, "path": "C:/other"})):
                    altered = {**receipt, field: invalid}
                    (root / "receipt.json").write_text(json.dumps(altered))
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        verify_receipt(root, "PASS")
                stale = {**receipt, "status": "RUNNING", "pid": 99999999,
                         "workerIdentity": {**receipt["workerIdentity"], "pid": 99999999}}
                launch["pid"] = 99999999
                launch["workerIdentity"] = stale["workerIdentity"]
                (root / "receipt.json").write_text(json.dumps(stale))
                (root / "launch.json").write_text(json.dumps(launch))
                with self.assertRaises(ValueError):
                    verify_receipt(root, "RUNNING")
    def test_real_command_progress_receipt_finishes_and_changed_source_fails(self):
        for changed in (False, True):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                binding = dict(path=str(root / "source"), commit="a" * 40, tree="b" * 40)
                request = dict(schemaVersion=1, kind="DURABLE_VALIDATION_JOB", lane="FAST_EDGE",
                               env={}, source=binding, maintenance={**binding, "path": str(root / "maintenance")},
                               cwd=str(root), command=[sys.executable, "-I", "-S", "-c", 'print("durable complete")'])
                (root / "request.json").write_text(json.dumps(request))
                calls = [None, None, ValueError("source changed")] if changed else [None] * 4
                with patch("validation_job.verify", side_effect=calls), patch("validation_job.identity", return_value={"created": 1}):
                    run(root)
                receipt = read_json(root / "receipt.json")
                self.assertEqual(receipt["status"], "FAIL" if changed else "PASS")
                self.assertEqual(receipt["exitCode"], 0)
                self.assertIn("finishedUtc", receipt)
                self.assertIn("childPid", receipt)
                self.assertEqual((root / "command.log").read_text().strip(), "durable complete")
                self.assertFalse((root / "receipt.update").exists())

    def test_stable_requires_matching_freeze_and_no_secret_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            executable = root / "command.exe"
            executable.write_bytes(b"test")
            binding = dict(path=str(root / "source"), commit="a" * 40, tree="b" * 40)
            request = dict(schemaVersion=1, kind="DURABLE_VALIDATION_JOB", lane="STABLE",
                           env={}, source=binding, maintenance={**binding, "path": str(root / "maintenance")},
                           cwd=str(root), command=[str(executable)], stableState=str(state), stableStateSha256="invalid")
            with patch("validation_job.verify"):
                for freeze in (None, {"status": "STABLE_QUALIFICATION_STARTED", "sourceCommit": "c" * 40,
                                      "sourceTree": "b" * 40}):
                    state.write_text(json.dumps({"stable": freeze}))
                    with self.assertRaises(ValueError):
                        validate_request(request, root / "output")
                request["env"] = {"OPENAI_API_KEY": "synthetic"}
                with self.assertRaisesRegex(ValueError, "environment"):
                    validate_request(request, root / "output")


if __name__ == "__main__":
    unittest.main()
