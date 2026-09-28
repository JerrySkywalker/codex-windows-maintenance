# G01 — upstream port audit

Goal ID: `WBP-UPSTREAM-0158-G01-PORT-AUDIT-001`

Purpose: determine what, if anything, must still be carried downstream on Codex 0.158.0.

## Required procedure

1. Use the existing maintenance `scripts/port.ps1` against exact upstream
   `rust-v0.158.0@064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`.
2. Review every changed path reported by the port script against:
   - `harness/windows-presentation/POLICY.md`;
   - `harness/windows-presentation/SPAWN-INVENTORY.md`;
   - the qualified 0.156.0 downstream diff;
   - newly introduced `Command`, `CreateProcessW`, `CreateProcessAsUserW`, pipe, Job Object,
     sandbox, hook, Git, MCP, notify, Code Mode and daemon launch boundaries.
3. Produce a machine-readable and human-readable port matrix. Every prior downstream behavior and
   every relevant changed upstream launch boundary must be classified as exactly one of:
   - `UPSTREAMED`;
   - `STILL_REQUIRED`;
   - `BOUNDARY_CHANGED`;
   - `OBSOLETE`;
   - `NEW_REVIEW_REQUIRED`.
4. Re-check the current source state associated with upstream issue `openai/codex#44768`; do not
   assume either that the issue's proposed fix is correct or that a newer release resolved it.
5. Identify the smallest candidate source delta before G03. Do not edit Codex source in this gate.

## PASS

`PASS_G01_WBP_0158_PORT_MATRIX_COMPLETE`

Any unclassified presentation/process boundary blocks G02/G03.
