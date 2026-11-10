# Claude Context Transfer

Fork of `context-transfer` for Claude Code destinations.

- **Claude -> Claude**: take over an oversized Claude Code session in a fresh
  session, archive the original transcript tree (main `.jsonl`, subagents,
  tool results, file-history, session-env, tasks, debug) into a verified 7-Zip
  LZMA2 archive, then retire it through the installed `thread-cleanup` skill.
- **Codex -> Claude**: reuse the installed Codex `context-transfer` runtime with
  the Claude session ID as destination; Codex-side retirement stays in Codex.

The helper is a single stdlib script:
`codex/skills/claude-context-transfer/scripts/claude_context_transfer.py`.
See `SPECIFICATION.md` for requirements and acceptance, and the skill's
`SKILL.md` for the operating procedure.

## Release

```powershell
python families/claude-context-transfer/scripts/release_local.py `
  --source-commit <verified-sha> `
  --release-root D:\Tools\claude-context-transfer `
  --claude-root $env:USERPROFILE\.claude
```

Writes a hash-verified release copy and an identical installed bundle under
`~/.claude/skills/claude-context-transfer`, refusing to overwrite edited copies.

## Tests

```powershell
$env:CLAUDE_TRANSFER_TEST_ROOT = "E:\Temp\<task>"
python -m pytest tests/test_claude_context_transfer.py
```
