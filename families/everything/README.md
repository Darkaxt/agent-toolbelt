# Everything Family

Everything-first filename/path discovery with conservative fallbacks for cases where `es.exe` is missing or the request is not a global search fit. This is not a content grep, symbol search, or RAG indexer.

Use this family if you want:

- global filename/path discovery
- install location lookup
- explicit Everything-powered searches

External requirements:

- `es.exe` from Everything available on `PATH` for full global lookup
- `rg` for repo-local fallback

CLI:

```bash
uv run --package agent-toolbelt-everything agent-toolbelt-everything --query "README.md"
```

JSON results include `diagnostics` with the requested mode, selected backend,
`fallback_used`, fallback reason, searched root, `es.exe` availability/path,
`match_path`, and max result cap. In global mode, `fallback_used=true` means
Everything was unavailable or failed and only the scoped fallback root was
searched.

Codex integration:

- `families/everything/codex/skills/everything-search`

Claude integration:

- `families/everything/claude/marketplaces/agent-toolbelt-local`
