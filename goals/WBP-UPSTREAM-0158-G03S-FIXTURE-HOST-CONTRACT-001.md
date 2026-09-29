# G03S — source guard fixture host contract

Goal ID: `WBP-UPSTREAM-0158-G03S-FIXTURE-HOST-CONTRACT-001`

Owner-authorized bounded G03 precondition. Architecture C requires a one-shot
clean native worker executing the real source guard and an executing nextest
parent assertion over its completed receipt. G00–G02/G03R remain PASS; gate order
remains G00 through G07. No package or installed WBP is used in this slice.

Maintenance owns orchestration and the validation contract. Source owns only the
test worker and receipt assertion. Production guard semantics, dependencies,
stable mapping, routing and installed binaries are unchanged.

Focused acceptance requires all of the following on the same exact source tree:

- Compile through `just test` and pinned nextest; discover one exact daemon test
  binary through matching nextest metadata, and seal its hash/build scope.
- Launch with supported breakaway; native controller and Rust worker must each
  prove the worker and fixture child have no Job membership. The controller may
  retain ambient Jobs. Failed/unknown worker/child query fails.
- Execute the actual `ensure_detached_child` with a real Tokio Child. Verify
  child membership independently before calling the guard. Guard must accept.
- Register a stable cleanup handle with the controller before the guard. Prove
  normal and fault cleanup, including death before registration. No PID-only
  termination or mutation of ambient/runner Jobs is permitted.
- Atomically complete bound Rust and controller receipts: schema/kind, fresh run
  ID, source commit/tree, exact test and binary hashes, worker/child PID and
  creation FILETIME, API returns/errors, accepted guard, zero worker exit, and
  child termination/reaping/handle closure.
- Run every original focused Rust case under `just test`/nextest: 68 pass, zero
  fail, zero skip. The existing positive parent test must validate fresh receipts
  and its own test binary; missing/stale/wrong/failed/incomplete evidence fails.
- Reject all specified contract faults with deterministic maintenance tests.
  Synthetic workers qualify only the harness, never the candidate source guard.

Completion requires fresh independently launched read-only review, normal
maintenance PR, exact-head CI PASS and merge before the source continuation relies
on the contract. G03S PASS alone is not G03 PASS. G03 must then complete all source
validation, including the separately Owner-approved complete `just test`, final
fmt/lint and source mapping. If a proven clean real child is rejected, stop for a
product blocker before changing lifetime semantics.
