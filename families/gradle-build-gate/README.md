# Gradle Build Gate

Windows desktop Gradle supervisor and cross-agent skill. The shared
`Local\Darka.AndroidGradleBuildGate` mutex covers cooperating Codex/Claude
launchers in one login session. It is not a lockfile or an automatic Android
Studio integration.

```powershell
python scripts/install.py
python codex/skills/gradle-build-gate/scripts/invoke_gradle_build_gate.py status
python codex/skills/gradle-build-gate/scripts/invoke_gradle_build_gate.py run --project D:/path/android -- :app:testDebugUnitTest
```

The installer creates a dependency-free shared runtime and installs personal
Codex, agents and Claude skills. Installed wrappers do not need the repository.
Runtime override: `GRADLE_BUILD_GATE_HOME`; explicit development checkout:
`AGENT_TOOLBELT_HOME`. No tasks, services or visible helper windows are created.

The supervisor acquires the mutex, subscribes to process-exit and daemon-log
events, checks active/idle/ambiguous identities and connections, waits for real
transitions, and retains ownership through wrapper exit. Log markers are read
incrementally with bounded memory. Failure to observe safely blocks launch.

Default profile: two workers, no parallel projects, 3 GB Gradle/Kotlin heaps,
one test fork. Other configured JVM flags are retained. Native environment hints
limit supporting CMake/Make workflows; they cannot guarantee Android/Ninja task
concurrency. Kotlin strategies are not silently changed. Raised heaps require a
diagnosed `--memory-reason`. Project/global properties are never rewritten.

Build output streams to stderr and a unique local log; final JSON reports the
real exit code, gate, requested/observed profile, memory evidence and gaps.
Repeated `--observe-home` selects extra daemon directories. `status` is only a
snapshot, not launch clearance. Ctrl+C retains supervision of a running command;
force-killing a supervisor still requires survivor inspection on the next run.

Tests use synthetic wrappers and Windows kernel/event operations, not an extra
real Gradle build. Verify the actual project/compiler/native profile with the
next required focused build. See the skill's runtime reference for limitations.
