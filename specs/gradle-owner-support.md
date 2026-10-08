# Gradle Owner Support

Authorization: already_authorized. Scope: stalled owned builds, diagnostics,
two-way owner support and deliberate cooperative cancellation. No daemon-wide
shutdown, forced termination, scheduler, cleanup or lock stealing.

## Requirements

- R1: Each launched build exposes its FIFO ticket, supervisor PID/start identity,
  owner task when known, project, log and current observed task/test. Unknown
  progress is explicit; output silence is not proof of deadlock.
- R2: A configurable diagnostic quiet interval creates one outstanding request
  per progress revision/review cycle. An explicit continue reply schedules another
  review without pretending the build made progress. It never decides failure, cancels or releases the
  gate. Capture exact owned process identities and optional JVM thread dumps.
- R3: Emit support requests through the existing captured tool session, which the
  supervising agent must keep yielding/reading. Codex additionally uses its
  installed app-tools MCP to notify the exact owner. No model invocation or
  settings changes. Record notification acceptance separately from owner response;
  unavailability is explicit. Claude's documented peer messaging is agent-only,
  so do not invent a helper CLI transport or impersonate a Claude session.
- R4: Owner responses require the exact ticket, current request ID and a reason.
  `continue` records justification; `cancel` requests Ctrl+C only in the private
  hidden console created for that wrapper, after native PID/start verification.
  Never send Cancel on a new Gradle daemon connection: that protocol belongs to
  the existing build connection. No taskkill, process-tree kill or gradle --stop.
- R5: Cancellation is best-effort, not proof of completion. Retain the shared
  mutex and ticket until wrapper exit and fresh Gradle activity inspection proves
  safe completion. An unresponsive build remains supervised and diagnosable.
- R6: No stale, completed or other-ticket request may affect a running build.
  Short per-ticket metadata locks must not join the build queue. No automatic
  cleanup under the build gate. Preserve fail-fast and memory/profile behavior.
- R7: Deploy verified helper/skill to Codex, agents and Claude, and sync reviewed
  source. Tests must cover notification failure, stale replies, exact cancellation
  and gate retention. Local evidence is not committed.

## Stages

1. COMPLETE: support state, owner transport and command contracts (R1,R3,R4,R6).
   Current-request, duplicate/stale rejection and native response roundtrip pass.
   Native cancellation integration belongs to Stage 2.
2. COMPLETE: diagnostic monitoring and supervised native cancellation (R2,R5).
   Native console fixture verifies exact PID/start binding, refusal of changed
   identity and preservation of an unrelated process. State/event fixtures cover
   responses, diagnostic rearming and gate retention until daemon idle.
3. ACTIVE: integrated verification, documentation, deployment and sync (R7).
   Required: real Gradle hanging-test cancellation, final focused checks and
   deployed source parity. Native cancellation and owned-JVM diagnostic probes
   passed. Runtime/skill installation and byte parity are verified; source sync
   remains.

Tracked deferral to Stage 3: real Gradle integration is resolved by the native
probes below. Installation is verified; source sync remains ordinary Stage 3 work.

## Evidence / Constraints

The installed Codex app-tools MCP was invoked from a separate Python process;
tools/list and list_threads succeeded. This verifies helper access, not receipt
or acknowledgement of a future support message. Native Claude messaging delivers
between tool calls and exposes no documented standalone sending CLI; the owned
tool-session channel therefore remains required for both clients.

A subsequent live helper-to-Codex message was accepted and received in its actual
owning task. No new task/model was launched. Runtime receipt and acknowledgement
remain distinct despite this successful channel test.

The first native integration attempt exposed String/Enum mixing in TestLogging
events. Fixed with TestLogEvent constants; the failed run is not pass evidence.

Native Gradle 9.8.0 hanging JUnit test: ticket
7f2ac751fc3b4a2eb976c518d8d22f2e acquired the production FIFO/mutex, observed
HangingTest > waitsForOwner STARTED, handled the exact owner cancel response,
returned exit 130, and verified completion before releasing ownership. Effective
Gradle profile: two workers, parallel false, maximum heap 3221225472 bytes;
one 128m test fork. No Kotlin compiler participates in this Java-only fixture.
The first fixture owner replied immediately, so its concurrent diagnostic snapshot
reported wrapper_identity_not_observed after cancellation; this is not evidence
of a successful JVM capture.

The strengthened native probe (ticket dfc18af14dcc48308ecd9be6af752dc6) waited
for its production FIFO turn and then for nonparticipating activity to finish.
It captured native-bound client, daemon and test-worker JVM thread dumps (all
jcmd exits 0), then replied cancel to the exact current hanging-test request.
The wrapper exited 130 and fresh activity inspection verified safe completion
before gate release. The same two-worker/3 GiB/one 128m test-fork profile passed.
Its owner response is a fixture; actual Codex message delivery was verified
separately above. No other owner's build was interrupted.

Final family checks: 75 tests passed with two opt-in native suites skipped in the
default run; the owner-support native suite ran separately and passed. Root CLI,
isolation and layout checks passed. Skill validators, bundle parity and PowerShell
syntax checks passed. Disposable native projects were removed by test teardown;
local support records/dumps remain deliberate verification evidence, not Git data.

Installed 0.5.0 content-addressed runtime d6404b7ea6432cd3: all 11 runtime files
match source bytes; Codex, agents and Claude skill bundles match canonical bytes.
All three installed validators and cancel help surfaces passed. Installed support
read confirms the final native fixture record is completed with exit 130 and
completion_verified true. No disposable native fixture directories remain.

Public preflight's customer-escalation candidate does not implement native Gradle
supervision. Keep this behavior in the existing helper. No third-party install.

References: https://code.claude.com/docs/en/cross-session-messaging and Gradle
DaemonClient.java (v8.6.0), which binds Cancel to the active build connection.
