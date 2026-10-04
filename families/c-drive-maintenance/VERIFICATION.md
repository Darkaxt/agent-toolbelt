# Verification and Reconciliation

- Streaming fixtures cover comma-containing paths, RidNacs drive root spelling,
  parent/child rollups, invalid/nonlocal paths and conflicting duplicate rows.
- Real user-supplied export parsed read-only; estimates grant no deletion authority.
- Installed transactional-cleanup fixture demonstrates reviewed removal and
  preservation of a concurrently created file. Protocol failures retain IDs.
- Native/shared targets are rejected by the generic adapter, including candidate
  manifests supplied to application. Only explicit disposable outputs are allowed.
- Isolated installation tests execute all three personal wrappers without repo
  bootstrap. Actual installed skill files match canonical hashes and validate.
- Owner prompt is explicit, compatible, verification/commit-bound and unsent until
  the agent uses its existing task API. No new task, scheduler or background worker.
- Root CLI/layout/isolation checks and local skills.sh discovery passed.
- Gradle cleanup-plan and skill regression checks confirm cleanup does not reserve
  the build gate. Build serialization and confirmed-idle retirement are unchanged.
- Cleanup installer tests preserve active legacy recovery runtimes and reject
  redirected deployment paths. Existing transaction evidence was not removed.

Scope distinction: this delivers the active operator skill and helper, not a
completed maintenance run against a user's live system. Real migrations, cache
retirement and app/WSL lifecycle actions require fresh consumer evidence when the
skill is invoked. Codex paginated database retirement is not implemented or
claimed; rollout offload must not be described as full database reclamation.

GitHub synchronization is checked after the final commit. No export, authentication
state, session content or personal maintenance ledger is included in this package.
