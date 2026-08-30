---
name: context-transfer
description: Use when a fresh Codex task must take over useful context from an oversized source task, preserve the complete source and child-agent rollout tree in a verified recovery archive on another drive, archive the source task, reclaim exact rollout files through a reviewed deletion ticket, or restore an offloaded task safely.
license: MIT
metadata:
  compatibility: Codex only. Requires local Codex state and rollout access, 7-Zip, and a non-C recovery drive.
  version: "0.1.0"
---

# Context Transfer

Use this workflow to retire an oversized Codex task without asking that source task to summarize or clean up itself. The destination task owns source analysis, live-state verification, handoff acceptance, archive coordination, and retirement.

Do not use this skill merely to continue a normal task. Use codex-thread-recall when the current task only needs its own earlier context.

## Non-Negotiable Boundaries

- Run from a fresh destination task with a different CODEX_THREAD_ID.
- Do not ask the source task to summarize itself.
- No direct SQLite mutation is allowed. The helper uses read-only SQLite for inventory and leaves lightweight thread rows in place.
- Do not load or paste the complete rollout tree into model context.
- Do not create a permanent second full-text rollout index.
- Do not archive or delete a live source until handoff acceptance and archive verification pass.
- Require explicit live-retirement authorization before invoking set_thread_archived, issuing a deletion ticket, or applying deletion to a real source.
- Never delete by wildcard, age, title, cwd, repository, broad directory, or inferred ownership.
- Do not include source repositories, worktrees, shared caches, cookies, or unrelated Codex state in the archive.

## Wrapper

Run python scripts/invoke_context_transfer.py followed by the command and arguments.

The wrapper resolves AGENT_TOOLBELT_HOME, the standard local checkout, or a parent repository checkout. Stop and repair the runtime if none resolves.

## Phase 1: Select And Inspect

Identify the source task with list_threads or read_thread. Use the source task ID, never only its title.

Run inspect with source-thread-id, destination-thread-id, archive-root E:\Codex\ThreadArchives, and an explicit output path for inspection.json.

Require retirement_ready=true, no blockers, every child terminal, and every rollout readable. Inspection is read-only unless output is explicitly supplied.

## Phase 2: Build Bounded Evidence

Run catalog against inspection.json. Use bounded excerpts and source offsets rather than a raw transcript dump.

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

In the child map, start one line per child with the exact thread ID followed by a colon.

Run validate-handoff with inspection.json and CONTEXT_TRANSFER.md.

Write destination-acceptance.json with schema agent_toolbelt_context_transfer.destination_acceptance.v1. It must include non-empty mapped_active_requirements, evidence_sources_inspected, repository_state_verified, a list of unresolved_uncertainties, empty critical_unmapped_objectives, an exact first_continuation_action, and the validated handoff hash.

Run validate-acceptance with inspection.json, CONTEXT_TRANSFER.md, and destination-acceptance.json.

Do not proceed if any active objective is absent or uncertain evidence is presented as verified.

## Phase 4: Pack And Verify

Create the archive directly under the non-C recovery root. Do not add a cancellation timeout.

Run pack with the reviewed manifest, handoff, and E:\Codex\ThreadArchives. Then run verify against thread-tree.7z.

Require maximum LZMA2 solid settings, successful 7z test, archive SHA-256, matching internal and external metadata, and representative rollout extraction.

## Phase 5: Archive And Retire

This phase always requires explicit live-retirement authorization for the selected real task.

1. Use set_thread_archived on the source root.
2. Verify through task retrieval that the source is archived.
3. Record archived-state evidence.
4. Run issue-deletion-ticket only after archive verification and destination acceptance.
5. Review the ticket exact paths, hashes, archive binding, and handoff binding.
6. Run apply-deletion only with the reviewed ticket.
7. Confirm residual manifest-bound rollout bytes are zero. Changed files must be skipped and require a fresh ticket; newly created files are ignored.

Do not claim disk reclamation from Codex archival alone.

## Restore

Use restore only against a verified transaction. It must test the archive, extract to target-drive staging, verify every hash, restore only absent exact original paths, skip identical files, and refuse conflicts. It must not rewrite SQLite. After successful file restoration, unarchive the task through Codex.

## Privacy

The recovery archive contains raw historical task rollouts and may include secrets that were present in the conversations. Keep it local and access-controlled. Do not publish or upload it.
