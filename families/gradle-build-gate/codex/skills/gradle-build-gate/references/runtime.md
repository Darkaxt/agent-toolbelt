# Runtime And Failure Boundaries

Install from the family with `python scripts/install.py`; it deploys a
content-addressed stdlib-only runtime under `%LOCALAPPDATA%/Tools/gradle-build-gate`
and skills into personal Codex, agents and Claude roots. Installed wrappers share
that runtime, not an editable repository dependency. `GRADLE_BUILD_GATE_HOME`
selects a runtime location; `AGENT_TOOLBELT_HOME` is an explicit development
checkout override. No background service or scheduled task is installed.

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
