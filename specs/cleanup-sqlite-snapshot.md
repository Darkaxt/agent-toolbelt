# Cleanup SQLite Snapshot Repair

## Scope

Repair the installed transactional cleanup failure shown by the user. Both live
failures occurred in apply -> _flush_results while saving a batch, after some
deletion had succeeded. Do not retry the revoked Gradle ticket, delete residual
caches, modify the one-off supervisor, or touch installed application data.
Deploy the verified helper/skills to Codex, agents and Claude and sync GitHub.

## Requirements

- S1: Reproduce an independent SQLite writer committing between apply batches;
  preserve evidence of SQLITE_BUSY_SNAPSHOT rather than assume an active owner.
- S2: No SELECT cursor/read snapshot may survive filesystem work or an apply
  checkpoint. Fetch bounded, fully exhausted candidate pages; keep exact signed
  membership, stable child-before-parent order, retry/result accounting and all
  deletion protections. Never materialize the complete manifest in memory.
- S3: Preserve disjoint target concurrency, lock-free status, reviewed tickets,
  dry runs and existing partial-apply behavior. No sleeps, deadlines, timeout
  increases, whole-operation global lock or speculative retry loop.
- S4: SQLite failures must return structured diagnostics instead of a traceback;
  preserve tickets/state and do not auto-revoke or bypass the helper.
- S5: Regression and installed isolated integration checks pass; source/runtime
  and all three installed skill bundles match, then commit and sync.

## Stages

1. Snapshot repair -- COMPLETE. The independent writer reproduced SQLite error
   517 (SQLITE_BUSY_SNAPSHOT) before the repair. Bounded exhausted pages, row
   integrity checks and structured failures now pass the focused and complete
   family tests, including concurrent claims, dry runs and partial retries.
2. Delivery -- COMPLETE. Version 0.4.2 is deployed to Codex, agents and Claude;
   activated-runtime hashes and all three skill bundles match repository source.
   Installed isolated concurrency/deletion probes, skill validators, family wiring
   and skills.sh validation passed. Repair commit f01dbde was pushed to GitHub.

## Verification And Reconciliation

- S1-S4: `python -B -m unittest discover -s families/transactional-cleanup/tests`
  passed; the subsequent installed integration test also verifies an independent
  SQLite writer committing between deletion pages in the activated runtime.
- S5: Root family CLI/isolation/layout tests and canonical/installed skill
  validation passed. Six focused tests were run against the actual installed
  engine, including stale snapshots, order, integrity and partial-apply retry.
- Installed production status successfully reads the historical transaction as
  revoked. No residual Gradle cache deletion or ticket reuse occurred. Active
  legacy JSON state and its recovery runtime were preserved by the installer.
- No blockers or required deferrals remain. Deleting historical residual caches
  is outside this repair and still requires a fresh reviewed snapshot and ticket.

## Diagnosis

The old apply iterator held a SELECT cursor across filesystem deletion and result
commits. An independent writer could advance WAL between checkpoints, leaving the
reader unable to promote its stale snapshot to a writer. A live competing process
need not remain present when later inspected. The deterministic regression produced
SQLITE_BUSY_SNAPSHOT; the two historical tracebacks report only "database is locked"
at the same result-flush site, not an extended code. This repair addresses the
reproduced cursor-lifecycle defect without claiming every historical lock has that
cause. No retries, timeout changes or whole-operation serialization were added.
