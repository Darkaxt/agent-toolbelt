---
name: uvrun-python
description: Prefer `uv` for standalone local Python script execution. Use the package-backed wrapper to decide when a local `.py` file should go through `uvrun.ps1` and when it should fall back to direct Python.
license: MIT
compatibility: Windows/local Python helper. Requires uv and the package-backed uvrun wrapper.
metadata:
  version: "0.1.0"
---

# UV Run Python

## Overview

Use `scripts/invoke_uvrun.py` to decide whether a local `.py` file should run through `uvrun.ps1` or fall back to direct Python execution. The wrapper delegates into the UVRun family package in this repo.

## Routing Rules

Use this skill when:

- Codex is about to run a direct local `.py` file.
- The script is a scratch file, temp utility, local helper, or one-off standalone script.
- The user explicitly asks to use `uv`, `uv run`, or `uvrun`.

Do not use this skill when:

- The command is `python -m ...`.
- The task is `pytest`, `ruff`, `mypy`, migrations, or a project CLI.
- The script lives in a project with nearby markers such as `pyproject.toml`, `uv.lock`, `requirements*.txt`, `poetry.lock`, `Pipfile`, `pixi.toml`, or `.git`.

## Script Interface

```bash
python scripts/invoke_uvrun.py <script.py> [--json] [--check] [--cwd <dir>] [--timeout-sec <n>] [-- <args>...]
```
