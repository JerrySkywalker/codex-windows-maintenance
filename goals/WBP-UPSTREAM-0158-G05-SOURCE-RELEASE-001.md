# G05 — source review and release

Goal ID: `WBP-UPSTREAM-0158-G05-SOURCE-RELEASE-001`

Purpose: move only the exact qualified source object into the public source fork release history.

## Required procedure

- Push the exact G04 candidate to a review branch in `codex-windows-patched`.
- Open one source PR against the source fork's public main.
- Obtain a fresh independent read-only review of the exact PR head/diff.
- Resolve every actionable finding and repeat exact-head qualification/review when source changes.
- Verify merge ancestry preserves the intended upstream 0.158.0 ancestry and downstream provenance
  policy.
- Merge only after the exact reviewed candidate remains qualified.
- Verify the merged source tree is the intended release tree. If the merge changes the qualified
  tree, requalify the merged object before tagging.
- Create the immutable downstream release tag only on the exact qualified release object. Expected
  naming convention: `v0.158.0-wbp-r1`, unless the port evidence justifies a later revision.

Do not update the maintenance stable mapping before the release object is proven.

## PASS

`PASS_G05_WBP_0158_SOURCE_RELEASE_PROVEN`
