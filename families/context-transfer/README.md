# Context Transfer

Codex-only task-tree inventory, compact handoff coordination, verified recovery archives, manifest-bound local retirement, and conflict-safe restore.

The implementation follows `docs/superpowers/specs/2026-08-30-context-transfer-design.md`. It remains read-only until a verified archive, destination acceptance, verified Codex archived state, and explicit live-retirement authorization permit exact-file retirement.

## Commands

```powershell
agent-toolbelt-context-transfer inspect --source-thread-id <id> --archive-root "E:\Codex\ThreadArchives" --output inspection.json
agent-toolbelt-context-transfer catalog --manifest inspection.json --output evidence-catalog.json
agent-toolbelt-context-transfer validate-handoff --manifest inspection.json --handoff CONTEXT_TRANSFER.md
agent-toolbelt-context-transfer validate-acceptance --manifest inspection.json --handoff CONTEXT_TRANSFER.md --acceptance destination-acceptance.json
agent-toolbelt-context-transfer pack --manifest inspection.json --handoff CONTEXT_TRANSFER.md --archive-root "E:\Codex\ThreadArchives"
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
- No hard execution timeout.
- No live task archival or rollout deletion without the explicit retirement gate.
- Raw archives may contain historical secrets and must remain local and access-controlled.
