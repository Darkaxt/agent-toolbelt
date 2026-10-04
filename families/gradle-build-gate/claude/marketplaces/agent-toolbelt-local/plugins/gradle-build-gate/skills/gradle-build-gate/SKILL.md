---
name: gradle-build-gate
description: Run Windows Gradle builds and tests through a shared session-wide mutex supervisor, inspect active versus idle daemons, and apply a conservative memory profile without interrupting other builds.
license: MIT
metadata:
  version: "0.3.0"
  compatibility: Windows desktop, Python 3.11+, Windows PowerShell, project gradlew.bat, existing JDK with source-file execution; no Python dependencies.
---

# Gradle Build Gate

Use the installed helper for every subsequent Windows Gradle invocation. Do not
recreate a per-project lock or run the wrapper directly while the helper waits.
The shared name is `Local\Darka.AndroidGradleBuildGate` for all agent installs.

```powershell
python scripts/invoke_gradle_build_gate.py status
python scripts/invoke_gradle_build_gate.py run --project D:/path/android-project -- :app:testDebugUnitTest
```

`status` is read-only and never launch clearance. `run` acquires the mutex before
inspection and holds it through command exit. Active or ambiguous existing
clients/daemons cause event-driven waiting. A tool's yielded command/session is
still running: wait for it; do not abandon it, launch another build, kill owners,
or replace the wait with a deadline. An abandoned mutex triggers reinspection.
The helper never decides that low CPU or old logs prove inactivity.

## Blocking Execution Gate

`run` is the request-and-wait interface. Launch it ONCE with the intended Gradle
command. It registers a monotonic FIFO ticket, waits on native turn/owner-exit
events, then acquires the shared mutex; do not poll
`status`, retry the launcher, or run Gradle directly while waiting. Once acquired,
the gate is held through existing activity, retirement, and build completion.

If the agent command tool yields a still-running session, retain that session and
wait for its completion using the tool's session-wait interface. A yielded tool
response is not a failed, canceled, or abandoned build request. Do not impose a
shell timeout that kills the waiting supervisor. Normal final output contains the
actual build result and `queue_ticket`. FIFO is guaranteed in registration order
among updated participating helpers in this Windows session. Older launchers and
Studio do not join automatically. Tickets remain held through supervision; dead
owners are reclaimed only from proven exit or exact PID/start identity mismatch.
Unknown identity or corrupt queue state blocks, never expires or steals a turn.
`status.queue` is read-only diagnostics. Observer reinspection follows events.

## Daemon Retirement

The default `--retire-daemons incompatible` retires confirmed-idle Gradle daemons
whose version or maximum heap differs from the next wrapper/profile. Matching
daemons remain reusable. Use `--retire-daemons all-idle` before `--` to retire all
confirmed-idle Gradle daemons before a build; `none` preserves previous retention.
Do not add an independent timed cleaner or wait 120 minutes inside this helper.

Retirement holds the same gate, reinspects activity, verifies native PID/start
identity and authenticated registry idle state, requests `StopWhenIdle`, and waits
for actual process exit. A racing external build can finish without cancellation.
Never substitute `gradle --stop`, taskkill, Stop-Process, or broad Java termination.
Unknown registry/distribution/JDK protocol blocks the build; diagnose it rather
than bypassing the guard. Custom wrapper names require `none` until their version
is explicitly supported. Inspect `daemon_retirement` in the final result.
Gradle 8.6 and newer callback/idle-state variants are handled. An
`adapter_compilation_failure` means no adapter shutdown request was sent, not
that a build is active. Inspect sanitized `retirement_diagnostics`; never bypass
compatibility failure with force termination or immediate shutdown.

This is pre-build retirement, not zero retention after every build. Kotlin
compiler daemons, workers, unrelated Java, and separate cleanup tasks are outside
its scope. `--no-daemon` after `--` remains available when no Gradle reuse is wanted;
Gradle's single-use daemon then exits after its build. No global settings change.

## Resource Profile

Defaults: two workers, no parallel projects, 3 GB Gradle and Kotlin daemon heaps,
one test fork per test task. Required other JVM flags are preserved; excessive
initial heaps and inherited conflicting settings need explicit resolution.
The helper does not edit project or global configuration.

Preserve the project Kotlin strategy unless its plugin/version has been assessed.
Only then use `--kotlin-strategy in-process` before `--`; it shares Gradle's heap.
Larger heaps require `--gradle-heap-gb` or `--kotlin-heap-gb` and
`--memory-reason` documenting the actual diagnosed memory failure.

Native tools receive `CMAKE_BUILD_PARALLEL_LEVEL=2` and a two-job Make budget.
Those environment hints are not proof that Android plugin/Ninja/custom tasks
honor them. Inspect the next required build's native commands and task-specific
Kotlin/test overrides; apply narrowly scoped project-specific controls when
needed. Do not invent a total-host memory guarantee or disable verification.

## Evidence And Coordination

Build output streams to stderr and a unique local log; stdout ends with JSON.
Inspect `gate_acquired`, `exit_code`, `requested_profile`, `observed_profile`,
`gradle_profile_verified`, `memory_failure_evidence`, and `verification_gaps`.
Missing profile markers do not prove effective settings. Report actual evidence.
For another Gradle home use repeated `--observe-home D:/path/gradle-home`.

Android Studio and other nonparticipating launchers are not automatically locked.
Inspect them and coordinate their subsequent launches; never claim universal
exclusion from a process snapshot. No builds in other Windows sessions are
covered by this Local mutex. Do not interrupt any current build or broaden work.

Read [runtime details](references/runtime.md) for installation, unusual daemon
states, shell argument restrictions, logging or supervisor interruption behavior.
