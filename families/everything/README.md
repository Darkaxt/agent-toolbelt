# Everything Family

Everything-first filename and path lookup with conservative fallbacks for cases where `es.exe` is missing or the request is not a global search fit.

Use this family if you want:

- global filename/path discovery
- install location lookup
- explicit Everything-powered searches

External requirements:

- `es.exe` from Everything for full global lookup
- `rg` for repo-local fallback

CLI:

```bash
uv run --package agent-toolbelt-everything agent-toolbelt-everything --query "README.md"
```

Codex integration:

- `families/everything/codex/skills/everything-search`

Claude integration:

- `families/everything/claude/marketplaces/agent-toolbelt-local`
