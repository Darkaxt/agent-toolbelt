# Silent Gradle Owner Notifications

## Authorized Outcome

Add a standard silent Windows desktop notification identifying the task and
project admitted to the Gradle build gate. Update and install the shared helper
for Codex and Claude, verify it without launching unrelated Gradle builds, then
commit and synchronize the verified source. Existing builds remain untouched.

## Requirements

- R1: Notify once after FIFO admission and actual mutex acquisition. Identify the
  mutex owner even during activity inspection or daemon retirement, without
  claiming the requested build is already running. Queued requests and read-only
  commands must not claim ownership. All normal build preflight still applies.
- R2: Show the project and an explicit `--owner-task` label. Fall back to the
  current Codex task ID or an explicitly supplied Claude session ID, otherwise
  report owner unknown with the supervisor PID. Never invent a task title.
- R3: Use Windows app notifications with silent audio, no focus stealing, prompt,
  network, service, scheduled task, extra dependency or global notification change.
  Register a per-user Gradle Build Gate Start-menu shortcut/AUMID during installation
  and its own HKCU app-identity metadata for unpackaged desktop toast support;
  do not alter other app identities/settings.
- R4: Notification delivery must be asynchronous and non-authoritative. Failures,
  disabled notifications and Do Not Disturb must not cancel, block or change the
  build, mutex, queue, resource profile or owner-support protocol. Report submitted
  separately from confirmed visibility. Diagnostic transport limits apply only to
  the notification subprocess, never to build execution or queue waiting.
- R5: Remove only this ticket's notification on normal/exceptional completion.
  Notification teardown must occur after mutex/ticket release; distinct ticket
  identities prevent one owner from removing another owner's notification.
  Forced termination cannot guarantee removal; the notification includes its
  admission timestamp and is informational, never live lock clearance.
- R6: Provide explicit `--no-notify` opt-out. Verify XML escaping, owner fallback,
  silent payload, ordering, failure isolation, failed-build preservation, cleanup,
  parser routing, and actual Windows submission/history removal. Do not change
  any project or run a real Gradle build only to test this feature.

## Stages

1. Notification transport and lifecycle (R1-R6): COMPLETE. Ordering and failure
   checks pass; native smoke verified silent task/project content in Windows
   notification history and ticket-scoped removal without a Gradle build.
2. Documentation, installation and verification (R2-R6): COMPLETE. Version 0.6.0
   is installed in the shared content-addressed runtime and Codex/agents/Claude
   skill roots; source/runtime/bundle hashes match. Installed CLI routing and
   structural validation pass. Family and root wiring checks pass, including
   focused rechecks of notification failure/cleanup changes. Native installed
   smoke confirms task/project content, silent audio and ticket-scoped history
   removal. No real Gradle build or existing owner was interrupted for this test.

Final delivery: commit and sync only the verified scope. No tracked deferrals.

Native investigation: querying ToastNotifier.get_Setting before the first
submission returned HRESULT 0x80070490, including for the newly registered ID.
That is not proof that Show would fail. Submit first, then report settings when
available; native notification history proves acceptance/removal independently.
The helper uses its own explicit identity/shortcut and per-user display metadata
to identify notifications as Gradle Build Gate rather than impersonating another
app. Registration and initial settings-probe issues do not alter Gradle behavior.
