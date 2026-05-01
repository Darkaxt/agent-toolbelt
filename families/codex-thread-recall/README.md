# codex-thread-recall

Inspect the current Codex thread's raw rollout history before doing fresh broad exploration.

This family is Codex-only. It reads the exact current thread from
`CODEX_THREAD_ID`, resolves its rollout path through the local Codex
`state_5.sqlite`, and builds a cached structured index of that thread's own
JSONL history. Exact current-thread resolution stays the default. Opt-in
workspace expansion only includes other readable threads whose normalized `cwd`
exactly matches the current thread. It still does not guess by title or fall
back when exact resolution fails.

The cache lives under `CODEX_HOME/cache/codex-thread-recall/`. It is
append-aware: the first recall on a thread builds the index, later calls reuse
it, and normal thread growth only indexes newly appended newline-terminated
JSONL records. Index builds are coordinated with a per-thread lock file in that
same cache directory so concurrent callers wait briefly, reclaim stale locks,
and fail closed with `index_busy` instead of hanging indefinitely.

`status` is intentionally lightweight and non-mutating: it resolves the thread,
reports cache freshness/lock/collector diagnostics, and does not build or append
the index. Use `collect` to warm caches explicitly, or let `recall`, `grep`,
`timeline`, and `worklog` ensure freshness when they are the command you
actually need.

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

Phase 4 makes recall more episode-aware and more resistant to prompt/runtime noise:

- `recall` and `timeline` now default to the current active episode, not the whole thread, when a thread naturally splits into multiple work slices.
- `grep` stays thread-wide by default for backward compatibility, but can be narrowed to the current episode or a specific episode.
- instruction/meta rows, transcript-dump rows, and compaction markers are hidden from default summaries and grouped timelines unless you explicitly opt back in.
- `status` now reports episode diagnostics so you can see what `current` means before asking for recall.
- grouped entity views now rank concrete artifact anchors ahead of generic helper/runtime identifiers when both appear in the same work slice.

Phase 8 makes audit-style queries less manual:

- `grep` and `timeline` now report `returned_matches`, `total_matches`, `truncated`, and `collapsed_mirror_matches`.
- `grep` adds `--all` and explicit `--sort relevance|time-asc|time-desc`.
- `timeline` adds `--all` and explicit `--sort time-asc|time-desc`.
- `worklog` answers first/last active-work span questions directly and collapses mirrored rollout envelopes by default.
- `recall`, `grep`, `timeline`, and `worklog` can opt into `--thread-source workspace` with exact-`cwd` thread expansion and `--max-threads <n>`.

Phase 9 improves audit search quality:

- `grep` and `worklog` keep literal substring search by default and add opt-in `--query-mode fts` for SQLite FTS5/BM25 phrase, boolean, and prefix queries.
- `grep` results include match snippets and stable `entry_ref` values, and `--context <n>` returns bounded neighboring evidence around each result.
- `status` reports FTS availability, FTS row health, supported query modes, and cache health so corrupted search indexes rebuild instead of silently degrading.

Phase 10 adds portable memory bundles as an explicit separate workflow:

- `memory export` writes a distilled JSON bundle of scoped recall facts and bounded evidence excerpts.
- `memory import`, `list`, `show`, `search`, and `forget` operate only on imported bundles under `CODEX_HOME/cache/codex-thread-recall/memory-bundles/`.
- imported bundles are never searched by default by `status`, `recall`, `grep`, `timeline`, or `worklog`.
- bundles are portable context artifacts, not source-of-truth rollout history; use them only when you intentionally need distilled context outside the current thread.

The scheduled collector keeps large active threads warm outside foreground
agent commands:

- `collect` warms current, recent, or exact-workspace thread indexes without changing recall query semantics.
- collector metadata is written under `CODEX_HOME/cache/codex-thread-recall/collector/`.
- the optional Windows scheduled task runs the collector every few minutes while the user is logged in.

## Commands

```powershell
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall status
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall collect --thread-source recent --max-threads 10 --updated-within-hours 48 --max-run-seconds 90
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall recall --profile general --scope current
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall timeline --kind shipped --group entity --scope current
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall grep --pattern "CODEX_THREAD_ID" --scope thread
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall worklog --pattern "codex-thread-recall" --scope thread
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall memory export --scope current --output recall.bundle.json
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall memory search --pattern "codex-thread-recall"
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

To install or remove the optional scheduled warm-cache collector:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\<you>\.codex\skills\codex-thread-recall\scripts\install_codex_thread_recall_collector_task.ps1
powershell -ExecutionPolicy Bypass -File C:\Users\<you>\.codex\skills\codex-thread-recall\scripts\uninstall_codex_thread_recall_collector_task.ps1
```

The scheduled task uses the staged runtime's `pythonw.exe` when available so
background collection does not open console windows. If it reports
`no_console: false`, install a refreshed runtime before enabling the task.

Optional filters and overrides:

- `--thread-id <id>` for offline debugging or tests
- `--codex-home <path>` to override the default Codex home directory
- `recall --profile general|shipping|debug`
- `recall --scope current|thread|episode --episode-id episode-N`
- `recall --thread-source current|workspace --max-threads <n>`
- `collect --thread-source current|recent|workspace --max-threads <n> --updated-within-hours <n> --max-run-seconds <n> --json-log <path>`
- `timeline --kind shipped|published|merged|pushed|installed|validated|all`
- `timeline --group entity|repo|none`
- `timeline --scope current|thread|episode --episode-id episode-N --include-meta`
- `timeline --all --sort time-asc|time-desc`
- `timeline --thread-source current|workspace --max-threads <n>`
- `grep --scope current|thread|episode --episode-id episode-N`
- `grep --role ... --entry-type ... --payload-type ... --after ... --before ... --include-noise`
- `grep --all --sort relevance|time-asc|time-desc`
- `grep --query-mode literal|fts --context 0..5`
- `grep --thread-source current|workspace --max-threads <n>`
- `worklog --pattern <term> [--pattern <term> ...]`
- `worklog --query-mode literal|fts`
- `worklog --scope current|thread|episode --episode-id episode-N`
- `worklog --include-incidental [--include-noise]`
- `worklog --thread-source current|workspace --max-threads <n>`
- `memory export --scope current|thread|episode --episode-id episode-N --output <path>`
- `memory import --path <bundle.json>`
- `memory list`
- `memory show --bundle-id <id>`
- `memory search --pattern <term> --query-mode literal|fts --limit <n> --all --sort relevance|time-asc|time-desc`
- `memory forget --bundle-id <id>`

## Output shape

- `status` resolves the current thread and rollout path and reports cache freshness, collector, lock, and current-episode diagnostics without mutating the index.
- `collect` warms selected thread indexes and returns per-thread outcomes such as `already_fresh`, `appended`, `rebuilt`, `busy`, or `failed`.
- `recall` returns a bounded brief with summary, known facts, decisions, touched
  paths, commands, blockers, open questions, and evidence pointers.
- `timeline` returns grouped or flat event history with timestamps, excerpts,
  entities, repos, PRs, commits, and elapsed timing.
- `grep` searches the indexed current-thread history and returns bounded evidence
  instead of raw transcript dumps. Search results include `entry_ref` and `match`
  metadata with query mode, highlighted snippets, matched patterns, and FTS rank
  when FTS is used.
- `worklog` returns first/last logical work evidence, collapsed mirror counts,
  and a human-readable duration for one or more patterns. Literal matching stays
  the default; FTS mode is opt-in.
- `memory export` returns a `codex-thread-recall.memory_bundle.v1` JSON bundle
  with source-thread metadata, selected scope, distilled goals, decisions, facts,
  blockers, questions, shipping/debug facts, and bounded evidence excerpts.
- `memory search` searches imported bundle facts and excerpts only. It returns
  bundle id, source-thread metadata, fact/evidence type, highlighted snippets,
  matched patterns, and source `entry_ref` values when present.

Successful scoped responses also include additive scope metadata:

- `scope.requested`
- `scope.applied`
- `scope.reason`
- `episode.id`
- `episode.started_at`
- `episode.ended_at`
- `episode.entry_count`
- `episode.dominant_entities`
- `episode.dominant_repos`
- `episode.selection_reason`
- `episode.substantive_entry_count`

Workspace-mode responses also include additive thread-set metadata:

- `thread_source.requested`
- `thread_source.applied`
- `thread_source.workspace_cwd`
- `thread_source.included_threads`
- `thread_source.skipped_threads`
- `thread_source.max_threads`

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
- `cache.health`
- `cache.freshness`
- `cache.collector`
- `search.fts_available`
- `search.fts_indexed_entry_count`
- `search.fts_missing_entry_count`
- `search.query_modes`
- `search.context_max`
- `episodes.total`
- `episodes.current`
- `episodes.last_boundary_reason`
- `episodes.current.selection_reason`
- `episodes.current.substantive_entry_count`

Failure is explicit:

- `thread_unavailable` when `CODEX_THREAD_ID` is missing or not found
- `rollout_missing` when the rollout JSONL path cannot be read
- `index_busy` when another live process still owns the per-thread cache lock after the brief wait budget
- runtime bootstrap failure when neither `AGENT_TOOLBELT_HOME`, a repo bundle, nor the private local runtime can be resolved
- `invalid_memory_bundle` when an imported bundle has the wrong format, missing required fields, or a mismatched deterministic bundle id
- `memory_bundle_too_large` when an import exceeds the local bundle size limit
- `memory_bundle_missing` when `memory show` or `memory forget` targets an unknown bundle id
