# Gemini Family

Gemini-powered public URL inspection for agent workflows, plus a Codex-only research companion lane.

Use this family if you want:

- public URL inspection and summarization
- trusted-by-default YouTube handling
- Codex-side second-pass research cross-checks

External requirements:

- `npx`
- `@google/gemini-cli`
- working Gemini CLI OAuth auth

CLI:

```bash
uv run --package agent-toolbelt-gemini agent-toolbelt-gemini url --url "https://example.com" --instruction "Summarize this page."
uv run --package agent-toolbelt-gemini agent-toolbelt-gemini research --question "Going Medieval issues"
```

Model and auth behavior:

- Defaults to `gemini-3-pro-preview`, then falls back through Flash/2.5 tiers and finally the Gemini CLI default only for model quota, capacity, or access failures.
- Strips Gemini API key and Vertex AI environment variables by default so local runs stay on cached OAuth quota instead of accidentally using paid API billing.
- Use `--model <name>` to try a specific model first; fallback still applies for model quota/capacity/access failures.
- Use `--allow-env-credentials` only when you intentionally want Gemini API key or Vertex AI environment routing.
- JSON output reports the requested model in `model_attempts[].model` and the actual main model from Gemini CLI stats in `model_used` when available.

Codex integration:

- `families/gemini/codex/skills/gemini-cli`

Claude integration:

- `families/gemini/claude/marketplaces/agent-toolbelt-local`
