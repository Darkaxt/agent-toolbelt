---
name: claude-context-transfer
description: Take over a long-running Claude Code session into a fresh independent session, or migrate a Codex task into Claude Code, with bounded context evidence, a verified recovery archive and disk-reclaiming retirement of the original. Use for oversized Claude transcripts, Codex-to-Claude moves, restoring an archived session, and searching this session's own transcript after compaction.
license: MIT
metadata:
  version: "0.2.0"
  compatibility: Windows, Python 3.11+, 7-Zip. Claude Code destination. Retirement uses the installed thread-cleanup skill; Codex sources reuse the installed Codex context-transfer runtime.
---

# Claude Context Transfer

Fork of Codex `context-transfer`. The **destination** is always the current,
fresh Claude Code session (`CLAUDE_CODE_SESSION_ID`). The destination owns
analysis, acceptance, archive and retirement; never ask the source to summarize.
Use ordinary context, not this skill, when the current session only needs its
own earlier context (Claude compaction and `--resume` already cover that).

Helper: `python -I <skill>/scripts/claude_context_transfer.py <command>`.
All commands print JSON; `ok:false` with `error` is a hard stop, not a retry cue.

## Authority

"Take over / migrate / offload this session" authorizes the normal endpoint:
accepted context, verified archive, then retirement of the selected source.
Do not ask again for retirement. "Copy context only / keep the original" is
preservation-only: stop after verify and write `Records/preservation-only.json`.
Never select sources by title, age or folder - exact full UUIDs only.

## Storage

Claude sources: `G:\Archives\Claude\ContextTransfers\<year>\<date>-<slug>\`
with `Records\` (inspection, catalog, handoff, acceptance, plans, results) and
`Archives\<source-id>\<UTC>\session-tree.7z`. Codex sources keep the Codex root
`E:\Codex\ContextTransfers` and its index. An explicit user-chosen non-C root
wins. Archives hold raw transcripts and may contain secrets: keep them local.

## Claude -> Claude

1. **Inspect** (read-only):
   `inspect --source-session-id <id> --output <Records>\inspection.json`
   Blockers: `source_live` (close the source tab/Reframe tile first),
   `destination_is_history_dependent` (you are in a resume/fork of the source -
   start a genuinely new session), `destination_transcript_missing`,
   `unsafe_members`. Note `reframe_tile_references` for the final report.
2. **Catalog**: `catalog --manifest inspection.json --output <Records>\catalog.json`.
   Read the catalog, not the raw transcript. Use targeted `Grep` on the source
   `.jsonl` for ambiguity. Verify repositories, branches, PRs and artifacts live;
   do not copy historical claims unchecked.
3. **Handoff**: write `Records\CONTEXT_TRANSFER.md` with sections
   Current Objective; Authoritative Specifications And Plans; Completed Work With
   Evidence; Active Stage And Exact Next Actions; Unresolved Blockers And Required
   Deferrals; Durable Decisions And User Constraints; Failed Approaches Not To
   Repeat; Repositories Branches And Artifacts; Subagent Contribution Map (one
   `agent-<id>: ...` line per `subagent_ids` entry); Uncertainties Requiring
   Verification; Archive And Recall References (archive path, source ID, the
   `restore` command). Run `validate-handoff`.
4. **Accept**: write `Records\destination-acceptance.json` with schema
   `agent_toolbelt_claude_context_transfer.destination_acceptance.v1`,
   `source_session_id`, `destination_session_id`, `handoff_ready: true`,
   `handoff_sha256`, non-empty `mapped_active_requirements`,
   `evidence_sources_inspected`, `repository_state_verified`, list
   `unresolved_uncertainties`, empty `critical_unmapped_objectives`, and
   `first_continuation_action`. Run `validate-acceptance ... --output
   <Records>\acceptance-validation.json`.
5. **Pack + verify**: `pack --manifest ... --handoff ... --transfer-directory <dir>`
   then `verify --archive <session-tree.7z>` (writes `Records\verification.json`).
   A `source_changed` refusal means re-inspect; never edit manifests.
6. **Title**: ask the user to run `/rename <source title>` in the destination
   (or rename its Reframe tile), then
   `title-status --expected "<title>" --output <Records>\title-status.json`.
   An unverified title keeps the takeover incomplete; never write transcripts.
7. **Retire** (skip for preservation-only): with the installed `thread-cleanup`
   skill, `plan --system claude --home %USERPROFILE%\.claude --thread-id <source>
   --protect-id <destination> --output <Records>\cleanup-plan.json`. Always pass
   the destination as `--protect-id` (thread-cleanup only auto-protects the
   legacy `CLAUDE_SESSION_ID` variable). Then
   `retirement-check --manifest --handoff --acceptance --verification
   --cleanup-plan`, and only on `ok:true` run thread-cleanup `delete-claude` with
   the returned `plan_sha256`. Save its JSON as `Records\retirement-result.json`;
   inspect `complete` and residuals.
8. **Complete**: `validate-completion --transfer-directory <dir>`. Report the
   verified endpoint, archive path, bytes reclaimed, and any Reframe tile still
   pointing at the retired session (the user removes it in Reframe; the helper
   never edits Reframe state).

## Codex -> Claude

Reuse the installed Codex runtime unchanged (read the Codex
`~/.codex/skills/context-transfer/SKILL.md` for details):

```powershell
$ct = "$env:USERPROFILE\.codex\skills\context-transfer\scripts\invoke_context_transfer.py"
python $ct inspect --source-thread-id <codex-id> --destination-thread-id $env:CLAUDE_CODE_SESSION_ID --output <Records>\inspection.json
python $ct catalog --manifest <Records>\inspection.json --output <Records>\catalog.json
python $ct validate-handoff --manifest ... --handoff <Records>\CONTEXT_TRANSFER.md
python $ct validate-acceptance --manifest ... --handoff ... --acceptance <Records>\destination-acceptance.json
python $ct pack --manifest ... --handoff ... --transfer-directory <E:\Codex\ContextTransfers\...>
python $ct verify --archive <thread-tree.7z>
python $ct read-database --archive <thread-tree.7z> --thread-id <codex-id> --pattern <term>
```

Use the Codex section names (`Child-Agent Contribution Map`, `Database Evidence
And Recall References`) and Codex acceptance schema
`agent_toolbelt_context_transfer.destination_acceptance.v1` with the Claude
session ID as `destination_thread_id`. Codex task tools (`read_thread`,
`set_thread_archived`) are not available from Claude: use the catalog,
`read-database` and the Codex `codex-thread-recall` CLI for detail.

Retirement of the Codex source needs live-owner evidence (`codex_task_api`) that
Claude cannot produce while Codex Desktop runs (a second app-server's
`notLoaded` is not proof). Finish the archive/delete step from any Codex chat
with `context-transfer` Phase 5 or `thread-cleanup`, citing the Claude
acceptance record. Until then report the endpoint as accepted + archived, not
retired.

## Restore

`restore --archive <session-tree.7z>` tests the archive, verifies every hash,
writes only absent original paths, skips identical files and refuses conflicts.
Then `claude --resume <id>`.

## Recall: search this session after compaction

Before re-researching something this session already knew, search its own transcript
(read-only, streaming; defaults to `CLAUDE_CODE_SESSION_ID`):

```powershell
python -I <skill>/scripts/claude_context_transfer.py search --pattern "<regex>" [--latest] [--limit 20] [--excerpt-chars 400]
python -I <skill>/scripts/claude_context_transfer.py search --pattern "gh pr merge" --tools --kind tool_use   # commands/tool inputs
python -I <skill>/scripts/claude_context_transfer.py search --pattern "<regex>" --subagents                   # include subagent transcripts
python -I <skill>/scripts/claude_context_transfer.py show --line <line> [--file <subagent file>] [--offset 0 --chars 4000]
```

Search covers user/assistant text, compaction summaries, titles, PR links and system errors;
`--tools` adds tool calls and results. Matching is case-insensitive. Results are bounded
(`truncated`, `total_matches`); narrow the pattern or use `--latest` instead of raising limits.
Never read the whole `.jsonl` into context; use `show` to expand one hit.
