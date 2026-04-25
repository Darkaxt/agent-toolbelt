# codex-thread-recall

Inspect the current Codex thread's raw rollout history before doing fresh broad exploration.

This family is Codex-only in v1. It reads the exact current thread from
`CODEX_THREAD_ID`, resolves its rollout path through the local Codex
`state_5.sqlite`, and summarizes that thread's own JSONL history. It does not
search other threads and does not guess by cwd or title when exact resolution
fails.

## Usage

```powershell
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall status
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall recall
uv run --project families/codex-thread-recall agent-toolbelt-codex-thread-recall grep --pattern "CODEX_THREAD_ID"
```

Optional overrides:

- `--thread-id <id>` for offline debugging or tests
- `--codex-home <path>` to override the default Codex home directory

Failure is explicit:

- `thread_unavailable` when `CODEX_THREAD_ID` is missing or not found
- `rollout_missing` when the rollout JSONL path cannot be read

The default recall output is a bounded brief plus evidence pointers into the raw
thread history.
