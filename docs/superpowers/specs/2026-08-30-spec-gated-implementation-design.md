# Specification-Gated Implementation Skill

## Purpose

Create a lightweight instruction-only skill that makes non-trivial implementation work follow a specification through every stage instead of treating the initial plan as the lasting source of truth.

The skill must work for both Codex and Claude and remain useful across repositories without requiring a helper process, database, or project-specific file layout.

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

1. Run fresh stage verification.
2. Re-read the authoritative specification, not only the plan.
3. Compare delivered behavior and evidence with every applicable requirement.
4. Record satisfied requirements and every remaining gap.
5. Classify each gap as a blocker or `tracked_deferral`.

### SGI-5: Blocker Closure

A blocker is a missing required feature, failed acceptance criterion, regression, safety failure, or unmet dependency for later work. Resolve all blockers and repeat verification and specification comparison before advancing.

### SGI-6: Deferral Is Scheduling Only

A `tracked_deferral` is required work that does not block the current stage. It must have a specific later stage or mandatory final-remediation target.

Tracked deferrals must be implemented before a dependent stage or during final remediation. They are not completion exemptions. Completion requires zero blockers and zero tracked deferrals.

If required work cannot be implemented, the plan remains incomplete unless the user explicitly changes or removes that requirement from the specification. Agents may not silently downgrade the specification.

### SGI-7: Completion Gate

Before declaring completion:

1. Execute a mandatory final-remediation stage if any deferral remains.
2. Re-read and reconcile the full specification.
3. Confirm zero blockers and zero tracked deferrals.
4. Run fresh end-to-end verification.
5. Report the evidence and any explicit user-approved specification revisions.

Commit, deploy, release, or sync according to the repository and user instructions only after this gate passes.

### SGI-8: Lightweight Integration

The skill should compose with existing discovery, brainstorming, planning, debugging, and verification skills. It must not duplicate their detailed methods or require a runtime package.

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
