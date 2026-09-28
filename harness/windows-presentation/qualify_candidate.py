"""Candidate qualification only. Never installs, routes, authenticates, or updates."""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from candidate_mapping import (FILES, ROOT, check_runtime_sol, git, load, package_files,
                               require, sha, sol_contract, write_json)
from daemon_rpc import RPC
from windows_native import Ledger, Process, lifetime_acceptance, snapshot, uds_connect

HERE = Path(__file__).resolve().parent


def isolated_environment(root, package=None):
    profile = root / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    # Explicit dependencies; no inherited API keys, cloud credentials or user settings.
    dependencies = [Path(sys.executable).parent, Path(shutil.which("git")).parent,
                    Path(os.environ["SystemRoot"]) / "System32",
                    Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0"]
    if package:
        dependencies.insert(0, package / "codex-path")
    environment.update(PATH=os.pathsep.join(map(str, dependencies)),
                       USERPROFILE=str(profile), HOME=str(profile),
                       APPDATA=str(profile / "AppData/Roaming"), LOCALAPPDATA=str(profile / "AppData/Local"),
                       TEMP=str(root), TMP=str(root), PYTHONDONTWRITEBYTECODE="1", GIT_CONFIG_NOSYSTEM="1",
                       GIT_CONFIG_GLOBAL=os.devnull, OPENAI_API_KEY="local-smoke-only",
                       CODEX_INTERNAL_APP_SERVER_REMOTE_CONTROL_DISABLED="1")
    return environment


def start(args, env, log, visible=False, separate_error=False):
    stream = Path(log).open("wb")
    error_stream = Path(str(log) + ".stderr.log").open("wb") if separate_error else None
    try:
        process = subprocess.Popen(list(map(str, args)), env=env, stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=error_stream if separate_error else subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE if visible else subprocess.CREATE_NO_WINDOW)
    finally:
        stream.close()
        if error_stream:
            error_stream.close()
    return process


def wait(process, timeout=30):
    try:
        code = process.wait(timeout)
        require(code == 0, f"Helper failed: {code}")
    except BaseException:
        if process.poll() is None:
            process.kill()  # The Popen owns an exact process handle.
            process.wait(5)
        raise


def ready(path, process, timeout=15):
    deadline = time.monotonic() + timeout
    while not path.exists():
        require(process.poll() is None and time.monotonic() < deadline, f"Helper readiness failed: {path}")
        time.sleep(.02)


def observer(pwsh, root, env, seconds, stop_path=None):
    event_file, ready_file = root / "windows.tsv", root / "observer.ready"
    args = [pwsh, "-NoProfile", "-File", HERE / "observe-windows.ps1",
            "-OutputPath", event_file, "-DurationSeconds", seconds, "-ReadyPath", ready_file]
    if stop_path:
        args.extend(["-StopPath", stop_path])
    process = start(args, env, root / "observer.log")
    try:
        ready(ready_file, process)
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait(5)
        raise
    return process, event_file


def relevant_events(path, started, owned=None):
    with path.open(encoding="utf-8-sig") as stream:
        events = list(csv.DictReader(stream, delimiter="\t"))
    names = {"codex", "codex-code-mode-host", "codex-command-runner", "codex-windows-sandbox-setup",
             "git", "pwsh", "powershell", "python", "rg", "cmd", "conhost", "OpenConsole"}
    relevant = []
    for event in events:
        if event["win_event"] not in ("0003", "8002") and not any(
                cls in event["class"] for cls in ("ConsoleWindowClass", "PseudoConsoleWindow")):
            continue
        identity = event["process_started_utc"]
        # Unknown console attribution is an ambiguity, never a silent exclusion.
        console = any(cls in event["class"] for cls in ("ConsoleWindowClass", "PseudoConsoleWindow"))
        if not identity:
            require(not console, "Visible console identity unavailable")
            continue
        created = datetime.fromisoformat(identity.replace("Z", "+00:00"))
        if created >= started and (event["process"] in names or console or
                                  (owned and int(event["pid"]) in owned)):
            relevant.append(event)
    return relevant


def positive_control(pwsh, root, env):
    root.mkdir()
    watching, events = observer(pwsh, root, env, 8)
    started = datetime.now(timezone.utc)
    command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
    control = subprocess.Popen([str(command), "/d", "/c", "title WBP-positive-control & timeout /t 2 /nobreak"],
                               env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
    try:
        wait(control, 10)
        wait(watching, 15)
        observed = relevant_events(events, started)
        require(any(event["win_event"] in ("8002", "0003") for event in observed),
                "Visible positive control show/foreground event was not observed")
        write_json(root / "control.json", {"status": "PASS", "pid": control.pid, "events": observed})
    finally:
        for process in (control, watching):
            if process.poll() is None:
                process.kill()
                process.wait(5)


def lifetime_fixture(root, env):
    root.mkdir()
    compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    executable, source = root / "LifetimeFixture.exe", HERE / "LifetimeFixture.cs"
    process = start([compiler, "/nologo", "/target:exe", "/platform:x64", f"/out:{executable}", source],
                    env, root / "build.log")
    wait(process)
    write_json(root / "build.json", {"compilerSha256": sha(compiler), "sourceSha256": sha(source),
                                    "executableSha256": sha(executable), "exitCode": process.returncode})
    process = start([executable, "0", root], env, root / "fixture.log")
    wait(process, 55)
    require((root / "PASS.txt").is_file(), "Native fixture incomplete")
    cases = {}
    for name, membership, survives in (("no-residual", False, True), ("harmless-outer", True, True), ("kill-outer", True, False)):
        result = dict(line.split("=", 1) for line in (root / name / "result.txt").read_text().splitlines())
        require(result["inInner"] == "False" and result["inAnyJob"] == str(membership) and
                result["survived"] == str(survives) and result["identityMatch"] == "true", "Native effect mismatch")
        accepted = False
        try:
            lifetime_acceptance(membership)
            accepted = True
        except ValueError:
            pass
        require(accepted == (not membership), "WBP lifetime policy regression")
        cases[name] = {"native": result, "policyAccepted": accepted}
    require(not any(Path(name).name.lower() == "lifetimefixture.exe" for _, _, name in snapshot()), "Fixture orphan remains")
    write_json(root / "lifetime-contract.json", {"contract": "REJECT_UNPROVEN_RESIDUAL_JOB_MEMBERSHIP", "cases": cases,
                                               "scope": "Native surrogate plus qualification policy; actual G03 source rejection requires G04 tests"})


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]


def check_sol_tool_requests(requests, expected_sol):
    require(expected_sol["tool_mode"] == "code_mode_only", "Admitted Sol tool contract changed")
    require(len(requests) == 4 and all(r["body"].get("model") == "gpt-6-sol" for r in requests),
            "Deterministic Sol request contract failed")
    visible = requests[0]["body"]["tools"]
    require(any(tool.get("name") == "exec" and tool.get("type") == "custom" for tool in visible) and
            not any(tool.get("name") == "exec_command" for tool in visible), "Sol CodeModeOnly tool exposure mismatch")
    for sequence in (1, 2, 3):
        require(any(item.get("type") == "custom_tool_call_output" and item.get("call_id") == f"call-{sequence}"
                    for item in requests[sequence]["body"]["input"]), "Sol did not execute the custom Code Mode call")


def managed_run(mapping_path, pwsh):
    mapping, paths = load(mapping_path)
    mapping_hash = sha(mapping_path)
    root, source, package = (paths[key] for key in ("outputDir", "sourcePath", "packageDir"))
    initial_package_files = package_files(package)
    build_receipt_hash = sha(package / "candidate-build.json")
    expected_sol = sol_contract(source, mapping["upstreamCommit"])
    require(expected_sol["tool_mode"] == "code_mode_only", "Admitted Sol tool contract changed")
    # Give the legacy smoke its own sanitized environment while keeping mapped output absent.
    # The no-daemon script creates output and home after its own candidate validation.
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), str(Path(shutil.which("git")).parent),
                                  str(Path(os.environ["SystemRoot"]) / "System32"),
                                  str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0")])
    env.update(USERPROFILE=str(root / "no-daemon/home"), HOME=str(root / "no-daemon/home"),
               APPDATA=str(root / "no-daemon/home/AppData/Roaming"), LOCALAPPDATA=str(root / "no-daemon/home/AppData/Local"),
               TEMP=str(root.parent), TMP=str(root.parent), PYTHONDONTWRITEBYTECODE="1",
               CODEX_HOME=str(root / "no-daemon/home"),
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    # Log outside root would violate evidence selection; stdout is captured before output creation.
    smoke = subprocess.Popen([pwsh, "-NoProfile", "-File", str(ROOT / "scripts/qualify.ps1"),
                              "-CandidateMapping", str(mapping_path), "-SourcePath", str(source),
                              "-PackageDir", str(package), "-Python", sys.executable,
                              "-OutputDir", str(root / "no-daemon")], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    smoke_handle = Process(smoke.pid)
    smoke_ledger = Ledger(smoke_handle, root / "no-daemon/processes.json")
    smoke_ledger.thread.start()
    try:
        output, _ = smoke.communicate(timeout=150)
        require(smoke.returncode == 0, "No-daemon candidate smoke failed")
        smoke_ledger.finish()
    except BaseException:
        smoke_ledger.finish(cleanup=True)
        raise
    finally:
        if root.exists():
            (root / "no-daemon-driver.log").write_bytes(output if 'output' in locals() else b"Timed out")
    env = isolated_environment(root, package)
    lifetime_fixture(root / "lifetime", env)
    positive_control(pwsh, root / "positive-control", env)
    workspace, home = root / "workspace", root / "home"
    workspace.mkdir()
    home.mkdir()
    wait(start([shutil.which("git"), "-C", workspace, "init"], env, root / "git-init.log"))
    managed_package = home / "packages/app-server-daemon/current"
    for name in FILES:
        destination = managed_package / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package / name, destination)
    require(package_files(managed_package) == package_files(package), "Managed copy identity mismatch")
    executable = managed_package / "bin/codex.exe"
    env["CODEX_HOME"] = str(home)
    env["PATH"] = str(managed_package / "codex-path") + os.pathsep + env["PATH"]
    hook_command = '& "' + sys.executable + '" "' + str(HERE / "hook_smoke.py") + '" "' + str(root / "hooks.jsonl") + '"'
    write_json(home / "hooks.json", {"hooks": {"PreToolUse": [{"matcher": "^Bash$", "hooks": [{"type": "command", "command": hook_command}]}]}})
    server, watcher, rpc, ledger = None, None, None, None
    stopped = False
    qualified = False
    daemon = None
    started = datetime.now(timezone.utc)
    transcript = None
    try:
        server = start([sys.executable, HERE / "mock_responses.py", "--port-file", root / "port.txt",
                        "--request-log", root / "requests.jsonl", "--workspace", workspace,
                        "--shell-marker", root / "shell.txt", "--tool-mode", "code_mode_only",
                        "--powershell", pwsh, "--python", sys.executable, "--rg", managed_package / "codex-path/rg.exe"], env, root / "mock.log")
        ready(root / "port.txt", server)
        port = int((root / "port.txt").read_text())
        # JSON strings are valid TOML basic strings for the paths used here.
        config = '\n'.join([
            'cli_auth_credentials_store = "file"', 'mcp_oauth_credentials_store = "file"',
            'model = "gpt-6-sol"', 'model_provider = "mock"', 'approval_policy = "never"',
            'sandbox_mode = "danger-full-access"', '[features]', 'hooks = true', 'code_mode = true', 'unified_exec = true',
            '[model_providers.mock]', 'name = "mock"', f'base_url = "http://127.0.0.1:{port}/v1"',
            'env_key = "OPENAI_API_KEY"', 'wire_api = "responses"',
            '[mcp_servers.package_smoke]', f'command = {json.dumps(sys.executable)}',
            f'args = {json.dumps([str(HERE / "mcp_smoke_server.py"), str(root / "mcp.jsonl")])}',
            'startup_timeout_sec = 10', 'tool_timeout_sec = 10',
            f'[projects.{json.dumps(str(workspace))}]', 'trust_level = "trusted"', ''])
        (home / "config.toml").write_text(config, encoding="utf-8")
        observer_stop = root / "observer.stop"
        watcher, event_file = observer(pwsh, root, env, 900, observer_stop)
        started = datetime.now(timezone.utc)
        version = start([executable, "--version"], env, root / "version.log", separate_error=True)
        wait(version)
        require((root / "version.log").read_text().strip() == f'codex-cli {mapping["upstreamVersion"]}', "Executable version mismatch")
        launch = start([executable, "app-server", "daemon", "start"], env, root / "daemon-start.json", separate_error=True)
        wait(launch, 30)
        info = json.loads((root / "daemon-start.json").read_text())
        require(info["status"] == "started" and Path(info["managedCodexPath"]).resolve() == executable.resolve(), "Unexpected managed start identity")
        require(info.get("appServerVersion") == mapping["upstreamVersion"], "Daemon readiness version mismatch")
        daemon = Process(info["pid"])
        require(Path(daemon.image).resolve() == executable.resolve() and sha(daemon.image) == sha(package / "bin/codex.exe"), "Daemon image/hash mismatch")
        require(daemon.created / 10000000 - 11644473600 >= started.timestamp(), "Daemon predates isolated launch")
        ledger = Ledger(daemon, root / "processes.json")
        ledger.thread.start()
        lifetime_acceptance(daemon.membership())
        socket_path = Path(info["socketPath"])
        require(socket_path.resolve().is_relative_to(home.resolve()), "Managed control socket escaped isolated home")
        transcript = (root / "rpc.jsonl").open("w", encoding="utf-8")
        rpc = RPC(uds_connect(socket_path), transcript)
        initialized = rpc.call("initialize", {"clientInfo": {"name": "wbp_qualification", "version": "1"},
                                              "capabilities": {"experimentalApi": True}})
        require(Path(initialized["codexHome"]).resolve() == home.resolve() and
                f'/{mapping["upstreamVersion"]}' in initialized["userAgent"], "RPC daemon identity mismatch")
        rpc.send({"method": "initialized"})
        hook_catalog = rpc.call("hooks/list", {"cwds": [str(workspace)]})
        hook_entries = [hook for entry in hook_catalog["data"] for hook in entry["hooks"]]
        require(len(hook_entries) == 1 and not any(entry["errors"] for entry in hook_catalog["data"]), "Unexpected isolated hook catalog")
        fixture_hook = hook_entries[0]
        require(Path(fixture_hook["sourcePath"]).resolve() == (home / "hooks.json").resolve() and
                fixture_hook.get("command") == hook_command and fixture_hook["currentHash"].startswith("sha256:"),
                "Hook fingerprint does not identify the known fixture")
        # Persist trust for this exact known fixture in the disposable home only.
        with (home / "config.toml").open("a", encoding="utf-8") as stream:
            stream.write(f'\n[hooks.state.{json.dumps(fixture_hook["key"])}]\nenabled = true\ntrusted_hash = {json.dumps(fixture_hook["currentHash"])}\n')
        trusted_hooks = rpc.call("hooks/list", {"cwds": [str(workspace)]})
        require(any(hook["key"] == fixture_hook["key"] and hook["trustStatus"] == "trusted"
                    for entry in trusted_hooks["data"] for hook in entry["hooks"]), "Fixture hook trust not active")
        models, cursor = [], None
        for _ in range(20):
            page = rpc.call("model/list", {"includeHidden": True, "limit": 100, "cursor": cursor})
            models.extend(page["data"])
            cursor = page.get("nextCursor")
            if cursor is None:
                break
        require(cursor is None, "Unbounded model catalog")
        runtime_sol = check_runtime_sol(models, expected_sol)
        write_json(root / "gpt-6-sol.json", {"status": "PASS", "runtime": runtime_sol,
                                           "sourceCatalogSha256": sha(source / "codex-rs/models-manager/models.json"),
                                           "upstreamSolContractUnchanged": True, "realAccountInference": "NOT_RUN_OWNER_G07"})
        thread = rpc.call("thread/start", {"model": "gpt-6-sol", "modelProvider": "mock", "cwd": str(workspace),
                                            "approvalPolicy": "never", "sandbox": "danger-full-access", "ephemeral": True})
        require(thread["model"] == "gpt-6-sol", "Candidate did not select Sol")
        # Helpers seen before first local inference are internal startup work, not the mock's Git shell tool.
        internal_git = any(Path(p.image).name.lower() == "git.exe" for p in ledger.records.copy().values())
        require(internal_git, "Internal Git path not reached; cannot claim qualification")
        turn = rpc.call("turn/start", {"threadId": thread["thread"]["id"],
                                       "input": [{"type": "text", "text": "Run bounded smoke commands from the local test endpoint."}]})
        rpc.completed_turn(thread["thread"]["id"], turn["turn"]["id"])
        require((root / "shell.txt").read_text(encoding="utf-8-sig").strip() == "shell-ok", "Bounded shell failed")
        wait(server, 10)
        requests = lines(root / "requests.jsonl")
        check_sol_tool_requests(requests, expected_sol)
        code_hosts = [p for p in ledger.records.copy().values() if Path(p.image).name.lower() == "codex-code-mode-host.exe"]
        require(code_hosts and all(Path(p.image).resolve() == (managed_package / "bin/codex-code-mode-host.exe").resolve()
                                  and sha(p.image) == initial_package_files["bin/codex-code-mode-host.exe"] for p in code_hosts),
                "Managed Code Mode host image/hash not proven")
        results = json.dumps(requests)
        require("shell-ok" in results and "codex-path" in results and "rg-probe-ok" in results, "Shell/bundled helper output missing")
        rg_processes = [p for p in ledger.records.copy().values() if Path(p.image).name.lower() == "rg.exe"]
        require(rg_processes and all(Path(p.image).resolve() == (managed_package / "codex-path/rg.exe").resolve() and
                                    sha(p.image) == initial_package_files["codex-path/rg.exe"] for p in rg_processes),
                "Bundled rg image/hash not observed")
        require(len(lines(root / "hooks.jsonl")) >= 3, "Representative hook not reached")
        mcp = lines(root / "mcp.jsonl")
        require(any(m.get("event") == "start" for m in mcp) and
                all(any(m.get("method") == method for m in mcp) for method in ("initialize", "tools/list")), "MCP stdio path incomplete")
        rpc.close()
        rpc = None
        transcript.close()
        stop = start([executable, "app-server", "daemon", "stop"], env, root / "daemon-stop.json", separate_error=True)
        wait(stop, 30)
        require(json.loads((root / "daemon-stop.json").read_text())["status"] == "stopped", "Daemon shutdown failed")
        time.sleep(.5)
        owned = set(ledger.records)
        ledger.finish()
        ledger = None
        daemon = None  # Ledger closed its root handle.
        stopped = True
        # Untracked package descendants are an ambiguity, even if polling missed ancestry.
        for pid, _, _ in snapshot():
            try:
                process = Process(pid)
            except OSError:
                continue
            try:
                require(not Path(process.image).resolve().is_relative_to(managed_package.resolve()), "Untracked managed package orphan")
            finally:
                process.close()
        require(watcher.poll() is None, "Managed observer ended before workload/shutdown completed")
        observer_stop.write_text("OWNED_WORKLOAD_SHUT_DOWN", encoding="ascii")
        wait(watcher, 15)
        require(json.loads(Path(str(observer_stop) + ".done.json").read_text(encoding="utf-8-sig"))["stopMarkerObserved"],
                "Managed observer did not acknowledge full observation interval")
        visible = relevant_events(event_file, started, owned)
        require(not visible, f"Relevant visible/foreground events: {len(visible)}")
        require(sha(mapping_path) == mapping_hash and sha(package / "candidate-build.json") == build_receipt_hash and
                package_files(package) == initial_package_files and package_files(managed_package) == initial_package_files,
                "Candidate identity changed during qualification")
        require(git(source, "rev-parse", "HEAD") == mapping["downstreamCommit"] and
                git(source, "show", "-s", "--format=%T", "HEAD") == mapping["downstreamTree"] and
                not git(source, "status", "--porcelain=v1", "--untracked-files=all"), "Source changed during qualification")
        write_json(root / "qualification.json", {"status": "UNRELEASED_CANDIDATE_QUALIFICATION_PASS",
            "mappingSha256": sha(mapping_path), "sourceCommit": mapping["downstreamCommit"],
            "sourceTree": mapping["downstreamTree"], "packageFiles": package_files(package),
            "noDaemonSmoke": "PASS", "managedDaemon": "PASS", "lifetimeContract": "PASS",
            "positiveControl": "PASS", "visibleEvents": 0, "internalGit": "PASS", "hooks": "PASS",
            "mcpStdio": "PASS", "gpt6SolDeterministic": "PASS", "ownedOrphans": 0, "released": False})
        qualified = True
    finally:
        cleanup_errors = []
        try:
            if rpc:
                rpc.close()
        except BaseException as error:
            cleanup_errors.append(str(error))
        try:
            if ledger:
                ledger.finish(cleanup=True)
                daemon = None
            elif daemon:
                daemon.terminate()
                daemon.close()
            if not qualified:
                # Startup can fail after detaching a child but before publishing JSON.
                # Only a freshly created process from this private copied package is owned.
                for pid, _, _ in snapshot():
                    try:
                        owned_process = Process(pid)
                    except OSError:
                        continue
                    try:
                        if Path(owned_process.image).resolve().is_relative_to(managed_package.resolve()):
                            require(owned_process.created / 10000000 - 11644473600 >= started.timestamp(), "Ambiguous private-package process lifetime")
                            owned_process.terminate()
                    finally:
                        owned_process.close()
        except BaseException as error:
            cleanup_errors.append(str(error))
        finally:
            if transcript and not transcript.closed:
                transcript.close()
            for process in (server, watcher):
                if process and process.poll() is None:
                    process.kill()
                    process.wait(5)
            if not qualified:
                write_json(root / "failure.json", {"status": "FAIL_CLOSED", "qualificationClaimed": False,
                           "gracefulDaemonShutdown": stopped, "cleanupErrors": cleanup_errors})
        require(not cleanup_errors, f"Qualification cleanup ambiguous: {cleanup_errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--pwsh", required=True)
    args = parser.parse_args()
    managed_run(args.mapping.resolve(), args.pwsh)
