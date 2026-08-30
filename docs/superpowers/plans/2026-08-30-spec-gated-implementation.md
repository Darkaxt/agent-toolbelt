# Specification-Gated Implementation Plan

Authoritative specification: `docs/superpowers/specs/2026-08-30-spec-gated-implementation-design.md`

Implementation authorization was already provided when the user asked to implement and deploy the approved skill design. No additional confirmation is required for this scope.

## Stage 1: Canonical Skill And Contract Tests

Requirements: SGI-1 through SGI-8.

- Add the canonical instruction-only skill and Codex metadata.
- Add focused tests for authorization reuse, per-stage reconciliation, blocker closure, and mandatory deferral closure.
- Verify the system skill validator and focused tests.

## Stage 2: Repository Discovery And Documentation

Requirements: SGI-8 and Distribution acceptance criteria.

- Register the skill with skills.sh validation.
- Document instruction-only skill layout and Codex/Claude installation paths.
- Verify local skills.sh discovery and root tests.

## Stage 3: Install, Validate, And Sync

Requirements: all acceptance criteria.

- Install the canonical skill in both active skill roots without divergent edits.
- Validate both installed copies and compare file hashes with canonical files.
- Run the full repository test and validation gates.
- Reconcile the complete specification with zero blockers and zero tracked deferrals.
- Commit, push, merge, fast-forward local `main`, and confirm a clean checkout.

## Reconciliation Ledger

| Stage | Status | Satisfied requirements | Blockers | Tracked deferrals | Evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | passed | SGI-1 through SGI-8 | 0 | 0 | System skill validator passed; 19 focused skill and layout tests passed. |
| 2 | passed | SGI-8 and distribution acceptance criteria | 0 | 0 | Local skills.sh discovery and repository validator found all 15 skills exactly once. |
| 3 | pending | - | - | - | - |

The plan cannot be marked complete while either the Blockers or Tracked deferrals column contains unresolved work.
