# G03 — minimal source port

Goal ID: `WBP-UPSTREAM-0158-G03-SOURCE-PORT-001`

Purpose: create the smallest architecture-preserving 0.158.0 WBP source candidate in
`codex-windows-patched`.

## Source rules

- Work from a branch whose ancestry includes exact upstream
  `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3` and preserves the source fork's public provenance
  policy.
- Port only behaviors classified `STILL_REQUIRED` or an explicitly resolved
  `BOUNDARY_CHANGED`/`NEW_REVIEW_REQUIRED` item from G01.
- Never mechanically replay the old patch series.
- Keep maintenance harnesses, Goal Train files, machine receipts and packages out of the source
  repository.
- Preserve interactive/ConPTY visibility while applying background presentation policy at actual
  final child-launch boundaries.
- Do not modify authentication semantics, account credentials, model entitlements or unrelated
  product behavior to make qualification pass.
- Follow upstream repository `AGENTS.md`, formatting and focused-test rules.

## Required local evidence

- exact base and candidate commit/tree;
- diff against upstream 0.158.0;
- mapping from every source change back to a G01 classification;
- focused tests for changed crates/paths;
- formatting/lint required by affected upstream crates.

## PASS

`PASS_G03_WBP_0158_SOURCE_CANDIDATE`

## Owner-authorized release-source amendment

The bounded [G03R lock normalization](WBP-UPSTREAM-0158-G03R-LOCKFILE-NORMALIZATION-001.md)
permits only the verified 158 local package version corrections after maintenance
review, CI and merge. Map this delta separately from the Windows behavior boundaries.

The Owner-authorized [G03S fixture host contract](WBP-UPSTREAM-0158-G03S-FIXTURE-HOST-CONTRACT-001.md)
requires native real-guard proof **and** nextest results **and** exact identity and
cleanup binding. Preserve every original focused test (68/68, zero skips). A
native-only receipt or a nextest-only run cannot close source lifetime validation.
Merge the reviewed and CI-validated maintenance contract before relying on it.
