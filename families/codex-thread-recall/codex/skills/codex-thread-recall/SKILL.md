---
name: codex-thread-recall
description: Use `scripts/invoke_codex_thread_recall.py` to inspect the current Codex thread's own raw rollout history before broad repo or web exploration on long-running or resumed work.
---

# Codex Thread Recall

Use `scripts/invoke_codex_thread_recall.py` when long-running or resumed work risks re-researching things this same thread already knew before context compactions.

## Workflow

1. Run `status` first to confirm the exact current thread resolves through `CODEX_THREAD_ID`.
2. Check the episode diagnostics in `status` before broad exploration. `recall` and `timeline` default to the current active episode when the thread has multiple work slices.
3. If the question is about prior shipped or merged work, run `timeline --kind shipped --group entity` first.
4. Run `recall --profile general|shipping|debug` to get a bounded brief with decisions, known facts, touched paths, commands, blockers, open questions, and evidence pointers into the rollout JSONL.
5. If one detail is still missing, run `grep --pattern <term>` with structured filters against this same thread before looking elsewhere.
6. If the question is “when did we work on X?” or “what was the first/last span for X?”, use `worklog --pattern <term>` instead of hand-assembling a grep span.
7. If you need broader operational context from the same workspace, opt into `--thread-source workspace --max-threads <n>`; this only includes threads whose normalized `cwd` exactly matches the current one.
8. Only do broad repo or web exploration after current-thread recall fails to answer it.

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

The helper keeps an append-aware cache under `CODEX_HOME/cache/codex-thread-recall/`.
The first run may build or rebuild the index; later runs should be warm and only
index newly appended committed JSONL lines. Cache mutation is protected by a
per-thread lock file in that same cache directory, so concurrent callers wait
briefly, reclaim stale locks, and fail closed with `index_busy` instead of
hanging indefinitely.
The installed skill now prefers a staged private local runtime selected by
`CODEX_HOME/tools/codex-thread-recall/active.json`. The old direct `.venv`
under `CODEX_HOME/tools/codex-thread-recall/.venv` is only a legacy fallback
when no active staged release exists. Only use `AGENT_TOOLBELT_HOME` when you
explicitly want to run against a development checkout instead of the local
runtime.

## Commands

```powershell
python scripts/invoke_codex_thread_recall.py status
python scripts/invoke_codex_thread_recall.py recall --profile general --scope current
python scripts/invoke_codex_thread_recall.py timeline --kind shipped --group entity --scope current
python scripts/invoke_codex_thread_recall.py grep --pattern "CODEX_THREAD_ID" --scope thread
python scripts/invoke_codex_thread_recall.py worklog --pattern "codex-thread-recall" --scope thread
```

Optional overrides:

```powershell
python scripts/invoke_codex_thread_recall.py status --thread-id <thread-id>
python scripts/invoke_codex_thread_recall.py recall --codex-home C:\temp\codex-home
python scripts/invoke_codex_thread_recall.py recall --profile shipping --scope episode --episode-id episode-3
python scripts/invoke_codex_thread_recall.py timeline --kind installed --group entity --scope thread --include-meta
python scripts/invoke_codex_thread_recall.py timeline --kind shipped --group none --all --sort time-desc --scope thread
python scripts/invoke_codex_thread_recall.py grep --pattern "PR" --role assistant --after 2026-04-25T00:00:00Z --scope current --sort time-desc
python scripts/invoke_codex_thread_recall.py worklog --pattern "codex-thread-recall" --thread-source workspace --max-threads 5
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

## Rules

- Current thread first. Only use `--thread-source workspace` when broader same-`cwd` context is explicitly useful.
- Fail closed if `CODEX_THREAD_ID`, the thread row, or the rollout file cannot be resolved exactly.
- Treat `thread_unavailable` or `rollout_missing` as recall unavailable; do not guess from cwd or title.
- Use the evidence pointers for recall, not raw transcript dumping.
- Check `index.built`, `index.stale`, and `index.appended_entries` when you need to
  understand whether a call rebuilt, reused, or incrementally extended the cache.
- Check `returned_matches`, `total_matches`, `truncated`, and `collapsed_mirror_matches` on `grep`, `timeline`, and `worklog` before assuming you saw the full audit trail.
- Use `status` when you need runtime and cache diagnostics such as
  `runtime.mode`, `runtime.release_root`, `cache.last_rebuild_reason`,
  `cache.lock_state`, `episodes.total`, `episodes.current.selection_reason`, or
  `episodes.current.substantive_entry_count`.
- Treat timeline/entity extraction as generic helper logic based on explicit identifiers, paths, repos, PRs, commits, and event verbs. Do not assume local repo layouts or marketplace names.
- If the wrapper cannot find either the private runtime or an explicit development checkout, stop and repair the runtime instead of guessing at another repo path.
- This family is Codex-only in v1; there is no Claude/plugin parity.
