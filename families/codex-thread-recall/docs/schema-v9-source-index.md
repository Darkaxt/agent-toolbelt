# Codex Thread Recall Schema v9 Source/Index Contract

## Goal

Schema v9 stops treating SQLite as a second transcript store. Rollout JSONL files remain the source of truth for raw evidence. The SQLite cache is a compact index that supports recall, timeline, worklog, and bounded search without permanently duplicating full rollout text.

## Storage Rules

- `entries` must not contain full `raw_text` or full `search_text` columns.
- `entries` stores stable source pointers: `rollout_path_id`, `entry_index`, `rollout_line`, `byte_start`, and `byte_end`.
- `entries` stores only compact metadata and bounded evidence: timestamp, role, entry/payload type, content class, command, noise fields, and short `excerpt`.
- Semantic facets stay normalized in facet tables: paths, blockers, retry signals, questions, goals, decisions, facts, entities, repos, PRs, commits, qualified IDs, and event kinds.
- `rollout_paths` maps integer `id` values to rollout JSONL paths so entry rows can reference source files without repeating paths.
- `entries_fts` indexes only bounded `search_text`. It must not index raw rollout text.

## Query Behavior

- Normal `recall`, `timeline`, and `worklog` use metadata, facets, excerpts, and bounded FTS search text.
- `grep` without `--include-noise` searches bounded index text and returns bounded snippets/excerpts.
- `grep --include-noise` performs raw evidence matching by reopening rollout JSONL entries with `byte_start` and `byte_end`. It does not require cached raw text.
- Raw evidence expansion is best-effort. If the rollout file is missing or moved, commands return existing semantic index evidence with diagnostics instead of inventing raw text.
- FTS mode is index-backed and searches bounded `search_text` only. Raw/noise forensic search should use literal mode so it can read rollout source entries on demand.

## Migration Behavior

- Existing v8 caches are rebuilt because they contain `entries.raw_text`, `entries.search_text`, and `entries_fts.raw_text`.
- Rebuilds parse rollout JSONL from source and persist byte offsets for each complete committed line.
- Append indexing keeps the current complete-line behavior: incomplete trailing JSONL lines are not committed until the newline arrives.

## Non-Goals

- Do not compress raw transcript blobs into SQLite.
- Do not rely on pruning to control database size.
- Do not add background crawling or cross-thread raw import.
- Do not remove source evidence pointers from user-facing grep/worklog results.
