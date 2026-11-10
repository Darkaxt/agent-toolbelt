# Claude Context Transfer Specification

Status: authoritative for version 0.1.0.

## Purpose

Fork of `context-transfer` for Claude Code. One installed skill covers two
source systems, both with a Claude Code session as the independent destination:

1. **Claude -> Claude takeover**: move a long-running Claude Code session into a
   fresh session, preserve a verified recovery archive, then retire the original
   to reclaim disk (Claude transcripts on this host reach multiple GB each).
2. **Codex -> Claude migration**: carry a Codex task's context into a Claude Code
   session. Preservation, catalog, handoff and acceptance reuse the installed
   Codex `context-transfer` runtime unchanged; only the destination differs.

## Requirements

R1. Read-only inspection of a Claude source session: exactly one
`projects/*/<id>.jsonl`, its owned sidecar tree (`projects/<slug>/<id>/`,
`file-history/<id>`, `session-env/<id>`, `tasks/<id>`, `debug/<id>.txt`,
`security_warnings_state_<id>.json`) - the same member set that `thread-cleanup`
deletes - with size, mtime and SHA-256 per file. Reparse/symlink members block.

R2. Blockers: source equals destination; source is live (registered running
process or explicit command-line reference); destination transcript missing;
destination history contains source records (fork/resume dependency); unsafe or
unreadable members. Reframe tiles bound to the source are reported, never edited.

R3. Bounded catalog: user prompts, assistant text, compaction summaries, errors,
titles and PR links with line offsets; first/last/milestone sampling with caps.
No full transcript dump.

R4. Handoff `CONTEXT_TRANSFER.md` with the Codex section contract (sections
renamed only where Codex-specific) and one `agent-<id>:` line per subagent
transcript. Destination acceptance JSON with the same fields as Codex, bound to
the handoff hash.

R5. Pack: re-hash every member (changes refuse), snapshot copies into
transaction staging, 7-Zip LZMA2 maximum solid archive under
`<root>/<year>/<date>-<slug>/Archives/<source-id>/<UTC>/`, manifest inside and
beside, staging removed on success and failure. Default root
`G:\Archives\Claude\ContextTransfers` (retained recovery material, storage
hierarchy); explicit `--archive-root` wins.

R6. Verify: `7z t`, full extraction to staging next to the archive, every member
hash compared, staging removed; verification bound to archive SHA-256.

R7. Retirement gate: accepted handoff + verified archive (hash re-checked) +
source not live + a `thread-cleanup` Claude plan whose every file is archived with
identical SHA-256 and whose protected IDs include the destination. Deletion itself
remains `thread-cleanup delete-claude` (no second deletion implementation).

R8. Restore: test archive, extract to staging, verify hashes, write only absent
exact original paths, skip identical, refuse conflicts.

R9. Title read-back: newest `custom-title` record of the destination transcript
(set by the user with `/rename`, or Reframe tile name) compared with the intended
title. The helper never writes transcripts or Reframe state.

R10. Completion check over the transfer records: verification, acceptance,
retirement result (`complete: true`) or explicit preservation-only endpoint, and
title read-back.

R11. Codex -> Claude: documented workflow through the installed Codex
`context-transfer` runtime with `--destination-thread-id <Claude session id>`.
Codex retirement needs live-owner evidence (`codex_task_api`) that Claude cannot
produce while Codex runs: retirement is executed from any Codex chat via the
existing context-transfer / thread-cleanup flow, citing the Claude acceptance.

## Non-goals

No SQLite or transcript mutation, no Reframe state edits, no automatic title
setting, no deletion engine, no permanent full-text index.

## Acceptance

A1 unit tests for R1-R10 against a synthetic Claude home.
A2 real read-only inspect + catalog on an existing Claude session.
A3 end-to-end on a disposable Claude session created for the test: inspect,
handoff, acceptance, pack, verify, retirement gate, thread-cleanup deletion,
restore from archive, completion check.
A4 Codex -> Claude: read-only inspect/catalog of a real Codex thread with a Claude
destination ID through the installed runtime.
A5 installed copy under `~/.claude/skills/claude-context-transfer` byte-identical
to the committed release.
