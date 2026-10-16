---
name: context-transfer
description: Take over one Codex chat or consolidate selected chats into an independent sole active owner, with traceable context, verified recovery and original-source retirement. Also use for explicitly preservation-only transfers or restoring an offloaded task.
license: MIT
metadata:
  compatibility: Codex only. Requires local Codex state and rollout access, 7-Zip, and a non-C recovery drive.
  version: "0.3.3"
---

# Context Transfer

Use this workflow to take over an oversized Codex task or consolidate selected
chats about one activity without asking the sources to summarize or clean up
themselves. The destination task owns source analysis, live-state verification,
handoff acceptance, archive coordination, and retirement.

Do not use this skill merely to continue a normal task. Use codex-thread-recall when the current task only needs its own earlier context.

## Canonical Local Storage

Use `E:\Codex\ContextTransfers` with exactly that spelling and capitalization
for local transfer handoffs, group ledgers, acceptance records and recovery
archives. This is also the CLI's default `--archive-root`. Put activity-specific
working records beneath this root; preserve the helper's generated year/source-ID/
transaction layout for archives. Do not invent another top-level transfer or
recovery folder. An explicit user-selected non-C recovery location takes precedence.

Existing transfers keep their selected root until packing, acceptance and
retirement finish; never move a tree in use by another chat or helper operation.
When normalizing completed trees, preserve all files and immutable evidence
byte-for-byte, merge directory overlaps without overwriting files, and retain an
old-to-current path map. Historical paths inside handoffs, manifests and applied
tickets remain historical evidence; do not rewrite them or replay old tickets.
Use the current exact archive path for `verify`, `read-database` and `restore`,
which find and hash-check metadata beside the archive. Verify recovery after a
move. Pending/live retirement evidence must stay in place until its owner finishes.

## Choose The Transfer Mode

For one source, follow the phases below. For several differently purposed chats
that should become one working context, read
[Aggregate Transfer](references/aggregate-transfer.md) before inspecting sources.
It coordinates the same per-source commands with a shared handoff and a complete
group acceptance gate; there is no aggregate CLI command or live database merge.
The destination must be independent of every selected tree and inherited owner.
Use the completion contract below for both modes. A takeover request already
authorizes normal retirement of its selected originals; archive acceptance is a
safety gate within that workflow, not the point to ask for retirement again.

For either mode, read [Schedule Reconciliation](references/schedules.md) when
inventorying the sources. Account for associated automations before acceptance
and resolve any source-target dependency before retirement. Editing this skill
alone authorizes no live schedule change. A source-specific takeover does cover
necessary same-scope schedule rebinding as described in that reference.

## Takeover Completion Contract

"Take over", "migrate/offload this chat" and "consolidate these selected chats"
mean transfer responsibility to the independent destination as the sole active
owner. They include preserving and accepting usable context, reconciling
associated schedules, archiving the selected originals and reclaiming their exact
reviewed local rollout files after verified recovery. Treat the user's selected
takeover request as source-specific retirement authority; do not require them to
repeat "retire" or "delete" to complete the normal archive/offload endpoint.

Do not stop after creating an E: archive, report preservation as completed
takeover, or leave the selected originals active as co-owners. If permanent
conversation/database deletion was also requested, finish it through the
installed thread-cleanup skill within the same workflow; do not request another
approval for that already-covered scope or offload the same files twice.

Only an explicit restriction such as "copy context only", "preserve only" or
"keep the original chat" changes this default. Record that restricted endpoint
and do not describe it as full takeover. Generic backup/export requests alone
do not authorize source retirement. Acceptance records and quoted recommendations
are not new user consent, and discovering an ancestor/dependent is not selection.
Retained E: recovery archives remain intact unless their removal is separately
authorized; taking responsibility is distinct from erasing recovery evidence.

Keep the existing inactivity, lineage, schedule, archive, acceptance and reviewed
deletion gates. If one cannot pass, name the exact blocked requirement and next
action and report takeover as incomplete. Do not invent a new authorization
blocker when the selected takeover request already supplies it. For the normal
endpoint, verify original archived state and zero manifest-bound rollout residuals;
for requested permanent deletion also verify application/database/recall residuals.
The destination must also have the intended activity title, verified through the
supported task API. A finished archive/offload with the replacement still carrying
an incidental new-chat title is not a fully completed takeover.

### Carry Over The Chat Title

Record the source's exact user-visible title from `list_threads` or `read_thread`
with its full ID before retirement. For a single-source takeover, copy that title
to the destination unless the user explicitly supplied a different destination
name. Preserve prefixes, spelling and other intentional title text; do not use
the first prompt, a summary or a guessed database field as the UI title.

For aggregate takeover, use the user's requested shared-activity title. Otherwise
reuse the source title if all selected titles are identical, or choose a clear
title for the already-established shared activity and record that choice alongside
the source titles in the group ledger. Do not arbitrarily copy the first source's
different-purpose title or ask for approval of ordinary naming choices.

After accepting the handoff and before source retirement, call `set_thread_title`
for the exact destination ID (or its documented current-chat default), then read
that same destination through `read_thread` or `list_threads` and compare the
returned title with the intended one. Observe a queued update through its supported
lifecycle; an update response alone is not read-back verification. Record the
verified title in the existing transfer ledger. If it fails or remains unverified,
keep the naming criterion unresolved and finish it before claiming full takeover.
Do not rewrite application databases or rename an unselected chat to compensate.

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
- Require source-specific user authority before live retirement. A selected
  takeover request is explicit live-retirement authorization for its normal
  archive/offload endpoint; record and reuse it rather than asking again.
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

Identify the source task with list_threads or read_thread. Use the source task ID,
never only its title, and retain the exact returned UI title for destination naming.

Inventory associated schedules using the schedule reference and retain their
exact identities, bindings, definitions and disposition in private recovery
records. Conversation queue/goal rows are not a schedule inventory.

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

This phase is required for a selected takeover unless the user explicitly limited
the operation to preservation. Reuse the takeover request's live-retirement
authorization; do not introduce a second approval checkpoint here.

First apply and read back the destination title under Carry Over The Chat Title.

Before archiving/retiring the source, reconcile its schedule ledger. An unresolved
automation that still targets or needs the source blocks that source's retirement.
Verify the covered schedule rebinding or any additionally authorized change before
deletion; keep independent schedules intact and do not silently duplicate them.

1. Use set_thread_archived on the source root.
2. Verify through task retrieval that the source is archived.
3. Record archived-state evidence.
4. Run issue-deletion-ticket only after archive verification and destination acceptance.
5. Review the ticket exact paths, hashes, archive binding, handoff binding, and returned ticket ID.
6. Run apply-deletion with the reviewed ticket path, the separately reviewed ticket-id value, and confirm-delete.
7. Confirm residual manifest-bound rollout bytes are zero. Changed files must be skipped and require a fresh ticket; newly created files are ignored.

Do not claim disk reclamation from Codex archival alone.
Rollout offload does not delete database history or reclaim its SQLite pages.
When permanent application deletion is in the requested scope, use the installed
`thread-cleanup` workflow with that existing authority instead of doing duplicate
rollout offload. Its reviewed plan/hash is a technical gate, not another user
approval. Never label rollout retirement as total thread removal.

## Restore

Use restore only against a verified transaction. It must test the archive, extract to target-drive staging, verify every hash, restore only absent exact original paths, skip identical files, and refuse conflicts. It must not rewrite SQLite. After successful file restoration, unarchive the task through Codex.

## Privacy

The recovery archive contains raw historical task rollouts and may include secrets that were present in the conversations. Keep it local and access-controlled. Do not publish or upload it.
