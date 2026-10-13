# Specification-Gated Implementation Plan

Authoritative specification: `docs/superpowers/specs/2026-08-30-spec-gated-implementation-design.md`

Implementation authorization was already provided when the user asked to implement and deploy the approved skill design. No additional confirmation is required for this scope.

## 2026-10-13 Revision Plan

The original implementation record below is historical. The current authorized
revision follows the updated specification, SGI-1 through SGI-11.

| Stage | Status | Scope and acceptance | Evidence |
| --- | --- | --- | --- |
| R1 | COMPLETE | Correct canonical skill, local AGENTS.md and focused contract tests; keep two gap categories, feature-complete validation and applicable evidence reuse. | Focused instruction contracts, family isolation/layout and canonical structural validation passed. |
| R2 | COMPLETE | Second consistency review; validate/deploy identical Codex, agents and Claude skill copies; notify ROMs Manager to reread. | Canonical and three installed copies validated and byte-matched; all 43 AGENTS.md sections preserved; local skills.sh discovery lists this skill once; notification sent. |

No required deferrals. The local AGENTS.md is private instruction text, not a
public source bundle; do not publish it or change application settings.

Required delivery after stage closure: commit and sync through the repository's
required PR/check/merge path. Verify local main against remote main before the
overall completion report; a local commit alone does not finish this task.

### Second Consistency Review

- Implementable missing acceptance work blocks advancement but keeps execution ACTIVE.
- Genuine parking does not pass acceptance or unblock dependent work; one ACTIVE stage remains the limit.
- A named deferral cannot excuse a current-stage requirement or survive final completion; no empty remediation stage is required.
- Feature validation follows complete wiring/integration. Correctness is established by validation, not assumed beforehand; failed validation returns the same feature to implementation.
- Diagnostic feedback cannot be relabeled into micro-validation; acceptance units cannot be shrunk to incomplete components. Complete specified non-feature outcomes remain supported.
- Applicable inspected evidence may be reused; missing/invalidated or explicitly required checks must run. Required safety/integration/recovery verification remains mandatory.
- Intermediate commit authority, explicit delivery authorization and instruction precedence remain intact. Configuration hashes stayed unchanged.

Review scope is instruction consistency and distribution. Contract tests verify
wording, not guaranteed future model compliance. The ROMs Manager notice requests
an explicit reread; sending it is not proof that the task has followed the update.

## Original Implementation Record

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
| 3 | passed | All requirements and acceptance criteria | 0 | 0 | Both installed copies validated and byte-matched canonical files; 40 root tests and skills.sh validation passed. |

The plan cannot be marked complete while either the Blockers or Tracked deferrals column contains unresolved work.

## Final Reconciliation

The authoritative specification was re-read after installation and validation. SGI-1 through SGI-8 and every acceptance criterion are satisfied. There are zero blockers and zero tracked deferrals. Repository synchronization is the remaining delivery action, not deferred implementation work.
