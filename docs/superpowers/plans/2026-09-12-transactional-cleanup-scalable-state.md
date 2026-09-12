# Transactional Cleanup Scalable State

## Authoritative Specification

`../specs/2026-08-03-transactional-cleanup-design.md` is authoritative. This plan
implements its targeted-discovery, normalized-state, bounded-durability, and
observable-progress requirements without weakening exact snapshot deletion.

## Stages

| Stage | Status | Acceptance Criteria | Blockers | Tracked Deferrals |
| --- | --- | --- | --- | --- |
| Normalized discovery and review | COMPLETE | SQLite WAL state; streaming baseline/review; workspace-only default; explicit broad-root opt-in; immutable signed manifest; bounded paginated inspection | None | None |
| Ticket, apply, and progress | COMPLETE | Tickets reference exact candidate rows; batched durable results; crash-safe retry; lock-free incremental status; compact terminal retention; explicit exact-name hard-link and leaf-reparse authority | None | None |
| Integration and deployment | COMPLETE | CLI, wrappers, docs, skills, legacy-state handling, focused/root/installed verification; committed repo state; Codex and Claude installs use the new release | None | None |

## Requirement Mapping

- Stage 1 owns storage normalization, bounded-memory discovery/review, root selection,
  row integrity, and review inspection.
- Stage 2 owns ticket integrity, exact application, batching, interruption recovery,
  progress visibility, and retention.
- Stage 3 owns compatibility surfaces, guidance, installation, and final integrated
  verification.

## Completion Rule

Only one stage is ACTIVE. A stage advances only after fresh verification of every
listed criterion. There are no required deferrals: all three stages must be COMPLETE
before the implementation is delivered as complete.

## Final Reconciliation

All authoritative requirements are satisfied with zero blockers and zero tracked
deferrals. The installed acceptance workflow used the v2 wrapper to review, inspect,
ticket, dry-run, and apply an exact hard-linked build output. The ticketed name was
removed, an unticketed external hard link remained readable, terminal details were
compacted, and a second reviewed ticket removed the task-owned fixture. Bare status
reported the completed operation from the normalized database, which was 84 KiB.

Codex, Agents, and Claude installs have identical v0.2.0 skill and wrapper hashes.
The installer found active v1 JSON state and retained the prior runtime plus launcher
routing for those exact legacy identifiers; new transactions use v2. No legacy state
was deleted or silently converted during deployment.
