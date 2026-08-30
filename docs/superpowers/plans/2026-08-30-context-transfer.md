# Context Transfer Staged Implementation Plan

Authoritative specification: `docs/superpowers/specs/2026-08-30-context-transfer-design.md`

## Authorization

- Design and plan creation: authorized.
- Implementation: `already_authorized` by the user's explicit `continue` instruction.
- Do not ask again between stages for this unchanged implementation scope.
- Destructive retirement of a live source task remains separately gated by archive verification, destination acceptance, verified Codex archival, and explicit live-retirement authorization.

## Stage 1: Read-Only Task-Tree Inventory

Requirements: CT-1, CT-2, CT-13, and the dry-run acceptance criteria.

- Add the package/family skeleton and read-only SQLite adapter.
- Resolve a source root and recursive spawn tree without writing Codex state.
- Inventory exact rollout identities and terminal child status.
- Add synthetic fixtures plus a read-only Apollo/Beacon acceptance check.
- Reconcile Stage 1 against the complete specification before advancing.

Verification:

- Unit tests for recursion, cycles, missing rows/files, active children, path boundaries, and source/destination identity rejection.
- Apollo/Beacon dry run reports 102 rollouts, 101 closed child edges, and `8,000,165,603` bytes.
- Database trace or adapter tests prove read-only access.

## Stage 2: Recovery Packaging And Integrity

Requirements: CT-5, CT-6, CT-7, and archive-layout acceptance criteria.

- Implement transaction roots under `E:\Codex\ThreadArchives`.
- Build the 7z payload directly on `E:` using recorded maximum-compression settings.
- Generate external/internal manifests, metadata exports, hashes, and verification evidence.
- Implement archive testing and representative extraction verification.
- Reconcile Stage 2 against the complete specification before advancing.

Verification:

- Fixture archives prove deterministic manifests and path mapping.
- Compression process has progress heartbeats but no cancellation timeout.
- Corrupt, incomplete, downgraded, or mismatched archives cannot verify.
- No multi-gigabyte staging path is created on `C:`.

## Stage 3: Destination-Owned Analysis And Skill Workflow

Requirements: CT-1, CT-3, CT-4, CT-8, CT-14, and handoff acceptance criteria.

- Add bounded source evidence extraction without permanent raw duplication.
- Add the Codex-only skill workflow for source selection, task retrieval, live repository verification, handoff writing, and acceptance.
- Define the handoff and acceptance schemas.
- Keep all task lifecycle mutation outside the helper until acceptance passes.
- Reconcile Stage 3 against the complete specification before advancing.

Verification:

- Tests reject missing objectives, unmapped blockers, unverified repository claims, and non-terminal child agents.
- Destination context contains the compact handoff, not raw rollout dumps.
- Skill validation and instruction tests pass.

## Stage 4: Archive Gate And Transactional Deletion

Requirements: CT-9, CT-10, CT-11, CT-13, and deletion acceptance criteria.

- Require verified Codex archived state before deletion-ticket issuance.
- Bind the single-use ticket to archive, handoff, task tree, and exact source file identities.
- Delete only unchanged manifest files and exact proven-owned cache artifacts.
- Skip and report changed or new files; keep retirement incomplete while residuals remain.
- Reconcile Stage 4 against the complete specification before advancing.

Verification:

- Tests prove no wildcard, broad-root, repository, worktree, shared-cache, or SQLite deletion.
- Replay, tampered, wrong-archive, changed-file, and partial-deletion cases fail or skip safely.
- A valid synthetic transaction reclaims only reviewed files.

## Stage 5: Conflict-Safe Restore

Requirements: CT-11, CT-12, CT-13, and restore acceptance criteria.

- Implement archive verification, staged extraction, file-hash validation, and exact-path placement.
- Skip identical files and refuse conflicts.
- Report absent metadata rows without writing SQLite.
- Document the subsequent Codex unarchive step.
- Reconcile Stage 5 against the complete specification before advancing.

Verification:

- Round-trip fixture restoration reproduces every original hash.
- Insufficient-space, corrupt archive, existing conflict, and missing-metadata cases are explicit and non-destructive.

## Stage 6: Installation And Apollo/Beacon Live Acceptance

Requirements: all specification requirements and acceptance criteria.

- Run complete package, root, skill, safety, and skills.sh validation.
- Install the Codex skill and private/local runtime without Claude parity in v1.
- Run Apollo/Beacon inventory and handoff preparation first without mutation.
- Review generated handoff, archive estimate, and exact deletion scope.
- Only after explicit live-retirement authorization: pack, verify, archive the source task, issue the deletion ticket, and apply it.
- Confirm the destination task can continue and source residual bytes are zero.
- Run a restore rehearsal against a separate staging target before claiming recovery readiness.
- Reconcile the complete specification with zero blockers and zero tracked deferrals.
- Commit, merge, sync, and clean transaction staging only after the final gate passes.

## Reconciliation Ledger

| Stage | Status | Satisfied requirements | Blockers | Tracked deferrals | Evidence |
| --- | --- | --- | --- | --- | --- |
| Planning | passed | All requirements mapped to Stages 1-6 | 0 | 0 | Approved design converted into the authoritative specification and compact plan. |
| 1 | passed | CT-1, CT-2, CT-13; dry-run acceptance | 0 | 0 | 16 focused tests pass. Live read-only inventory: 102 rollouts, 101 closed edges, 8,000,165,603 bytes, zero blockers, no archive-root creation, unchanged live database size and mtime. |
| 2 | passed | CT-5, CT-6, CT-7; archive-layout acceptance | 0 | 0 | 29 cumulative tests pass, including real NanaZip pack/test/extract round trips, maximum LZMA2 solid argument checks, direct partial-to-final transaction flow, internal/external metadata hashes, representative rollout extraction, and corruption/downgrade/incomplete rejection. |
| 3 | passed | CT-1, CT-3, CT-4, CT-8, CT-14; handoff acceptance | 0 | 0 | 43 cumulative family tests pass. Streaming catalog retains only bounded excerpts and offsets; exact handoff sections and child IDs are required; destination acceptance rejects missing objectives or repository evidence; pack revalidates the handoff. Codex-only skill, wrapper, validator, and monorepo checks pass. |
| 4 | passed | CT-9, CT-10, CT-11, CT-13; deletion acceptance | 0 | 0 | 55 cumulative tests pass. Ticket issue binds verified archive, accepted handoff, exact task tree, and Codex archived-state evidence; apply requires the separately reviewed ticket ID and deletes only unchanged listed files. Changed files are skipped, new files ignored, replay/tamper/outside-root cases rejected, and no recursive, wildcard, cache, or SQLite deletion path exists. |
| 5 | passed | CT-11, CT-12, CT-13; restore acceptance | 0 | 0 | 62 cumulative tests pass. Real NanaZip round trips restore every absent exact path with matching hashes, skip identical files, block conflicts before placement, enforce target-volume free space, reject corruption, report missing metadata rows through read-only SQLite, and clean exact staging. |
| 6 | pending | - | - | 0 | - |

Implementation completion requires every stage to pass, `blockers = 0`, `tracked_deferrals = 0`, verified recovery evidence, and zero residual manifest-bound source files.
