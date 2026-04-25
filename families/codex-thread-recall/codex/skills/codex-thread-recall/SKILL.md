---
name: codex-thread-recall
description: Use `scripts/invoke_codex_thread_recall.py` to inspect the current Codex thread's own raw rollout history before broad repo or web exploration on long-running or resumed work.
---

# Codex Thread Recall

Use `scripts/invoke_codex_thread_recall.py` when long-running or resumed work risks re-researching things this same thread already knew before context compactions.

## Workflow

1. Run `status` first to confirm the exact current thread resolves through `CODEX_THREAD_ID`.
2. If the question is about prior shipped or merged work, run `timeline --kind shipped --group entity` first.
3. Run `recall --profile general|shipping|debug` to get a bounded brief with decisions, known facts, touched paths, commands, blockers, open questions, and evidence pointers into the rollout JSONL.
4. If one detail is still missing, run `grep --pattern <term>` with structured filters against this same thread before looking elsewhere.
5. Only do broad repo or web exploration after current-thread recall fails to answer it.

The helper keeps an append-aware cache under `CODEX_HOME/cache/codex-thread-recall/`.
The first run may build or rebuild the index; later runs should be warm and only
index newly appended committed JSONL lines.

## Commands

```powershell
python scripts/invoke_codex_thread_recall.py status
python scripts/invoke_codex_thread_recall.py recall --profile general
python scripts/invoke_codex_thread_recall.py timeline --kind shipped --group entity
python scripts/invoke_codex_thread_recall.py grep --pattern "CODEX_THREAD_ID"
```

Optional overrides:

```powershell
python scripts/invoke_codex_thread_recall.py status --thread-id <thread-id>
python scripts/invoke_codex_thread_recall.py recall --codex-home C:\temp\codex-home
python scripts/invoke_codex_thread_recall.py grep --pattern "PR" --role assistant --after 2026-04-25T00:00:00Z
```

## Rules

- Current thread only. Do not search other threads in v1.
- Fail closed if `CODEX_THREAD_ID`, the thread row, or the rollout file cannot be resolved exactly.
- Treat `thread_unavailable` or `rollout_missing` as recall unavailable; do not guess from cwd or title.
- Use the evidence pointers for recall, not raw transcript dumping.
- Check `index.built`, `index.stale`, and `index.appended_entries` when you need to
  understand whether a call rebuilt, reused, or incrementally extended the cache.
- Treat timeline/entity extraction as generic helper logic based on explicit identifiers, paths, repos, PRs, commits, and event verbs. Do not assume local repo layouts or marketplace names.
- This family is Codex-only in v1; there is no Claude/plugin parity.
