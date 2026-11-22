---
name: everything-search
description: Deprecated. Use pathweft-monitor through LLM Coordinator for global indexed file and folder search.
license: MIT
metadata:
  version: "0.3.0"
  deprecated: true
  replacement: pathweft-monitor
---

# Everything Search — deprecated

Retired by the user on 22 November 2026. Do not install, enable or use this
skill or its historical invoke_everything.py helper for new work. Everything
has been replaced by the Pathweft indexer.

Read the installed `pathweft-monitor` skill and use its managed MCP workflow.
Discover the actual `search_files` schema; it supports indexed filename/path
queries, filters, paging and sorting. Use `get_file_details`, `list_folder`
and `get_folder_size` for metadata and cached sizes. End the owned workflow
and verify release as that skill requires.

Repository-local listings/content search still use `rg --files`/`rg`;
PATH resolution uses `Get-Command` or `where.exe`. Do not silently replace a
failed global indexed search with a partial recursive scan. Missing MCP
capabilities are reported explicitly; they do not revive this retired route.
