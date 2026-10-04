---
name: gradle-build-gate
description: Run Windows Gradle builds and tests through a shared session-wide mutex supervisor, inspect active versus idle daemons, and apply a conservative memory profile without interrupting other builds.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows desktop, Python 3.11+, Windows PowerShell, project gradlew.bat; no Python dependencies.
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
