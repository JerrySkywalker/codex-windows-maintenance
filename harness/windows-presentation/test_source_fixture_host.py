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
