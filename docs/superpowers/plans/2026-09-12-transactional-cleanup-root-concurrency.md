# Transactional Cleanup Root Concurrency And Git Classification

## Authoritative Specification

`../specs/2026-08-03-transactional-cleanup-design.md` is authoritative. This plan
adds root-aware operation concurrency and corrects false Git classification without
weakening exact-ticket, dangerous-path, or tracked-file protections.

## Stages

| Stage | Status | Acceptance Criteria | Blockers | Tracked Deferrals |
| --- | --- | --- | --- | --- |
| Root-aware operation claims | COMPLETE | Disjoint canonical roots may overlap in time; equal and ancestor/descendant roots return `target_busy`; dead owners leave no permanent claim; legacy runtime lock remains honored | None | None |
| Non-repository Git classification | COMPLETE | Empty `.git` marker does not exclude explicit generated output; real Git inspection failure remains fail-closed | None | None |
| Integration and deployment | COMPLETE | Focused/family/root tests pass; runtime and Codex/Claude skills deploy; Git commit and origin/main synchronize | None | None |

## Completion Rule

Only one stage is ACTIVE. All acceptance criteria, blockers, and tracked deferrals
must be resolved before completion.

## Final Reconciliation

Disjoint operation claims were verified concurrently, overlapping paths were
rejected, and a killed owner left a claim that the next process reclaimed. The
installed runtime reviewed the two real Go cache roots as 10,362 candidates totaling
1,194,555,792 bytes with zero exclusions; that proof transaction was revoked without
deletion and compacted. Real Git inspection failures remain protected. Family,
root-wiring, and all three installed-skill validations pass. No blockers or tracked
deferrals remain.
