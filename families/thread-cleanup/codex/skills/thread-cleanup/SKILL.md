---
name: thread-cleanup
description: Permanently retire explicitly selected inactive Codex or Claude conversations, including database history and exact session artifacts; separate from recoverable context migration or ordinary artifact cleanup.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows, Python 3.11+, installed Codex app-server and transactional-cleanup filesystem runtime. Codex and Claude.
---

# Permanent Thread Cleanup

This is irreversible conversation retirement, not ordinary cache cleanup or
context-transfer. Require explicit source-specific authority. The selected chat
and its children must be inactive; exclude current/protected chats and their
descendants. Resolve full UUIDs, never delete using shortened IDs, age, topic or
absence from a limited listing. A stale child edge is not live activity proof.
Use context-transfer first when useful context/recovery must survive on E:/Codex.
Do not invent a backup requirement for explicitly disposable conversations.

## Review And Apply

Use `scripts/invoke_thread_cleanup.py` from this installed bundle. Read the JSON
result, inspect the written plan's complete file/row inventory and record its
SHA-256 before a separate deletion invocation. Existing deletion authorization
does not require asking again; the plan/hash/exact-ID gate prevents accidental
scope expansion. Keep private plans/reports outside Git.

```powershell
python scripts/invoke_thread_cleanup.py plan --system codex --home <codex-home> --thread-id <full-id> --protect-id <preserved-id> --output <private-plan.json>
python scripts/invoke_thread_cleanup.py delete-codex --plan <private-plan.json> --plan-sha256 <reviewed-sha256> --activity-evidence <fresh-activity.json> --codex-executable <verified-codex.exe> --confirm-thread-id <full-id>
python scripts/invoke_thread_cleanup.py plan --system claude --home <claude-home> --thread-id <full-id> --protect-id <preserved-id> --output <private-plan.json>
python scripts/invoke_thread_cleanup.py delete-claude --plan <private-plan.json> --plan-sha256 <reviewed-sha256> --confirm-thread-id <full-id>
```

### Codex

Resolve the installed app-server executable and confirm its protocol exposes
`thread/delete`. The helper uses that application API for chat/history deletion,
never database replacement, VACUUM or SQL editing of conversation content.
One tested application omission has a narrow adapter: after deletion, and only
when the thread no longer exists and no queued content remains, an immediate
SQLite transaction removes its content-free `queued_thread_revisions` rows.
The exact two-column schema is required; unknown schemas fail closed. The result
reports this mutation separately. No account/model changes,
network research, generation, turn resumption or process killing is involved.

Before each application deletion, refresh owning-app status through supported
task tools. Write activity evidence with `source: codex_task_api`, `thread_id`,
`status`, `observed_at` and `plan_sha256`. Allowed inactive statuses are idle,
notLoaded, completed, failed, cancelled and closed. A second app-server's own
notLoaded state alone does not prove inactivity in the original owner. Do not
fabricate evidence from archival, file age or a quiet process.

Inspect the complete child tree, verify each child inactive, delete leaves first,
then re-plan the parent after its child edges are removed. Protect current chats,
unselected dependent chats and selected exclusions. Changed source snapshots
require a renewed plan; an application error is not permission for custom SQL.
Also inspect `fork_dependents`: these are history dependencies, not child-agent
edges. The application refuses deletion while surviving forks reference the
source. Preserve unselected/current forks; do not edit lineage headers or database
content to circumvent that refusal. Use an independently accepted replacement
chat before retiring the dependent fork, then its ancestor chain.
The replacement must be a normal new independent chat, not another fork. Use
context-transfer to preserve/accept the leaf's own and inherited database/rollout
evidence first; then delete the selected old leaf and its selected ancestors.
If an unselected fork still depends on a parent, retain that parent and report
the exact fork ID. Do not broaden authority to delete the unselected fork.

Inspect `complete`, `database_residuals` and `file_residuals`, not just the RPC
return. Actual paginated items, state rows, goals/queue/memory rows where present,
and every known rollout segment count separately. Unsupported residuals remain
explicitly incomplete. Thread deletion may free SQLite pages for reuse without
shrinking the file. Do not claim physical reclamation or run live compaction.
After application deletion, the helper also invokes the installed recall
helper's `purge-thread-cache` under its existing per-thread lock. Inspect the
`recall_cache` result; an unavailable/outdated runtime is not successful cleanup.
The application deletes its current rollout pointer but may retain older resumed
segments. After all selected app rows are gone, the helper removes only remaining
reviewed rollout names through the same identity/hash-bound Windows primitive.
No wildcard deletion is performed; changed/new files are not swept up. This
addresses a tested lifecycle omission, not an execution-policy denial workaround.

Storage coverage is the live state, paginated history, goals, queue and memory
databases, reviewed rollout segments and the derived recall index. This is not
forensic erasure: diagnostic logs, independent historical database backups,
exports and user-retained recovery archives are not conversation stores and
must not be swept up. Identify separate retained copies when relevant; never
claim every historical trace or physical SQLite allocation has disappeared.

### Claude

The helper inventories the exact project's `<session-id>.jsonl`, owned subagent
tree, file-history/session-env/tasks directories, exact debug file and warning
sidecar. It rechecks current registrations and explicit process command references,
including forks still reading the selected history. No force-closing sessions.

Matching shared history/index records are filtered under an exclusive Windows
file handle; unrelated rows survive. Unsupported index formats or sharing
failures are real residuals, not reasons to rewrite entire profiles. Exact file
removal reuses the installed cleanup runtime's identity/content-bound Windows
handle primitive. Historical conversation retirement has its own explicit plan
gate; do not falsely register it as task-generated trash to bypass normal rules.

Never touch credentials, settings, plugins, shared memory, source repositories,
other sessions, daemon authentication material or arbitrary referenced files.
Empty owned directories may be removed; there is no recursive deletion sweep.
Reviewed hard-linked history names may be unlinked without altering another link
name or its contents. If a partial operation has already removed the main history,
use `delete-claude --resume` with the same reviewed plan/hash/ID to retry only its
original exact residuals. New files survive; changed identities/content remain
skipped and require a new attributable review, never a directory sweep.
Report exact residuals, distinguish sharing/ACL errors from tool-policy denial,
and never use another method to evade a rejected operation.
