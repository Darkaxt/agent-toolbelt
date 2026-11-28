# Gemini Context Transfer Specification

Status: authoritative for version 0.1.0.

## Purpose

Move a long-running Gemini conversation from the Antigravity CLI (`agy`, root
`%USERPROFILE%\.gemini\antigravity-cli`) into an independent Claude Code session
(`CLAUDE_CODE_SESSION_ID`), keep a verified recovery archive, then reclaim the
conversation's disk (brain trees and per-conversation databases reach hundreds
of MB).

## Source layout

- `cache/conversation_metadata.json`: shared index (`conversations.<id>.summary`
  with `Title`, `NumSteps`, `UpdatedAt`, `WorkspaceURIs`).
- Owned: `brain/<id>/` (all files, including `.system_generated/logs/transcript.jsonl`),
  `conversations/<id>.db` (+ `-wal`/`-shm` if present), `annotations/<id>.pbtxt`.
- Shared, never edited: `conversation_summaries.db`, `history.jsonl`, `cache/*`,
  `jetski_state.pbtxt`, `log/`.

## Requirements

R1. `list`: id, title, steps, updated, per-member sizes from metadata + disk.
R2. `inspect`: exact full UUID only (never by title); inventory of owned members
with bytes, mtime and SHA-256; title and workspaces from the metadata cache;
Reframe hook workspaces reported as tile references; shared index residuals.
Blockers: `source_live` (any running process named agy/antigravity/language_server,
conservative), `unsafe_members` (reparse points), `destination_transcript_missing`.
R3. `catalog`: bounded user requests (`<USER_REQUEST>` text), checkpoints, final
assistant message of each turn, files and commands from tool calls, GitHub repos
and release/PR references, plus head/milestone/tail sampling.
R4. `validate-handoff` with the Claude section contract, `Subagent Contribution Map`
renamed `Gemini Subagent And Task Map` (one `<name>:` line per subagent and `task-*`
directory). `validate-acceptance` schema
`agent_toolbelt_gemini_context_transfer.destination_acceptance.v1`, bound to the
handoff hash, with `source_conversation_id` and `destination_session_id`.
R5. `pack`: refuses live source, changed or added members; copies members into
staging and archives with the Claude helper's 7-Zip settings into
`<root>/<year>/<date>-<slug>/Archives/<id>/<UTC>/conversation-tree.7z`, `Records/`
beside it. Default root `G:\Archives\Gemini\ContextTransfers`; if its drive is
missing, pack refuses and requires an explicit non-C `--transfer-directory`.
C: is always refused.
R6. `verify`: `7z t`, full extraction, every hash compared, staging removed.
R7. `restore`: writes only absent paths, skips identical files, refuses conflicts.
R8. `retire`: needs accepted handoff, verified archive (hash re-checked), no live
agy process, and every current owned file archived with an identical hash.
`--dry-run` emits the plan and its `plan_sha256`; the real run must quote it.
Deletes only the owned members, writes `Records/retirement-result.json` with
`bytes_reclaimed`, and reports shared index residuals and Reframe references.
R9. `validate-completion`: acceptance, verification and a complete retirement
result or `preservation-only.json`, all for the same source id.
R10. `search` / `show`: bounded, streaming recall over a source transcript.

## Non-goals

No edits to shared agy indexes or Reframe state, no title setting, no SQLite
inspection of the conversation database.

## Acceptance

A1 unit tests for R1-R10 against a synthetic agy home.
A2 read-only `list`/`inspect`/`catalog` on a real conversation.
A3 installed copy under `~/.claude/skills/gemini-context-transfer` byte-identical
to the committed release.
