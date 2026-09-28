# G06 — provenance and stable mapping promotion

Goal ID: `WBP-UPSTREAM-0158-G06-MAPPING-PROMOTION-001`

Purpose: update public provenance and the stable maintenance mapping only after G05 proves the
release object.

## Required changes

- Update source-fork public provenance metadata/documentation to identify the exact upstream
  0.158.0 commit, qualified downstream release commit/tree and release tag.
- Update maintenance `manifest.json` to the same exact release mapping.
- Update maintenance README examples/version text if required.
- Ensure bootstrap/qualify from a fresh checkout accept the promoted release and reject a
  mismatched source commit/tree/tag.
- Run maintenance CI and a fresh stable-manifest bootstrap/qualification smoke.
- Open normal PRs in the repositories that own the changed metadata. Review exact diffs before
  merge.

The source release tag itself must not move during this gate.

## PASS

`PASS_G06_WBP_0158_MAPPING_PROMOTED`
