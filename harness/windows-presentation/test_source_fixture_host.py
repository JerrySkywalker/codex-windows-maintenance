"""Real native cleanup faults on disposable synthetic workers; no Rust guard proof."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

from candidate_mapping import read_json, sha
from source_fixture_contract import TEST_NAME
from source_fixture_host import run_host
import source_fixture_host


class SourceFixtureHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.TemporaryDirectory(prefix="wbp-source-fixture-")
        cls.binary = Path(cls.root.name) / "Synthetic.exe"
        compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        source = Path(__file__).with_name("SourceFixtureSynthetic.cs")
        subprocess.run([str(compiler), "/nologo", "/target:exe", "/platform:x64",
                        "/reference:System.Web.Extensions.dll", f"/out:{cls.binary}", str(source)],
                       check=True, capture_output=True, timeout=60,
                       creationflags=subprocess.CREATE_NO_WINDOW)

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()

    def binding(self):
        return {"schemaVersion": 1, "kind": "HARNESS_PROTOCOL_ONLY", "runId": str(uuid.uuid4()),
                "sourceCommit": "1" * 40, "sourceTree": "2" * 40,
                "testName": TEST_NAME, "binarySha256": sha(self.binary)}

    def test_build_discovery_preserves_only_installation_locations(self):
        locations = {"ProgramFiles": "C:\\Program Files", "ProgramFiles(x86)": "C:\\Program Files (x86)",
                     "ProgramW6432": "C:\\Program Files", "SystemDrive": "C:"}
        isolated_home = Path(self.root.name) / "discovery-home"
        with patch.dict(os.environ, {**locations, "OPENAI_API_KEY": "synthetic-test-secret",
                                     "HOME": "C:\\unrelated-personal-home",
                                     "USERPROFILE": "C:\\unrelated-personal-home"}):
            env = source_fixture_host.isolated_env(isolated_home, {})
        self.assertEqual({key: env[key] for key in locations}, locations)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual({key: env[key] for key in ("HOME", "USERPROFILE")},
                         {"HOME": str(isolated_home), "USERPROFILE": str(isolated_home)})

    def test_exit_race_requires_same_owned_handle_exit(self):
        def exited(*args):
            source_fixture_host.c.set_last_error(5)
            return 0
        with patch.object(source_fixture_host, "wait", side_effect=[258, 0, 0]) as waiting, \
             patch.object(source_fixture_host, "terminate", side_effect=exited):
            source_fixture_host.stop_owned(123, "worker")
        self.assertEqual(waiting.call_args_list[1].args, (123, 5000))

    def test_cleanup_denied_or_unknown_exit_remains_failure(self):
        for error, final_wait in ((5, 258), (5, 0xffffffff), (6, 0)):
            with self.subTest(error=error, final_wait=final_wait):
                def denied(*args):
                    source_fixture_host.c.set_last_error(error)
                    return 0
                with patch.object(source_fixture_host, "wait", side_effect=[258, final_wait]), \
                     patch.object(source_fixture_host, "terminate", side_effect=denied):
                    with self.assertRaises(OSError):
                        source_fixture_host.stop_owned(123, "worker")

    def test_original_child_and_registered_handles_close(self):
        output = Path(self.root.name) / "normal"
        result = run_host(self.binary, self.binding(), output, synthetic_args=[])
        self.assertTrue(result["completed"])
        cleanup = read_json(output / "host-cleanup.json")
        self.assertEqual(cleanup["errors"], [])
        self.assertFalse(cleanup["candidateGuardAcceptance"])
        self.assertEqual(cleanup["scope"], "HARNESS_PROTOCOL_ONLY")

    def test_source_launch_restriction_never_falls_back(self):
        output = Path(self.root.name) / "source-host-restriction"
        binding = self.binding()
        binding["kind"] = "SOURCE_GUARD_NATIVE_FIXTURE"
        def blocked(*args):
            source_fixture_host.c.set_last_error(5)
            return 0
        with patch.object(source_fixture_host, "create", side_effect=blocked) as creation:
            with self.assertRaises(OSError):
                run_host(self.binary, binding, output)
        self.assertEqual(creation.call_count, 1)
        self.assertTrue(creation.call_args.args[5] & 0x01000000)
        self.assertFalse((output / "controller-receipt.json").exists())
        self.assertFalse(read_json(output / "host-cleanup.json")["candidateGuardAcceptance"])

    def test_registration_failure_crash_and_timeout_reject_acceptance(self):
        for fault in ("registration-failure", "crash-before-debug-check", "crash-before-registration",
                      "crash-during-registration", "crash-after-registration", "timeout"):
            with self.subTest(fault=fault):
                output = Path(self.root.name) / fault
                with self.assertRaises((ValueError, TimeoutError, OSError)):
                    run_host(self.binary, self.binding(), output, timeout=2,
                             synthetic_args=[], fault=fault)
                self.assertFalse((output / "controller-receipt.json").exists())
                cleanup = read_json(output / "host-cleanup.json")
                self.assertFalse(cleanup["completed"])
                self.assertEqual(cleanup["errors"], [])
                self.assertFalse(cleanup["candidateGuardAcceptance"])
                if fault in ("crash-before-debug-check", "crash-before-registration", "crash-during-registration"):
                    self.assertEqual(cleanup["faultObservation"]["wait"], 0)
                    self.assertTrue(cleanup["faultObservation"]["handleClosed"])
                    self.assertFalse(cleanup["faultObservation"]["childTerminationUsed"])


if __name__ == "__main__":
    unittest.main()
