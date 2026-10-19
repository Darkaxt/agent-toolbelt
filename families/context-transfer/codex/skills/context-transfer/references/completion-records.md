# Final takeover record gate

Run this automatically as part of finishing each selected takeover, including
aggregate takeovers. No recurring monitor or new approval checkpoint is involved.
The destination already owns the checks; it does not ask retired sources to
summarize themselves or wake other owners just to finish its own records.

First complete the existing recovery, acceptance, supported destination-title
readback, schedule reconciliation and exact retirement verification. The command
below checks their record coverage and bindings, not their semantic truth or the
authenticity of an agent-written assertion. Preserve all original receipts and
immutable archive evidence. A missing canonical filename alone does not mean a
historical migration failed: inspect its existing final/group/per-source receipts
and add a traceable summary rather than repeat successful retirement.

## Canonical activity files

Under the selected `<activity>/Records`, retain `CONTEXT_TRANSFER.md`, write
`destination-acceptance.json` and `schedule-ledger.json` (including a documented
zero-match inventory when applicable), and write `migration-result.json` with:

- `status: "COMPLETE"`, the actual timezone-aware `completed_at`, exact
  `destination_thread_id`, and `source_thread_ids` covering every selected source.
  A single source may instead use `source_thread_id`. Do not add unselected owners.
- `source_archived_verified: true` and integer `residual_rollout_bytes: 0` only
  after actual archival/retirement evidence proves them. Do not claim database
  deletion from rollout offload. Retain the original endpoint and receipts.
- `destination_title` from supported task API readback and
  `destination_title_verified: true`; `schedule_reconciled: true` only when the
  exact applicable dispositions are verified. No pending changes/dependencies.
- `remaining_migration_actions: []`; ongoing project work is recorded separately.
- `evidence`: objects containing `path` (activity-relative or exact absolute)
  and `sha256` for metadata files inside this activity. Bind at least the canonical
  handoff, acceptance and schedule ledger, plus title/retirement/recovery receipts.
  Refer to archive verification metadata rather than load large recovery payloads
  into this metadata-only gate. Historical paths remain in original receipts;
  summary references use their exact current locations and hashes.
- `sources`: one object per selected source, each with `source_thread_id`,
  `retirement_verified: true`, integer `residual_rollout_bytes: 0` and nonempty
  `evidence_paths` naming its retirement receipts from the bound `evidence` list.
  Keep identity and coverage explicit when a receipt covers more than one source.

For aggregate mode, the canonical acceptance summary has `handoff_ready: true`,
`critical_unmapped_objectives: []`, the same source set/destination and the actual
shared `handoff_sha256`. It references the authoritative per-source acceptances
and group ledger; it does not overwrite or replace them. Normal single-source
acceptance retains the existing schema and validation requirements.

Use the original completion date when already proven. If a required criterion is
only completed now, record that accurately and distinguish original source
retirement from today's final criterion. Unknown dates are not invented. Never
rewrite an original receipt to make the summary pass.

## Validate and read back

From the installed skill, using the actual destination ID:

```powershell
python scripts/invoke_context_transfer.py validate-completion --transfer-directory "<activity>" --destination-thread-id "<destination-ID>" --output "<activity>/Records/completion-validation.json"
```

Inspect `ok`, returned source/destination IDs, `completed_at`, summary digest and
bound evidence. Read back `migration-result.json` and the validation output before
the final takeover claim. A stale validation file is not success after a failed
invocation or changed input; rerun against the current records.

If validation fails, reconcile the exact record gap under the existing takeover
authority. While a required gap remains, mark the mutable migration summary
`INCOMPLETE` with the precise next action; do not leave a misleading COMPLETE
claim or redo successful deletions. Historical project deferrals are not migration
blockers. If essential context needs another current owner, messaging still needs
the user's explicit authorization; this gate grants none.
