---
name: spec-gated-implementation
description: Use for non-trivial implementation work that must start from a specification, proceed through a compact staged plan, reuse existing user authorization, reconcile every stage against the specification, and close all blockers and tracked deferrals before completion.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Instruction-only workflow for Codex, Claude, and other agents that can maintain project documents and run verification.
---

# Specification-Gated Implementation

Keep the authoritative specification, not the staged plan, as the source of truth throughout implementation.

Skip this workflow for trivial one-step edits or purely read-only investigation. Use it for features, projects, migrations, and other multi-stage implementation where omissions can accumulate between stages.

## 1. Establish The Specification

Create or identify one authoritative specification document before implementation. Follow the repository's documentation conventions when they exist.

The specification must contain clear requirements and acceptance criteria. Give non-trivial requirements stable identifiers when that improves traceability.

Do not silently weaken, reinterpret, or remove a requirement. Only an explicit user decision can revise the specification.

## 2. Derive A Compact Staged Plan

Create a simplified staged plan from the specification. For each stage, record:

- objective;
- specification requirements covered;
- intended changes and dependencies;
- verification evidence required.

Map every specification requirement to a stage. An unassigned requirement is a planning blocker.

Keep a cumulative reconciliation ledger in the plan or a nearby status artifact. It must show satisfied requirements, blockers, tracked deferrals, and verification evidence for each stage.

## 3. Reuse Existing Authorization

Review the current task history before asking for implementation approval.

- If the user already said to implement, proceed, go ahead, execute the plan, or create the specification and carry out the work, record the scope as `already_authorized` and continue.
- Authorization may have been given before the specification was written. It remains valid for the same scope.
- A request only to assess, review, design, or write a specification is not implementation authorization.
- If authorization is absent, stop after the specification and plan and ask once.
- Never ask again for the same approved scope. Ask only when a material scope or authority change is required.

## 4. Run The Stage Loop

For every stage:

1. Implement only the planned stage scope.
2. Run fresh stage verification.
3. Re-read the authoritative specification, not only the plan.
4. Compare the delivered behavior and evidence with every applicable requirement.
5. Update the reconciliation ledger.
6. Classify every gap as a `blocker` or `tracked_deferral`.
7. Resolve all blockers, rerun verification, and reconcile again before advancing.
8. Implement any deferral required by the next stage before starting that stage.

Do not pass a stage merely because its tasks were checked off. The stage passes only when the specification comparison supports it.

## 5. Classify Gaps Correctly

### Blocker

A blocker is any of the following:

- required behavior is missing;
- an acceptance criterion or verification fails;
- the stage introduces a regression or safety issue;
- a later stage depends on the missing work.

Blockers must be fixed before advancing.

### Tracked Deferral

A `tracked_deferral` is required work that does not block the current stage. Record its exact requirement, reason, destination stage, and verification method.

Deferral changes scheduling only. It does not remove the requirement and it is not an acceptable final state. Implement it before a dependent stage or in the mandatory final-remediation stage.

If the work cannot be implemented, keep the plan incomplete unless the user explicitly revises the specification. Reclassifying required work as "out of scope" without that decision is prohibited.

## 6. Complete Only At Zero

Before claiming the plan complete:

1. Run a final-remediation stage for every remaining tracked deferral.
2. Re-read and reconcile the full specification.
3. Confirm `blockers = 0` and `tracked_deferrals = 0`.
4. Run fresh end-to-end verification.
5. Report implementation evidence and any explicit user-approved specification revisions.

Only then follow the repository's commit, deploy, release, and sync requirements. "Tracked for later" is not completion.

## Related Skills

- Use brainstorming when requirements or product direction are still ambiguous.
- Use writing-plans when the user needs a detailed task-by-task implementation plan; this skill still requires stage reconciliation.
- Use systematic-debugging for unexpected behavior or failing verification.
- Use verification-before-completion before any success claim.
