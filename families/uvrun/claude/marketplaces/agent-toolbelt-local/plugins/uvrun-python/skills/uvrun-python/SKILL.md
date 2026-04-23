---
name: uvrun-python
description: Use `scripts/invoke_uvrun.py` when Claude is about to run a direct standalone local `.py` file. The wrapper bootstraps the UVRun family from the local `agent-toolbelt` workspace and routes eligible scripts through `uvrun.ps1`.
version: 0.1.1
---

# UV Run Python

Use `scripts/invoke_uvrun.py` to decide whether a local `.py` file should run through `uvrun.ps1` or fall back to direct Python execution. The wrapper delegates into the UVRun family package in this repo; if the workspace lives somewhere else, set `AGENT_TOOLBELT_HOME`.

## Routing Rules

Use this skill when:

- Claude is about to run a direct local `.py` file.
- The script is a scratch file, temp utility, local helper, or one-off standalone script.
- The user explicitly asks to use `uv`, `uv run`, or `uvrun`.

Do not use this skill when:

- The command is `python -m ...`.
- The task is `pytest`, `ruff`, `mypy`, migrations, or a project CLI.
- The script lives in a project with nearby markers such as `pyproject.toml`, `uv.lock`, `requirements*.txt`, `poetry.lock`, `Pipfile`, `pixi.toml`, or `.git`.

## Behavior

- Eligible standalone scripts should default to `uvrun.ps1`.
- `uvrun.ps1` still uses `uvrun_helper.py` to add a PEP 723 `# /// script` block the first time it sees an eligible script with no inline metadata.
- `uvrun.bat` remains supported as a deprecated compatibility shim.
- If `uvrun.ps1`, `uvrun.bat`, or `uv` is unavailable, fall back to direct Python execution and say that the `uv` path was unavailable.
- Do not route eligible scripts through `pyrun.bat` automatically. Treat `pyrun.bat` as a legacy manual option.

## Script Interface

```bash
python scripts/invoke_uvrun.py <script.py> [--json] [--check] [--cwd <dir>] [--timeout-sec <n>] [-- <args>...]
```
