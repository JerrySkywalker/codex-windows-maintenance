"""Durable target control. Stable qualification freezes target and source identity."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from candidate_mapping import read_json, require, sha

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "goals/WBP-ROLLING-0159-FAST-FORWARD-001.manifest.json"


def exact(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value), "Exact Git object required")


def target(value):
    require(set(value) == {"version", "tag", "commit"}, "Invalid target fields")
    require(re.fullmatch(r"0\.\d+\.\d+", value["version"]) and
            value["tag"] == "rust-v" + value["version"], "Stable upstream target required")
    exact(value["commit"])


def transition(state, action, evidence):
    result = deepcopy(state)
    require(state["schemaVersion"] == 1 and state["goalId"] == read_json(CONTROL)["goalId"],
            "Unknown rolling state")
    history = state.get("history")
    require(isinstance(history, list), "Rolling history missing")
    if state.get("stable") is None:
        require(not any(isinstance(event, dict) and event.get("action") == "begin-stable" for event in history),
                "Stable qualification was already started")
    if action == "retarget":
        require(state.get("stable") is None, "Stable target is frozen")
        target(evidence)
        require(evidence == read_json(CONTROL)["targetUpstream"], "Retarget requires reviewed control admission")
        result["targetUpstream"] = evidence
        result["edge"] = None
    elif action == "begin-stable":
        require(state.get("stable") is None, "Stable qualification already started")
        require(state["targetUpstream"] == read_json(CONTROL)["targetUpstream"],
                "Stable target does not match reviewed control")
        require(evidence.get("status") == "FAST_EDGE_PASS" and
                evidence.get("goalId") == state["goalId"] and
                evidence.get("upstreamCommit") == state["targetUpstream"]["commit"],
                "Exact FAST Edge PASS required")
        for key in ("sourceCommit", "sourceTree", "maintenanceCommit", "maintenanceTree"):
            exact(evidence[key])
        require(evidence.get("checks") == {
            "deltaAudit": "PASS", "releaseSourceSanity": "PASS", "format": "PASS",
            "affectedSource": "PASS", "nativeNextest68": "PASS", "solCatalog": "PASS",
            "independentReview": "PASS"}, "Incomplete FAST evidence")
        result["edge"] = evidence
        result["stable"] = {"status": "STABLE_QUALIFICATION_STARTED",
                            "targetUpstream": deepcopy(state["targetUpstream"]),
                            "sourceCommit": evidence["sourceCommit"], "sourceTree": evidence["sourceTree"],
                            "maintenanceCommit": evidence["maintenanceCommit"],
                            "maintenanceTree": evidence["maintenanceTree"]}
    else:
        raise ValueError("Unknown transition")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("init", "retarget", "begin-stable", "status"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    require(args.state.is_absolute() and ROOT not in args.state.resolve().parents,
            "Caller-owned external state required")
    if args.action == "status":
        print(json.dumps(read_json(args.state), indent=2))
        return
    # Exclusive transition lock: abandoned locks require explicit investigation.
    lock = args.state.with_suffix(".transition.lock")
    lock_file = lock.open("x")
    try:
        if args.action == "init":
            require(not args.state.exists(), "Rolling state already exists")
            control = read_json(CONTROL)
            value = {"schemaVersion": 1, "goalId": control["goalId"],
                     "targetUpstream": control["targetUpstream"], "edge": None, "stable": None,
                     "history": []}
        else:
            require(args.evidence is not None, "Evidence required")
            value = transition(read_json(args.state), args.action, read_json(args.evidence))
        event = {"action": args.action, "utc": datetime.now(timezone.utc).isoformat(),
                 "controlSha256": sha(CONTROL)}
        if args.evidence:
            event["evidenceSha256"] = sha(args.evidence)
            if args.action == "begin-stable":
                value["stable"]["edgeEvidenceSha256"] = event["evidenceSha256"]
                value["stable"]["startedUtc"] = event["utc"]
        value["history"].append(event)
        temporary = args.state.with_suffix(".new")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        temporary.replace(args.state)
    finally:
        lock_file.close()
        lock.unlink()


if __name__ == "__main__":
    main()
