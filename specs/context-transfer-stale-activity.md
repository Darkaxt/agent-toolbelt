# Context Transfer Stale Activity Reconciliation

## Authoritative Scope

Implement a read-only reconciliation path for stale spawn-edge records. A recorded
open child is not proof of a running worker. Age, lack of recent writes, archived
flags, API errors and absence from a partial listing are not inactivity proof.
This task updates/deploys the helper and verifies synthetic retirement gates; it
does not retire, delete, restore or rewrite the referenced real task.

## Requirements

- Add `reconcile-activity --manifest --activity-evidence [--output]`.
- Evidence is a metadata-only sidecar from supported Codex task APIs, bound by
  SHA-256 to the exact inspection manifest and both task IDs. Each source/child
  observation identifies its local host, status, tool and observation timestamp.
- Only explicit idle/notLoaded or terminal statuses establish inactivity.
  Active/running/pending/waiting/unknown or missing observations block retirement.
  Check the source as well as every descendant, including recorded closed edges.
- Preserve recorded edges; report stale-inactive children separately. Never
  change SQLite or claim that a stale edge was actually closed.
- Bind reconciliation to exact task-tree metadata and rollout file identities.
  Recheck current metadata and file identities before reconciliation/pack; never
  use arbitrary deadlines or sleeps. Existing archive/acceptance/deletion gates
  remain required. Missing rollout content cannot be excused by inactivity.
- Preserve verified resumed segments including the source-id_resume-id filename
  form observed in the live database; ownership still requires session_meta.
- Refresh installed Codex skill/runtime; verify and sync the completed patch.

## Stages And Acceptance

1. COMPLETE: add evidence-bound reconciliation, CLI routing and regression fixtures.
   Prove stale open children can pass with complete inactive evidence, live/unknown
   source or children cannot pass, and mismatched/changed evidence fails closed.
2. COMPLETE: integrate pack revalidation and resumed filenames, update guidance;
   prove packaging still rejects missing files and changed task state.
3. COMPLETE: focused integration/skill validation, installed-runtime parity,
   commit and required GitHub sync. No unresolved blockers or tracked deferrals.

## Live Investigation

The reference ID is already archived in local SQLite; its root/child rollout
pointers are missing locally. Five July child edges remain open. Task retrieval
fails with missing-source-rollout lineage, not an inactive status. No live
retirement readiness is claimed from that state; no source task was mutated.

## Verification

The context-transfer suite passes, including synthetic 7-Zip packaging after
reconciliation with unchanged open-edge audit records. Active/unknown/missing
observations, incorrect binding, changed metadata/files and missing recovery
content are covered. Root wiring and installed skill validation pass. The staged
runtime and deployed skill/reference hashes match verified repository sources.
Synthetic temporary fixtures clean themselves; no real task was retired.
