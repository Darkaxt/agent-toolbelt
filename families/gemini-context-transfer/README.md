# Gemini Context Transfer

Take over a Gemini (Antigravity CLI `agy`) conversation into a fresh Claude Code
session: bounded catalog of the source transcript, handoff + destination
acceptance, a verified 7-Zip LZMA2 archive of the conversation's own files, and
an exact retirement that deletes only `brain/<id>`, `conversations/<id>.db` and
`annotations/<id>.pbtxt`. Shared agy indexes are reported as residuals, never
edited.

The helper is a single stdlib script:
`codex/skills/gemini-context-transfer/scripts/gemini_context_transfer.py`.
See `SPECIFICATION.md` for requirements and acceptance, and the skill's
`SKILL.md` for the operating procedure.

## Release

```powershell
python families/gemini-context-transfer/scripts/release_local.py `
  --source-commit <verified-sha> `
  --release-root D:\Tools\gemini-context-transfer `
  --claude-root $env:USERPROFILE\.claude
```

## Tests

```powershell
$env:GEMINI_TRANSFER_TEST_ROOT = "E:\Temp\<task>"
python -m pytest tests/test_gemini_context_transfer.py
```

Tests use a synthetic agy home in a temporary directory and never read `~/.gemini`.
