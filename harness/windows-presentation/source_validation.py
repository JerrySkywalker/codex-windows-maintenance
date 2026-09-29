"""Compile with just/nextest, execute real native fixture, then execute nextest."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from candidate_mapping import contained, git, read_json, require, sha
from source_fixture_contract import TEST_NAME, validate_completed
from source_fixture_host import atomic_json, isolated_env, run_host


def invoke(command, cwd, env, log, *, machine_json=False):
    with log.open("xb") as output:
        if machine_json:
            with log.with_suffix(".stderr.log").open("xb") as errors:
                result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                                        stdout=output, stderr=errors,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                                    stdout=output, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0, f"Required source command failed; see {log}")


FOCUSED_SELECTION = ["-p", "codex-utils-pty", "-p", "codex-app-server-daemon", "--lib"]


def validate_selection(test_args, full_suite=False):
    require(test_args == ([] if full_suite else FOCUSED_SELECTION),
            "Focused validation requires both complete libraries; full suite requires default selection")


def validate_accounting(text, full_suite=False):
    require(re.search(r"PASS.*" + re.escape(TEST_NAME), text), "Positive nextest parent assertion did not pass")
    summaries = re.findall(r"(\d+) tests run: (\d+) passed(?:[^\n]*?), (\d+) skipped", text)
    require(bool(summaries), "Nextest result accounting is missing")
    total, passed, skipped = map(int, summaries[-1])
    if full_suite:
        require(total > 68 and total == passed, "Complete default suite did not pass")
    else:
        require((total, passed, skipped) == (68, 68, 0), "Focused Rust accounting mismatch/skip")
    return {"testsRun": total, "passed": passed, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser()
    for name in ("source", "commit", "tree", "just", "cargo", "toolchain", "cargo-home",
                 "rustup-home", "target-dir", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--dependency-path", action="append", default=[])
    parser.add_argument("--full-suite", action="store_true")
    parser.add_argument("--durable-job", type=Path)
    parser.add_argument("test_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    source, output = Path(args.source).resolve(), Path(args.output).resolve()
    maintenance = Path(__file__).resolve().parents[2]
    for name in ("source", "just", "cargo", "cargo_home", "rustup_home", "target_dir", "output"):
        require(Path(getattr(args, name)).is_absolute(), f"Absolute caller-selected {name} required")
    for name in ("just", "cargo"):
        require(Path(getattr(args, name)).is_file(), f"Missing {name} executable")
    for name in ("cargo_home", "rustup_home"):
        require(Path(getattr(args, name)).is_dir(), f"Missing {name} cache")
    require(not contained(output, source) and not contained(output, maintenance), "Evidence must be outside repositories")
    require(not output.exists(), "Source validation output already exists")
    for value in (args.commit, args.tree):
        require(re.fullmatch("[0-9a-f]{40}", value), "Exact source object required")
    def verify_source():
        require(git(source, "rev-parse", "HEAD") == args.commit and
                git(source, "show", "-s", "--format=%T", "HEAD") == args.tree and
                not git(source, "status", "--porcelain=v1", "--untracked-files=all"), "Source changed or dirty")
    verify_source()
    if args.full_suite:
        require(args.durable_job is not None, "Full qualification requires a durable external job")
        from validation_job import validate_request
        job = read_json(args.durable_job / "request.json")
        validate_request(job, args.durable_job.resolve())
        require(job["lane"] == "STABLE" and job["source"]["commit"] == args.commit and
                job["source"]["tree"] == args.tree and
                read_json(args.durable_job / "receipt.json").get("status") == "RUNNING",
                "Running bound Stable job required")
    train = read_json(maintenance / "goals/WBP-ROLLING-0159-FAST-FORWARD-001.manifest.json")
    git(source, "merge-base", "--is-ancestor", train["targetUpstream"]["commit"], args.commit)
    output.mkdir(parents=True)
    test_args = args.test_args[1:] if args.test_args[:1] == ["--"] else args.test_args
    validate_selection(test_args, args.full_suite)
    require(not any(arg in test_args for arg in ("--no-run", "--no-tests", "--ignore-default-filter")),
            "Source wrapper cannot replace execution or suppress discovery")
    require("--all-features" not in test_args, "All-features requires a separately justified workflow")
    env = isolated_env(output / "home", {})
    dependency_dirs = [Path(sys.executable).parent, Path(args.just).resolve().parent,
                       Path(args.cargo).resolve().parent] + [Path(path).resolve() for path in args.dependency_path]
    require(all(path.is_dir() for path in dependency_dirs), "Dependency path missing")
    env.update(PATH=os.pathsep.join(map(str, dependency_dirs)), CARGO_HOME=args.cargo_home,
               RUSTUP_HOME=args.rustup_home, RUSTUP_TOOLCHAIN=args.toolchain,
               CARGO_TARGET_DIR=str(Path(args.target_dir).resolve()), CARGO_HTTP_TIMEOUT="60",
               CARGO_NET_RETRY="1", CARGO_NET_GIT_FETCH_WITH_CLI="true", NEXTEST_PROFILE="local")
    nextest = shutil.which("cargo-nextest.exe", path=env["PATH"])
    require(nextest is not None, "Explicit pinned nextest dependency required")
    invoke([args.cargo, "nextest", "--version"], source / "codex-rs", env, output / "nextest-version.log")
    require(re.search(r"cargo-nextest 0\.9\.103\b", (output / "nextest-version.log").read_text()),
            "Source validation requires upstream-pinned nextest 0.9.103")
    invoke([args.just, "test", "--locked", *test_args, "--no-run"], source, env, output / "compile.log")
    invoke([args.cargo, "nextest", "list", "--locked", *test_args, "--message-format", "json"],
           source / "codex-rs", env, output / "nextest-list.json", machine_json=True)
    metadata = read_json(output / "nextest-list.json")
    suites = metadata["rust-suites"]
    matches = [suite for suite in suites.values() if suite["package-name"] == "codex-app-server-daemon"
               and TEST_NAME in suite["testcases"]]
    require(len(matches) == 1, "Ambiguous or missing exact daemon test binary")
    suite = matches[0]
    case = suite["testcases"][TEST_NAME]
    require(case["ignored"] is False, "Positive Rust case must execute")
    binary = Path(suite["binary-path"]).resolve()
    require(binary.is_file(), "Nextest test binary missing")
    binding = {"schemaVersion": 1, "kind": "SOURCE_GUARD_NATIVE_FIXTURE", "runId": str(uuid.uuid4()),
               "sourceCommit": args.commit, "sourceTree": args.tree, "testName": TEST_NAME,
               "binarySha256": sha(binary)}
    atomic_json(output / "source-build.json", {"binding": binding, "binaryPath": str(binary),
                "testArgs": test_args, "nextestMetadataSha256": sha(output / "nextest-list.json"),
                "toolchain": args.toolchain, "nextestPath": nextest, "nextestSha256": sha(nextest),
                "testExecution": "just test / pinned nextest"})
    verify_source()
    native = output / "native"
    run_host(binary, binding, native)
    env.update(CODEX_TEST_NATIVE_DIR=str(native), CODEX_TEST_NATIVE_RUN_ID=binding["runId"],
               CODEX_TEST_NATIVE_SOURCE_COMMIT=args.commit, CODEX_TEST_NATIVE_SOURCE_TREE=args.tree)
    invoke([args.just, "test", "--locked", *test_args, "--status-level", "all", "--final-status-level", "all"],
           source, env, output / "nextest-run.log")
    text = (output / "nextest-run.log").read_text(encoding="utf-8", errors="replace")
    accounting = validate_accounting(text, args.full_suite)
    require(sha(binary) == binding["binarySha256"], "Nextest rebuilt/changed the native-proven binary")
    verify_source()
    receipt, envelope = (read_json(native / name) for name in ("worker-receipt.json", "controller-receipt.json"))
    validate_completed(envelope, receipt, binding)
    require(read_json(native / "host-cleanup.json")["errors"] == [], "Unknown native cleanup")
    status = "SOURCE_NATIVE_AND_DEFAULT_WORKSPACE_NEXTEST_PASS" if args.full_suite else "SOURCE_NATIVE_AND_FOCUSED_68_NEXTEST_PASS"
    atomic_json(output / "validation.json", {"status": status,
                "binding": binding, "nextestLogSha256": sha(output / "nextest-run.log"),
                "accounting": accounting, "fullSuite": args.full_suite, "packageQualification": False})


if __name__ == "__main__":
    main()
