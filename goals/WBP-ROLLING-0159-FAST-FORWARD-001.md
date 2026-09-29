# Rolling Edge and Stable promotion

Goal: `WBP-ROLLING-0159-FAST-FORWARD-001`.

This supersedes the active 0.158 release train. Freeze `e5cdced97ee29a81724fb8087f123af8e9aa6b37`
as a semantic donor, including its exact change map and prior boundary decisions.
It is not qualified or release eligible. Preserve uncommitted G03S fixture work
separately; do not silently identify it with that commit. The stable manifest and
default routing continue to identify the qualified 0.156 rollback.

## Rolling Edge

Exact first target: `rust-v0.159.0`, commit
`687a119f0fcaace47e1f1abcc77cec6c813fd6da`. Before Stable qualification starts,
a new latest stable can be admitted by reviewed control-manifest retarget and
a new Edge audit. A retarget invalidates the previous Edge validation.

Compute only the donor-upstream to target-upstream delta. Intersect it with the
32 donor boundaries / 35 mapped files, while checking the other previously
audited preservation boundaries and newly introduced launch sites. Do not rerun
the complete historic port audit. `UNAFFECTED` inherits the prior reviewed
decision, not an uncompleted runtime qualification. Review `CHANGED`, `UPSTREAMED`
and `NEW` with exact before/after blobs and an attributable semantic decision.
The delta report is an impact inventory until those reviews resolve it.
Never mechanically cherry-pick commits or replay an entire donor patch.

Create a clean candidate rooted in exact target upstream. Carry only still-needed
semantic deltas. Keep release-source normalization distinct from Windows behavior.
The generalized G03R sanity gate derives workspace-local packages from the exact
target, permits only their stale release-version fields to change, preserves all
external records byte-for-byte and all dependency edges, and checks full locked
Cargo metadata plus a locked check. Reject unrelated generated lock changes.
Run the upstream Bazel lock refresh in isolation and prove no unexplained drift.

FAST Edge requires exact clean commit/tree and ancestry, resolved delta audit,
release-source sanity, formatting and bounded affected-source checks, GPT-6 Sol
catalog preservation, and the merged G03S clean native worker / pinned nextest
contract. Retain all original 68 focused tests with zero skips. A synthetic
worker, native-only proof or nextest-only proof cannot satisfy it. Edge PASS
records exact source/evidence and permits an explicitly selected side-by-side
candidate; it does not imply Stable PASS or change default routing.

## Stable

`rolling_control.py begin-stable` freezes the exact FAST-passing target, source
commit/tree and evidence hash before starting qualification. Once frozen, a new
upstream stable never retargets that qualification, including after a failure.
Corrections require a new reviewed candidate and a new qualification attempt;
retain the original freeze and receipts.

Run one complete Stable qualification for the selected Edge, including default
`just test`, required lint, package build and isolated package qualification,
managed-daemon/native lifetime/presentation proof with visible positive control,
fresh-clone reproduction, hashes and zero owned-child leaks. Long tests and
qualification run as durable external jobs; persist a request, process identity,
command/log hashes, source and maintenance identity, final exit and receipts.
The interactive agent checks receipts without waiting on the long process.
Interrupted, missing or inconsistent receipts never count as PASS. Full-suite
skips must exactly match the ignored-test identities in bound nextest discovery;
any nonzero set is `PENDING_SKIP_REVIEW` until independent review accepts those
exact identities and the resulting receipt. Focused-68 skips remain forbidden.

Ordered promotion: Stable qualification -> source review/release -> provenance
and manifest review/CI/PR/merge -> side-by-side installed qualification -> G07
Owner-attended authenticated GPT-6 Sol canary -> routing promotion -> reply to
`openai/codex#44768` -> WBP closeout -> FleetSplice 0.159 incremental
requalification. Do not access FleetSplice before WBP closeout. Preserve rollback
and official fallback. Never access/copy credentials for the Owner canary.

Maintenance changes require fresh independently launched read-only review,
passing Windows CI on the exact reviewed PR head, and merge before source use.
Only stop for a genuine hard blocker, unresolved independent review, or G07
Owner canary. Full-suite authorization is granted by this goal.
