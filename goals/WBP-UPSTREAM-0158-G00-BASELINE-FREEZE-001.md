# G00 — baseline freeze and admission

Goal ID: `WBP-UPSTREAM-0158-G00-BASELINE-FREEZE-001`

Purpose: establish an exact, reversible starting point before any port or maintenance-script change.

## Required checks

- Verify the maintenance checkout is based on the admitted Goal Train commit.
- Verify the current stable `manifest.json` still resolves to the qualified
  `v0.156.0-wbp-r1` commit and tree.
- Verify the source fork's current public main and the old qualified release tag are both reachable.
- Fetch upstream Codex read-only and prove `rust-v0.158.0` resolves to
  `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`.
- Record clean-worktree state for both repositories.
- Record the currently routed Codex/WBP executables and versions read-only. Do not switch routing.
- Confirm the old WBP remains available as rollback.
- Create a fresh evidence root outside both repositories.

## Prohibited

No source patching, manifest promotion, release tagging, PATH/routing change, credential mutation,
FleetSplice change, or production daemon migration.

## PASS

`PASS_G00_WBP_0158_BASELINE_FROZEN`
