# Claude Context Diagnostics

Version 0.1.0 is a self-contained, read-only Python skill for Claude Code's
recorded session usage, compaction cadence and large tool-result additions.
It works with native or gateway-backed sessions; it does not require the proxy.

Canonical bundle: `codex/skills/claude-context-diagnostics`. Copy the whole
folder to the personal Claude skills root. Run its `scripts/context_diagnostics.py
report --session-id <uuid>` with Python 3.11+. See SKILL.md for interpretation
and optional exact transcript/config-root/branch selection. No dependencies,
plugin, daemon, hook, network, session changes or inference are involved.

The helper selects a bounded byte snapshot and reports missing/malformed data
explicitly. It follows recorded parent ancestry and deduplicates UUID/request
records. It cannot prove the active UI branch, effective model capacity,
unrecorded thinking or exact token attribution to a tool result.

Focused verification: set `CLAUDE_CONTEXT_TEST_ROOT` to an exact task-owned
scratch folder and run `python -B -m unittest tests.test_claude_context_diagnostics`.
Fixtures are retained for reviewed transactional cleanup. Use
`python -B families/claude-context-diagnostics/scripts/release_local.py --help`
for versioned local bundle installation and hash receipts.
