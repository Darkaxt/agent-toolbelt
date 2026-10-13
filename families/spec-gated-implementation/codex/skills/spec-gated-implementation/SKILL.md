---
name: spec-gated-implementation
description: Use for non-trivial implementation work that must start from a specification, proceed through a compact staged plan, reuse existing user authorization, reconcile every stage against the specification, and close all blockers and tracked deferrals before completion.
license: MIT
metadata:
  version: "0.3.0"
  compatibility: Instruction-only workflow for Codex, Claude, and other agents that can maintain project documents and run verification.
---

# Specification-Gated Implementation

Keep the authoritative specification, not the staged plan, as the source of truth throughout implementation.

Skip this workflow for trivial one-step edits or purely read-only investigation. Use it for features, projects, migrations, and other multi-stage implementation where omissions can accumulate between stages.

Applicable standing instructions govern authority, stage statuses, parking and
delivery. This skill supplies reconciliation techniques, not permission to add
approvals, delegation, release authority or new scope.

## 1. Establish The Specification

Create or identify one authoritative specification document before implementation. Follow the repository's documentation conventions when they exist.

The specification must contain clear requirements and acceptance criteria. Give non-trivial requirements stable identifiers when that improves traceability.

Do not silently weaken, reinterpret, or remove a requirement. Only an explicit user decision can revise the specification's required behavior or scope, subject to higher-priority constraints. Ordinary wording corrections that preserve requirements do not require new approval.

## 2. Derive A Compact Staged Plan

Create a simplified staged plan from the specification. For each stage, record:

- objective;
- specification requirements covered;
- intended changes and dependencies;
- verification evidence required.

Map every specification requirement to a stage. An unassigned requirement is a planning blocker.

Use complete specification-defined features as acceptance units, or complete
specified outcomes for non-feature work. Do not split one coherent feature into
component-only validation stages. If existing stage boundaries conflict with the
specification, reconcile them without weakening criteria or pulling unrelated
later-stage scope into the current stage.

Keep a cumulative reconciliation ledger in the plan or a nearby status artifact. It must show satisfied requirements, blockers, tracked deferrals, and verification evidence for each stage.

Use the existing ledger's concise current state at meaningful integration
checkpoints. Do not create a new document, artificial stage or checkpoint report
for each component or small edit.

## 3. Reuse Existing Authorization

Review the current task history before asking for implementation approval.

- If the user already said to implement, proceed, go ahead, execute the plan, or create the specification and carry out the work, record the scope as `already_authorized` and continue.
- Authorization may have been given before the specification was written. It remains valid for the same scope.
- A request only to assess, review, design, or write a specification is not implementation authorization.
- If authorization is absent, stop after the specification and plan and ask once.
- Never ask again for the same approved scope. Ask only when a material scope or authority change is required.

## 4. Run The Stage Loop

For every stage:

1. Implement only the planned stage scope, with at most one ACTIVE stage.
2. Prioritize the narrowest required integrated workflow and its remaining acceptance criteria.
3. Validate fully implemented features against their assigned acceptance criteria; inspect applicable evidence and run affected checks when evidence is missing or invalidated, or an explicit requirement mandates a new run.
4. Re-read the authoritative specification, not only the plan.
5. Compare the delivered behavior and evidence with every applicable requirement.
6. Update the reconciliation ledger and classify every required gap as a `blocker` or `tracked_deferral`.
7. Resolve all blockers, rerun verification where needed, and reconcile again before ordinary advancement.
8. Complete deferrals in their assigned stages, before dependent work needs them.
9. Perform the stage-closure refactoring assessment below before ordinary advancement; resolve any current-acceptance finding within the current stage.

Do not pass a stage merely because its tasks were checked off. The stage passes only when the specification comparison supports it.

### Cohesive Implementation And Verification

Formal validation is feature-complete only. Implement the specification-defined
feature's required behavior, wiring and integration before acceptance validation.
Do not validate micro-implementations as checkpoints or rename an incomplete
component a feature or vertical slice to bypass this rule. A narrow vertical
slice qualifies only when it fully implements a feature already defined by the
specification/current-stage criteria; missing parts remain advancement blockers.
Implementation complete means the required paths are present and integrated,
not that correctness has already been proven. Validation determines correctness;
a failed check returns the same feature to implementation and affected revalidation.

Prefer cohesive patches over fragmented micro-implementations and repeated
edit/test/report cycles. Cohesive means one meaningful integrated outcome, not a
line-count quota or permission to mix stages or unrelated changes. Once a real
vertical slice works, close the remaining stage criteria rather than repeatedly
reopening verified parts. Avoid speculative micro-optimizations, abstractions and
optional edge-case work while required integration remains unfinished.

Batch related edits when practical, without suppressing meaningful test-first
reproductions or necessary diagnostics. Diagnostic feedback is not feature
validation, stage acceptance or a completion claim. It must not become repeated
component build/device/report ceremonies. Use the smallest credible affected checks.
An interim diagnostic must answer a concrete implementation question; do not
relabel micro-validation as diagnostics to evade the feature-complete boundary.
Reuse inspected current-task results only when relevant code, configuration,
environment, dependencies and integration conditions are unchanged and no
applicable requirement mandates a new run. Otherwise rerun affected checks.
Stage closure, a new report or a commit alone does not invalidate evidence or
require the full suite. Broaden checks when risk or an explicit requirement
requires it. Required integration and recovery checks must not be skipped to
make a patch appear efficient.

### Stage-Closure Refactoring Assessment

After a stage is fully implemented and verified, assess accumulated design debt
once at its closure boundary, and once at final reconciliation. This is a
lightweight assessment, not automatic refactoring. Reuse an unchanged assessment
at final reconciliation; do not repeat an audit or create a new report merely
because the stage or task is closing. Record evidence and the scheduling decision
in the existing reconciliation ledger. No material finding means advance normally
without a consolidation stage.

Limit inspection to the implemented scope and known upcoming dependencies. Look
for duplicated business logic, stacked workarounds, conflicting state ownership,
obsolete implementation paths, or complexity demonstrably obstructing a required
integration. Cite the concrete behavior/code and maintenance burden or dependency
risk, not merely a preference for cleaner-looking code. Assessment does not authorize
scope expansion: refactoring must serve an existing specification requirement or
explicitly authorized maintenance. Optional opportunities are not missing required
work; do not turn them into mandatory tracked deferrals or silently add requirements.

Fixes necessary for current acceptance remain current-stage blockers: keep the
stage ACTIVE and resolve/reverify them before completion. Required consolidation
that current acceptance does not depend on may belong to a named later stage
under the existing deferral rules, before its dependent work and before overall
completion. Preserve the one ACTIVE stage limit and actual prerequisites. Do not
use consolidation to escape unfinished work or casually reopen completed stages
for cosmetic polishing. A genuine regression still requires affected reconciliation.

Schedule a bounded consolidation stage only when material evidence and existing
authority justify it. Batch related debt rather than refactoring after every
stage. Specify the problems, affected components, requirement/authority basis,
preserved behavior and safety/recovery contracts, observable acceptance criteria,
and verification of affected complete workflows. Examples of outcomes are one
authoritative state owner or removal of a proven obsolete path, not a line-count
or abstraction-count target. Stop when its acceptance criteria pass; do not expand
into another improvement hunt. No numerical cadence or periodic rewrites. Do not
add speculative abstractions or new features; performance work requires evidence
of a relevant bottleneck and existing authorization, or an explicit requirement.

Verify the complete consolidation outcome, not each internal edit. Do not validate
individual cleanup edits as checkpoints. Revalidate affected complete workflows
and update invalidated evidence in the ledger; reuse unaffected applicable evidence.
There are no unrelated full-suite reruns or new approval/delegation requirements.

## 5. Classify Gaps Correctly

### Blocker

Missing required work has exactly two categories: advancement blockers and
tracked deferrals. Do not introduce an unclassified unfinished-work bucket.

A blocker is missing work or a defect that prevents:

- a current-stage acceptance criterion from passing;
- required integration or verification from passing;
- resolution of a regression or safety failure in the current stage;
- an assigned prerequisite for dependent work from being satisfied.

A blocker blocks stage completion and ordinary advancement; it does not stop
implementation inside the stage. Implementable gaps keep the stage ACTIVE.
Blockers must be fixed before advancing, except for an explicitly justified
BLOCKED-stage parking transition under standing parking and dependency rules.

BLOCKED status requires an identified condition that cannot presently be resolved,
not merely unfinished, slow or difficult work. Record the affected criterion,
reason, internal/external cause, resolution condition and dependent work.
Parking is not completion: retain every criterion and resume when actionable.
Do not start dependent work whose prerequisite is unresolved. Keep at most one
ACTIVE stage, including after parking.

### Tracked Deferral

A `tracked_deferral` is required work assigned to a specifically named later stage.
Record its exact requirement, reason, destination stage, and verification method.
It is valid only when current-stage acceptance criteria do not depend on it and
the move preserves the specification, integration and verification requirements.
Otherwise it is an advancement blocker, not a deferral.

Deferral changes scheduling only. All required tracked deferrals must be
implemented in their assigned stage, before dependent work or final completion.
If real remaining work needs a named remediation stage, add one without opening
concurrent stages or weakening acceptance. No empty remediation stage is required.

If the work cannot be implemented, keep the plan incomplete unless the user explicitly revises the specification. Reclassifying required work as "out of scope" without that decision is prohibited.

## 6. Complete Only At Zero

Before claiming the plan complete:

1. Complete every required blocker and tracked deferral in its assigned stage or a justified named remediation stage.
2. Re-read and reconcile the full specification.
3. Confirm `blockers = 0` and `tracked_deferrals = 0`.
4. Inspect end-to-end evidence applicable to the integrated result; run checks where evidence is missing or invalidated or an applicable requirement mandates them.
5. Perform the final refactoring assessment above, reusing unchanged stage-closure evidence; resolve any required finding under the same blocker/deferral rules, then repeat zero-gap reconciliation and affected verification.
6. Report implementation evidence and any explicit user-approved specification revisions.

Final completion claims and delivery require this gate. Intermediate commits
remain allowed when applicable instructions permit them; they do not validate
an incomplete feature or close a stage. Deployment, release and sync follow their
actual authorization and repository requirements. "Tracked for later" is not completion.

For an existing task after instruction updates, explicitly reread the current
standing instructions and installed skill before continuing under the changed
wording. Successful deployment is not proof that an active task has loaded or
followed those instructions. Preserve its existing scope, authorization and work.

## Related Skills

- Use brainstorming when requirements or product direction are still ambiguous.
- Use writing-plans when the user needs a detailed task-by-task implementation plan; this skill still requires stage reconciliation.
- Use systematic-debugging for unexpected behavior or failing verification.
- Use verification-before-completion before any success claim.
