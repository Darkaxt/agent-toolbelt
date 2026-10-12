# Generated Git Markers And Gradle Daemon Lifecycle

## Authorized Scope

Implement both fixes requested on 2026-10-13; deploy the verified helpers and
skills for Codex and Claude and sync GitHub. This specification supersedes the
matching-daemon retention default in gradle-daemon-retirement.md. No real project
build is needed solely to test this change. Existing supervisors are untouched.

## Requirements

- G1: Permit exact reviewed generated workflow-tree marker files directly inside
  a standalone checkout's internal .git directory, with explicit kind, exact-path
  confirmation, provenance and pre-existing-output authority. Never grant general
  deletion of Git metadata, objects, refs, configuration, source or directories.
- G2: Preserve snapshot/ticket semantics, file and ancestor identities, regular
  single-link checks and content hashing. New files, replacements and edited
  markers survive. The default Git protection remains unchanged.
- G3: Policy-denied deletions remain denied. Do not retry the previously rejected
  Nuvio marker through this helper; verify with fresh synthetic fixtures instead.
- D1: Default builds retire all independently verified-idle Gradle daemons before
  launch, using the existing authenticated StopWhenIdle adapter. Preserve active
  or ambiguous processes, actual exit supervision, FIFO and shared mutex.
- D2: Run Gradle with native --no-daemon by default so its single-use daemon exits
  after use. Provide an explicit --keep-daemon opt-out; reject contradictory raw
  daemon flags/properties. Preserve JVM arguments and memory budgets. Never use
  force-kill, broad Java termination, timeouts or polling delays for retirement.
- D3: Keep the gate through confirmed completion. Use lifecycle events to wait
  for residual active/ambiguous Gradle activity; request graceful retirement only
  for confirmed-idle remaining Gradle daemons. Report post-build exit verification
  and retirement failures separately from the original build result.
- D4: Kotlin compiler daemons and unrelated Java are not Gradle daemons. Preserve
  them; document the boundary and the existing assessed in-process option.
- V1: Focused negative/positive regressions, root wiring, skill validation and
  installed copy/runtime parity must pass before commit and GitHub sync.

## Compact Staged Plan

1. Git marker cleanup -- COMPLETE. G1-G3: exact-file/hash/ancestor contract,
   source/object preservation, edited/replaced marker negative controls and the
   complete cleanup family suite pass. No denied real deletion retried.
2. Gradle lifecycle -- COMPLETE. D1-D4: default native single-use lifecycle,
   all-idle preflight, event-driven post-build verification, explicit warm-reuse
   option and preserved build results pass focused checks. Existing protocol,
   FIFO, cancellation, notification and usage tests pass; real build smoke tests
   remain intentionally opt-in. A stale installed-version assertion was updated
   and its entire focused test module rerun successfully.
3. Installation and verification -- COMPLETE. V1: integrated checks, both clients,
   installed entrypoints/hashes and specification reconciliation pass. Commit and
   protected-branch GitHub delivery follow these verified implementation stages.

No required deferrals. Test fixtures stay under D:/Temp and are removed by their
test lifecycle. No original denied deletion is retried and no real build stopped.

## Verification And Deployment Evidence

- Cleanup: complete family suite passes; added exact-marker regressions also
  verify replaced ancestors, hard links and linked worktree rejection.
- Gradle: lifecycle, failure policy, cancellation, kernel/FIFO, compatibility,
  telemetry and installation checks pass. The final installed-version assertion
  was corrected and its focused module passed. Native project smoke builds remain
  intentionally unrequested; tests never interrupted a real build.
- Root CLI/isolation/layout checks pass. Six installed Codex/agents/Claude skills
  pass structural validation and match canonical files; both shared runtimes match
  source hashes. Installed CLI help exposes both new interfaces.
- Deployed cleanup 0.5.1 runtime 88b04ad7c53723dc8fd47feaabb180fe and Gradle 0.8.0
  runtime 512f3f02e4298a19. Existing supervisors retain their original runtime.
- Read-only host inspection found active Gradle 9.6.1 work and two queue tickets;
  it was preserved. No real build was launched or daemon retired for testing.
- Cleanup installer reports no deployment residuals; a recovery runtime for 16
  pre-existing legacy transactions remains intentionally retained. It is not
  task-generated expendable state and was not removed.

## Delivery Record

Implementation commit e68b093 is pushed in GitHub PR #95. Direct main push was
rejected by branch protection, so delivery uses the required pull-request/checks
route, not a protection bypass. Final merge and main parity are verified in the
task's closing report rather than predicted in this pre-merge document.

The requested NuvioDV notification was delivered through the app to task
01a091fa-f544-7942-809b-df4d7589d45f with the installed version, exact marker contract,
validation request and explicit distinction between helper eligibility and the
original execution-policy denial. No new release or build was requested there.
