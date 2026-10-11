# Cleanup Routing Specification

## Scope

Clarify cleanup routing without weakening the helper's deletion protections.
The user authorized implementation, deployment and notifications to identifiable
recent affected tasks. No cleanup of those tasks' files is authorized here.

## Requirements And Acceptance

- R1: Distinguish reviewed source removal, exact generated-output cleanup and
  disposable validation clones. Git tracking is not a blanket cleanup refusal.
- R2: Source removal must be within the user's requested scope, inspect callers
  and working-tree changes, preserve unrelated edits, verify and commit through
  normal Git change review. Do not add a tracked-file override to the helper.
- R3: A tracked-file exclusion must not stop independent eligible cleanup.
  Mixed targets must retain accurate candidate/exclusion/residual reporting.
- R4: Deploy matching guidance to Codex, agents and Claude. Preserve the runtime
  and existing transactions because this change does not alter deletion policy.
- R5: Identify recent affected tasks using actual message evidence and notify
  them with the installed procedure; do not claim their cleanup has occurred.

## Compact Stages

1. Procedure and regression verification (R1-R3): COMPLETE. Routing is documented
   in both bundles and README; mixed tracked/generated regression and existing
   disposable-repository tests pass. No deletion implementation changed.
2. Deployment and notification (R4-R5): COMPLETE. Installed guidance hashes match
   across Codex, agents and Claude; runtime pointer is unchanged. The source task
   and the related maintenance task received scoped procedure-update messages.

## Completion Evidence

- Family verification: 71 tests passed, including exact-file mixed output cleanup
  that preserves a modified tracked template and its Git repository.
- Codex and Claude canonical bundles both pass quick_validate.py; git diff --check
  passes. Source/template deletion remains outside ticket authority.
- Root family CLI, isolation and monorepo-layout verification: 31 tests passed.
- Installed guidance SHA256 is identical across all three skill roots:
  AA55B29286E9D64ACAF9A76A4E62A84CBC3E610C1DC3AD892055BE2DC2BE72ED.
- All three installed skills pass structural validation. The unchanged active
  runtime pointer preserves existing cleanup transactions; no runtime reinstall
  or deletion-policy modification was needed.
- Notification receipts succeeded for the evidence-matched source task and the
  related maintenance task. Notices direct reinspection of current targets and
  preserve existing scope; no claim is made that their cleanup was performed.
- Task fixtures were isolated in temporary directories and removed by test
  teardown. No user project files or existing cleanup state were modified.
- Required blockers: zero. Required tracked deferrals: zero.
