# Context-transfer storage normalization

Authorization: normalize existing transfer folders on E: and the installed skill.
User identified an active consumer of E:/CodexTransfers; preserve that live tree
until its transfer finishes. This authorizes file-preserving consolidation and
skill/runtime correction, not archive expiry, conversation retirement or new schedules.

## Requirements

- N1: Use `E:/Codex/ContextTransfers` as the canonical local transfer/recovery
  root, including CLI defaults, maintained examples and installed instructions.
  Preserve explicitly requested alternative non-C recovery drives/roots.
- N2: Consolidate the existing `E:/Codex/context-transfer`,
  `E:/Codex/ContextTransfer`, `E:/CodexTransfers` and the verified transfer-only
  `E:/CodexRecovery` contents into the canonical root. Preserve relative activity,
  source-ID and transaction paths; merge directory-only overlaps without file
  overwrite, archive repacking, duplicate data or symlinks. Keep unrelated E: data
  and RetroBat sync-retirement evidence intact.
- N3: Inventory and hash every selected file before moving; verify matching
  content/identity and complete coverage afterward. Preserve immutable handoffs,
  manifests, verification files and tickets byte-for-byte; retain a compact path
  relocation map for their historical absolute references. Verify moved archives
  through their current exact paths. Move only completed/inactive transfer trees;
  leave TailD's live tree in place until supported status and artifact state permit.
- N4: Verify meaningful relocated-archive recovery behavior and changed CLI
  behavior, install source/skill/runtime parity, clean task scratch and obsolete
  empty grouping directories through the installed cleanup helper, reconcile all
  requirements and commit the completed result.

## Execution

| Stage | Status | Acceptance |
|---|---|---|
| Canonical skill and runtime storage | COMPLETE | N1/N4 archive relocation and CLI/runtime tests passed; installed Codex/agents skills and selected runtime match; defaults and explicit override verified |
| Consolidate existing recovery folders | COMPLETE | N2–N4 all 493 original files retain hashes/identities/size/mtime; all 25 archives pass installed recovery verification; four legacy roots and task scratch absent |

Blockers: none. Tracked deferrals: none. TailD's transfer completed; supported idle
status, COMPLETE ledger and zero visible consumers permitted its tree move.
All source directories were merged without overwrite. Main agent executed directly.

Design: keep existing archive/restore verification, which resolves metadata beside
the caller-supplied archive path and already verifies immutable hashes. No path
redirect layer, database rewrite or recovery-copy store is required. Historical
path references are retained as evidence and translated by the external move map.

## Final reconciliation

- N1: Installed Codex/agents skills and selected staged runtime match source.
  Actual inspect/pack parser defaults are E:/Codex/ContextTransfers; explicit
  alternative-root behavior remains supported. Maintained examples agree.
- N2/N3: 493 original files totaling 1,261,785,389 bytes preserved with unchanged
  hashes, identities, sizes and modification times. All 25 archives passed native
  recovery verification, including metadata comparison, archive testing and
  representative rollout/database extraction. No missing or unexpected files.
  Private path mapping is retained under the canonical root in
  `_PathNormalization-20261016/PATH_MAP.md` and `inventory-before.json`.
- N4: Archive integration checks (including move/verify/restore without evidence
  rewrite), CLI, skill and runtime checks passed. Empty legacy grouping directories
  and task scratch were reviewed/ticketed/removed through transactional-cleanup;
  all transactions are applied. No unrelated E: data or schedules changed.

Closure assessment: reuse existing same-directory metadata resolution and recovery
verification. One default-path correction and explicit skill storage rules suffice;
no redirect layer, symlinks, data copy, archive rewrite or migration framework added.
