# codex-thread-recall

Inspect the current Codex thread's raw rollout history before doing fresh broad exploration.

This family is Codex-only. It reads the exact current thread from
`CODEX_THREAD_ID`, resolves its rollout path through the local Codex
`state_5.sqlite`, and builds a cached structured index of that thread's own
JSONL history. It does not search other threads and it does not guess by cwd or
title when exact resolution fails.

The cache lives under `CODEX_HOME/cache/codex-thread-recall/`. It is
append-aware: the first recall on a thread builds the index, later calls reuse
it, and normal thread growth only indexes newly appended newline-terminated
JSONL records. Index builds are coordinated with a per-thread lock file in that
same cache directory so concurrent callers wait briefly, reclaim stale locks,
and fail closed with `index_busy` instead of hanging indefinitely.

The installed Codex skill is self-contained by default. It prefers:

1. `AGENT_TOOLBELT_HOME` when you explicitly want to run against a development checkout
2. repo-relative source discovery when the wrapper is being run from inside an `agent-toolbelt` checkout
3. the active staged private runtime recorded in `CODEX_HOME/tools/codex-thread-recall/active.json`
4. the legacy direct `.venv` under `CODEX_HOME/tools/codex-thread-recall/.venv` only when `active.json` is absent

That means normal day-to-day use should not depend on any particular workspace checkout once the local runtime has been installed.

The helper is intentionally thread-generic. It uses broad signals such as:

- timestamps, roles, entry types, and commands
- ordinary file paths
- explicit backticked identifiers
- repos, PR numbers, commit ids, and event verbs like `published` or `merged`

It does not bake in repo-local folder names, marketplace names, or workspace-specific heuristics.

## Commands

```powershell
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall status
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall recall --profile general
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall timeline --kind shipped --group entity
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall grep --pattern "CODEX_THREAD_ID"
```

To install or refresh the private local runtime from a repo checkout:

```powershell
python families/codex-thread-recall/codex/skills/codex-thread-recall/scripts/install_codex_thread_recall_runtime.py
```

That helper now stages a fresh release under
`CODEX_HOME/tools/codex-thread-recall/releases/<stamp>/`, validates it by
running `status` against a synthetic local Codex home, and only then flips
`active.json` to the new release.

To refresh it from an installed skill while pointing at a development checkout:

```powershell
$env:AGENT_TOOLBELT_HOME='D:\path\to\agent-toolbelt'
python C:\Users\<you>\.codex\skills\codex-thread-recall\scripts\install_codex_thread_recall_runtime.py
```

Optional filters and overrides:

- `--thread-id <id>` for offline debugging or tests
- `--codex-home <path>` to override the default Codex home directory
- `recall --profile general|shipping|debug`
- `timeline --kind shipped|published|merged|pushed|installed|validated|all`
- `timeline --group entity|repo|none`
- `grep --role ... --entry-type ... --payload-type ... --after ... --before ... --include-noise`

## Output shape

- `status` resolves the current thread and rollout path.
- `recall` returns a bounded brief with summary, known facts, decisions, touched
  paths, commands, blockers, open questions, and evidence pointers.
- `timeline` returns grouped or flat event history with timestamps, excerpts,
  entities, repos, PRs, commits, and elapsed timing.
- `grep` searches the indexed current-thread history and returns bounded evidence
  instead of raw transcript dumps.

Successful indexed responses also include cache metadata:

- `index.used`
- `index.built`
- `index.stale`
- `index.entry_count`
- `index.noise_filtered_count`
- `index.appended_entries`
- `index.schema_version`
- `index.last_indexed_line`
- `index.last_indexed_offset`
- `index.built_at`
- `index.last_rebuild_reason`
- `index.lock_state`

`status` also returns additive runtime and cache diagnostics:

- `runtime.mode`
- `runtime.python`
- `runtime.release_root` or `runtime.repo_root`
- `cache.path`
- `cache.schema_version`
- `cache.entry_count`
- `cache.noise_filtered_count`
- `cache.last_indexed_line`
- `cache.last_indexed_offset`
- `cache.built_at`
- `cache.last_rebuild_reason`
- `cache.lock_state`

Failure is explicit:

- `thread_unavailable` when `CODEX_THREAD_ID` is missing or not found
- `rollout_missing` when the rollout JSONL path cannot be read
- `index_busy` when another live process still owns the per-thread cache lock after the brief wait budget
- runtime bootstrap failure when neither `AGENT_TOOLBELT_HOME`, a repo bundle, nor the private local runtime can be resolved
