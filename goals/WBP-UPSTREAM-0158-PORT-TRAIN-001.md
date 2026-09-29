# WBP upstream 0.158 port Goal Train

Historical train: superseded by [Rolling Edge / Stable](WBP-ROLLING-0159-FAST-FORWARD-001.md).
The 0.158 candidate is frozen as a semantic donor and must not proceed to release.
Prior reviewed semantic decisions remain usable; unfinished qualification remains unfinished.

Goal ID: `WBP-UPSTREAM-0158-PORT-TRAIN-001`

Purpose: advance the existing Windows compatibility maintenance workflow from the qualified
`v0.156.0-wbp-r1` baseline to upstream Codex `rust-v0.158.0` without bypassing the
two-repository governance model, weakening source provenance, or replacing evidence-driven
Windows presentation qualification with a mechanical rebase.

## Authority and baseline

- Maintenance repository baseline: `JerrySkywalker/codex-windows-maintenance@82691e666bb9e421282233a9c7750d2b9e36ce4a`.
- Current stable mapping: `manifest.json` -> upstream `0.156.0@fe74a774532af67b5a4a3dec03ce9469e17f89af`,
  downstream tag `v0.156.0-wbp-r1@44093ea5c1d33f008f6035ec1a519e1247f04295`,
  tree `2a9dacb7e34dd719730946eaefcf755c47aae56e`.
- Source fork public main at train admission:
  `JerrySkywalker/codex-windows-patched@132ba3d1aee04f51af4df4cbe75beed8cf7d1f08`.
- Target upstream release: `rust-v0.158.0`, exact upstream commit
  `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`.
- OpenAI Codex issue `#44768` is current external evidence for the Windows managed-daemon
  presentation defect class. It is context, not implementation authority.

All Goal Train control files live in this maintenance repository. The source fork must remain a
Codex source/provenance repository; do not add Goal Train control documents there.

## Train sequence

| Gate | Goal | Required outcome |
| --- | --- | --- |
| G00 | Baseline freeze and admission | Exact old/new refs and rollback path proven; no routing mutation |
| G01 | Upstream port audit | Every prior WBP launch boundary classified against 0.158.0 |
| G02 | Maintenance workflow hardening | Candidate qualification path and managed-daemon presentation gate are explicit |
| G03 | Minimal source port | Only still-required Windows behavior is ported into the source fork |
| G04 | Exact candidate qualification | Source/package/runtime behavior passes on Windows with isolated evidence |
| G05 | Source review and release | Fresh exact-head review, source PR, merge and immutable release tag |
| G06 | Provenance and manifest promotion | Public provenance and stable maintenance mapping move to the qualified release |
| G07 | Side-by-side deployment and handoff | New WBP is installed without destroying rollback; routing changes only after acceptance |

Execute gates in order. A later gate may not convert an earlier blocker into a pass.

## Cross-train invariants

1. Never silently replay the old WBP patch series. The existing `port.ps1`, presentation policy,
   spawn inventory and actual upstream diff are the starting authorities.
2. Preserve the qualified `0.156.0-r1` installation/tag as rollback until G07 is complete.
3. Do not mutate the user's official Codex installation, credentials, or account state as part of
   source qualification.
4. Use isolated `CODEX_HOME`, disposable workspaces and caller-selected evidence directories for
   automated tests.
5. Background Windows children must not create visible console windows or steal focus. Interactive
   terminal/ConPTY behavior must remain visible and functional.
6. Managed-daemon qualification must exercise the defect class represented by upstream issue
   `#44768`; `--no-daemon` qualification alone is insufficient for this train.
7. Do not hide a failed background presentation check by changing the Windows default terminal,
   power policy, sandbox policy, or user shell profile.
8. Do not update the stable `manifest.json` to an unqualified candidate merely to make
   `bootstrap.ps1` or `qualify.ps1` accept it. If a pre-promotion candidate mapping is required,
   add an explicit fail-closed mechanism in G02.
9. The source fork preserves upstream ancestry and keeps maintenance tooling out of Codex source.
10. A GPT-6 Sol acceptance check belongs to release qualification/promotion; do not patch an old
    bundled model catalog merely to emulate a newer release.
11. No FleetSplice code or production infrastructure is changed by this train. FleetSplice may be
    requalified only after G07 through a separate handoff.

## Stop conditions

Stop with a bounded blocker rather than improvising if:

- the exact upstream tag/commit cannot be proven;
- the old qualified source or rollback package cannot be identified;
- port audit leaves an unclassified changed process-launch boundary;
- a candidate requires broad unrelated upstream modification;
- a Windows background process creates a visible/foreground event;
- a native effect or credential state becomes ambiguous;
- the candidate cannot be bound to an exact commit/tree/package hash;
- an independent review has an unresolved actionable finding;
- a source/manifest/provenance mapping would claim an object that was not actually qualified.

## Terminal success

The complete train may report success only when all child goals are complete:

```text
DISPOSITION=PASS_WBP_0158_PROMOTED_SIDE_BY_SIDE
GOAL_ID=WBP-UPSTREAM-0158-PORT-TRAIN-001
UPSTREAM_VERSION=0.158.0
UPSTREAM_COMMIT=064c6b8c737f5b41d171fdda80bd9ef10ad06eb3
OLD_WBP_ROLLBACK_RETAINED=true
PORT_AUDIT=PASS
MANAGED_DAEMON_PRESENTATION_GATE=PASS
SOURCE_PORT=PASS
PACKAGE_QUALIFICATION=PASS
GPT_6_SOL_ACCEPTANCE=PASS
INDEPENDENT_REVIEW=CLEAN
SOURCE_RELEASE_TAG=PROVEN
MAINTENANCE_MANIFEST_PROMOTED=true
SIDE_BY_SIDE_INSTALL=PASS
ROUTING_PROMOTION=PASS
FLEETSPLICE_MUTATED=false
```

Then stop and issue a separate FleetSplice requalification handoff.
