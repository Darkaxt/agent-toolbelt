# UVRun Family

Standalone Python execution routing that prefers `uvrun.ps1` for local one-off scripts while keeping project-managed Python workflows out of scope.

Use this family if you want:

- `uv`-first standalone script execution
- metadata insertion through the local `uvrun` helper flow
- a conservative fallback to direct Python when the `uv` path is unavailable

External requirements:

- `uv`
- `uvrun.ps1` or deprecated `uvrun.bat`

CLI:

```bash
uv run --package agent-toolbelt-uvrun agent-toolbelt-uvrun scratch.py --check
```

Codex integration:

- `families/uvrun/codex/skills/uvrun-python`

Claude integration:

- `families/uvrun/claude/marketplaces/agent-toolbelt-local`
