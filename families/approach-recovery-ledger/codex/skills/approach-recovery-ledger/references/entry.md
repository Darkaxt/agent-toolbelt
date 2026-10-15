# Entry contract v1

Use a stable caller-chosen `attempt_id` (ASCII letters/digits/dot/underscore/hyphen,
maximum 80 characters). Retain it on a failed write. The helper appends an atomic
immutable record and generates `recorded_at` in UTC. Repeating identical contents
with the same ID returns the original receipt; changed contents are refused.

Start from [the fictional example](../examples/attempt.json). Required fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `thread_id` | Actual owning thread/session identity; not a guessed title |
| `attempted_at`, `attempt_time_source` | Original aware ISO timestamp and `event`, `thread_record`, `thread_report` or `unknown`; unknown requires null |
| `interrupted_at` | Original aware ISO timestamp or null when unavailable |
| `context` | Client, model (or null), observed program, source and evidence reference |
| `plan` | Actual objective, scope, method, ordered steps, intended next action and original acceptance criteria |
| `execution` | `tool_outcome`, concise actual result, and scoped evidence references |
| `outcome` | `interrupted`, `technical_failure`, `partial` or `completed`; attempt outcomes are not implementation-stage statuses |
| `interruption` | Null or observed kind/code/message and separately qualified cause |
| `satisfied_criteria`, `outstanding_criteria` | Disjoint lists that together cover every original plan criterion exactly |
| `lesson`, `applies_when` | Reusable observation and the context in which it is relevant |
| `next_decision` | `action`, rationale and concrete next step |

Times are normalized to UTC. `attempted_at <= interrupted_at` when both are
known; neither may be later than recording. Do not invent a timestamp, policy
revision or triggering action. A null attempt time is not the recovery time.
Search uses recorded_at as its ordering/filter fallback for unknown attempt times;
the returned attempt_time_source and null attempted_at make this distinction visible.

Tool outcomes are `completed`, `failed`, `not_run` or `unknown`. A tool can have
completed successfully while the attempt outcome is interrupted. If the backend
rejects subsequent generation, that is not evidence that the tool was denied.

Interruption kinds: `cyber_policy`, `model_refusal`, `tool_policy`, `transport`,
`unknown`. Preserve the observed message and code (code may be null). Set
`cause_confidence` to `confirmed`, `inferred` or `unknown`. An unknown cause must
be null; an inferred association is not a confirmed trigger. Evidence references
remain necessary even when the thread knows its actual execution plan.

`next_decision.action`: `continue_independent`, `alternative`, `pause`, `resolved`.
The rationale explains the decision within existing authority; it is not a
permission token. `completed` is refused while criteria remain outstanding.
`partial` requires outstanding criteria. Neither result certifies the whole project.

## Mode evidence

`context` requires `client`, `model`, `cyber_access_program`, `program_source`,
`program_evidence`. Optional fields: `raw_cyber_access_program` and boolean/null
`desktop_daybreak_preference`.

| Program | Display label |
| --- | --- |
| `standard` | Daybreak off; ordinary safeguards still apply |
| `daybreak_blue` | Blue |
| `daybreak_red` | Red |
| `unknown` | Unavailable/unverified |

Evidence sources are `codex_turn_context`, `responses_api`, `user_report`,
`unknown`. A user report is a report, not backend attestation. Known modes require
an explicit non-unknown source and reference. Desktop preferences, account access
and model names alone cannot establish a known effective program.

Read the interrupted turn's metadata, not merely the recovery turn's current
setting. A mode selected after interruption must not be backdated onto that
attempt. If the original mode is unavailable, record unknown. Preserve any
desktop preference separately when it conflicts with the turn metadata.

`context --input <scoped-json> --source codex_turn_context` accepts a turn_context
envelope or its payload and extracts model/cyber_access_program. For
`--source responses_api`, it extracts model/access_programs.cyber. Missing fields
stay unknown. An explicitly null access_programs on a non-error API response
means standard per the current API documentation; missing is not equivalent to
null. Error responses do not prove effective access and normalize to unknown.
Only normalized metadata is printed; unrelated response body fields are omitted.

## Linked later attempts

Optional `previous_attempt_id` and `relationship` must appear together. Supported
relationships: `continuation`, `alternative`, `supersedes`. Referenced attempts
must already exist in this shared ledger. No cross-ledger guessed references.

`supersedes` requires a completed new attempt with the same objective, scope and
original criteria. A narrower source-only success cannot supersede a native
qualification gap. Runtime/model/program and method may differ, but the later
entry must document its independently valid authority, justification and proof.
Show/search preserve the original entry and expose linked `superseded_by` IDs;
they never delete history or declare the older rejection globally invalid.

Search accepts AND-separated literal words, exact program/model/outcome filters,
an aware `--since` timestamp and `--limit 1..100` (default 20). It searches
objective, scope, method, lesson and applicability, not raw transcripts. Older
observations remain dated; nothing expires into retry authorization.

Keep entries under 64 KiB. Unsupported fields and recognizable credential/private
key patterns are rejected. This is not comprehensive secret detection: review
entries before sharing, and keep the real ledger out of Git. Evidence references
are recorded without opening their targets; helper success does not verify their
truth, authorization or completeness.
