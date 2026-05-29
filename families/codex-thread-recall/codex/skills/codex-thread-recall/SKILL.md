---
name: codex-thread-recall
description: Use `scripts/invoke_codex_thread_recall.py` to inspect the current Codex thread's own raw rollout history before broad repo or web exploration on long-running or resumed work.
license: MIT
metadata:
  version: "0.1.0"
---

# Codex Thread Recall

Use `scripts/invoke_codex_thread_recall.py` when long-running or resumed work risks re-researching things this same thread already knew before context compactions.

Compatibility: Codex only. Requires `CODEX_THREAD_ID`, local Codex `state_5.sqlite`, and readable rollout JSONL files.

## Workflow

1. For normal resumed work, run `recall --profile general --scope current` directly. Do not chain `status; recall` in one shell command.
2. Run `status` only when you need diagnostics, or after `recall` returns `index_busy`, `thread_unavailable`, or `rollout_missing`.
3. Check `status.cache.freshness`, `status.cache.lock_state`, and `status.cache.collector` when deciding whether the collector has already warmed the cache.
4. If the question is about prior shipped or merged work, run `timeline --kind shipped --group entity` first.
5. Run `recall --profile general|shipping|debug` to get a bounded brief with decisions, known facts, touched paths, commands, blockers, open questions, and evidence pointers into the rollout JSONL.
6. If one detail is still missing, run `grep --pattern <term>` with structured filters against this same thread before looking elsewhere.
7. If the question is “when did we work on X?” or “what was the first/last span for X?”, use `worklog --pattern <term>` instead of hand-assembling a grep span.
8. If you need broader operational context from the same workspace, opt into `--thread-source workspace --max-threads <n>`; this only includes threads whose normalized `cwd` exactly matches the current one.
9. If you need to carry distilled context elsewhere, explicitly use the `memory` subcommands. Imported memory bundles are not searched by default and are not source-of-truth rollout recall.
10. Only do broad repo or web exploration after current-thread recall fails to answer it.

Default scope behavior:

- `recall` defaults to `--scope current`
- `timeline` defaults to `--scope current`
- `grep` stays `--scope thread` by default for backward compatibility
- `worklog` defaults to `--scope thread`
- use `--scope episode --episode-id episode-N` when you need a specific historical slice
- workspace mode is opt-in and thread-scoped only; `--thread-source workspace` coerces `--scope current` to `thread` and rejects `episode`

Noise behavior:

- default recall and grouped timelines suppress meta/instruction rows, transcript-dump rows, and compaction markers
- use `grep --include-noise` to search raw noisy rows when needed
- use `timeline --include-meta` when you intentionally want meta-only events back in the grouped output
- grouped entity timelines prefer concrete artifact anchors over helper/runtime identifiers when both appear in the same episode
- `status` now tells you why the current episode was selected and how many substantive rows it contains
- `grep`, `timeline`, and `worklog` collapse mirrored rollout envelopes so audit counts reflect logical events instead of duplicated wrappers
- `grep` and `worklog` keep literal matching by default; use `--query-mode fts` only when you need phrase, boolean, prefix, or BM25-ranked audit search
- use `grep --context <n>` with `n` from 0 to 5 when a match needs bounded neighboring evidence

Memory bundle behavior:

- `memory export` creates a portable `codex-thread-recall.memory_bundle.v1` JSON file from scoped distilled facts and bounded evidence excerpts
- `memory import`, `list`, `show`, `search`, and `forget` use only imported bundles under `CODEX_HOME/cache/codex-thread-recall/memory-bundles/`
- normal `status`, `recall`, `grep`, `timeline`, and `worklog` calls never query imported bundles
- use memory bundles only when an explicitly portable, distilled context artifact is needed; prefer source-thread recall when the rollout is available

The helper keeps an append-aware cache under `CODEX_HOME/cache/codex-thread-recall/`.
The first run may build or rebuild the index; later runs should be warm and only
index newly appended committed JSONL lines. Cache mutation is protected by a
per-thread lock file in that same cache directory, so concurrent callers wait
briefly, reclaim stale locks, and avoid hanging indefinitely. If a read command
overlaps another live process and a prior cache exists, it uses that existing
stale cache with a `busy-using-stale-cache` diagnostic instead of failing with
`index_busy`. If no cache exists yet, it still fails closed with `index_busy`.
`status` is fast and non-mutating by default. It reports cache freshness and
collector diagnostics but does not build or append the index. Use `collect` to
warm caches explicitly, or let the command you actually need (`recall`, `grep`,
`timeline`, or `worklog`) ensure freshness.
The optional Windows scheduled collector runs `collect --thread-source recent`
every few minutes so large active threads stay warm outside foreground agent
calls.
The installed skill now prefers a staged private local runtime selected by
`CODEX_HOME/tools/codex-thread-recall/active.json`. The old direct `.venv`
under `CODEX_HOME/tools/codex-thread-recall/.venv` is only a legacy fallback
when no active staged release exists. Only use `AGENT_TOOLBELT_HOME` when you
explicitly want to run against a development checkout instead of the local
runtime.

## Commands

```powershell
python scripts/invoke_codex_thread_recall.py status
python scripts/invoke_codex_thread_recall.py collect --thread-source recent --max-threads 10 --updated-within-hours 48 --max-run-seconds 90
python scripts/invoke_codex_thread_recall.py recall --profile general --scope current
python scripts/invoke_codex_thread_recall.py timeline --kind shipped --group entity --scope current
python scripts/invoke_codex_thread_recall.py grep --pattern "CODEX_THREAD_ID" --scope thread
python scripts/invoke_codex_thread_recall.py worklog --pattern "codex-thread-recall" --scope thread
python scripts/invoke_codex_thread_recall.py memory export --scope current --output recall.bundle.json
python scripts/invoke_codex_thread_recall.py memory search --pattern "codex-thread-recall"
```

Optional overrides:

```powershell
python scripts/invoke_codex_thread_recall.py status --thread-id <thread-id>
python scripts/invoke_codex_thread_recall.py recall --codex-home C:\temp\codex-home
python scripts/invoke_codex_thread_recall.py recall --profile shipping --scope episode --episode-id episode-3
python scripts/invoke_codex_thread_recall.py timeline --kind installed --group entity --scope thread --include-meta
python scripts/invoke_codex_thread_recall.py timeline --kind shipped --group none --all --sort time-desc --scope thread
python scripts/invoke_codex_thread_recall.py grep --pattern "PR" --role assistant --after 2026-04-25T00:00:00Z --scope current --sort time-desc
python scripts/invoke_codex_thread_recall.py grep --pattern '"audit search" AND artifact*' --query-mode fts --context 2
python scripts/invoke_codex_thread_recall.py worklog --pattern '"audit search" AND artifact*' --query-mode fts
python scripts/invoke_codex_thread_recall.py worklog --pattern "codex-thread-recall" --thread-source workspace --max-threads 5
python scripts/invoke_codex_thread_recall.py collect --thread-source workspace --max-threads 5
python scripts/invoke_codex_thread_recall.py memory import --path recall.bundle.json
python scripts/invoke_codex_thread_recall.py memory list
python scripts/invoke_codex_thread_recall.py memory show --bundle-id <bundle-id>
python scripts/invoke_codex_thread_recall.py memory forget --bundle-id <bundle-id>
```

Refresh the private local runtime after repo updates:

```powershell
python scripts/install_codex_thread_recall_runtime.py
```

That helper stages a fresh release under
`CODEX_HOME/tools/codex-thread-recall/releases/<stamp>/`, validates it by
running `status` against a synthetic local Codex home, and only then flips
`active.json` to the new release.

From an installed skill, point the refresh helper at a development checkout:

```powershell
$env:AGENT_TOOLBELT_HOME='D:\path\to\agent-toolbelt'
python scripts/install_codex_thread_recall_runtime.py
```

Install or remove the optional scheduled warm-cache collector:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_codex_thread_recall_collector_task.ps1
powershell -ExecutionPolicy Bypass -File scripts/uninstall_codex_thread_recall_collector_task.ps1
```

The scheduled collector should report `no_console: true`; it uses `pythonw.exe`
from the staged runtime to avoid opening console windows. If it reports
`no_console: false`, refresh the runtime before enabling the task.

## Rules

- Current thread first. Only use `--thread-source workspace` when broader same-`cwd` context is explicitly useful.
- Do not chain `status; recall`; run `recall` directly for normal resumed work.
- Fail closed if `CODEX_THREAD_ID`, the thread row, or the rollout file cannot be resolved exactly.
- Treat `thread_unavailable` or `rollout_missing` as recall unavailable; do not guess from cwd or title.
- Use the evidence pointers for recall, not raw transcript dumping.
- Check `index.built`, `index.stale`, and `index.appended_entries` when you need to
  understand whether a call rebuilt, reused, or incrementally extended the cache.
- Check `returned_matches`, `total_matches`, `truncated`, and `collapsed_mirror_matches` on `grep`, `timeline`, and `worklog` before assuming you saw the full audit trail.
- Check `match.snippet`, `match.matched_patterns`, and `entry_ref` on `grep` and `worklog` evidence before expanding to raw rollout inspection.
- Do not treat memory bundles as implicit recall. They are opt-in portable summaries and must be queried through `memory search` or inspected through `memory show`.
- Use `status` when you need runtime and cache diagnostics such as
  `runtime.mode`, `runtime.release_root`, `cache.last_rebuild_reason`,
  `cache.lock_state`, `cache.health`, `cache.freshness`, `cache.collector`, `search.fts_available`,
  `episodes.total`, `episodes.current.selection_reason`, or
  `episodes.current.substantive_entry_count`.
- Treat timeline/entity extraction as generic helper logic based on explicit identifiers, paths, repos, PRs, commits, and event verbs. Do not assume local repo layouts or marketplace names.
- If the wrapper cannot find either the private runtime or an explicit development checkout, stop and repair the runtime instead of guessing at another repo path.
- This family is Codex-only in v1; there is no Claude/plugin parity.
