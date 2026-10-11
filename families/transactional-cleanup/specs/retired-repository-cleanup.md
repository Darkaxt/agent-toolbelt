# Explicit Legacy Repository Retirement

## Authoritative Contract

Add retirement of an exact obsolete standalone checkout outside Temp without
weakening ordinary tracked-file protection or the Temp-only validation-clone mode.
This task implements and deploys the capability; it does not delete a real checkout
whose deletion an execution tool previously rejected. No policy bypass is provided.

- R1: Require kind `retired-repository`, `--regenerated`, an external JSON retirement
  evidence file, and `--confirm-retire-repository` matching the exact scan root.
  Reject the transaction workspace and its ancestors/descendants, protected roots,
  redirected roots, linked worktrees, submodules and additional worktrees.
- R2: Require a clean source checkout, including untracked and ignored files.
  Preserve local work by verifying every ref, HEAD and reflog-reachable commit
  against an independent existing bare recovery repository. Require complete Git
  object integrity, no alternates/shallow storage and a documented recovery command.
  Do not create a recovery copy automatically or claim remote tracking refs prove
  that commits are actually published.
- R3: Require recorded user authorization, ownership/scheduler/service/dependency
  checks and a declaration of no remaining consumers. Inspect visible process
  command lines at register, review and apply. Unknown external consumers remain
  the owner's responsibility; do not claim universal process detection or acquire
  the Gradle execution gate for cleanup.
- R4: Freeze repository identity, Git/recovery proof and evidence into the signed
  review. Revalidate before first destructive application; retries tolerate already
  removed Git metadata but still verify root identity, recovery and process state.
  New files survive. Hash retired regular files and compare through the exclusive
  deletion handle so same-identity edits survive too. Never recursively delete.
- R5: Keep old snapshots/tickets and all ordinary protections compatible. Provide
  distinct actionable failure kinds, focused regressions, installed smoke proof,
  deployment to Codex/agents/Claude, GitHub sync and a scoped notification.
- R6: Report helper state inventory and support explicitly discarding unissued
  open/reviewed transactions with a reason. Preserve active operations and issued
  tickets. Compact discarded inventories without deleting any target files.
  Support authenticated legacy open snapshots using bounded reads, not another
  in-memory copy of their huge inventories. Never prune based on age alone.
- R7: Require task scratch under D:/Temp or E:/Temp, including disposable clones,
  evidence staging and tool-configurable temporary directories. Keep maintained
  repositories and intentional deliverables in their actual locations. Do not
  relocate existing source or block attributable cleanup outside Temp. Explicitly
  close or discard abandoned snapshots when a task finishes or changes strategy.

## Evidence Schema

`version: 1`, `repository` (exact absolute root), `authorization` (explicit user
request), `recovery_repository` (external existing bare repo),
`recovery_instructions`, and `consumer_review` containing `checked_at`,
`ownership`, `schedulers_services`, `dependencies` (nonempty review descriptions),
and `active_consumers` (an empty list). Keep the evidence outside the retired root.
These are owner attestations, not automatically verified truth. The helper also
performs the concrete Git, identity, integrity and visible-process checks above.

## Stages

1. Contract, helper, guidance and regression verification (R1-R4, R6, R7): COMPLETE.
2. Documentation, installed verification, deployment and notification (R5, R7):
   COMPLETE.

GitHub integration is the required final delivery step after verified stage
closure, not an implementation stage. Completion of this task additionally
requires the reviewed changes on origin/main and a clean synchronized checkout;
a local commit or feature-branch push is not final delivery evidence.

Stage 1 evidence: retirement regressions cover exact authority, dirty/untracked/
ignored work, recovery completeness and pruning anchors, dependent worktrees,
consumer refusal, post-review changes, concurrent files and same-identity edits.
State regressions cover open/reviewed compaction, physical SQLite shrinkage,
issued-ticket preservation, live ownership and bounded authenticated legacy reads.
The installed-runtime fixture verifies real process inspection, deletion of only
test-owned repositories, recovery cloning and unissued discard. The root wiring
checks and skills.sh validation pass. No stage blockers or tracked deferrals remain.

Stage 2 evidence: v0.5.0 installed in Codex, agents and Claude with identical skill
content, valid structure and no deployment residuals. Morphe Extended was notified
with the exact retirement and scratch-placement procedure and asked to validate it.
No real obsolete checkout was deleted. Six explicitly selected superseded unissued
snapshots were compacted without target-file deletion; observed helper state fell
from 2.44 GB to about 0.70 GB while unrelated cleanup jobs continued. Issued tickets
and partial manifests were preserved. The one leftover task-owned failed-test
fixture was removed through a reviewed exact-file ticket.

## Discovery

Public scout inspected a generic Git workflow skill, not a matching exact-file
retirement implementation. Results were capped and partially unavailable (503);
they do not establish that no alternative exists. Extend the installed local
ticket mechanism rather than replace it with that unrelated Git guidance.
