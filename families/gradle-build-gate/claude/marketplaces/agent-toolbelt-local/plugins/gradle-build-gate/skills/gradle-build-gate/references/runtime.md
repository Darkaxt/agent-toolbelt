# Runtime And Failure Boundaries

Install from the family with `python scripts/install.py`; it deploys a
content-addressed runtime under `%LOCALAPPDATA%/Tools/gradle-build-gate`
and skills into personal Codex, agents and Claude roots. Installed wrappers share
that runtime, not an editable repository dependency. `GRADLE_BUILD_GATE_HOME`
selects a runtime location; `AGENT_TOOLBELT_HOME` is an explicit development
checkout override. No background service or scheduled task is installed.

The installer registers `Darka.GradleBuildGate` using a per-user `Gradle Build
Gate.lnk` in the Start-menu Programs folder and its own HKCU AppUserModelId
DisplayName/IconUri metadata. An existing shortcut with another identity is not
overwritten. No COM activation handler or execution action is added to the toast;
the shortcut target is a hidden immediate-exit system PowerShell invocation.
Silent toast submission/removal uses a hidden Windows PowerShell/WinRT transport
with JSON on stdin, never interpolated task text as code. Its diagnostic transport
limit applies only to that optional subprocess. Notification work runs separately,
and teardown joins only after mutex/ticket release, including exceptional exits.
It never takes the build mutex, cancels Gradle or changes owner-support requests.
Use `desktop_notification` for submitted/disabled/unavailable/removal evidence;
no notification API receipt proves a banner was actually seen.

Execution tickets live under the shared local runtime's `queue/session-<id>`
directory, independent of skill/runtime-release overrides. Metadata updates use
`Local\Darka.AndroidGradleBuildQueue`; this is not a substitute for the build
mutex. Native per-ticket events broadcast head transitions and waiters re-arm
the head process-exit handle. Owner identity uses exact native FILETIME values,
not PID alone. Monotonic numbers survive clean completion. Atomic metadata
replacement prevents partial readers; corrupt metadata is not silently reset.
Cancellation before launch removes only the caller's ticket. Forced supervisor
exit wakes waiters but does not authorize launch past a surviving build.
Read-only `status.queue` may show unreclaimed dead tickets; it is not clearance.

The known-project catalog is `%LOCALAPPDATA%/Tools/gradle-build-gate/usage.json`,
independent of runtime overrides. Atomic updates use a short metadata-only
`Global\\Darka.AndroidGradleUsageCatalog.<root-hash>` mutex, not a replacement
for the session-local build gate. It stores project/home paths, wrapper versions,
explicit reservations and diagnostic timestamps, never wrapper URLs or commands.
Corrupt catalogs are not silently reset. Build-time tracking failure is additive.

`inventory` and `cleanup-plan` are read-only snapshots, not locked cleanup
transactions. They enumerate only `wrapper/dists/gradle-<version>-bin|all` and
`caches/<version>`; no whole-drive/repository scan or shared-cache sweep.
Reported sizes are logical metadata estimates, not guarantees of reclaimed disk
space. Links and incomplete scans cannot be proposed. Activity or unknown
references block proposals rather than assuming non-use.

Registration of all relevant projects and branch/offline reservations is the
agent's responsibility; the catalog is not a census of the machine. Re-read
references and activity under the build mutex before independent transactional
cleanup. These reports never delete or grant delete authority.

Python has no third-party dependencies. Retirement additionally needs the target
daemon's existing JDK with source-file execution and installed Gradle jars. The
adapter reads the authenticated registry under Gradle's registry lock; tokens
never appear in output or artifacts. The internal protocol is version-sensitive:
unknown/incompatible implementations block, never fall back to process killing.
Read-only registry probes cover installed versions, not all historical/future Gradle.
The adapter implements both Action and Consumer callback signatures and compares
the idle enum name, supporting the older 8.6 API without separate unsafe paths.
Compiler diagnostics expose only allowlisted symbols/signatures; runtime errors
expose fixed step/reason/type codes, never arbitrary exception messages or tokens.
Inspect `retirement_diagnostics` and `failure_kind` when retirement is blocked.

`run` defaults to `--retire-daemons all-idle` plus native `--no-daemon`.
Pre-build `incompatible` limits retirement to different versions/heaps; `none`
disables only pre-build retirement. Each request uses `StopWhenIdle` and
waits for the identity-checked target's native process-exit event. An external
build racing the request is allowed to finish. Active/ambiguous activity is never
forcefully stopped. Signals retain supervision during retirement too.
The same-version/same-heap policy does not promise full Gradle JVM compatibility
(other JVM flags or Java homes can also differ); use all-idle when needed.
The post-build phase waits on lifecycle events for active/ambiguous activity,
then rechecks each idle identity and retires survivors under the same mutex.
Only an empty authoritative Gradle activity snapshot establishes
`post_build_daemons.exit_verified`. The guarantee covers inspected observation
homes and the current session, not all future external launches. Explicit
`--keep-daemon` skips the post-build phase and selects native daemon reuse;
combine with `--retire-daemons incompatible` for matching reuse.
No Kotlin shutdown, new cleaner, force-kill or 120-minute timer is added.

The main OS thread owns the named mutex. Observer subprocesses are hidden and
subscribe to process exit and daemon-log changes before authoritative inspection.
Process identities include creation time. Idle classification requires an
identity-compatible log's last idle marker and no established local client
connection; inaccessible identity/socket/log evidence remains ambiguous.
Daemon logs are streamed incrementally, not judged from a fixed tail. Supply
additional observation homes for daemons using custom directories. Unknown
markers remain ambiguous; inspect the evidence instead of overriding the gate.

Failure policy is invocation-local: the helper explicitly supplies
`GRADLE_GATE_COLLECT_ALL_FAILURES` to the Gradle client environment; the init
script configures native Test.failFast and never suppresses test failure status.
An inherited environment value cannot silently opt out. Use the explicit helper
flag before `--` for a complete failure census. This is early stopping, not forced
process cancellation. Already-dispatched tests can finish; hangs with no reported
failure are not detected. Missing configuration-time test markers (including
configuration-cache reuse) leave policy verification false. Bounded console
failure evidence is not an authoritative event channel or a cancellation trigger.

Owner support records live beside the session FIFO metadata under `support/` and
include the exact supervisor/wrapper identities, log, observed task/test, current
request, notification receipt state and independent owner response. They contain
local diagnostic evidence, not source deliverables. Task/test progress is observed
from native console lifecycle output (test logging includes typed TestLogEvent
values and remains configuration-cache compatible); unknown fields stay null.

The finite diagnostic quiet wait (default 300 seconds) only schedules support.
The control loop uses a native response event and keeps handling responses while
notification/JVM diagnostics run separately. A continue reply rearms diagnostics
without incrementing progress. There is no age-based cancellation or ticket expiry.
CLI `support`, `respond` and `cancel` do not acquire the build mutex or enter FIFO.
Responses require the current request and reason; stale/replied/completed records
are refused. Cancellation is rechecked against progress before being handled.

Codex notification calls the installed bundled MCP with executor task metadata,
omitting model overrides. Acceptance is not acknowledgement; transport failure or
unknown delivery does not free the build gate. Every client must continue reading
the owned tool-session stream. Claude's ListAgents/SendMessage are agent tools,
not a verified standalone helper sending API; no impersonated/stale inbox is used.

The helper's `owner` probe walks only its native process ancestry, verifies each
creation identity and reads exact `<pid>.json` Claude registrations under
`CLAUDE_CONFIG_DIR/sessions` (default `~/.claude/sessions`). Registration PID and
procStart must match; only the bound session's name is used. Explicit CLI labels
win. Live Claude identity takes precedence over inherited Codex environment data;
the owner platform/session is persisted separately from the operation label.
No history scan, fuzzy project match, registration rewrite or private key read.

`watch-support --ticket <id> [--after-request <id>]` subscribes to a separate native
support-change event before reading state and waits on that event plus the exact
supervisor process handle. It emits one JSON line and exits for an actionable
request, unavailable monitor, recorded exit or proven supervisor exit. Atomic
support writes signal the event; no polling, execution deadline or build/queue
mutex is involved. Claude's Monitor tool can run this read-only waiter and deliver
its stdout as an event. Its required, rearmable diagnostic deadline may terminate
only the waiter. Keep observing the original managed build task for final results.
Use only new-release runs: older supervisors do not publish support-change events.
An emitted line proves command output, not that a live Claude model handled it.

A private hidden console contains the owned wrapper. A disposable signal process
verifies native PID/start identity and attaches only to that console to request
Ctrl+C. It never detaches the supervising agent's console. Wrapper termination is
not sufficient cancellation evidence: fresh daemon/client inspection must pass
before ownership is released. No deadline, daemon stop, force-kill or lock stealing
is used. A build that cannot cooperate remains supervised, not falsely completed.

JVM thread dumps and messaging have separate diagnostic boundaries. Expiration
stops only the owned diagnostic process, not Gradle. Read their state/errors; lack
of a dump is not proof of absence of a deadlock. Binding requires exact process
identities and reciprocal client-daemon connections; do not infer unrelated JVMs.

Each run retains its diagnostic log until it is no longer needed. Use
transactional cleanup for task-owned expendable logs after verification. Never
include these logs, credentials or Gradle caches in repository commits.

The wrapper's real exit code is returned. Ctrl+C during supervised execution
does not release the gate early: the supervisor waits for command completion.
Force-killing the supervisor cannot guarantee child termination; the next holder
must recheck survivors. Do not kill a build to obtain the mutex.

Gradle command arguments containing batch-shell control/expansion characters are
rejected. This is not authorization to work around command-policy rejection.
`--stop`, persistent/foreground execution, conflicting worker options and
project-directory redirection are rejected. Use the explicit `--project` path.

The profile init script reports actual Gradle worker/parallel/JVM settings and
test-task forks/heaps. It is invocation-local and sets one test fork. Kotlin
task-specific overrides, native jobs and emulator workloads still require
project-specific verification; the helper explicitly reports this gap. A helper
test is not a real project memory-profile acceptance test: use the next already
required focused project build, not an unrelated extra build.

## Tray Observer

The independent hidden PowerShell/WinForms observer draws a local elephant icon
and owns only its own session-scoped singleton mutex. It reads queue.json and
telemetry.json with delete-sharing so its reads do not block atomic replacement.
It never opens the execution mutex or queue metadata mutex. No startup task or
service is registered. Explicit `tray stop` requests only observer exit; the next
new request may auto-start it again. --no-tray disables telemetry for that request.

Telemetry lives beside session queue metadata, with a separate metadata mutex,
atomic JSON updates and at most 100 recent results plus cumulative counters.
It contains labels, project paths, identities, phases and timing, not commands or
environment. Final durations use monotonic timestamps; live elapsed display uses
wall time and is diagnostic only. Build time stops at wrapper exit; gate time
includes preflight/completion checks but excludes post-release toast cleanup.
No historical usage is fabricated for older installed versions. Missing or
inaccessible identity/state remains unknown. Stale exited supervisors are not
reported as successful builds. An observer is not Gradle activity inspection.

Publication is asynchronous and best effort; tray_tracking reports failures.
Optional readiness/snapshot/telemetry-collection bounds apply only to diagnostics,
never build execution or queue waiting. Collection occurs after release. Lost
telemetry is a coverage gap, not grounds for cancellation or lock manipulation.
Exit tray or stop the observer before removing obsolete runtime files it uses;
never interrupt supervising builds to update the tray.

References: [Gradle daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html),
[Kotlin compiler strategies](https://kotlinlang.org/docs/compiler-execution-strategy.html),
[Windows mutex](https://learn.microsoft.com/en-us/dotnet/api/system.threading.mutex).
