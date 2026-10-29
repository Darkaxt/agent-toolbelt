---
name: claude-context-diagnostics
description: Inspect this Claude Code session's recorded token usage, compaction cadence and large context additions when context fills rapidly or recovery repeats.
license: MIT
metadata:
  version: "0.1.1"
  compatibility: Claude Code JSONL transcripts and Python 3.11+; local read-only diagnostics, including behind an LLM gateway.
---

# Claude Context Diagnostics

Run the bundled helper instead of reading transcript contents into context.
Current session ID supplied by Claude Code: `${CLAUDE_SESSION_ID}`.

```text
python -B <installed-skill-directory>/scripts/context_diagnostics.py report --session-id <current-session-uuid>
```

Resolve the helper relative to this SKILL.md. Personal Claude installs normally
live at `~/.claude/skills/claude-context-diagnostics`. Replace the placeholders
with actual paths/UUIDs using the current shell's quoting. If current-session
substitution is unavailable, obtain the exact ID from the session's existing
metadata or an explicit caller-provided transcript; do not guess from cwd,
title, newest file or another client's ID.

Optional `--claude-home <directory>` selects the Claude config root;
`--transcript <exact.jsonl>` selects an explicitly known transcript for the same
required session ID. `--cycles 5 --top 5` bounds detail (maximum 10 each).
`--leaf-uuid <uuid>` selects an explicit recorded conversation branch; otherwise
the latest recorded mainline leaf is used. An unresolved/partial ancestry means
the report is incomplete; inspect its warnings before drawing conclusions.
Invalid parent references cannot establish complete ancestry. Unsupported trailing
metadata does not select a new conversation leaf; unknown ancestry bridges remain
available with a warning. Invalid/out-of-range timestamps are unavailable and
disclosed, not inferred or exposed through a traceback.

Interpret the report:

- `latest_usage` is the latest recorded request, timestamped, including cached
  input exactly once. It is not a live meter, remaining budget or model capacity.
- `compactions` lists completed boundaries, recorded pre/post tokens, duration,
  elapsed time between boundaries and the first observed request input afterward.
- `largest_tool_results` measures characters, not tokens. Dense hex/assembly can
  consume much more context per line than ordinary text.
- `largest_input_growth` compares consecutive recorded request inputs within one
  compaction segment and identifies intervening tool results. Growth includes
  other request changes: it is not an exact per-tool tokenizer measurement.
- Summed usage across requests is not current context. Retained summaries,
  restored instructions/tools and cached input all still occupy context.

Use at an existing decision/checkpoint when diagnosing rapid compaction, or
after a meaningful workflow change to assess it. Do not poll after each read.
The helper writes no cache/settings/history, runs no inference, follows no
paths from tool output and exposes no raw prompts, thinking or tool contents.
Filename basenames and tool IDs are local diagnostic metadata; review before sharing.

When growth is excessive, ask a concrete question before each read, run
exhaustive mechanical checks locally and return findings with necessary
excerpts. Preserve explicit full-review coverage wherever required. Keep the
existing checkpoint concise: verified findings and evidence references,
unresolved criteria and the exact next cursor. Restore only relevant material,
while following mandatory instructions. Do not disable compaction, invent
token budgets, raise limits beyond verified capacity, or change providers.

Installing this bundle does not establish that an already-running session
has loaded it. Read this installed SKILL.md explicitly when first adopting it.
