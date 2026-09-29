"""External validation worker. Requests and receipts survive the interactive session."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

from candidate_mapping import contained, git, read_json, require, sha
from rolling_control import exact
from source_fixture_host import atomic_json, isolated_env, identity, current, open_process, close, wait, image

ENV_KEYS = {"PATH", "CARGO_HOME", "RUSTUP_HOME", "RUSTUP_TOOLCHAIN", "CARGO_TARGET_DIR",
            "CARGO_HTTP_TIMEOUT", "CARGO_NET_RETRY", "CARGO_NET_GIT_FETCH_WITH_CLI",
            "NEXTEST_PROFILE", "UV_HTTP_TIMEOUT", "UV_HTTP_RETRIES", "BAZELISK_HOME"}
ROOT = Path(__file__).resolve().parents[2]


def update_receipt(path, value):
    # Native fixture atomic_json is deliberately write-once. Job progress replaces
    # its receipt only after closing and flushing this single writer's temp file.
    temporary = path.with_suffix(".update")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def verify(binding):
    exact(binding["commit"])
    exact(binding["tree"])
    source = Path(binding["path"])
    require(source.is_absolute() and git(source, "rev-parse", "HEAD") == binding["commit"] and
            git(source, "show", "-s", "--format=%T", "HEAD") == binding["tree"] and
            not git(source, "status", "--porcelain=v1", "--untracked-files=all"), "Validation source changed/dirty")


def validate_request(request, output):
    require(request["schemaVersion"] == 1 and request["kind"] == "DURABLE_VALIDATION_JOB", "Unknown job request")
    require(request["lane"] in ("FAST_EDGE", "STABLE"), "Unknown validation lane")
    require(set(request["env"]) <= ENV_KEYS, "Non-validation environment override")
    for binding in (request["source"], request["maintenance"]):
        verify(binding)
        require(not contained(output, Path(binding["path"]).resolve()), "External job output required")
    require(Path(request["cwd"]).is_absolute() and Path(request["cwd"]).is_dir(), "Absolute job cwd required")
    command = request["command"]
    require(isinstance(command, list) and command and all(isinstance(x, str) for x in command) and
            Path(command[0]).is_absolute() and Path(command[0]).is_file(), "Explicit command executable required")
    require(not any(x in command for x in ("--yolo", "--dangerously-bypass-approvals-and-sandbox")), "Unsafe job command")
    if request["lane"] == "STABLE":
        state = read_json(request["stableState"])
        freeze = state.get("stable") or {}
        require(freeze.get("status") == "STABLE_QUALIFICATION_STARTED" and
                (freeze.get("sourceCommit"), freeze.get("sourceTree")) ==
                (request["source"]["commit"], request["source"]["tree"]) and
                (freeze.get("maintenanceCommit"), freeze.get("maintenanceTree")) ==
                (request["maintenance"]["commit"], request["maintenance"]["tree"]),
                "Stable freeze missing/mismatched")
        require(sha(request["stableState"]) == request["stableStateSha256"], "Stable state changed")


def verify_receipt(output, expected_status, *, executing=False):
    """Accept only one launched, bound job; a stale RUNNING file is insufficient."""
    output = Path(output).resolve()
    request_path = output / "request.json"
    request, launch, receipt = (read_json(output / name) for name in
                                ("request.json", "launch.json", "receipt.json"))
    validate_request(request, output)
    require(receipt.get("schemaVersion") == 1 and receipt.get("kind") == "DURABLE_VALIDATION_RECEIPT" and
            receipt.get("status") == expected_status and receipt.get("lane") == request["lane"] and
            receipt.get("source") == request["source"] and receipt.get("maintenance") == request["maintenance"],
            "Durable receipt status or source binding mismatch")
    require(receipt.get("requestSha256") == launch.get("requestSha256") == sha(request_path) and
            receipt.get("workerSha256") == launch.get("workerSha256") == sha(__file__) and
            receipt.get("executableSha256") == sha(request["command"][0]), "Durable command/code hash mismatch")
    worker = receipt.get("workerIdentity")
    child = receipt.get("childIdentity")
    require(isinstance(worker, dict) and isinstance(child, dict) and
            worker == launch.get("workerIdentity") and
            worker.get("pid") == receipt.get("pid") == launch.get("pid") and
            not worker.get("inJob") and worker.get("created", 0) > 0 and
            child.get("pid") == receipt.get("childPid") and child.get("created", 0) > 0 and
            child.get("queryReturn") == 1 and not child.get("inJob"), "Durable process identity mismatch")
    require(Path(launch["workerExecutable"]).is_absolute() and
            launch.get("workerExecutableSha256") == sha(launch["workerExecutable"]),
            "Durable worker executable changed")
    if expected_status == "RUNNING":
        handle = open_process(0x101000, False, worker["pid"])
        require(handle, "Durable worker exited")
        try:
            require(identity(handle) == worker and wait(handle, 0) == 258 and
                    image(handle) == Path(launch["workerExecutable"]).resolve(),
                    "Stale or replaced durable worker")
        finally:
            close(handle)
        if executing:
            require(receipt["childPid"] == os.getpid() and identity(current()) == child and
                    request["command"] == sys.orig_argv, "Unbound qualification command")
    else:
        require(expected_status == "PASS" and receipt.get("exitCode") == 0 and
                receipt.get("logSha256") == sha(output / "command.log") and
                receipt.get("stderrSha256") == sha(output / "command.stderr.log") and
                receipt.get("finishedUtc"), "Incomplete final validation receipt")
    return request, receipt


def run(output):
    request_path = output / "request.json"
    request = read_json(request_path)
    digest = sha(request_path)
    receipt = {"schemaVersion": 1, "kind": "DURABLE_VALIDATION_RECEIPT", "status": "RUNNING",
               "requestSha256": digest, "pid": os.getpid(), "startedUtc": datetime.now(timezone.utc).isoformat(),
               "source": request["source"], "maintenance": request["maintenance"], "lane": request["lane"],
               "workerSha256": sha(__file__), "executableSha256": sha(request["command"][0])}
    atomic_json(output / "receipt.json", receipt)
    try:
        receipt["workerIdentity"] = identity(current())
        validate_request(request, output)
        env = isolated_env(output / "home", {})
        env.update(request["env"])
        with (output / "command.log").open("xb") as log, (output / "command.stderr.log").open("xb") as errors:
            child = subprocess.Popen(request["command"], cwd=request["cwd"], env=env,
                                     stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=errors if request.get("machineJson", False) else subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            receipt["childPid"] = child.pid
            receipt["childIdentity"] = identity(int(child._handle))
            update_receipt(output / "receipt.json", receipt)
            code = child.wait()
        receipt.update(exitCode=code, logSha256=sha(output / "command.log"), stderrSha256=sha(output / "command.stderr.log"))
        for binding in (request["source"], request["maintenance"]):
            verify(binding)
        require(sha(request_path) == digest, "Job request changed")
        receipt["status"] = "PASS" if code == 0 else "FAIL"
    except Exception:
        receipt.update(status="FAIL", error=traceback.format_exc())
    receipt["finishedUtc"] = datetime.now(timezone.utc).isoformat()
    update_receipt(output / "receipt.json", receipt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "run", "status"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    require(args.output.is_absolute() and not contained(output, ROOT), "Absolute external job output required")
    if args.action == "run":
        run(output)
    elif args.action == "status":
        print(json.dumps(read_json(output / "receipt.json"), indent=2))
    else:
        require(args.request is not None and not output.exists(), "Fresh job output and request required")
        request = read_json(args.request)
        validate_request(request, output)
        output.mkdir()
        atomic_json(output / "request.json", request)
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
        # Failed breakaway is a blocker, never an in-session fallback.
        try:
            with (output / "worker.log").open("xb") as log:
                process = subprocess.Popen([sys.executable, "-S", "-B", str(Path(__file__).resolve()), "run", "--output", str(output)],
                                           cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=flags, close_fds=True)
        except OSError:
            atomic_json(output / "receipt.json", {"status": "LAUNCH_FAILED", "error": traceback.format_exc(),
                        "requestSha256": sha(output / "request.json")})
            raise
        atomic_json(output / "launch.json", {"pid": process.pid, "requestSha256": sha(output / "request.json"),
                    "workerIdentity": identity(int(process._handle)), "workerExecutable": sys.executable,
                    "workerExecutableSha256": sha(sys.executable),
                    "workerSha256": sha(__file__), "utc": datetime.now(timezone.utc).isoformat()})
        print(f"DURABLE_JOB_STARTED pid={process.pid} receipt={output / 'receipt.json'}")


if __name__ == "__main__":
    main()
