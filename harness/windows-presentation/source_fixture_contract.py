"""Fail-closed source-validation receipts. Synthetic results are never guard proof."""
import re
import uuid

from candidate_mapping import require

TEST_NAME = "backend::windows::tests::completely_detached_child_is_accepted"


def validate_binding(binding, *, synthetic=False):
    require(set(binding) == {"schemaVersion", "kind", "runId", "sourceCommit",
                             "sourceTree", "testName", "binarySha256"}, "Unknown binding fields")
    require(type(binding["schemaVersion"]) is int and binding["schemaVersion"] == 1,
            "Unknown fixture schema")
    kinds = {"HARNESS_SYNTHETIC_FIXTURE", "HARNESS_PROTOCOL_ONLY"} if synthetic else {"SOURCE_GUARD_NATIVE_FIXTURE"}
    require(binding["kind"] in kinds, "Synthetic fixture cannot prove source guard")
    require(str(uuid.UUID(binding["runId"])) == binding["runId"], "Invalid run ID")
    require(binding["testName"] == TEST_NAME, "Wrong selected source test")
    for key, length in (("sourceCommit", 40), ("sourceTree", 40), ("binarySha256", 64)):
        require(isinstance(binding[key], str) and
                re.fullmatch(f"[0-9a-f]{{{length}}}", binding[key]), f"Invalid {key}")


def validate_identity(identity, *, protocol_only=False):
    require(set(identity) == {"pid", "created", "queryReturn", "lastError", "inJob"},
            "Incomplete process identity/API evidence")
    require(type(identity["pid"]) is int and identity["pid"] > 0 and
            type(identity["created"]) is int and identity["created"] > 0,
            "Unknown process identity")
    require(type(identity["queryReturn"]) is int and identity["queryReturn"] == 1 and
            type(identity["lastError"]) is int and identity["lastError"] == 0 and
            type(identity["inJob"]) is bool, "Failed/unknown Job query")
    require(protocol_only or identity["inJob"] is False, "Residual Job membership")


def validate_worker(receipt, binding, *, synthetic=False):
    validate_binding(binding, synthetic=synthetic)
    require(set(receipt) == {"binding", "binaryBlake3", "worker", "child", "guard",
                             "debugKillOnExitReturn", "testResult", "cleanup"}, "Unknown worker receipt fields")
    require(receipt["binding"] == binding, "Stale or mismatched worker binding")
    require(isinstance(receipt["binaryBlake3"], str) and
            re.fullmatch("[0-9a-f]{64}", receipt["binaryBlake3"]), "Missing worker fingerprint")
    protocol_only = synthetic and binding["kind"] == "HARNESS_PROTOCOL_ONLY"
    for key in ("worker", "child"):
        validate_identity(receipt[key], protocol_only=protocol_only)
    require(receipt["worker"]["pid"] != receipt["child"]["pid"], "Worker is its own child")
    require(receipt["child"]["created"] >= receipt["worker"]["created"], "Reused child identity")
    expected = "HARNESS_PROTOCOL_EXERCISED" if protocol_only else ("SYNTHETIC_ACCEPTED" if synthetic else "ACCEPTED")
    require(receipt["guard"] == expected, "Actual source guard did not accept")
    require(type(receipt["debugKillOnExitReturn"]) is int and
            receipt["debugKillOnExitReturn"] == 1, "Crash cleanup backstop unproven")
    require(receipt["testResult"] == "PASSED", "Selected fixture failed")
    require(set(receipt["cleanup"]) == {"killed", "reaped", "originalChildHandleClosed",
                                       "debugImageHandlesClosed"} and
            all(value is True for value in receipt["cleanup"].values()), "Incomplete original-child cleanup")


def validate_completed(envelope, receipt, binding, *, synthetic=False):
    validate_worker(receipt, binding, synthetic=synthetic)
    require(set(envelope) == {"binding", "workerReceipt", "worker", "child", "workerExit",
                              "childWait", "registeredBeforeGuard", "workerHandleClosed",
                              "childHandleClosed", "completed"}, "Unknown controller receipt fields")
    require(envelope["binding"] == binding, "Stale or mismatched controller binding")
    require(envelope["workerReceipt"] == receipt, "Worker/controller receipts disagree")
    require(envelope["worker"] == receipt["worker"] and
            envelope["child"] == receipt["child"], "Controller process identity/API mismatch")
    require(envelope["completed"] is True and envelope["registeredBeforeGuard"] is True,
            "Controller did not complete the registered fixture")
    for key in ("workerExit", "childWait"):
        require(type(envelope[key]) is int and envelope[key] == 0, f"Failed {key}")
    for key in ("workerHandleClosed", "childHandleClosed"):
        require(envelope[key] is True, f"Missing {key}")
