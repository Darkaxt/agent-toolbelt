# Gemini Family

Gemini-powered public URL inspection for agent workflows, plus a Codex-only research companion lane.

Use this family if you want:

- public URL inspection and summarization
- trusted-by-default YouTube handling
- Codex-side second-pass research cross-checks

External requirements:

- `npx`
- `@google/gemini-cli`
- working Gemini CLI auth

CLI:

```bash
uv run --package agent-toolbelt-gemini agent-toolbelt-gemini url --url "https://example.com" --instruction "Summarize this page."
uv run --package agent-toolbelt-gemini agent-toolbelt-gemini research --question "Going Medieval issues"
```

Codex integration:

- `families/gemini/codex/skills/gemini-cli`

Claude integration:

- `families/gemini/claude/marketplaces/agent-toolbelt-local`
