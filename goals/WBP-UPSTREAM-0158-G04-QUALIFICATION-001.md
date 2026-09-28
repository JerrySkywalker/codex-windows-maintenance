# G04 — exact candidate qualification

Goal ID: `WBP-UPSTREAM-0158-G04-QUALIFICATION-001`

Purpose: prove the exact G03 source candidate and its Windows package before any release claim.

## Required qualification

- Build from the exact candidate source commit/tree using the source repository's own package
  builder and pinned resources.
- Use the G02 candidate mapping mechanism if the stable release manifest has not yet been promoted.
- Use fresh isolated `CODEX_HOME` and disposable workspaces.
- Run existing package qualification plus the G02 managed-daemon presentation gate.
- Exercise the existing background classes represented by the policy/inventory: shell/pipe,
  hooks/notify, Git/plugin Git, MCP, Code Mode and relevant Windows sandbox/helper paths.
- Require zero visible/foreground background events and a passing visible positive control.
- Verify package metadata, expected files and SHA-256 inventory.
- Verify no owned native/daemon child is left after qualification.
- Verify GPT-6 Sol is recognized by the candidate model contract/catalog without altering account
  entitlements.
- Run the focused source tests required by changed crates. Run broader source tests when a shared
  process-launch abstraction changed; record any upstream/baseline failures distinctly.
- Run a fresh-clone reproduction of the candidate mapping/build/qualification path.

## Hard blockers

A presentation event, ambiguous process lifetime, source/tree mismatch, package mismatch, hidden
test skip, or unclassified upstream regression blocks release.

## PASS

`PASS_G04_WBP_0158_EXACT_CANDIDATE_QUALIFIED`
