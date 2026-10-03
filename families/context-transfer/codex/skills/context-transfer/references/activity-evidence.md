# Task Activity Evidence

Use actual statuses returned by `read_thread`, `wait_threads`, `list_threads` or
`list_archived_threads`. Match exact IDs and local host. Never infer a status from
an error, title, archive bit, timestamp, partial listing omission or prose summary.
If a tool cannot report a child's status, leave it unknown and stop retirement;
read-only context collection remains available.

After inspection, capture source and descendant statuses and save only this
metadata (replace all example values with verified observations):

```json
{
  "schema": "agent_toolbelt_context_transfer.activity_evidence.v1",
  "evidence_source": "codex_task_api",
  "source_thread_id": "<source ID>",
  "destination_thread_id": "<destination ID>",
  "inspection_sha256": "<SHA-256 of the exact inspection file>",
  "observations": [
    {
      "thread_id": "<source ID>",
      "host_id": "local",
      "status": "idle",
      "tool": "read_thread",
      "observed_at": "<actual ISO observation timestamp>"
    },
    {
      "thread_id": "<child ID>",
      "host_id": "local",
      "status": "notLoaded",
      "tool": "list_threads",
      "observed_at": "<actual ISO observation timestamp>"
    }
  ]
}
```

Use one unambiguous observation per task. Include recorded terminal descendants
too: a closed edge does not prove that a resumed worker is inactive. The helper
accepts exact idle/notLoaded and closed/completed/failed/cancelled/canceled states;
all other states stay blocked. Never fabricate these fields merely to pass.

```powershell
(Get-FileHash -LiteralPath '<inspection path>' -Algorithm SHA256).Hash.ToLowerInvariant()
python scripts/invoke_context_transfer.py reconcile-activity --manifest '<inspection path>' --activity-evidence '<activity sidecar>' --output '<reconciled manifest>'
```

Keep sidecar and returned manifest local. They contain no message bodies or
credentials. The archive preserves reconciliation metadata and original edge
statuses for audit. The helper verifies the task-tree fingerprint and rollout
size/mtime transitions before reconciliation and packaging; archive snapshots
also verify content hashes. No age threshold or arbitrary expiry is used.

Once verified inactive, retain all normal handoff, archive, source archival and
exact-file deletion-ticket gates. Reconciliation is not deletion authorization.
