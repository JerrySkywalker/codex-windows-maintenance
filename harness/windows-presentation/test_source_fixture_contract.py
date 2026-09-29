"""Required receipt rejection cases; no source guard acceptance is claimed."""
import copy
import unittest

from source_fixture_contract import TEST_NAME, validate_completed


class SourceFixtureContractTests(unittest.TestCase):
    def setUp(self):
        self.binding = {"schemaVersion": 1, "kind": "SOURCE_GUARD_NATIVE_FIXTURE",
                        "runId": "25b2b1b6-2f9b-4c92-a90c-9bfd94b8b53f", "sourceCommit": "1" * 40,
                        "sourceTree": "2" * 40, "testName": TEST_NAME, "binarySha256": "3" * 64}
        worker = {"pid": 101, "created": 1000, "queryReturn": 1, "lastError": 0, "inJob": False}
        child = dict(worker, pid=102, created=1001)
        self.receipt = {"binding": copy.deepcopy(self.binding), "binaryBlake3": "4" * 64,
                        "worker": worker, "child": child, "guard": "ACCEPTED",
                        "debugKillOnExitReturn": 1, "testResult": "PASSED", "cleanup": {
                        "killed": True, "reaped": True, "originalChildHandleClosed": True,
                        "debugImageHandlesClosed": True}}
        self.envelope = {"binding": copy.deepcopy(self.binding), "workerReceipt": copy.deepcopy(self.receipt),
                         "worker": copy.deepcopy(worker), "child": copy.deepcopy(child),
                         "workerExit": 0, "childWait": 0, "registeredBeforeGuard": True,
                         "workerHandleClosed": True, "childHandleClosed": True, "completed": True}

    def verify(self):
        validate_completed(self.envelope, self.receipt, self.binding)

    def reject_receipt(self, path, value):
        target = self.receipt
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        self.envelope["workerReceipt"] = copy.deepcopy(self.receipt)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            self.verify()

    def test_completed_contract(self):
        self.verify()

    def test_absent_receipt(self):
        self.receipt = {}
        with self.assertRaises((ValueError, KeyError)):
            self.verify()

    def test_stale_run(self):
        self.reject_receipt(["binding", "runId"], "15b2b1b6-2f9b-4c92-a90c-9bfd94b8b53f")

    def test_wrong_commit(self):
        self.reject_receipt(["binding", "sourceCommit"], "5" * 40)

    def test_wrong_tree(self):
        self.reject_receipt(["binding", "sourceTree"], "5" * 40)

    def test_wrong_binary(self):
        self.reject_receipt(["binding", "binarySha256"], "5" * 64)

    def test_wrong_test(self):
        self.reject_receipt(["binding", "testName"], "different::test")

    def test_failed_job_query(self):
        self.reject_receipt(["child", "queryReturn"], 0)

    def test_unknown_job_query(self):
        self.reject_receipt(["child", "inJob"], None)

    def test_residual_job(self):
        self.reject_receipt(["child", "inJob"], True)

    def test_api_error(self):
        self.reject_receipt(["worker", "lastError"], 5)

    def test_guard_failure(self):
        self.reject_receipt(["guard"], "REJECTED")

    def test_missing_original_handle_cleanup(self):
        self.reject_receipt(["cleanup", "originalChildHandleClosed"], False)

    def test_missing_reap(self):
        self.reject_receipt(["cleanup", "reaped"], False)

    def test_missing_debug_handle_cleanup(self):
        self.reject_receipt(["cleanup", "debugImageHandlesClosed"], False)

    def test_missing_crash_backstop(self):
        self.reject_receipt(["debugKillOnExitReturn"], 0)

    def test_worker_failure_timeout_or_missing_controller_cleanup(self):
        for key, value in (("workerExit", 91), ("childWait", 258), ("completed", False),
                           ("registeredBeforeGuard", False), ("workerHandleClosed", False),
                           ("childHandleClosed", False)):
            with self.subTest(field=key):
                envelope = copy.deepcopy(self.envelope)
                envelope[key] = value
                with self.assertRaises(ValueError):
                    validate_completed(envelope, self.receipt, self.binding)

    def test_split_receipts(self):
        self.envelope["workerReceipt"]["binaryBlake3"] = "5" * 64
        with self.assertRaises(ValueError):
            self.verify()

    def test_wrong_native_identity(self):
        self.envelope["child"]["created"] += 1
        with self.assertRaises(ValueError):
            self.verify()

    def test_synthetic_is_not_guard_acceptance(self):
        self.reject_receipt(["guard"], "SYNTHETIC_ACCEPTED")

    def test_protocol_receipts_are_truthful_and_never_source_proof(self):
        binding = copy.deepcopy(self.binding)
        binding["kind"] = "HARNESS_PROTOCOL_ONLY"
        receipt = copy.deepcopy(self.receipt)
        receipt["binding"] = binding
        receipt["guard"] = "HARNESS_PROTOCOL_EXERCISED"
        receipt["worker"]["inJob"] = True
        receipt["child"]["inJob"] = True
        envelope = copy.deepcopy(self.envelope)
        envelope.update(binding=binding, workerReceipt=receipt, worker=receipt["worker"], child=receipt["child"])
        validate_completed(envelope, receipt, binding, synthetic=True)
        with self.assertRaises(ValueError):
            validate_completed(envelope, receipt, binding)
        with self.assertRaises(ValueError):
            validate_completed(envelope, receipt, self.binding)


if __name__ == "__main__":
    unittest.main()
