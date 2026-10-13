# Specification-Gated Implementation Skill

## Purpose

Create a lightweight instruction-only skill that makes non-trivial implementation work follow a specification through every stage instead of treating the initial plan as the lasting source of truth.

The skill must work for both Codex and Claude and remain useful across repositories without requiring a helper process, database, or project-specific file layout.

## Authorized 2026-10-13 Revision

The user approved correcting the skill and local Codex AGENTS.md together, followed
by a second consistency review, installed parity validation and repository sync.
Retain exactly two categories for missing required work: advancement blockers and
tracked deferrals. A blocker does not by itself mean execution is impossible or
the stage status is BLOCKED. Preserve the standing single-ACTIVE-stage, justified
parking, authorization, data-protection and delivery boundaries. Change instruction
text and skill distribution only; do not change application configuration.

## Requirements

### SGI-1: Specification First

Before implementation, create or identify one authoritative specification document. The specification must state the requested behavior and acceptance criteria clearly enough to detect omissions later.

### SGI-2: Compact Staged Plan

Derive a simplified staged plan from the specification. Every specification requirement must be assigned to at least one stage or the plan is incomplete.

The plan should stay compact: stage objective, mapped requirements, intended changes, dependencies, and verification evidence. It must not expand into low-value document ceremony.

### SGI-3: Authorization Reuse

Determine whether the user already authorized implementation in the current task, including authorization given before the specification request. Phrases such as "implement this plan," "go ahead," or an explicit request to create the specification and carry out the work count for the stated scope.

If implementation is not already authorized, stop after the specification and plan and ask once for confirmation. Do not ask again for the same approved scope.

### SGI-4: Stage Reconciliation

After every stage:

1. Inspect verification applicable to the current implementation; run affected
   checks when evidence is absent, invalidated or an applicable rule requires it.
2. Re-read the authoritative specification, not only the plan.
3. Compare delivered behavior and evidence with every applicable requirement.
4. Record satisfied requirements and every remaining gap.
5. Classify each gap as a blocker or `tracked_deferral`.

### SGI-5: Blocker Closure

A blocker is missing required work or a defect that prevents current-stage
acceptance, required integration or verification, or an assigned dependency from
passing. It prevents stage completion and ordinary advancement, not further
implementation within that stage. Implementable gaps keep the stage ACTIVE.
Reserve BLOCKED status for an identified condition that genuinely prevents further
progress, with a resolution condition. Respect standing parking/dependency rules;
parking never satisfies the blocked criteria or permits dependent work to pass.
Resolve advancement blockers and reconcile before advancing, rerunning only
verification whose evidence is missing or invalidated.

### SGI-6: Deferral Is Scheduling Only

A `tracked_deferral` is required work assigned to a specifically named later stage,
with a reason and verification method, that does not affect current-stage acceptance.

Tracked deferrals must be implemented in their named stage, before a dependent
stage or final completion. They are not completion exemptions. Completion requires
zero blockers and zero tracked deferrals. Add a named remediation stage only when
real remaining work needs one; never require an empty ceremony stage.

If required work cannot be implemented, the plan remains incomplete unless the user explicitly changes or removes that requirement from the specification. Agents may not silently downgrade the specification.

### SGI-7: Completion Gate

Before declaring completion:

1. Complete every remaining required item in its assigned stage or a justified,
   named remediation stage; no empty remediation stage is required.
2. Re-read and reconcile the full specification.
3. Confirm zero blockers and zero tracked deferrals.
4. Inspect applicable end-to-end evidence; run required checks if evidence is
   absent or invalidated. A full-suite rerun is risk/requirement-driven, not automatic.
5. Report the evidence and any explicit user-approved specification revisions.

Final completion claims and delivery require this gate. Intermediate commits
remain governed by standing instructions and do not imply feature validation or
stage closure. Deployment, release and sync require their actual authorization.

### SGI-8: Lightweight Integration

The skill should compose with existing discovery, brainstorming, planning, debugging, and verification skills. It must not duplicate their detailed methods or require a runtime package.

### SGI-9: Cohesive Stage Closure

Prefer cohesive patches that close a real workflow over isolated component
edit/test/report cycles. Prove the narrowest required integrated path, then finish
its remaining criteria. Patch size means coherent scope, not a line quota or
permission to mix stages. Do not pursue speculative optimizations, abstractions,
optional edge cases or redundant verification while required integration waits.

User clarification: formal validation applies only to fully implemented features
as defined by the authoritative specification/current-stage criteria, not to
micro-implementations. Required wiring, user behavior and integration must exist
before acceptance validation begins. Diagnostic/test-first feedback during work
is not feature validation and must not become repeated component build/device/
report ceremonies. Do not rename an incomplete component a feature or vertical
slice to bypass this boundary; required verification still follows implementation.
For non-feature tasks use the complete specified outcome. Implementation complete
means required paths are present/integrated, not already proven correct; validation
determines correctness. Failed validation returns the same feature to implementation.
Interim diagnostics must answer a concrete question, not relabel micro-validation.

### SGI-10: Evidence Reuse And Compact Records

Batch related edits when useful. Preserve meaningful test-first reproductions and
diagnostics. Reuse inspected current-task results only when relevant code, config,
environment, dependencies and integration conditions are unchanged and no applicable
requirement mandates a new run. Otherwise rerun affected checks; do not skip required
verification. Update one current reconciliation ledger at meaningful checkpoints,
not a new document or build after each small edit.

### SGI-11: Precedence And Existing Tasks

The skill supplies reconciliation techniques and does not override applicable
standing instructions, authorize releases or add approvals/delegation. Existing
tasks must explicitly reread changed guidance before relying on it; file deployment
alone is not proof that an active task has loaded or followed the new wording.

## Non-Goals

- Replacing project-specific specifications or test plans.
- Requiring a fixed filename or documentation directory in every repository.
- Treating every typo or trivial one-step maintenance edit as a staged project.
- Allowing "documented for later" to mean "finished."

## Distribution

Keep one canonical public skill under `families/spec-gated-implementation/codex/skills/spec-gated-implementation`. Install that same skill directory into the active Codex and Claude-compatible personal skill roots. Do not maintain divergent Codex and Claude instruction copies.

## Acceptance Criteria

- The skill validator accepts the canonical and installed copies.
- Repository tests assert authorization reuse, repeated specification reconciliation, blocker closure, and zero-deferral completion.
- Local skills.sh discovery lists the skill exactly once.
- Codex and Claude installations byte-match the canonical skill files.
- No runtime package, account state, credentials, or machine-specific paths are included.
- Review the revised skill and local AGENTS.md against each other, including
  implementable blockers, genuine parking, named deferrals, invalidated evidence,
  required safety/integration checks and zero-deferral completion.
