---
name: windows-elevation-gate
description: Queue Windows administrator actions through an elevated session broker with broker-owned Accept/Cancel and feedback. One native UAC starts the broker; each command requires its own approval. Use for authorized administrator actions across tasks.
license: MIT
metadata:
  version: "0.2.0"
  compatibility: Windows interactive login session, Python 3.11+, protected .NET Framework broker and installed shared client runtime
---

# Windows Elevation Gate

Use `scripts/invoke_windows_elevation_gate.py` for genuinely required, authorized
administrator actions. Full filesystem access does not imply an elevated token.
Do not elevate ordinary commands, change UAC policy, request credentials, or use
this helper to circumvent a known tool-policy rejection. It is not a permission
bypass or automatically started administrator service. Normal clients intentionally
submit requests; only the protected broker's own dialog can approve execution.

## Start Once, Approve Each Action

Run `broker-start` once for this login session. Native Windows UAC grants the
broker its elevated token; never automate that security prompt. It stays elevated
until explicitly disabled/exited or Windows ends the session. There is no startup
entry, service, schedule or UAC-policy change. Normal `run` uses this broker and
does NOT request native UAC again for each command. If unavailable, diagnose/start
it; never silently fall back to another execution method or repeat a submitted action.

The compiled broker lives under `Program Files/Darka.WindowsElevationGate` with
administrator ownership and non-administrator read/execute-only permissions.
Python and agent skill files remain unprivileged IPC clients. The broker owns
consent and command state in memory; submitting JSON cannot grant consent.

## Request Once, Wait In FIFO Order

1. Establish why elevation is necessary and the exact approved scope. Inspect
   `--help`/`preview` if invocation is uncertain. Prepare one cohesive command;
   complex actions belong in an explicit script supplied with `--bind-file`.
2. Supply the actual conversation title as `--thread-name` and the specific
   operation as `--owner-task`, not a project path, UUID or invented title.
   Explain the reason, expected changes and exact targets honestly. Do not put
   passwords, tokens, private keys or sensitive business content in argv/labels.
3. Submit `run` ONCE. All installed copies share the broker's FIFO approval queue and
   `Local\Darka.WindowsElevation.Prompt` mutex in the current Windows login session.
   Never create a per-project queue, acquire the Gradle gate, poll/relaunch the
   command, or treat `status` as permission to launch outside the helper.
4. Retain and observe the original managed session. The top-most dialog waits
   for Accept/Cancel; optional feedback returns to the requesting task. Closing
   or Escape cancels. The already-elevated broker owns the dialog, freezes request
   data and independently checks/holds exact input handles. Accept executes only
   that displayed action. Feedback NEVER modifies the command.
5. `user_declined` (exit 3) or `uac_declined` stops the dependent action. Read the
   feedback, report cancellation and do not automatically retry or bypass it.
   A new changed request requires the user's instruction to continue.
6. The prompt slot releases after the approval decision; another request
   may explain while the previous administrative job runs. This serializes
   prompts, NOT administrative workloads. Use domain-specific resource coordination
   too when necessary. The original supervisor waits for its command's actual exit.
7. Inspect `ok`, `launched`, `elevated`, `command_exit_code`, `execution_model`,
   feedback, failure kind and bounded output. Launch success alone is not task
   success. Captured stdout/stderr may be truncated and must never be described
   as complete logs when the corresponding flag is true.

`completion_unverified` means the response connection was lost: do not resubmit
automatically, because the command may have started. Keep the queued receipt and
inspect broker `status`/history. Thread/task labels are attribution, not credentials.
Requests are restricted to the current account/login session; clients are allowed
to request actions but cannot send approval flags or an execution-only operation.

## Disable Administrator Execution

Use the shield tray icon's **Disable administrator execution** item, or submit
`broker-stop` and accept its broker-owned control dialog. New requests are refused,
pending approvals are cancelled and already-started commands drain under supervision.
No process is force-killed. CLI stop waits for actual broker exit. `status` reports
draining separately from stopped. Restarting later requires native UAC again.

## Invocation

```powershell
python scripts/invoke_windows_elevation_gate.py broker-start
python scripts/invoke_windows_elevation_gate.py broker-status
python scripts/invoke_windows_elevation_gate.py preview --owner-task "Inspect administrator identity" --thread-name "Actual conversation title" --reason "Verify the elevated token" --changes "Read-only; no system changes" --target "Current process token" --cwd "$PWD" -- "$env:WINDIR/System32/whoami.exe" /user
python scripts/invoke_windows_elevation_gate.py run --owner-task "Inspect administrator identity" --thread-name "Actual conversation title" --reason "Verify the elevated token" --changes "Read-only; no system changes" --target "Current process token" --cwd "$PWD" -- "$env:WINDIR/System32/whoami.exe" /user
python scripts/invoke_windows_elevation_gate.py status
python scripts/invoke_windows_elevation_gate.py broker-stop
```

An absolute `.exe` is required; `.cmd`/`.bat`/shell aliases are not accepted as
executables. For PowerShell pass the absolute PowerShell executable, `-NoProfile`
and `-File` plus an explicit reviewed script. Script flags, `.ps1`/`.py` arguments
and `--bind-file` inputs are hash-bound along with executable and elevation host.
The broker rechecks hashes and holds write/delete-excluding file and ancestor
handles through approval and execution. Changed/redirected inputs fail closed.
This does not sandbox approved commands, discover every dependency, make task
labels trustworthy, or turn the popup into Windows' secure desktop. Only approve
commands and dependency provenance appropriate to the requested administrative scope.

## Visual Preview

For a visual-only check, add `--show-dialog` to `preview` before `--`. It is
clearly marked DESIGN PREVIEW, has working Looks Good / Needs Changes buttons and
cannot launch UAC or execute the command. A `preview_approved` response only rates
the design; it is not execution consent. Do not confuse preview with queued `run`.

## Interrupted Owners And Metadata

Broker waits are event-driven, with no arbitrary timeout, lease expiry or process
killing. Disconnect before approval cancels that request; disconnect after launch
does not cancel the supervised command or establish its completion.

The explicit legacy `run --one-shot` path remains for protected installation or
diagnosed recovery only. It retains the former custom popup followed by native
UAC, per-action worker and on-disk FIFO state. Never select it merely because a
broker call failed. `one-shot-status`, `recover` and `finalize` apply only to that
legacy path. Its recovery contract follows:

No timeout, lease expiry, low CPU heuristic or stale lockfile steals a legacy ticket.
Dead owners before UAC can be reclaimed through exact PID/start identity. An owner
lost during UAC leaves `owner_recovery_required`; queued requests wait safely.
Inspect `status` and the real desktop. Only after the USER confirms the old UAC
or dialog is settled may you use `recover --request-id <id>
--confirm-old-prompt-settled`. Never kill another owner to free the gate.

Normal completed requests remove their exact intrinsic payload/result metadata;
queue history keeps at most 100 compact records. If the supervisor died after
launch, `finalize --request-id <id>` only removes completed request metadata after
both verified process identities have exited. Incomplete/ambiguous evidence is
preserved for diagnosis, not automatically swept. Use transactional cleanup for
task-generated script/log files once expendable; don't sweep helper state.

## Installation And Routing

Build with `scripts/build_broker.py --output <exact-task-Temp>/WindowsElevationBroker.exe`,
then install with `scripts/install.py --broker-exe <compiled-exe> --thread-name
"<actual conversation title>"`. Protected installation uses the existing explained
one-shot/native-UAC flow before activating the new client runtime; cancellation
does not activate a partial upgrade. No pre-approved elevation task is created.

It deploys the protected content-addressed broker plus an unprivileged client
runtime under local Tools and identical skills for Codex, agents and Claude. No global
application settings, models, schedules or UAC policies change. The launcher
resolves the installed runtime; explicit `AGENT_TOOLBELT_HOME` selects a development
checkout. A missing runtime is an actionable error, not clearance for raw RunAs.
Verify the compiled protected release/hash/ACL and actual IPC smoke, not only
Python source or skill copies. Client-only test installations do not prove broker
deployment. Preserve the previous local runtime for explicit rollback, and stop
the broker through its own interface before upgrading its protected active release.
Existing tasks must explicitly reread this installed file; installation is not
proof of immediate active-session skill registry discovery.
