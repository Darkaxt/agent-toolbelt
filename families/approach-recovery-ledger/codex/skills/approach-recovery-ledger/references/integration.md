# Recovery-thread integration

This version is a skill/helper contract for the existing recovery implementation.
The recovered thread owns the write. Do not make the controller generate guessed
plans, retry blocked operations or silently edit model/access settings.

## Recovery sequence

1. Deliver the observed interruption and retained task context to the recovered
   thread through its existing supported recovery path.
2. The thread reads the authoritative specification, last persisted plan and
   actual results. It writes its own concrete execution plan and distinguishes
   that known intent from an unknown rejection trigger. No private reasoning dump.
3. The thread selects a stable attempt ID, prepares a private entry and invokes
   `record`. Inspect the receipt before treating the attempt as recorded.
4. Query relevant shared history and inspect full records with `show` when a
   summary leaves uncertainty. Read timestamps, program provenance, applicability
   and superseding records before proposing the next permissible approach.
5. Record the justified next decision in the entry. Later results become new
   linked entries; do not overwrite the interrupted record. If the next decision
   changes after writing, append an appropriately linked attempt with its evidence.
6. Reconcile unfinished criteria with the existing specification/stage ledger.
   Source checks, completed tool calls and partial alternatives must not silently
   satisfy an outstanding original acceptance criterion.

There is no new approval gate. Existing scope, access and safety constraints still
apply. The helper neither launches the next action nor declares it permissible.
Where recovery cannot continue, retain the affected criterion and its concrete
blocker rather than spinning through equivalent requests.

## Calling contract

```powershell
$helper = '<bundle>/scripts/invoke_approach_recovery_ledger.py'
python -B $helper --ledger 'E:/Codex/ledgers/approach-recovery/ledger.sqlite3' record --input '<private-entry.json>'
python -B $helper --ledger 'E:/Codex/ledgers/approach-recovery/ledger.sqlite3' search --query 'parser reference' --limit 10
python -B $helper --ledger 'E:/Codex/ledgers/approach-recovery/ledger.sqlite3' show --attempt-id '<id>'
```

The process returns JSON on stdout and exit 0 only for success. Failures include
`failure_kind` and sanitized errors. Important outcomes:

| Result | Caller behavior |
| --- | --- |
| `already_recorded: true` | Original immutable record exists; keep its receipt |
| `immutable_conflict` | Inspect existing ID; don't replace it; append a distinct attempt for genuinely new facts |
| `invalid_entry` | Correct the declared schema, timestamps, evidence or criteria; do not weaken the specification |
| `unknown_previous_attempt` | Resolve the actual shared-ledger ID/path; don't fabricate a link |
| `ledger_busy` | Retain original entry/ID; resolve or observe the competing writer and resubmit the same write after contention resolves |
| `unsupported_ledger` | Wrong database or schema; do not mutate Codex's own databases or perform an implicit migration |
| `ledger_io_error` / `ledger_database_error` | Diagnose the concrete storage problem; don't claim the write succeeded |

SQLite transactions make each append atomic. The helper has no busy-wait/retry
loop, stale-lock stealing or execution deadline. No file-based global mutex is
introduced. Read/search/status on a missing ledger return empty/nonexistent
without creating it. All participating threads must use the same local path.
Do not put this database on an SMB/cloud-sync share for concurrent writing.

## Acceptance fixture for the recovery implementer

Simulate a completed read-only tool call followed by a cybersecurity interruption.
Resume the thread and verify it records its actual plan, tool_outcome=completed,
attempt outcome=interrupted, exact observed interruption, unknown trigger when
unproven, original timestamps or explicit unknowns, and the original acceptance
partition. In a second thread, verify a relevant query retrieves that record.
Record a later genuinely permitted completed attempt as superseding it only when
all original criteria pass. Check that both historical records remain readable.

Run this in an isolated test ledger with fictional evidence. Do not provoke real
cybersecurity rejections, change access modes or replay a rejected operation to
test integration. This bundle has not been wired into any live recovery loop.

## Sources and limits

- User's shared design discussion: https://chatgpt.com/share/6ad0f467-ea74-83ed-8fc9-ed3bae958a33
- API program metadata: https://developers.openai.com/api/docs/guides/daybreak
- Cybersecurity error context: https://developers.openai.com/api/docs/guides/safety-checks/cybersecurity

The local Codex per-turn field `cyber_access_program` was observed during design;
its presence is client-version dependent. Missing or changed metadata must remain
unknown. API and Codex safeguards are distinct. The ledger stores observations,
not undisclosed policy versions, a definitive trigger detector or policy advice.
