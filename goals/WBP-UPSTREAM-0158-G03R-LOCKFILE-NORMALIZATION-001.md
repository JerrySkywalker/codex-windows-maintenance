# G03R — upstream 0.158 workspace version lock normalization

Goal ID: `WBP-UPSTREAM-0158-G03R-LOCKFILE-NORMALIZATION-001`

Owner authorization: `UPSTREAM_0158_WORKSPACE_VERSION_ONLY_LOCK_NORMALIZATION`.
This bounded amendment admits only the release-source correction below. It does
not alter the 32 Windows behavior boundaries, the upstream ancestry, or Gate order.

## Exact release condition and proof

Exact upstream is `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`; its parent is
`f3d021e0df2d3b5a350f5cf57fe0b901b05634bd`. The release changed only the workspace
version in `codex-rs/Cargo.toml`, from 0.0.0 to 0.158.0. Its Cargo.lock blob
`13f4c2a6a027014a221a4625108b782c517c290e` is identical to its parent's.
The 158 source-less local records remain at 0.0.0: 153 explicit members and five
automatic members, confirmed against full Cargo metadata workspace membership.

The attached expected-package set and semantic proof define the exact correction.
In an isolated exact-upstream copy, both full locked metadata and locked
`cargo check -p codex-utils-pty --lib` rejected the stale lock (exit 101).
After the verified replacement, both succeeded (exit 0) without changing the lock.
`--no-deps` metadata is insufficient and is not used as the locked acceptance proof.

## Allowed delta and invariants

- Cargo.toml remains byte-identical to the exact upstream Git object after EOL normalization.
- Exactly the attached 158 local package versions change 0.0.0 to 0.158.0.
- All other local fields, dependency lists, external package blocks and semantic
  records remain identical; external versions, sources, checksums and features do not change.
- Preserve checkout EOL when applying the correction. Canonical LF SHA256 is
  `e93a06df3e346a7de763d5715715eaf51675a83a632c14e22ca3e5651c1fc74d`;
  original canonical LF SHA256 is
  `5c3fd1fe59676117cd7fc9c55daafee90d95d0afedd13b9e1a71e10cad029a81`.
- Do not regenerate dependencies or accept Cargo output without independent semantic validation.
- No unrelated generated-file change is authorized. Run the upstream Bazel lock
  refresh in isolation; any required unrelated delta blocks source acceptance.

## Ordered application and stop rules

1. Obtain fresh independent read-only review of the amendment and isolated proof.
2. Open a maintenance PR, require CI PASS on its exact reviewed head, then merge.
3. Only then apply the verified lock correction to the existing source worktree,
   preserving draft `0cfbb7e824def95d4a9a91ce746705e74a62a34c` as an ancestor.
4. Make the lock correction separately attributable and extend the source change
   map with G03R release-source normalization, distinct from Windows boundaries.
5. Resume G03 focused tests and required lint. Stop after G03; never start G04 here.

Stop on a semantic mismatch or ambiguous validation. No package build, release tag,
manifest, routing, installed WBP, credentials, production daemon or FleetSplice change.

Evidence: `C:\Dev\artifacts\WBP-UPSTREAM-0158-PORT-TRAIN-001\G03R`.
Isolated logs, receipts and independent proof live there; this amendment grants no
qualification or release acceptance.
