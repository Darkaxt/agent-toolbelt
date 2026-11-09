# Exact Android Download task-directory cleanup

Authority: maintenance of the reported transactional-cleanup failure in Skill
Creator. This fixes the existing A3 exact-task-directory contract; it does not
authorize deleting the reported phone folders, messaging their owner, or using
Files as an alternate deletion mechanism.

## Required behavior

- D1: Keep existing top-level task directories supported and admit one exact
  task-owned immediate child of `/storage/emulated/0/Download`. Reject Download
  itself, other standard user-data roots, protected task-root names, nested
  root selections, traversal and aliases. Inventory remains confined to the
  selected task directory; no shared-directory inventory or wildcard selection.
- D2: Bind the shared Download parent's ordinary-directory identity at review
  and recheck it after inventory and before each apply member. Preserve the
  existing endpoint, target-root, internal ancestry, link, content, signed-ticket,
  new/changed member, retry and package-removal protections. Never ticket the
  shared Download parent or unrelated sibling files.
- D3: Explain the supported exact-root form and the distinction between a
  helper capability rejection and an actual command-policy denial. Existing
  task cleanup authority does not need a new Files/helper-rule override after
  this supported flow exists. Actual policy denials must never be bypassed.
- D4: Verify the coherent Android flow and host regressions, commit the change,
  release a versioned local package and validate installed runtime/skill parity
  for Codex, shared agents and Claude. Use isolated fixtures; no live phone
  cleanup is authorized by this maintenance report.

## Stages

| Stage | Status | Acceptance |
| --- | --- | --- |
| Correct exact-root flow and guidance | COMPLETE | D1-D3 implemented and verified through complete ticket flows, sibling/new/changed content preservation, parent replacement and protected-root cases. |
| Release and verify installed delivery | COMPLETE | D4 family regressions, committed versioned local release, installed parity and installed-runtime behavior verified. |

D1-D3 verified: the complete Android test suite passes (one Windows-inapplicable
POSIX symlink case skipped); generated shell unlink/quoting checks also pass.
Exact Download-root and sibling preservation, changed/new files and retries,
parent replacement before/during review/apply, broad roots and aliases are
covered. Both source references agree. No new architecture or refactoring is needed.

Delivery verification: full family regression suite passed (156 checks, one
Windows-inapplicable POSIX skip). Local release 0.7.2 was built from committed
source 046edbb and independently reopened; every archive member and its digest
match. The activated shared runtime and full installed Codex/agents/Claude skill
bundles match that release, and all installed skills validate. The complete
Android suite also passed against the activated runtime (27 checks, the same
POSIX skip), exercising the exact reported Download path without accessing the
phone. Installed CLI help exposes the supported ticket flow. Deployment left
no residual files; existing legacy recovery state remains preserved.

The local release is `D:/Tools/transactional-cleanup/releases/0.7.2/`. No remote
publication, live phone cleanup or owner-thread message occurred. Existing
callers must reread the installed Android reference before using the new flow.
D1-D4 are verified; no blockers or tracked deferrals remain. The narrow path
validation and parent proof reuse existing ticket/transport mechanisms, with
no further refactoring required.
