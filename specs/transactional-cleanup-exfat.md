# Transactional Cleanup exFAT Support

Already authorized: fix the exFAT compatibility defect, deploy to Codex/Claude,
synchronize GitHub and notify SkyrimResearch to validate and clean its leftovers.
Do not delete its compiler scratch or change its research records in this task.

## Requirements

- E1: Detect exFAT through the opened handle when FileIdInfo is unsupported.
  Use volume serial, 64-bit file index and creation time, explicitly labeled as
  exFAT identity. Never silently substitute legacy IDs on NTFS/ReFS or arbitrary
  API failures. Keep existing NTFS/ReFS identity strings/tickets compatible.
- E2: Freeze SHA-256, size and write time for ordinary exFAT regular files in the
  signed review. Apply compares them through the same exclusively write/delete
  guarded handle used for deletion. Edited/replaced files survive; new concurrent
  files survive; empty directories alone may be removed. No path-based deletion.
- E3: Preserve exact-root coordination, Git/provenance/critical-root checks, ticket
  integrity, sharing checks and retry. Unreadable/locked content is excluded with
  diagnostics without blocking unrelated eligible output. Keep special repository
  retirement/disposable-clone/Git-marker contracts NTFS/ReFS-only in this patch.
- E4: Test API selection, error preservation, missing proof, modification/replacement,
  new-file preservation, locked-file retry and live disposable E: fixtures. Reuse
  existing NTFS/repository/state/installer regression coverage.
- E5: Deploy and verify installed runtime/skill parity on Codex, agents and Claude,
  and validate skills and the actual installed launcher on E:.

| Stage | Status | Acceptance |
| --- | --- | --- |
| exFAT reviewed-handle cleanup | COMPLETE | E1-E5 implemented, verified and deployed; evidence below. |

No tracked deferrals. The user's four residual files remain owned by the originating
task for final validation and cleanup. This task uses only independently generated
test fixtures; no policy-denied operation is retried by another mechanism.
Delivery then requires synchronization through normal PR checks and notification
to SkyrimResearch with the fresh-snapshot procedure, not an exception or discarded
ticket. Those actions remain part of the authorized outcome.

## Evidence

Live read-only queries on E: root, Temp, task root and one compiler scratch file
confirm GetFileInformationByHandle succeeds and FileIdInfo fails with WinError 87.
FileBasicInfo succeeds. E: reports exFAT. The filesystem type is not inferred merely
from its drive letter. The old helper excludes this root during review, before
ticket/apply. This is not a shell policy denial, ACL issue or sharing violation.

Microsoft documents filesystem-specific/reusable IDs and the need for 128-bit IDs
on ReFS: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/ns-fileapi-by_handle_file_information
Handle-bound filesystem detection: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationbyhandlew
The exFAT contract is therefore content-bound and stricter than NTFS same-identity
mutable generated-output cleanup; it does not claim eternal uniqueness of IDs.

## Final Reconciliation

- E1: Live E: readback and API-selection regressions prove exFAT fallback, no ReFS
  downgrade, no fallback on access failure, rejection of unusable regular-file
  index and unchanged existing 128-bit identity format.
- E2-E4: 110 cleanup/state/repository/installer tests pass, including 13 new API
  and real exFAT tests. Changed same-size content with restored write time survives;
  replacements/new files survive; locked apply retries; unreadable review content
  does not prevent independent cleanup; read-only ordinary output is handled.
- Root CLI/isolation/layout checks: 33 pass. Source and installed skills validate.
- E5: Installed v0.5.2 runtime hashes match source; Codex, agents and Claude skill
  copies match. Official installer preserved legacy state/recovery runtime and
  reported no deployment residuals. Codex begin/register/review/inspect/ticket,
  Claude dry-run and Codex apply completed on disposable E: output from outside
  the repo, using the default installed runtime. Both reviewed members were
  removed, 57 bytes reclaimed, transaction applied and fixture root absent.
- All four Skyrim compiler scratch files still match the originating evidence
  hashes. Its records and research source were not changed. Test fixture lifecycle
  left no exFAT fixture/state directories. No Gradle gate was acquired.

No blockers or deferrals remain in this helper implementation stage. Special
repository contracts remain NTFS/ReFS-only; ordinary exFAT generated cleanup is
the implemented scope, not an unsupported-filesystem exception.
