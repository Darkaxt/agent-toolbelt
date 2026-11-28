---
name: gemini-context-transfer
description: Take over a Gemini (Antigravity CLI agy) conversation into a fresh Claude Code session with bounded context evidence, a verified recovery archive and exact disk-reclaiming retirement of the original conversation files. Use for Gemini-to-Claude moves, restoring an archived Gemini conversation and searching a Gemini transcript.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows, Python 3.11+, 7-Zip. Claude Code destination. Source is the Antigravity CLI home %USERPROFILE%\.gemini\antigravity-cli.
---

# Gemini Context Transfer

The **destination** is always the current Claude Code session
(`CLAUDE_CODE_SESSION_ID`). The destination owns analysis, acceptance, archive and
retirement; never ask the Gemini source to summarize.

Helper: `python -I <skill>/scripts/gemini_context_transfer.py <command>`.
All commands print JSON; `ok:false` with `error` is a hard stop, not a retry cue.

## Authority

"Take over / migrate this Gemini thread" authorizes the normal endpoint:
accepted context, verified archive, then retirement of the selected source. Do not
ask again for retirement. "Copy context only / keep the original" is
preservation-only: stop after verify and write `Records\preservation-only.json`.
Resolve the user's thread name with `list`, then use the exact full UUID only;
never select by title, age or folder. If several titles match, ask.

## Storage

`G:\Archives\Gemini\ContextTransfers\<year>\<date>-<slug>\` with `Records\`
(inspection, catalog, handoff, acceptance, verification, retirement result) and
`Archives\<id>\<UTC>\conversation-tree.7z`. If G: is missing, pack refuses: pass an
explicit non-C `--transfer-directory` on D: and record the pending G: move. C: is
always refused. Archives hold raw transcripts and may contain secrets: keep them local.

## Procedure

1. **Find**: `list` (id, title, steps, updated, sizes).
2. **Inspect** (read-only):
   `inspect --source-conversation-id <id> --output <Records>\inspection.json`.
   Blockers: `source_live` (any agy/Antigravity/language_server process; ask the
   user to close agy), `destination_transcript_missing`, `unsafe_members`. Note
   `reframe_tile_references` and `shared_index_residuals` for the final report.
3. **Catalog**: `catalog --manifest <Records>\inspection.json --output <Records>\catalog.json`.
   Read the catalog, not the raw transcript; use `search`/`show` for detail. Verify
   repositories, branches, releases and artifacts live; do not copy historical
   claims unchecked.
4. **Handoff**: write `Records\CONTEXT_TRANSFER.md` with sections Current Objective;
   Authoritative Specifications And Plans; Completed Work With Evidence; Active
   Stage And Exact Next Actions; Unresolved Blockers And Required Deferrals; Durable
   Decisions And User Constraints; Failed Approaches Not To Repeat; Repositories
   Branches And Artifacts; Gemini Subagent And Task Map (one `<name>: ...` line per
   `subagent_ids` and `task_directories` entry); Uncertainties Requiring
   Verification; Archive And Recall References (archive path, source id, `restore`
   command). Run `validate-handoff --manifest ... --handoff ...`.
5. **Accept**: write `Records\destination-acceptance.json` with schema
   `agent_toolbelt_gemini_context_transfer.destination_acceptance.v1`,
   `source_conversation_id`, `destination_session_id`, `handoff_ready: true`,
   `handoff_sha256`, non-empty `mapped_active_requirements`,
   `evidence_sources_inspected`, `repository_state_verified`, list
   `unresolved_uncertainties`, empty `critical_unmapped_objectives`,
   `first_continuation_action`. Run `validate-acceptance ... --output
   <Records>\acceptance-validation.json`.
6. **Pack + verify**: `pack --manifest ... --handoff ... [--transfer-directory <dir>]`
   then `verify --archive <conversation-tree.7z>` (writes `Records\verification.json`).
   `source_changed` means re-inspect (and re-run handoff/acceptance); never edit manifests.
7. **Retire** (skip for preservation-only):
   `retire --manifest --handoff --acceptance --verification <Records>\verification.json --dry-run`,
   review the plan, then the same command without `--dry-run` plus
   `--plan-sha256 <plan_sha256>`. It deletes only `brain/<id>`,
   `conversations/<id>.db` and `annotations/<id>.pbtxt` and writes
   `Records\retirement-result.json` (`bytes_reclaimed`, residuals).
8. **Complete**: `validate-completion --transfer-directory <dir>`. Report endpoint,
   archive path, bytes reclaimed, shared index residuals (metadata cache,
   summaries DB, history; agy rebuilds or ignores them; never edit them) and any
   Reframe hook/tile still pointing at the source (the user removes it in Reframe).

## Restore

`restore --archive <conversation-tree.7z>` tests the archive, verifies every hash,
writes only absent original paths, skips identical files and refuses conflicts.

## Recall

```powershell
python -I <skill>/scripts/gemini_context_transfer.py search --conversation-id <id> --pattern "<regex>" [--tools] [--kind user] [--latest] [--limit 20]
python -I <skill>/scripts/gemini_context_transfer.py show --conversation-id <id> --line <line> [--offset 0 --chars 4000]
```

Search covers user requests, assistant text, checkpoints and system messages;
`--tools` adds tool calls and outputs. Results are bounded; narrow the pattern
rather than raising limits. Search works while the source exists or after `restore`.
