---
name: everything-search
description: Use this skill when the user asks to find a file anywhere, locate a folder, discover where an app is installed, run broad filename or extension searches, or explicitly asks to use Everything.
version: 0.1.0
---

# Everything Search

Use `scripts/invoke_everything.py` for global filename/path discovery. The wrapper delegates into the Everything family package in this repo. This is not a content grep, symbol search, or RAG indexer.

Read the JSON `diagnostics` object when results are surprising. It reports the
requested mode, selected backend, `fallback_used`, fallback reason, searched
root, `es.exe` availability/path, `match_path`, and result cap. In global mode,
`fallback_used=true` means Everything was unavailable or failed and the wrapper
searched only within the provided root with a scoped fallback.
