# Gradle Gate Tray Status

Authorization: the user requested a Gradle-related tray icon showing queue size,
current task/project, duration and usage statistics. Extend the existing installed
helper for Codex and Claude; preserve all gate, queue and build safety behavior.

## Requirements

- R1: One read-only tray observer per Windows login session. Use a locally drawn
  Gradle-related elephant icon, not a generic system icon. Hover shows task,
  project, phase, elapsed gate/build time, waiting requests and usage statistics;
  click opens a full readable details window. Differentiate busy/idle/uncertain.
- R2: Ownership is published only after actual mutex acquisition. Queue head is
  not ownership evidence. Distinguish queued, preflight, waiting for external
  activity, retiring, running and completion verification. Verify supervisor
  PID/start identity; dead, legacy, unreadable and uncertain state must not claim
  an active owner or global inactivity.
- R3: Statistics cover observed updated-helper requests only: finished builds,
  failures, aborted requests, total gate-held/build time and average queue/build
  time. Persist bounded recent history and cumulative counters outside repos;
  never store commands, environment, credentials or unbounded logs. Final elapsed
  metrics use monotonic time. Live wall-clock elapsed is diagnostic only.
- R4: Publish observational updates asynchronously. The tray never acquires the
  build mutex or FIFO metadata lock, modifies queue state, starts/cancels builds,
  retires daemons, or infers inactivity from elapsed time. UI refresh timers are
  display-only. Metadata/observer failures cannot change build results or delay
  release of the gate. No service, scheduled task, startup registration or network.
- R5: Auto-start on new requests; provide explicit tray start/status/stop and
  per-invocation --no-tray. Exit stops only the observer. Preserve silent toasts
  and --no-notify independently. Existing supervisors are never interrupted.
- R6: Verify pure metadata contracts, native concurrent/singleton tray lifecycle,
  hover content/icon, uncertain/dead/legacy handling and integration ordering
  without launching a real Gradle build just for this feature. Install verified
  runtime/skills, commit and sync using repository protection/check requirements.

## Stages

1. COMPLETE: observational lifecycle metadata and bounded statistics (R2-R4).
   Verify timing, errors, duplicate completion, abandoned identity and integration
   ordering. UI implementation is assigned to stage 2, not required in stage 1.
2. COMPLETE: native elephant tray, CLI/install/docs and verification (R1,R5,R6).
   Verify native observer with isolated fixture namespace, real installed status,
   unchanged mutex/queue behavior, installed hashes and clean remote sync.

## Design

Session-local telemetry lives beside queue.json, using a separate metadata mutex
and atomic JSON replacement. Writers run on a dedicated observational worker;
cleanup waits only after the build mutex and queue ticket have been released.
Diagnostic worker join is bounded independently of build execution; an unfinished
diagnostic write is reported unavailable, never grounds to cancel a build.
The tray reads queue/telemetry directly without synchronization authority. A
one-second WinForms UI timer refreshes displayed elapsed time and diagnostics; it
does not drive execution, lock expiry, cancellation or ticket advancement.
The UI uses an expanded non-activating hover card because legacy Windows Forms
native tooltip text is limited to 63 characters. Full details remain available
on click. Windows may put the icon in the notification-area overflow.

## Reconciliation

Stage 1 verified timing, bounded history, duplicate completion, unknown/dead
identities, asynchronous publication, unchanged failed-build results and release
ordering. Native isolated queue still advances when its observer raises.
No required deferrals beyond the explicit stage map.
Public scout results were unrelated code-review/crypto skills, not Gradle tray
implementations; they are not appropriate replacements for this local helper.

Stage 2 verified native singleton start/stop, launcher-independent lifetime,
actual WinForms startup with the locally drawn elephant, expanded hover content,
task/project/queue statistics, unknown and dead identities, concurrent metadata
writers, CLI routing and independent toast/tray opt-outs. The observer reads files
with FILE_SHARE_DELETE so it does not prevent atomic replacement. Legacy requests
report registered count, not a fabricated waiting count or owner.

The family regression suite passed (99 checks, 3 opt-in skips); the expanded tray
suite subsequently passed all 13 checks. Root family/isolation/layout/portability
checks passed. Installed runtime and all three personal skill bundles match source;
all installed skill structural validators passed. The actual installed observer
was started and queried outside the repo; a subsequent real request published its
queued project record without interrupting existing builds. No Gradle build was
started solely for this feature. Temporary test fixtures self-cleaned; old runtime
releases remain because active supervisors can still use them.

Final delivery follows verified stage closure: commit, protected remote integration
and clean main/origin reconciliation. Do not claim remote sync until confirmed.
