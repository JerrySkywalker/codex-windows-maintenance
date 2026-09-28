# G07 — side-by-side deployment and promotion

Goal ID: `WBP-UPSTREAM-0158-G07-SIDE-BY-SIDE-PROMOTION-001`

Purpose: deploy the qualified 0.158.0 WBP as a reversible daily-driver candidate while retaining
the previous WBP and official Codex fallback.

## Required sequence

1. Build/install from the promoted stable mapping into a new versioned per-user directory.
2. Do not overwrite or delete `v0.156.0-wbp-r1`.
3. Prove the new launcher/package version, source mapping and hashes.
4. Run installed-copy qualification, including the managed-daemon presentation gate.
5. Verify the official Codex fallback remains independently invokable.
6. Run an Owner-attended ChatGPT-authenticated canary that selects GPT-6 Sol and performs one
   harmless turn. Do not copy or export credentials.
7. Only after the canary passes, promote the user's normal WBP routing to the new version.
8. Open a fresh shell and verify routing resolves to the intended 0.158.0 WBP while rollback and
   official fallback remain available.
9. Record a rollback command/path and final receipt.

## FleetSplice boundary

Do not resume or mutate FleetSplice in this gate. Emit a separate handoff containing the new
qualified Codex executable path/version/hash so FleetSplice can perform an incremental native
requalification later.

## PASS

`PASS_G07_WBP_0158_SIDE_BY_SIDE_PROMOTED`
