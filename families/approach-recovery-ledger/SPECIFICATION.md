# Approach Recovery Ledger v0.1.0

## Authoritative requirements

Create a first shareable skill/helper for the thread implementing recovery.
The recovered thread writes its actual execution plan after recovery. No
controller integration, interception, automatic continuation or installation is
part of this version.

- R1: One private local ledger is shared across projects and agent threads.
  Read/search without creating a ledger; record durable atomic entries without
  overwriting prior attempts. Stable caller IDs make repeated writes idempotent.
- R2: Record the actual objective, scope, method, steps, intended next action,
  acceptance criteria, completed criteria, remaining criteria, evidence, observed
  execution outcome, interruption and justified next decision. This is an
  execution plan, not a request for private internal reasoning or a guessed trigger.
- R3: Keep attempted/interrupted/recorded timestamps distinct. Unknown attempt
  times stay null and explicitly unknown. Normalize supplied aware timestamps
  to UTC; generate recorded_at on durable entry creation. Preserve all history.
- R4: Record model/client and observed cyber access program independently of
  interruption type. Support standard, daybreak_blue, daybreak_red and unknown,
  with the raw mode, evidence source and reference. Desktop preferences alone
  must not establish the effective mode. Provide a read-only metadata normalizer
  for Codex turn_context and Responses API response metadata.
- R5: Search relevant cross-thread history before planning/recovery. Bounded
  exact query/filter results must expose timestamps, context and superseding
  entries. A later completed attempt may supersede an older one only while
  preserving its objective, scope and acceptance criteria. No age-based retry,
  automatic policy inference, global technique bans or cosmetic retry advice.
- R6: Keep required acceptance criteria partitioned into satisfied/outstanding.
  Interrupted does not mean technically invalid. Completed attempts cannot
  conceal outstanding criteria and never certify project completion.
- R7: Bundle one self-contained standard-library Python helper and identical
  Codex/Claude-compatible instructions. Keep private records, raw transcripts,
  sessions and credentials out of Git. Provide an integration contract and
  synthetic example; validate, commit and sync the first version.

## Compact plan

One ACTIVE stage: deliver the complete record/query/context-normalization
workflow, instructions and recovery integration contract. Acceptance covers
R1-R7; no tracked deferrals. Test meaningful entry rejection, immutable/idempotent
writes, shared database contention, timestamps, search filters, supersession and
mode evidence. Use synthetic fixtures only. Do not modify recovery code, current
providers, active skills, account configuration or live thread ledgers.

Discovery: the installed scout was run during design. Its inspected public
`ledger` candidate concerns FinOps/cloud costs, not recovery. Its automated
recommendation does not match this workflow; no public skill was installed.

## State

Stage: COMPLETE. All stage acceptance criteria passed; no unresolved blockers or
tracked deferrals. Delivery remains source-only; live recovery integration is
explicitly outside this version.

## Verification and reconciliation

- R1: Subprocess CLI record plus cross-thread search/show passed. Immutable IDs,
  idempotent receipts, contention/resumption and unrelated-database preservation
  were verified against isolated synthetic SQLite files.
- R2: Actual-plan/evidence validation and tool-success/interruption separation
  passed. The skill and integration contract assign the write to the recovered
  thread, not a controller or guessed trigger detector.
- R3: UTC normalization, unknown timestamps and invalid chronology rejection
  passed. Repeated writes preserve the original recording timestamp.
- R4: Codex/API normalization, explicit null versus absent API metadata, error
  responses, unsupported raw values and source requirements passed. No account,
  model, provider or access settings were changed.
- R5: Cross-thread literal search/filter/limit behavior and linked supersession
  passed. Supersession with weakened original criteria is rejected; the original
  observation remains readable with its later link.
- R6: Missing/overlapping criteria and incomplete completion claims are rejected.
  Instructions retain governing stage rules and distinguish attempt outcomes
  from project completion.
- R7: Standard-library bundled helper, agent metadata, references, synthetic
  example and repository discovery wiring are present. Official quick_validate
  passed; skills.sh validation discovered all 24 canonical skills locally.

Verification command: `python -B -m unittest tests.test_approach_recovery_ledger
tests.test_monorepo_layout tests.test_family_isolation tests.test_family_clis`:
50 checks passed, including 17 ledger behavior checks. These are synthetic
integration results, not a claim that live thread recovery was integrated.
Default-branch remote discovery was intentionally skipped by the existing
validator on the feature branch. GitHub branch synchronization is the delivery
step, not installation or publication of a release.

Both test scratch roots were removed through the installed transactional-cleanup
review/inspect/ticket/apply flow, with no residuals. Only source, documentation
and fictional examples belong in the commit; no private ledger or session data.
