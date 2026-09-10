# Cleanup Review Scaling

## Authoritative Requirements

The snapshot safety contract remains
`../specs/2026-08-03-transactional-cleanup-design.md`.

- R1: Review registration matching must scale with path depth rather than the
  product of inventory size and registration count.
- R2: Preserve deepest matching registration, first-registration tie behavior,
  Windows case-insensitivity and path-component boundaries. Preserve all existing
  candidate/exclusion and exact-deletion safety rules.
- R3: Do not change live transaction scope, stop processes, delete user outputs,
  introduce a timeout, or imply that matching optimization removes broad scan cost.
- R4: Explain targeted scan scope and the distinction between live lock ownership
  and computational work. Commit verified repository changes only; installation
  and publication are not part of this correction's authorization.

## Evidence

The reported review completed during investigation. It explicitly selected D:\Temp
and had 133 registrations, a roughly 707 MiB baseline and 847 MiB manifest. No ticket
was issued at inspection. A synthetic 5,000-path/133-registration probe measured
5.57 seconds for existing matching versus 0.063 seconds for ancestor lookup, with
identical results. This measures matching only, not total filesystem review time.

## Stages

| Stage | Status | Acceptance | Remaining | Blockers | Tracked Deferrals |
| --- | --- | --- | --- | --- | --- |
| Matching correction | COMPLETE | R1-R3; operation-count regression passes; deepest match, first tie and path boundaries verified against real files | None | None | None |
| Integration and guidance | COMPLETE | R2-R4; synthetic installed-wrapper review/ticket/dry-run/apply/status workflow and Windows identity/retry safety regressions pass; docs distinguish scope and lock behavior | None | None | None |

## Final Reconciliation

R1 is verified with a deterministic operation-count regression, not a timing
deadline. The original path/registration cross-product made 66,500 containment
checks for 500 entries and 133 registrations; ancestor lookup removes this product.
R2 is verified by matching precedence/component-boundary tests and existing real
Windows disposable-tree workflow tests. R3 is satisfied by retaining scanner,
ticket and apply behavior; no live transaction was modified or process stopped.
R4 is reflected in both skill bundles and README, with repository-only delivery.

Fresh family, root wiring and full root verification passed; skill validation and
diff checks passed. All disposable fixtures were cleaned by their test teardown.
No live installation, user-folder cleanup or publication was performed. Both
stages are COMPLETE with zero blockers and zero tracked deferrals.
