# Thread recall storage maintenance

Authorization: already_authorized by the user's 2026-10-16 “Go ahead” following
the measured storage assessment. Includes implementation, installed activation,
reviewed live cache maintenance, verification and commit. Existing raw histories,
application databases, E: recovery archives and imported memory bundles remain intact.

## Requirements and acceptance

- R1: Persist compact collector diagnostics with exact skip counts by reason and
  bounded examples, without duplicate skip lists or private titles. Bound the
  collector JSONL to 16 MiB, retaining complete recent records, under a writer lock.
  Compact legacy last-run diagnostics on read. Preserve detailed collect results.
- R2: Provide read-only maintenance inventory and explicit plan/hash-bound apply.
  Evict only selected derived thread caches with unavailable registered AND cached
  rollout paths (or orphan rows with no index metadata). Recheck metadata, source
  paths and row counts under the existing per-thread lock and SQLite transaction.
  Preserve busy/changed/restored sources; access errors are not absence evidence.
  Never mutate application DBs, raw sources, recovery archives or memory bundles.
- R3: Use SQLite's native transactional VACUUM/checkpoint, with lock/error
  diagnostics; never replace a live database or kill consumers. Report actual
  file sizes, free pages, deleted entries and verification. No cancellation deadline.
- R4: Review overlapping facet/entity indexes; remove only exact nonunique prefix
  indexes whose retained composites support the same query paths. Prove lookup
  plans and preserve literal/FTS search, append indexing and evidence pointers.
- R5: Validate source and both installed skill roots plus selected runtime. Update
  collector's pinned runtime action while preserving schedule/settings. Run the
  reviewed live maintenance and verify retained recall, SQLite/FTS integrity and
  actual storage reduction. Clean task scratch through transactional-cleanup.

## Stages and reconciliation

| Stage | Status | Requirements | Acceptance evidence |
|---|---|---|---|
| Implement and verify complete storage maintenance workflow | COMPLETE | R1–R4 | Family suite passes; reviewed CLI/hash application, concurrent bounded logs, restored/moved/access-error/busy source preservation, native writer conflict, prefix lookup plans and existing literal/FTS/append contracts |
| Install, reclaim and verify live storage | COMPLETE | R5 | Live maintenance, integrity/recall/parity, scheduled completion and ticketed scratch cleanup passed |

Blockers: none. Tracked deferrals: none. All R1–R5 criteria are satisfied and
verified. Optional FTS redesign/content compression is outside scope.

Stage-one design assessment: one dedicated maintenance module uses existing
per-thread locks and native SQLite transactions. No second database, replacement
protocol, timers or generic maintenance framework introduced. No material debt
finding requiring another stage.

Live coordination: the first apply encountered a scheduled writer with zero
deletions; after that writer completed, the next apply committed 11 thread-cache
evictions (372,091 entries) before a subsequent scheduled run acquired the writer
lock. Both returned explicit SQLITE_BUSY results. Future collector launches are
temporarily paused while the current run completes; resume from fresh inventory
and restore the original enabled state in finally. No running consumer is killed.

Final integration finding: one pre-existing interrupted orphan build has 2,638
entries, no rollout_indexes completion row, and one missing FTS row. Its registered
raw history is available. R2 already authorizes orphan residue eviction; the R5
integration fix makes that case explicit and adds a raw-preservation/rebuild
regression. This is not permission to evict complete available-source caches.

## Verified live result

- Total directory: 7,602,596,197 -> 1,128,436,751 bytes at verification
  (6,474,159,446 bytes reclaimed, approximately 6.03 GiB / 85%). Normal active
  indexing can subsequently grow the derived database.
- Database: 4,108,435,456 -> 1,119,748,096 bytes; collector JSONL now
  8,280,193 bytes with a 16 MiB retention bound. Collector last-run is compact.
- Reviewed eviction: 234 unavailable-source caches plus one incomplete orphan,
  864,466 derived entries. Zero remaining eligible candidates. All 62 other
  retained entry populations were preserved; fourteen redundant prefix indexes
  were removed, with covering lookup plans verified on the live tables.
- Native VACUUM and FTS optimize completed; checkpoint returned [0, 0, 0].
  Full SQLite integrity_check returned ok, no foreign-key violations, FTS native
  integrity-check passed, and there are zero missing/orphan FTS rows.
- Live literal and FTS search both returned real current-chat evidence; cache
  health reports ok. Available orphan raw history was SHA-256 identical before
  and after eviction. Imported memory-bundle file hashes are unchanged.
- Current runtime release: 20261016-090954-574826Z. All three runtime modules
  match source, and all seven skill files match in both installed roots. Both
  installed skills validate and the revised installed guidance was reread.
- Collector uses the matching quiet pythonw runtime. Original triggers/settings
  were preserved byte-for-byte in exported XML after normalizing only the runtime
  executable. Maintenance pauses were restored in finally; enabled state is true.
- Final installed-runtime scheduled execution at 12:15:32 Europe/Bucharest
  completed with LastTaskResult=0. Post-run status remains healthy, no eligible
  candidates remain, and total storage is 1,131,152,841 bytes. Saved diagnostics
  summarize 866 skipped chats in ten examples without a duplicate list;
  serialized status is 8,936 bytes.
- Source regression suite: 116 tests passed, including interrupted orphan
  eviction followed by a real raw-source rebuild. No unrelated repository changes.
- Design assessment: native SQLite coordination remains the sole database write
  mechanism, with existing per-thread ownership locks. No unresolved design debt
  or further implementation stage is required for this scope.
- Task scratch and both rounds of setuptools build/egg-info intermediates were
  removed through reviewed transactional-cleanup tickets. All transactions are
  terminal; the exact task scratch root no longer exists. Maintained source,
  installed runtimes and required recovery/history artifacts remain intentional.

SQLite references: https://sqlite.org/lang_vacuum.html and
https://sqlite.org/queryplanner.html (prefix-index and native compaction behavior).
