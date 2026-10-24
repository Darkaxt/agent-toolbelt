# Rejection register

This ledger is also the shared cybersecurity rejection register. Use the
existing private database and immutable `record`, `search` and `show` operations;
there is no second store or schema. Read [entry.md](entry.md) for required fields.
Do not copy an entire private transcript into the ledger.

## When and what to record

After an observed cybersecurity rejection, the resumed chat records the actual
attempt before selecting further related work, when permitted execution is
available. Record a policy denial from another layer when it materially affects
the approach. Ordinary compiler/transport failures must not be called cyber
rejections; unknown layers stay unknown. No automatic backend hook is installed,
and a blocked response may be unable to write until recovery.

- `plan`: actual objective, scope, method, steps, intended next action and all
  original acceptance criteria. Do not reconstruct private reasoning or guess
  the trigger. Put useful, non-sensitive operation terms in method/applies_when
  so related chats can find the entry.
- `execution`: actual tool outcome and scoped evidence references. Use `not_run`
  only when evidence establishes denial before launch; a successful tool call
  followed by rejected generation remains `completed`. Unknown stays `unknown`.
- `interruption`: observed `cyber_policy`, `model_refusal`, `tool_policy` or
  `unknown` kind, exact code and concise message after necessary secret redaction.
  Identify redaction and retain a protected original reference where available.
  Separate confirmed rejection from unproven cause. Unknown cause is null.
- `attempted_at`/`interrupted_at`: original evidenced times or null with unknown
  provenance. `recorded_at` is receipt time, never an invented attempt time.
- `context`: original client/model and evidenced program metadata, otherwise
  unknown. Full access, a UI preference or model name is not program attestation.
- `satisfied_criteria`/`outstanding_criteria`: preserve every criterion exactly;
  interruption does not erase successful work or satisfy unfinished verification.
- `next_decision`: justified independent permitted work, a permissible alternative
  or a pause with its concrete resolution condition. Old records are evidence,
  not authority to repeat a denied procedure.

The `execution.evidence` list can link an Inspector report, exact-command digest
receipt and the original rejection separately. Inspector output is a local
simulation, not proof of Guardian/backend policy or the original trigger. A
no-match result or later success does not annul the original denial.

## Search, receipt and follow-up

Use the installed helper's `search --query '<specific objective/method terms>'`
and inspect relevant entries with `show --attempt-id <id>`. Read applicability,
dates, actual outcome and linked superseding records. For a cyber-only review,
inspect `interruption.kind` in the returned entries; no kind filter is claimed.
Search indexes method/lesson/applicability, not raw rejection messages.

Prepare the private v1 entry, invoke `record --input <entry.json>`, and inspect
the JSON receipt. Retain its stable attempt ID. Identical re-submission is
idempotent; changed facts require a new linked entry. An unresolved write is not
a recorded rejection. Do not insert fictional acceptance fixtures into the live
register.

Use `previous_attempt_id` and `relationship` for later outcomes. Only a verified
completion satisfying the same objective, scope and all original criteria may
`supersede` an earlier attempt; otherwise use `continuation` or `alternative`.
Preserve original evidence and never turn rejection history into an auto-retry,
global blacklist, access-program switch or policy-bypass recipe.
