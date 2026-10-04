# Active C-Drive Maintenance

## Authoritative Requirements

Deliver an on-demand maintenance skill for Codex and Claude, not a passive monitor.
It must reclaim verified expendable artifacts, coordinate compatible toolchain
consolidation with existing project tasks, and prevent recurring growth through
supported retention or relocation. A free-space target is a priority signal,
never deletion authority. Default target: 200 GiB, explicitly labelled.

Reuse transactional-cleanup for exact-file deletion and gradle-build-gate for
Gradle build coordination. Cleanup must NOT acquire the Gradle build mutex or
enter the build queue; use exact-target cleanup coordination and skip active or
ambiguous consumers. Correct the existing Gradle/cleanup guidance and runtime
cleanup-plan message that erroneously required this coupling. Do not introduce another deletion engine, background task,
global cleanup lock, model delegation, or arbitrary command execution mechanism.
The main agent owns native-manager actions and task coordination; the helper
supports export triage, bounded request construction, reviewed cleanup preparation
and application. It does not automatically upgrade projects from a CSV.

RidNacs exports are historical directory rollups, not an authorization manifest.
Parse the final two comma-separated columns so unquoted commas in paths work.
Never double-count ancestor/descendant totals. Recheck ownership, current size,
activity, references, recovery and offline needs before acting.

Cover Gradle caches/distributions, SDK/NDK/images, emulator snapshots, temp/build
outputs, package caches, NVIDIA download caches versus installed components,
agent histories and helper state, WSL and persistent content. Installed apps,
signing material, credentials, active worktrees, app data and system-managed
files are protected. Archive offload is not database-history reclamation.

The cleanup adapter must stop between review and application, require the exact
reviewed manifest digest, and delegate snapshot/ticket identity checks. New files
must survive. Native/shared lifecycle targets must not enter the generic adapter.
Blocked/partial cleanup retains resumable transaction details; never revoke or
switch deletion mechanisms automatically.

Dependency requests identify the actual existing owner, exact project, current
and candidate version, compatibility evidence, focused verification, commit,
exceptions and fresh usage registration. Newer is not automatically compatible.
Wait for verified completion before removing old versions. No task broadcasts,
duplicate requests or new tasks by default.

Do not run live destructive maintenance as part of developing this skill.
Use isolated fixtures, then install all three local skill copies and sync GitHub.

## Stages

| Stage | Acceptance | Status |
| --- | --- | --- |
| 1: Helper vertical slice | Streaming triage, safe request output, prepare/review/apply through installed cleanup, regression tests | COMPLETE |
| 2: Operator and integration | Action-oriented skill, lifecycle recipes, package/root wiring, installation and installed smoke | COMPLETE |
| 3: Closure | Focused/root validation, fixture cleanup, deployment parity, commit and GitHub synchronization | COMPLETE |

All stages reconcile against these requirements. No required deferrals at closure.

Stage 1 evidence: focused regression suite and installed transactional-cleanup
fixture passed. Reviewed old output removed; concurrently created file retained.
Protocol failures preserve transaction/ticket identifiers. No live data deleted.

Stage 2 evidence: isolated installed-wrapper checks passed for all three roots,
canonical/Claude bundle parity passed, and actual deployed skills validated and
matched canonical file hashes. Real RidNacs export tested read-only. Root wiring
and local skills.sh discovery passed. No maintenance request was sent and no live
cache, snapshot or project was changed. User-provided evidence exposed a policy
defect in existing Gradle cleanup guidance: fixed both agent bundles and runtime
cleanup-plan text; regression checks enforce no build-gate acquisition for cleanup.

Stage 3 evidence: focused regressions, cleanup installer checks, root wiring,
skill validation, bundle/deployment hashes and local public discovery passed.
Disposable fixtures were removed by test lifecycle; the superseded runtime made
during this task was reviewed and removed through its exact cleanup ticket.
Verified code committed as 26a3236 and pushed to its GitHub branch, with zero
ahead/behind difference. Default-branch merge and final synchronization are
delivery postconditions checked before the final completion report.

Final reconciliation: all implementation requirements above satisfied and verified;
no required blockers or tracked deferrals. Unsupported live database retirement
and universal compatibility are explicitly not claimed as implemented capabilities.

## Discovery

skills-sh-scout found a partial Windows storage skill, but source inspection was
rate-limited. Broad keyword matches to generic maintenance were not coverage
proof. No inspected alternative established the local transactional cleanup,
Gradle gate and existing-task consolidation contracts. Keep this implementation
small and reuse the already-installed domain helpers.
