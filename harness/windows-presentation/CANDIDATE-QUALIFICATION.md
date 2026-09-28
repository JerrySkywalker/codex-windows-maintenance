# Unreleased candidate qualification

The stable `manifest.json` remains unchanged until G06. Candidate build and
qualification use a separate, caller-owned JSON file with exactly these fields:

```json
{
  "schemaVersion": 1,
  "kind": "UNRELEASED_CANDIDATE",
  "goalId": "WBP-UPSTREAM-0158-PORT-TRAIN-001",
  "upstreamVersion": "0.158.0",
  "upstreamCommit": "064c6b8c737f5b41d171fdda80bd9ef10ad06eb3",
  "downstreamCommit": "EXACT_40_CHARACTER_CANDIDATE_COMMIT",
  "downstreamTree": "EXACT_40_CHARACTER_CANDIDATE_TREE",
  "target": "x86_64-pc-windows-msvc",
  "packageVariant": "codex",
  "cargoProfile": "release",
  "sourcePath": "CALLER_SELECTED_ABSOLUTE_SOURCE_PATH",
  "packageDir": "CALLER_SELECTED_ABSOLUTE_NEW_PACKAGE_DIRECTORY",
  "outputDir": "CALLER_SELECTED_ABSOLUTE_NEW_EVIDENCE_DIRECTORY"
}
```

The placeholders are deliberately invalid. Obtain the candidate commit/tree from
the completed G03 source port. The upstream commit must be its ancestor; source
status must be clean. Paths must be absolute, separate and outside both repositories.
Existing build/evidence outputs are rejected. A new build writes an explicitly
unreleased receipt binding mapping SHA256, source commit/tree and all six package
file hashes. Qualification rejects missing or altered provenance and package
metadata. This is local build evidence, not an immutable release tag or public
provenance claim. Build directories should be controlled by the caller.

```powershell
./scripts/build-candidate.ps1 -CandidateMapping candidate.json -Python PYTHON_EXE
# Retry qualification only with a new output mapping and a new build receipt;
# the exact mapping bytes are bound into candidate-build.json.
./scripts/qualify-candidate.ps1 -CandidateMapping candidate.json -Python PYTHON_EXE
```

These entrypoints have no install option. They never rewrite the stable mapping,
select an installed Codex, bootstrap/download a managed package, or enable remote
control. The managed daemon uses a verified copy of the candidate package under
the new isolated home. Dependency paths are explicit, account/credential variables
are not inherited, and the sole model endpoint is a loopback mock.

The existing no-daemon smoke runs first, including Code Mode handshake. The new
gate then compiles/runs the isolated three-case nested Job surrogate and exercises
a separate visible positive control with an observer-ready handshake. The actual
managed daemon must report the expected version/home, have a pinned native handle
and exact candidate image/hash, and have no residual Job membership. A failed or
unknown Job query fails closed. No API rule accepting a harmless-looking ancestor
is assumed. The native surrogate confirms why even successful inner breakaway is
insufficient and tests that both benign and dangerous residual membership are
rejected by qualification policy. G03/G04 must separately verify actual source
preflight/child rejection and cleanup; G02 does not claim that port implemented.

A bounded RPC client connects to the private managed control socket, initializes,
pages `model/list`, creates an ephemeral GPT-6 Sol thread and executes one bounded
local-mock turn. Assertions require shell output, hooks, bundled helper output,
MCP initialize/tools-list lifecycle and an internal Git child observed before model
tool execution. Unreachable required paths fail closed. GPT-6 Sol's complete source
catalog entry must equal the admitted upstream entry; the binary must expose its
default/supported reasoning efforts and default tier through `model/list`, select
Sol, and send Sol in all local mock requests. This deterministic check uses no real
account. The G07 Owner inference canary remains separate.

The managed mock follows Sol's upstream `code_mode_only` contract: top-level
`exec` custom-tool calls run JavaScript that invokes the bounded nested
`exec_command` tools. Requests must expose custom `exec`, keep `exec_command` out
of the top-level tool list and return custom-tool outputs for each call. A managed
Code Mode host process must also be observed. Hidden-handler dispatch cannot
substitute for the Code Mode execution path. The old no-daemon gpt-5.5 smoke keeps
its separate function-call fixture.

After graceful daemon stop, pinned daemon/descendant handles and an additional
managed-package process scan must prove no owned orphan. The observer must report
zero relevant visible-console/pseudo-console/foreground events; unknown console
identity fails closed. Short-lived helpers can be missed by polling: they cannot
satisfy required functional coverage, and ambiguous coverage must stop G04. No
system/ancestor Jobs or terminal settings are changed to force success. A host
whose Jobs prevent independent daemon lifetime will fail qualification.

Both workload observers use ready and stop-marker acknowledgments, with hard
maximum durations. The managed observer must remain alive until graceful daemon
and descendant shutdown is proven; an early observer exit cannot produce PASS.
The visible positive control requires an actual show/foreground event.

Run focused tests with `scripts/test-hardening.ps1`. On an interactive Windows
desktop also run `validate_windows_fixtures.py --output NEW_DIRECTORY --pwsh PWSH_EXE`.
This second test intentionally displays one short-lived positive-control console.
CI performs syntax, candidate-admission/provenance, catalog, RPC and native socket
tests; it does not claim an interactive presentation or Codex package qualification.
