# UVRun Family

Internal standalone Python execution routing that prefers `uvrun.ps1` for local one-off scripts while keeping project-managed Python workflows out of scope.

This family is kept as a package-level helper only. It is not published as an agent skill; use the official Astral `uv` skill for general Python package management, project workflows, and ordinary `uv run` guidance.

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

Agent integration:

- No public Codex or Claude skill is shipped for this family.
- Use this package directly only when the local `uvrun.ps1` wrapper behavior is specifically needed.
