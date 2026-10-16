# Context Transfer

Codex-only task-tree inventory, compact handoff coordination, verified recovery archives, manifest-bound local retirement, and conflict-safe restore.

Local storage uses `E:\Codex\ContextTransfers` (skill 0.3.3), including the CLI
default, handoffs and recovery archives. Keep live transfers in their chosen
location until completion. Completed tree relocation preserves immutable
evidence and records an old-to-current path map; verification, offline reads and
restore use the current exact archive path. Explicit non-C roots remain supported.

Skill 0.3.4 normalizes the contents: `<year>/<YYYY-MM-DD>-<activity>/Records`
holds handoffs and working evidence, while `Archives/<source-ID>/<UTC-stamp>`
holds complete immutable transactions. Multi-source records use
`Records/Sources/<source-ID>`. Pass the shared dated activity path through
`pack --transfer-directory` to keep all sources together; omitted paths derive
from the source title and UTC date. Maintenance receipts have their own
`Maintenance/<YYYY-MM-DD>-<purpose>` directory.

Skill version 0.3 adds aggregate transfer: several selected chats with different
purposes within one activity become one independent working context. Read the
skill's `references/aggregate-transfer.md` for source/owner coverage, consolidated
requirements, shared handoff and complete group acceptance. It coordinates the
existing single-source CLI with source-specific acceptance files; it does not
merge live databases or add an aggregate CLI command. Shared ancestors retain
verified recovery coverage and unselected dependents remain protected. Archive
expiry still requires separate authority. Skill version 0.3.1 makes takeover's
endpoint explicit: the selected request authorizes verified context acceptance,
necessary same-scope schedule rebinding, original archival and exact rollout
offload. Do not stop at preservation or ask for retirement again. Only an explicit
preservation-only restriction keeps the originals as working chats; requested
permanent database/conversation deletion uses thread-cleanup in that same workflow.

Skill version 0.3.2 also carries over the source chat's exact UI title (or the
user's chosen replacement name). Aggregate transfers use the shared-activity
title rule. Apply the destination name with the supported task tool and verify
its read-back before declaring takeover complete.

Both transfer modes now reconcile associated schedules through the skill's
`references/schedules.md`. Definitions and exact source bindings are preserved
separately from rollout/database archives; unresolved dependencies block source
retirement. Any authorized schedule change uses the owning tool with read-back,
preserving timing, prompt scope and notification settings. The skill update
itself changes no live schedules.

Version 0.2 includes scoped database-row evidence from the source/child tree in
the archive. The required handoff explains important database-only context and
exact recall/recovery references. Normal recall does not follow loose/moved
references or fall back to database history. Use `read-database --archive <7z>
--thread-id <id> [--table thread_items] [--pattern <term>] [--limit 10]` for bounded
offline evidence without importing it into live Codex databases. Rollout offload
does not purge those databases; permanent removal uses separate thread-cleanup.

Use an independent new destination, not a fork. Inventory reports inherited
history ancestors and surviving fork dependents separately from child agents.
Preserve necessary ancestors separately and include their exact archive/row
references in the handoff. `pack --preserve-referenced-history` permits verified
inactive ancestor preservation when surviving fork references are its only
blocker; the archive cannot issue a deletion ticket. After accepted migration,
permanent cleanup retires selected leaves before selected ancestors. Unselected
forks remain protected and can keep their ancestors non-deletable.

Inventory includes verified earlier/resumed rollout segments in both Codex
rollout roots, not only the current SQLite pointer. `threads[].rollouts` and
`rollout_count` expose coverage. Filename candidates must have matching
`session_meta.payload.id`; discovery/identity failures block retirement.
Read-only catalogs and provisional handoffs report retirement blockers without
requiring children to be terminal. Packaging and deletion remain gated.

Stale spawn edges can be reconciled with `reconcile-activity --manifest
inspection.json --activity-evidence activity.json --output reconciled.json`.
Capture explicit local task-API statuses for the source and every descendant;
see the skill's activity-evidence reference. Idle/notLoaded evidence can clear
stale edge blockers without SQLite mutation. Active, unknown or missing statuses
remain blocked. Packaging rechecks task-tree metadata and rollout identities.

The implementation follows `docs/superpowers/specs/2026-08-30-context-transfer-design.md`. It remains read-only until a verified archive, destination acceptance, verified Codex archived state, and explicit live-retirement authorization permit exact-file retirement. Packing copies reviewed rollout bytes into a temporary transaction-local snapshot so 7-Zip never opens Codex's live rollout paths directly.

## Commands

```powershell
agent-toolbelt-context-transfer inspect --source-thread-id <id> --archive-root "E:\Codex\ContextTransfers" --output inspection.json
agent-toolbelt-context-transfer catalog --manifest inspection.json --output evidence-catalog.json
agent-toolbelt-context-transfer validate-handoff --manifest inspection.json --handoff CONTEXT_TRANSFER.md
agent-toolbelt-context-transfer validate-acceptance --manifest inspection.json --handoff CONTEXT_TRANSFER.md --acceptance destination-acceptance.json
agent-toolbelt-context-transfer pack --manifest <activity>/Records/inspection.json --handoff <activity>/Records/CONTEXT_TRANSFER.md --transfer-directory "E:\Codex\ContextTransfers\2026\2026-10-16-example"
agent-toolbelt-context-transfer verify --archive <thread-tree.7z>
agent-toolbelt-context-transfer issue-deletion-ticket --verification <verification.json> --acceptance <destination-acceptance.json> --archived-state <archived-state.json> --confirm-live-retirement
agent-toolbelt-context-transfer apply-deletion --ticket <deletion-ticket.json> --ticket-id <reviewed-id> --confirm-delete
agent-toolbelt-context-transfer restore --archive <thread-tree.7z>
```

The catalog stores only bounded excerpts and exact source offsets. Raw rollout JSONL remains the evidence source of truth.

## Local Runtime

Install the private staged runtime before copying the Codex skill into the active skill root:

```powershell
python families/context-transfer/codex/skills/context-transfer/scripts/install_context_transfer_runtime.py
```

The installer creates a versioned release under `CODEX_HOME/tools/context-transfer/releases`, validates the copied package, and only then atomically updates `active.json`. The wrapper does not impose a cancellation timeout on archive operations.

## Safety

- No direct SQLite mutation.
- No source-task self-summary.
- No broad or wildcard deletion.
- No archive staging on `C:`.
- No 7-Zip access to live rollout paths; verified snapshots are removed after packing or failure.
- No hard execution timeout.
- No live task archival or rollout deletion without the explicit retirement gate.
- Raw archives may contain historical secrets and must remain local and access-controlled.
