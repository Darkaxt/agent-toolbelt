---
name: context-transfer
description: Use when a fresh Codex task must take over useful context from an oversized source task, preserve the complete source and child-agent rollout tree in a verified recovery archive on another drive, archive the source task, reclaim exact rollout files through a reviewed deletion ticket, or restore an offloaded task safely.
license: MIT
metadata:
  compatibility: Codex only. Requires local Codex state and rollout access, 7-Zip, and a non-C recovery drive.
  version: "0.2.0"
---

# Context Transfer

Use this workflow to retire an oversized Codex task without asking that source task to summarize or clean up itself. The destination task owns source analysis, live-state verification, handoff acceptance, archive coordination, and retirement.

Do not use this skill merely to continue a normal task. Use codex-thread-recall when the current task only needs its own earlier context.

## Non-Negotiable Boundaries

- Run from a fresh destination task with a different CODEX_THREAD_ID.
- The destination must be independent, not a fork of the source or its ancestors.
  A different ID alone is insufficient. Start a normal new chat, inspect lineage,
  and refuse `destination_is_history_dependent`; do not just fork again.
- Do not ask the source task to summarize itself.
- No direct SQLite mutation is allowed. Inventory/export is read-only; migration preserves scoped database evidence and leaves live application databases unchanged. Permanent deletion is a separate `thread-cleanup` workflow through the supported application lifecycle.
- Do not load or paste the complete rollout tree into model context.
- Do not create a permanent second full-text rollout index.
- Do not archive or delete a live source until handoff acceptance and archive verification pass.
- Require explicit live-retirement authorization before invoking set_thread_archived, issuing a deletion ticket, or applying deletion to a real source.
- Never delete by wildcard, age, title, cwd, repository, broad directory, or inferred ownership.
- Do not include source repositories, worktrees, shared caches, cookies, or unrelated Codex state in the archive.

## Wrapper

Run python scripts/invoke_context_transfer.py followed by the command and arguments.

The installed wrapper prefers the staged private runtime selected by `CODEX_HOME/tools/context-transfer/active.json`. Repository development may override it with `AGENT_TOOLBELT_HOME` or a parent checkout. Stop and repair the runtime if none resolves.

Install or refresh the staged runtime from the repository with:

```powershell
python scripts/install_context_transfer_runtime.py --agent-toolbelt-home <agent-toolbelt-checkout>
```

The installer validates a complete versioned release before atomically switching `active.json`. Runtime commands have no cancellation timeout; long archive operations must be observed rather than killed by an arbitrary deadline.

## Phase 1: Select And Inspect

Identify the source task with list_threads or read_thread. Use the source task ID, never only its title.

Run inspect with source-thread-id, destination-thread-id, the reviewed non-C recovery root, and an explicit output path for inspection.json.

Inspection is read-only unless output is explicitly supplied. Inspect `threads[].rollouts` and `rollout_count`, not only the database's current `rollout_path`: resumed tasks can have earlier segments in sessions or archived_sessions. Discovered segments require matching session_meta identity; ambiguous or unreadable segments block retirement.

Inspect `database_evidence` too: paginated conversations retain actual content in
`thread_history_1.sqlite`, not just raw rollouts. Source/child rows from state,
history, goals, queue and memory databases are exported to the recovery archive.
Exports are private historical evidence, not permission to rewrite live databases.
Inspect `history_reference_dependents` separately from child spawn edges: a fork
can still depend on source database/rollout history without being a spawned agent.
Those references block retirement. An external archive is evidence storage, not
an automatic redirect for Codex's live paginated history. Do not delete an ancestor
of a surviving fork or edit lineage headers/SQL to bypass the application's guard.
An independent replacement chat must explicitly accept usable context before
the dependent fork and its ancestors can be permanently retired.
`source_history_ancestors` lists inherited history owners and boundaries. Preserve
each necessary ancestor separately (its database rows AND every rollout segment),
and put every exact ancestor ID/archive reference in the required database section.
For inactive ancestors blocked only by surviving fork references, pack with
`--preserve-referenced-history`; its verified archive is explicitly preservation-
only and cannot issue a deletion ticket. All other activity/identity blockers
remain binding. Do not claim complete inherited history from the fork's own rows.

After the independent destination accepts the complete handoff, retire the selected
leaf fork first, then its selected ancestors in reverse dependency order. Re-plan
and refresh status after each deletion. Unselected forks must remain intact: their
parents remain blocked unless the user separately authorizes migrating/retiring
those forks too. Context acceptance and a copied archive alone do not detach a
live paginated-history reference; never edit fork headers/SQL as a shortcut.
When retirement is blocked, `export-database --manifest <inspection.json>
--output <private-E-drive-evidence.jsonl>` still preserves scoped rows read-only.
It is database evidence, not a complete rollout recovery archive or permission
to delete ancestors. Give the replacement chat the exact output path, table/ID
scope and returned digest. Optional compression must verify those exact bytes.

`retirement_ready=false` does not prevent read-only catalog generation or provisional handoff validation. Preserve and report `retirement_blockers`; never guess that old open-child records mean terminal children, mutate SQLite, or use a hand-crafted retirement manifest. Normal packaging/deletion requires retirement_ready=true, no blockers, every child terminal or verified inactive, and every rollout readable. The sole packaging exception is preservation-only mode above: explicit reconciled inactive-status evidence is required and only surviving fork references may remain. It never permits deletion.

Lineage inspection reports known references from readable registered rollout
headers. Missing or compressed headers are not proof of independence or complete
coverage; verify unresolved lineage through supported app evidence. The owning
application's deletion refusal remains authoritative.

### Stale Open-Child Records

An old spawn edge is not runtime status. Capture explicit live status for the source and every descendant through supported task tools, then run `reconcile-activity --manifest inspection.json --activity-evidence activity.json --output reconciled-inspection.json`. Use that returned manifest for subsequent catalog/handoff/pack steps; do not edit blockers manually.

Read [references/activity-evidence.md](references/activity-evidence.md) for the metadata-only sidecar contract. Idle/notLoaded or terminal API status can establish inactivity; active, pending, unavailable, unknown or absent status cannot. Do not infer inactivity from age, an archived flag, lack of file changes or absence from a limited task listing. Missing-source-rollout API errors are errors, not idle evidence.

`stale_inactive_child_ids` records verified stale edges without closing them in SQLite. Reconciliation is bound to the inspected tree; packaging rechecks task metadata and files. A changed tree or rollout requires renewed inspection/status evidence, not a retry delay or a forced deletion. Missing history still blocks retirement independently. Refresh task-status evidence immediately before the packaging handoff and never run the source while retiring it.

## Phase 2: Build Bounded Evidence

Run catalog against inspection.json. Use bounded excerpts and source offsets rather than a raw transcript dump.

Catalogs sample every readable verified segment within per-thread/total bounds. Check truncation and unavailable segments; do not declare complete recovered context merely because the latest resumed segment was readable. A provisional handoff is useful for continuation but is not retirement authorization.

Read selected recent or older source turns through read_thread when the catalog points to ambiguity. Inspect every child contribution at least through its task metadata and mapped evidence. Verify current repositories, branches, commits, pull requests, deployments, and artifacts from live repository or filesystem state; do not copy historical claims without checking them.

## Phase 3: Write And Validate The Handoff

Write a bounded CONTEXT_TRANSFER.md with these exact sections:

- Current Objective
- Authoritative Specifications And Plans
- Completed Work With Evidence
- Active Stage And Exact Next Actions
- Unresolved Blockers And Required Deferrals
- Durable Decisions And User Constraints
- Failed Approaches Not To Repeat
- Repositories Branches And Artifacts
- Child-Agent Contribution Map
- Uncertainties Requiring Verification
- Database Evidence And Recall References

In the last section, record source/child IDs, the reviewed archive location,
important database-only facts or unresolved coverage, and the offline
`read-database` command below. Tell the replacement thread that normal recall
requires an exact thread row and readable rollout path: loose title/cwd references,
an old cache, or the presence of database items are not automatic fallback. Moved
rollouts yield `rollout_missing`; deleted rows yield `thread_unavailable`. Imported
recall memory bundles remain explicitly queried summaries, not raw recall.

In the child map, start one line per child with the exact thread ID followed by a colon.

Run validate-handoff with inspection.json and CONTEXT_TRANSFER.md.

Write destination-acceptance.json with schema agent_toolbelt_context_transfer.destination_acceptance.v1. It must include non-empty mapped_active_requirements, evidence_sources_inspected, repository_state_verified, a list of unresolved_uncertainties, empty critical_unmapped_objectives, an exact first_continuation_action, and the validated handoff hash.

Run validate-acceptance with inspection.json, CONTEXT_TRANSFER.md, and destination-acceptance.json.

Do not proceed if any active objective is absent or uncertain evidence is presented as verified.

## Phase 4: Pack And Verify

Create the archive directly under the non-C recovery root. Do not add a cancellation timeout. The helper snapshots each reviewed rollout into temporary transaction-local storage and gives 7-Zip only those verified copies; do not kill Codex or a source-task process to release a rollout handle.

Run pack with the reviewed manifest, handoff, and the reviewed non-C recovery root. Then run verify against thread-tree.7z.

Require maximum LZMA2 solid settings, `source_snapshot.source_paths_passed_to_seven_zip=false`, successful 7z test, archive SHA-256, matching internal and external metadata, and representative rollout extraction. The temporary rollout snapshot must be absent after the command returns, including after failure.

New archives include `context-transfer/database-evidence.jsonl`, with selected
rows, per-table counts and a verified digest. Require
`database_evidence_verified=true`; older archives lack this coverage. Important
database-only information must be understood by the replacement thread, not
merely packed without mention. Read without restoring live state:

```powershell
python scripts/invoke_context_transfer.py read-database --archive <thread-tree.7z> --thread-id <exact-source-id> --table thread_items --pattern <term> --limit 10
```

Results are bounded; inspect `total_matches` and `truncated`. Raw evidence may
contain credentials, so do not publish it. This export is deliberately scoped,
not a full backup of unrelated conversations or a permanent second search index.

## Phase 5: Archive And Retire

This phase always requires explicit live-retirement authorization for the selected real task.

1. Use set_thread_archived on the source root.
2. Verify through task retrieval that the source is archived.
3. Record archived-state evidence.
4. Run issue-deletion-ticket only after archive verification and destination acceptance.
5. Review the ticket exact paths, hashes, archive binding, handoff binding, and returned ticket ID.
6. Run apply-deletion with the reviewed ticket path, the separately reviewed ticket-id value, and confirm-delete.
7. Confirm residual manifest-bound rollout bytes are zero. Changed files must be skipped and require a fresh ticket; newly created files are ignored.

Do not claim disk reclamation from Codex archival alone.
Rollout offload does not delete database history or reclaim its SQLite pages.
Use the separate explicitly authorized `thread-cleanup` workflow for permanent
application deletion; never label rollout retirement as total thread removal.

## Restore

Use restore only against a verified transaction. It must test the archive, extract to target-drive staging, verify every hash, restore only absent exact original paths, skip identical files, and refuse conflicts. It must not rewrite SQLite. After successful file restoration, unarchive the task through Codex.

## Privacy

The recovery archive contains raw historical task rollouts and may include secrets that were present in the conversations. Keep it local and access-controlled. Do not publish or upload it.
