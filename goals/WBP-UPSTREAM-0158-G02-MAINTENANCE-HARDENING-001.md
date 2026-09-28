# G02 — maintenance workflow hardening

Goal ID: `WBP-UPSTREAM-0158-G02-MAINTENANCE-HARDENING-001`

Purpose: close maintenance-workflow gaps exposed by a new upstream port without weakening the
stable-manifest contract.

## Required outcomes

### Candidate mapping

The current stable `manifest.json` remains the authority for released WBP builds. If the existing
scripts cannot qualify a pre-release candidate without first replacing that stable mapping, add an
explicit fail-closed candidate mechanism. It must bind at least:

- target upstream version and exact upstream commit;
- candidate downstream commit and source tree;
- target triple/package variant/profile;
- caller-selected evidence/output paths.

A candidate mechanism must not make an unqualified object look released and must not silently
rewrite `manifest.json`.

### Managed-daemon presentation gate

Extend the Windows qualification harness so the release train can exercise the managed/shared
app-server path relevant to `openai/codex#44768`. The gate must use isolated state and prove, at
minimum:

- daemon start/readiness and exact executable/version identity;
- one bounded background shell execution;
- representative hook execution;
- representative internal Git/helper execution when reachable;
- representative MCP/stdio helper execution when reachable;
- clean shutdown with no orphan under the test's ownership;
- zero relevant visible console/pseudo-console or foreground-steal events;
- a separate visible positive control so a zero-event result proves observer function.

Do not replace the existing `--no-daemon` smoke; the two paths are complementary.

### GPT-6 Sol release check

Add a deterministic release check that proves the candidate recognizes the upstream GPT-6 Sol
model contract/catalog. A real-account inference can remain an Owner promotion canary in G07;
credentials must not be copied into the harness.

## Validation

Run repository syntax/structure checks and focused harness tests. Obtain a fresh review if this gate
changes control logic beyond straightforward harness extension.

## PASS

`PASS_G02_WBP_0158_MAINTENANCE_READY`
