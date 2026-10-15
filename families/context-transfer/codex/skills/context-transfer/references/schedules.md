# Reconcile Schedules Before Retiring Their Chats

Applies to single-source and aggregate transfers. Conversation goals/queue rows,
archive status and file age do not establish scheduled-task coverage. A heartbeat
can still target a chat after its history has been accepted elsewhere.

## Discover And Preserve Associations

Use the available supported automation tools. In Codex, discover
`automation_update`; inspect `$CODEX_HOME/automations/*/automation.toml` read-only
to find candidate IDs, then use `automation_update` in view mode to verify each
matched definition through the owning application. Record unavailable access or
unknown fields as coverage gaps, not proof that no schedules exist. Do not edit
TOML directly or write raw scheduler directives as a substitute for the tool.

Check the exact source, child and necessary ancestor IDs. Distinguish:

- Direct binding: for example a heartbeat's `target_thread_id`/`targetThreadId`
  matches a history owner being migrated. This is an explicit retirement dependency.
- Explicit contextual dependency: the prompt names a source ID, source-only
  artifact, saved context or other evidence the job actually needs. Inspect that
  dependency; a mention solely documenting historical evidence need not be a live
  target. Similar title/topic alone is insufficient.
- Independent job: a standalone project/cron automation may share the activity
  without targeting or needing the chat. Preserve its existing identity and
  configuration; sharing a project does not authorize moving or deleting it.

If evidence identifies another scheduler, inspect that exact owned task through
its supported read interface. Do not assume Codex's automation inventory covers
Windows Task Scheduler or unrelated services; do not broadly collect unrelated
jobs or credentials. A known necessary scheduler that cannot be inspected remains
a source-specific coverage blocker.

Keep a private schedule ledger containing the exact automation ID/provider,
association evidence and linked source IDs; kind, target/project/environment;
prompt and working scope; rule and its authoritative timezone; status; notification
policy; and any exposed running/queued execution. Preserve returned fields rather
than guessing absent values or replacing the job with today's defaults. Keep
definitions outside Git/public handoffs where they contain private data. Reference
the exact local export/receipt paths from the handoff and record their digests.

Schedule definitions are not currently included by the scoped database/rollout
archive helper. Preserve them explicitly as separately verified private recovery
artifacts; never claim `database_evidence_verified` includes automation TOML or
another scheduler. The compact handoff must explain this separate coverage.

## Record Disposition And Authority

Assign every associated automation one explicit disposition:

| Disposition | Required evidence before source retirement |
| --- | --- |
| Keep | The job remains usable without the source; or retain the source and record that dependency as a retirement blocker |
| Retarget | Authorized exact destination and prompt/reference changes are applied through supported tooling and verified |
| Pause | Authorized pause is verified; any remaining old-thread binding must be known safe through supported lifecycle evidence, otherwise retain the source |
| Delete | Exact automation retirement is authorized, its removal is verified, and no owned execution still needs the source |

Record the user instruction providing authority and the concrete intended result.
Thread-context acceptance, source deletion authority or a request to improve this
skill does not automatically authorize schedule creation, retargeting, disabling,
merging or deletion. Reuse any existing applicable authorization. When a necessary
schedule change lacks authority, prepare the exact reviewed change first and ask
only for that missing decision; retain the source until resolved. Archiving the
chat is not a substitute for reconciling the job.

Several chats may refer to one automation: keep one identity record with every
source link. Several automations may have different responsibilities after their
chats consolidate: preserve those responsibilities unless the user explicitly
authorizes merging/removing them. Do not duplicate a job to manufacture a working
destination or replace a heartbeat with cron as a workaround.

## Apply Authorized Changes And Verify

Use the owning scheduler's supported update/delete operation, preserving all
unrequested fields. In Codex, resolve the existing ID and full current fields,
then update that automation through `automation_update`. Preserve the prompt's
actual scope, schedule/timezone, status, notification policy and execution
environment unless their change is authorized. Keep notification preferences in
their dedicated field, not the prompt. If retargeting is unsupported, record the
limitation; do not edit scheduler storage, create an unrequested replacement,
change models/providers or silently abandon the original automation.

Refresh any running/queued owner state before acting. Observe existing executions
to supported completion or an explicitly authorized cancellation; do not infer
inactivity from quiet logs, elapsed time or a paused future schedule. Do not
trigger an extra production run merely to prove the move. Apply the installed
background-automation-safety guidance when implementing local scheduled/startup
changes; this reference does not authorize creating any.

Read back the exact automation after mutation and verify its target, prompt,
schedule/timezone, status and notification policy against the reviewed result.
Confirm old live references were removed or are demonstrably harmless. A saved
export or successful update response alone is not verified schedule migration.
For deletion, verify the exact ID is absent using the supported interface and
account for its outstanding execution lifecycle.

Record before/after evidence, returned identity and residuals in the existing
source/group ledger. A reconciled inventory may support handoff acceptance while
an authorized change is still pending, but that pending dependency blocks source
retirement. Group retirement remains incomplete while any required schedule
dependency is unresolved. Report source-context transfer and schedule migration
as distinct verified outcomes; editing the skill itself performs neither.
