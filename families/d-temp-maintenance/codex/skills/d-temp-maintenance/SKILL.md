---
name: d-temp-maintenance
description: Maintain D:/Temp agent-generated leftovers through owner-aware review and verified cleanup. Use for LLM temporary clones, worktrees, build trees, captures and downloads accumulating on D drive; not general drive cleanup or age-based purging.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows; installed transactional-cleanup for deletion. Everything and existing task-owner tools improve discovery. Same instructions for Codex and Claude.
---

# D-Temp Maintenance

Operate on demand on **D:/Temp**, or the user's explicitly selected temporary root.
Do not create a monitor or schedule. Maintenance authorization covers verified
disposable leftovers, not everything beneath a directory named Temp. When asked
to execute maintenance, clean actionable targets rather than returning only sizes.
Creating/installing this skill alone is not authorization to purge existing data.

## Discover Without Repeating The Expensive Scan

1. Measure D-drive free bytes and enumerate the root's immediate children. Include
   loose files, not only directories. Do not follow reparse points. Keep the run's
   private ledger and receipts **outside** the root being cleaned and outside Git;
   use [references/ledger.md](references/ledger.md).
2. Prefer Everything's indexed path/size evidence or a supplied RidNacs export to
   rank candidates. Confirm the actual backend, cap and live path existence.
   Indexed/export sizes are estimates; parent sizes include children. Use a
   bounded live traversal of selected directories if indexed evidence is absent,
   and label unreadable/linked/unknown coverage. Never hash all Temp for ranking.
3. For the largest actionable roots, resolve the creating task/command, project,
   current consumers and whether the output is reproducible. Check live processes,
   existing task state, Git status/branches/worktrees and helper transactions as
   applicable. Read only targeted history; do not import every conversation.
   Age, a familiar LLM filename, no process match, or clean Git status alone do
   not establish inactivity, ownership or expendability.
4. Classify the exact target with [references/actions.md](references/actions.md).
   Separate safe output children from retained source/input/toolchain children;
   an active project does not protect unrelated independently verified leftovers.
   Likewise a disposable output does not make its containing repository disposable.

## Act On Verified Targets

Read transactional-cleanup and use its installed wrapper from the current agent's
personal skill root. Do not depend on a repository-relative wrapper or invent a
second deletion mechanism. Every snapshot must use repeated explicit `--scan-root`
for selected outputs; registration alone does not narrow the scan.

For ordinary pre-existing generated output, use the begin/register/review/inspect/
ticket/apply route in the action reference. Verify provenance before using
`--regenerated`. Disposable validation repositories and leaf link names require
their separate helper contracts. Linked worktrees use Git lifecycle only after
source-retention and consumer checks; never force removal or convert links to
ordinary files merely to get deletion accepted.

Recheck consumers and preservation evidence before application. New files are not
swept into an old ticket. Wait for actual helper completion; a yielded command or
slow review is not an excuse to skip the operation. Use lock-free status for real
progress. Inspect existing reviewed manifests instead of repeatedly hashing them.
Resolve partial results through the same valid ticket after the concrete lock or
ACL condition is resolved. Diagnose database errors rather than blind retries.
Preserve IDs and residual paths; do not auto-revoke or bypass policy rejection.

Cleanup **must not acquire the Gradle build mutex or join its queue**, even for
build output. Use exact-target cleanup coordination and current consumer evidence.
Gradle execution, if genuinely required by an owner, uses gradle-build-gate; never
launch a build just to justify cleanup or interrupt another build for clearance.

## Ownership And Recurrence

For project-wide litter whose owning task is still working, prefer an **end-of-round
owner sweep**: [references/owner-sweep.md](references/owner-sweep.md). The owner
finishes its specified current round, preserves required source changes in the
authoritative GitHub repository, then reviews all attributable temporary roots
and removes expendable leftovers. Do not limit its sweep to the current checkout
or leave reproducible clones merely because they contain tracked files. Reconcile
any retained folders with a concrete reason; do not silently exempt all source.

If owner evidence is needed, identify the actual existing task and exact path.
Send one bounded request for retention/consumer status or owner cleanup, not a
broadcast, a new task, or a request to resume unrelated implementation. Record
dispatch and inspect the result. Inactive tasks may still own valuable unpushed
work. Unknown owners remain `needs_evidence`, not assumed disposable.

For future work, register expected output roots before creation and clean them at
task/stage completion when expendable. Keep source and output separate. Promote
intentionally persistent dependencies to an appropriate stable location only
within explicit relocation authority, updating/verifying real consumers first.
Do not move the same litter to another folder or create purposeless backups.

Close the run with exact actions/bytes, preserved paths and reasons, unresolved
owner actions or residuals, and fresh free space. Distinguish logical deleted bytes
from volume change during concurrent work. Preserve a ledger for any partial run;
do not report a ticket, dry run or sent owner request as completed cleanup.
