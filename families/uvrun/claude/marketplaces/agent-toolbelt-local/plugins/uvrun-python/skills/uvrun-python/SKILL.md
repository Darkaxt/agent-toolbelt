---
name: uvrun-python
description: Use this skill when Claude is about to run a direct standalone local `.py` file, or when the user explicitly asks to use `uv`, `uv run`, or `uvrun`.
version: 0.1.0
---

# UV Run Python

Use `scripts/invoke_uvrun.py` to decide whether a local `.py` file should run through `uvrun.ps1` or fall back to direct Python execution. The wrapper delegates into the UVRun family package in this repo.
