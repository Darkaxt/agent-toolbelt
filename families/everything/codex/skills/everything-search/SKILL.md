---
name: everything-search
description: Use Everything CLI through `es.exe` for global filename and path discovery on Windows, with safe fallbacks when Everything is unavailable.
license: MIT
compatibility: Windows only. Best with Everything and es.exe installed; documented fallback behavior applies when Everything is unavailable.
metadata:
  version: "0.1.0"
---

# Everything Search

## Overview

Use `scripts/invoke_everything.py` for global filename/path discovery. The wrapper delegates into the Everything family package in this repo. This is not a content grep, symbol search, or RAG indexer.

## Routing Rules

Use this skill when:

- The user asks to find a file anywhere.
- The user asks to locate a folder or install path.
- The user asks for broad filename or extension discovery.
- The user explicitly asks to use Everything.

Do not use this skill for:

- content grep
- symbol search
- ordinary repo-local `rg --files` listing
- exact PATH semantics where `where.exe` or `Get-Command` is the real question

## Script Interface

```bash
python scripts/invoke_everything.py --query "<search>" [--max-results <n>] [--match-path] [--json]
```

## Diagnostics

Read the JSON `diagnostics` object when results are surprising. It reports the
requested mode, selected backend, `fallback_used`, fallback reason, searched
root, `es.exe` availability/path, `match_path`, and result cap. In global mode,
`fallback_used=true` means Everything was unavailable or failed and the wrapper
searched only within the provided root with a scoped fallback.
