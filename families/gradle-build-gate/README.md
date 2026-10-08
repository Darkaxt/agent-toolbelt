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

`run` registers a monotonic execution ticket and waits in FIFO registration order.
Only the live queue head can attempt the original build mutex. Submit once and
wait on that same running session, without status polling or relaunches. Native
turn events and process-exit handles wake waiters. Tickets are held through full
supervision and stale owners are reclaimed only after proven exit/PID identity
change, never by elapsed age. Unknown owner identity and corrupt state block.
FIFO covers updated participating helpers in this Windows session, not Studio
or older launchers. `queue_ticket` identifies the completed request; `status.queue`
is a read-only diagnostic snapshot. The queue stores no commands or project data.

Default tests use synthetic wrappers and Windows kernel/event operations. The
opt-in native failure-policy fixture below runs real Gradle through the gate.
Verify each actual project/compiler/native profile with its next required
focused build. See the skill's runtime reference for limitations.

Before each build the default retirement policy removes confirmed-idle daemons
with a different wrapper version or maximum heap. Matching daemons remain reusable.
`--retire-daemons all-idle` removes every confirmed-idle Gradle daemon first;
`--retire-daemons none` preserves prior behavior. This does not stop Kotlin or
unrelated Java and does not change a separate periodic cleanup task.

Retirement uses a small source-mode Java adapter with the target daemon's existing
JDK and distribution jars. Gradle's internal authenticated `StopWhenIdle` protocol
is used, not immediate `--stop`: racing work can finish. The helper waits for native
identity-checked process exit while holding the gate and fails closed on protocol
incompatibility. No new Java dependencies are downloaded; an existing source-capable
JDK is required. `daemon_retirement` records requested policy and verified exits.
The adapter handles both Gradle 8.6 Action callbacks/older idle enums and newer
Consumer callbacks. Compilation errors expose bounded sanitized symbol/signature
diagnostics as `adapter_compilation_failure`; runtime codes identify identity,
registry, connection, request or exit failures. Raw registry/exception data is
never printed. Compatibility failures still block rather than force-kill.

## Owner Support And Cancellation

Each new supervised build has a ticket-bound support record. After a configurable
diagnostic quiet interval (default 300 seconds), the helper emits
`owner_support_requested` in its captured tool session. It also notifies the exact
Codex owner through the installed app-tools MCP when available. The live bridge
has been tested; a successful send remains unacknowledged until an owner responds.
Claude must read the request in its existing tool session: its agent messaging
tool is not a standalone helper API. No duplicate agent or model is launched.

```powershell
python codex/skills/gradle-build-gate/scripts/invoke_gradle_build_gate.py support --ticket <id>
python codex/skills/gradle-build-gate/scripts/invoke_gradle_build_gate.py respond --ticket <id> --request <request-id> --decision continue --reason "Diagnostic evidence"
python codex/skills/gradle-build-gate/scripts/invoke_gradle_build_gate.py cancel --ticket <id> --request <request-id> --reason "Diagnosed owned hang"
```

Only task/test lifecycle observations reset progress. The interval schedules
diagnostics, never a build deadline, failure classification or automatic kill.
Continue replies schedule a fresh review rather than permanently muting a hang.
Diagnostics capture native identities, reciprocal client-daemon bindings and
best-effort owned JVM thread dumps; detached/unbound JVMs are not guessed.
Transport and diagnostic-attach limits apply only to those diagnostic subprocesses.

The wrapper runs in its own hidden console. Cancellation verifies its exact
native PID/start identity and requests Ctrl+C in that console, never force-kills,
stops unrelated Java or sends daemon-wide shutdown. Cancellation is best-effort.
The original supervisor keeps the mutex and FIFO ticket until wrapper exit and
fresh activity inspection proves safe completion. Reject stale, answered and
completed requests. Read `owner_support`, not a submitted reply alone, to assess
the outcome. Support metadata uses short per-ticket locks, not the build mutex.

Native integration is opt-in: set `GRADLE_GATE_SUPPORT_SMOKE=1` and run
`python -B -m unittest discover -s tests -p test_owner_support.py` from this family.
It uses the production FIFO/mutex and cached offline Gradle/JUnit dependencies.

## Failure Policy

Test tasks use native fail-fast by default, without scanning arbitrary exception
or ERROR text to terminate builds. The mutex remains held until wrapper exit.
Only for an intentional complete failure census:

```powershell
python codex/skills/gradle-build-gate/scripts/invoke_gradle_build_gate.py run --project D:/path/android --collect-all-failures -- :app:testDebugUnitTest
```

The opt-out disables early stopping, never the failed result. It is required for
Gradle `--continue`; raw `--fail-fast` / `--no-fail-fast` are rejected. Inspect
`requested_profile.test_fail_fast`, `test_profile_evidence`,
`test_failure_policy_verified` (configuration evidence) and
`failure_output_evidence` (up to 20 diagnostic lines of 500 characters).
No test markers means unverified policy, not success. Already-dispatched tests
may finish; a hang before any failure is reported still requires diagnosis.
This policy does not cancel existing builds or introduce timeouts or force kills.

Native offline integration verification is opt-in and uses the production FIFO
and mutex, installed Gradle 9.8.0 and cached JUnit 4.13.2/hamcrest 1.3:

```powershell
$env:GRADLE_GATE_NATIVE_SMOKE='1'
python -B -m unittest discover -s families/gradle-build-gate/tests -p test_failure_policy.py -k native_gradle
```

## Version Reuse And Disk Review

During already-authorized Android build-tool maintenance, the skill directs
agents to prefer an existing newer compatible baseline, prove actual
AGP/Kotlin/plugin/JDK compatibility with the required focused gated verification,
and commit the scoped change. Routine builds never trigger upgrades; the helper
does not rewrite wrappers or force every project onto the highest version.

`run` records known wrapper versions and selected Gradle homes automatically.
The shared catalog contains paths, versions, rollback/offline reservations and
diagnostic timestamps, not commands or wrapper URLs. Metadata uses an atomic
interprocess update; failures are reported in `usage_tracking` without hiding
the build result.

```powershell
python codex/skills/gradle-build-gate/scripts/invoke_gradle_build_gate.py register-project --project D:/path/android --keep-version 8.6
python codex/skills/gradle-build-gate/scripts/invoke_gradle_build_gate.py inventory
python codex/skills/gradle-build-gate/scripts/invoke_gradle_build_gate.py cleanup-plan
```

Register relevant projects not recently built and keep versions needed for
rollback or offline work. Repeated `--keep-version` replaces reservations;
omitting it preserves them, while `--clear-reservations` explicitly clears them.
`unregister-project --project <path>` removes metadata only. Read-only reports can
include additional `--project` and `--observe-home` paths without registration.

Inventory refreshes known wrappers and lists installed stable baseline candidates
as **compatibility unverified**. Cleanup plans propose exact distribution and
version-cache roots with logical size estimates, never delete files or grant
deletion authority. Referenced/reserved/live versions, unknown project references,
active/ambiguous processes, linked content and incomplete inventories are
protected. Shared caches, configuration, daemon registries and JDKs are excluded.

Activity protection is per version, not host-wide idle clearance. A known active
or ambiguous daemon and its observed wrapper/batch clients protect that version;
unrelated otherwise-eligible artifacts can still be reviewed. Each artifact carries
`activity_evidence` (PID/start time, state, attribution source). Unattributed clients,
unavailable connection evidence or changed snapshot identities remain conservative.
No guessed mapping, force-stop, build mutex or automatic deletion is used.

"Not referenced by known projects" is not proof of global non-use. Review project
coverage, branches and reservations before separate transactional cleanup; recheck
references/activity and skip in-use or ambiguous targets. Cleanup must not acquire
the build mutex, join the build queue or hold up unrelated builds. Use its own
exact-target coordination; preserve shared artifacts when safe native lifecycle
or owner coordination cannot be established. No timer, new task, automatic
upgrade, or automatic deletion is added. No existing cache is deleted by install.
