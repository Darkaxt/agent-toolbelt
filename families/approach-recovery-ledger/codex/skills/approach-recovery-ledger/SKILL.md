---
name: approach-recovery-ledger
description: Record actual execution plans, cybersecurity rejections and recovery outcomes in a shared private ledger; consult related attempts before selecting permitted next work. Preserves evidence and unfinished criteria without retrying denied operations or changing access programs.
license: MIT
metadata:
  version: "0.1.1"
  compatibility: Self-contained Python 3.11+ helper; same instructions for Codex and Claude.
---

# Approach Recovery Ledger

Use the shared ledger to avoid repeated dead ends while preserving real progress
and outstanding acceptance criteria. The owning chat writes the entry on an
observed rejection or **after recovery**, describing its actual execution plan: objective, scope,
method, steps and intended next action. Do not substitute a guessed triggering
command or reconstruct unavailable private reasoning.

For cybersecurity or other policy rejections, use
[the rejection-register contract](references/rejections.md). This is the same
shared ledger, not a second database. A resumed chat records observed rejections
when it can execute; no automatic backend interception hook is installed.

## Workflow

1. Before choosing an approach for relevant work, query this shared history using
   specific task/method terms. On recovery, inspect the last persisted plan and
   actual execution results, then query related attempts before replanning.
2. Write a private JSON entry following [the entry contract](references/entry.md).
   Account for every original acceptance criterion as satisfied or outstanding.
   Record commands that completed as completed even if generation was later
   blocked. A cyber interruption does not establish technical invalidity.
3. Record attempt/interruption timestamps from available events or explicit
   thread records. Unknown times stay unknown. The helper generates recorded_at;
   never use recovery time as an invented time of the original attempt.
4. Record the model and observed program: standard, daybreak_blue, daybreak_red
   or unknown. Keep its evidence source and raw value. Use `context` for scoped
   Codex turn_context or Responses API metadata. A desktop toggle, account
   entitlement, permission profile or model name alone does not prove the
   effective program. Missing evidence stays unknown, not standard.
5. Call `record --input <private-file>`, inspect its result, and retain the stable
   attempt ID. The helper rejects conflicting rewrites. For follow-up work,
   create a new entry linked to the prior ID; do not erase or rewrite history.
6. Use dated, context-matched observations to inform a concrete permissible next
   step. Record why it is justified. Do not automatically retry rejected or
   materially equivalent procedures, make cosmetic variations to avoid a check,
   switch models/access programs or interpret old age as new authorization.
   Later genuinely permitted verification can supersede a historical result
   while preserving its original objective/scope/criteria and linking the proof.
7. If no permissible alternative exists, preserve the affected criterion and
   report the unresolved limitation. Follow the governing stage/dependency rules
   for independent work or parking. Do not declare incomplete verification done.

## Shared storage and commands

The helper is [scripts/invoke_approach_recovery_ledger.py](scripts/invoke_approach_recovery_ledger.py).
Default Windows storage: `E:/Codex/ledgers/approach-recovery/ledger.sqlite3`.
Use `APPROACH_RECOVERY_LEDGER` or global `--ledger <path>` for another shared file.
Keep records outside repositories and published bundles. Never copy credentials,
raw transcripts, cookies or whole request/response bodies into an entry; reference
scoped evidence instead. The helper reads no evidence contents when recording.

```powershell
python -B scripts/invoke_approach_recovery_ledger.py status
python -B scripts/invoke_approach_recovery_ledger.py search --query 'parser reference' --limit 10
python -B scripts/invoke_approach_recovery_ledger.py search --program daybreak_blue --outcome interrupted
python -B scripts/invoke_approach_recovery_ledger.py record --input <private-attempt.json>
python -B scripts/invoke_approach_recovery_ledger.py show --attempt-id <stable-id>
python -B scripts/invoke_approach_recovery_ledger.py context --input <metadata.json> --source codex_turn_context
```

`context` reads only the supplied metadata file, never scans conversations or
changes settings. `status`/`search`/`show` do not create a ledger. On `ledger_busy`,
retain the entry and its ID, resolve/observe the concrete competing operation,
then submit the same entry; do not skip the record or invent a second attempt.
There is no lock stealing, background job or automatic retry loop.

The helper enforces schema, timestamp and acceptance bookkeeping. The thread
remains responsible for factual accuracy and permissible next work. Shared
lessons are scoped observations, not global blacklists or permission grants.
Do not turn this into a ledger update for every edit or tool call; record actual
attempt outcomes and meaningful changes of approach.

For the recovery implementer, use [integration.md](references/integration.md).
