# Runtime And Failure Boundaries

Install from the family with `python scripts/install.py`; it deploys a
content-addressed runtime under `%LOCALAPPDATA%/Tools/gradle-build-gate`
and skills into personal Codex, agents and Claude roots. Installed wrappers share
that runtime, not an editable repository dependency. `GRADLE_BUILD_GATE_HOME`
selects a runtime location; `AGENT_TOOLBELT_HOME` is an explicit development
checkout override. No background service or scheduled task is installed.

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

`run` defaults to `--retire-daemons incompatible`: different version or heap is
retired after fresh idle evidence. `all-idle` retires all confirmed-idle Gradle
daemons; `none` preserves previous behavior. Each request uses `StopWhenIdle` and
waits for the identity-checked target's native process-exit event. An external
build racing the request is allowed to finish. Active/ambiguous activity is never
forcefully stopped. Signals retain supervision during retirement too.
The same-version/same-heap policy does not promise full Gradle JVM compatibility
(other JVM flags or Java homes can also differ); use all-idle when needed.
No post-build sweep, Kotlin shutdown, new cleaner, or 120-minute timer is added.

The main OS thread owns the named mutex. Observer subprocesses are hidden and
subscribe to process exit and daemon-log changes before authoritative inspection.
Process identities include creation time. Idle classification requires an
identity-compatible log's last idle marker and no established local client
connection; inaccessible identity/socket/log evidence remains ambiguous.
Daemon logs are streamed incrementally, not judged from a fixed tail. Supply
additional observation homes for daemons using custom directories. Unknown
markers remain ambiguous; inspect the evidence instead of overriding the gate.

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

References: [Gradle daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html),
[Kotlin compiler strategies](https://kotlinlang.org/docs/compiler-execution-strategy.html),
[Windows mutex](https://learn.microsoft.com/en-us/dotnet/api/system.threading.mutex).
