---
name: windows-elevation-gate
description: Queue Windows administrator actions with a top-most explanation, Accept/Cancel, optional user feedback and native UAC. Use before authorized elevated commands when several tasks may request administrator rights.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows interactive login session, Python 3.11+ with Tkinter and the installed shared runtime
---

# Windows Elevation Gate

Use `scripts/invoke_windows_elevation_gate.py` for genuinely required, authorized
administrator actions. Full filesystem access does not imply an elevated token.
Do not elevate ordinary commands, change UAC policy, request credentials, or use
this helper to circumvent a known tool-policy rejection. It is not a permission
bypass, persistent administrator service, or general command dispatcher.

## Request Once, Wait In FIFO Order

1. Establish why elevation is necessary and the exact approved scope. Inspect
   `--help`/`preview` if invocation is uncertain. Prepare one cohesive command;
   complex actions belong in an explicit script supplied with `--bind-file`.
2. Supply the actual conversation title as `--thread-name` and the specific
   operation as `--owner-task`, not a project path, UUID or invented title.
   Explain the reason, expected changes and exact targets honestly. Do not put
   passwords, tokens, private keys or sensitive business content in argv/labels.
3. Submit `run` ONCE. All installed copies share one FIFO registration queue and
   `Local\Darka.WindowsElevation.Prompt` mutex in the current Windows login session.
   Never create a per-project queue, acquire the Gradle gate, poll/relaunch the
   command, or treat `status` as permission to launch outside the helper.
4. Retain and observe the original managed session. The top-most dialog waits
   for Accept/Cancel; optional feedback returns to the requesting task. Closing
   or Escape cancels. Accept acknowledges the exact displayed action, then native
   UAC independently asks for elevation. Feedback NEVER modifies the command.
5. `user_declined` (exit 3) or `uac_declined` stops the dependent action. Read the
   feedback, report cancellation and do not automatically retry or bypass it.
   A new changed request requires the user's instruction to continue.
6. The prompt slot releases after confirmed worker launch, so another request
   may explain/elevate while the previous administrative job runs. This serializes
   prompts, NOT administrative workloads. Use domain-specific resource coordination
   too when necessary. The original supervisor waits for its command's actual exit.
7. Inspect `ok`, `launched`, `elevated`, `command_exit_code`, `worker_exit_code`,
   feedback, failure kind and bounded output. Launch success alone is not task
   success. Captured stdout/stderr may be truncated and must never be described
   as complete logs when the corresponding flag is true.

## Invocation

```powershell
python scripts/invoke_windows_elevation_gate.py preview --owner-task "Inspect administrator identity" --thread-name "Actual conversation title" --reason "Verify the elevated token" --changes "Read-only; no system changes" --target "Current process token" --cwd "$PWD" -- "$env:WINDIR/System32/whoami.exe" /user
python scripts/invoke_windows_elevation_gate.py run --owner-task "Inspect administrator identity" --thread-name "Actual conversation title" --reason "Verify the elevated token" --changes "Read-only; no system changes" --target "Current process token" --cwd "$PWD" -- "$env:WINDIR/System32/whoami.exe" /user
python scripts/invoke_windows_elevation_gate.py status
```

An absolute `.exe` is required; `.cmd`/`.bat`/shell aliases are not accepted as
executables. For PowerShell pass the absolute PowerShell executable, `-NoProfile`
and `-File` plus an explicit reviewed script. Script flags, `.ps1`/`.py` arguments
and `--bind-file` inputs are hash-bound along with executable and elevation host.
The bytes are rechecked after acceptance and before the payload executes. This
protects accidental input drift, not malicious same-user modification of Python,
imports or queue state. The explanatory popup is not a Windows security dialog.

## Visual Preview

For a visual-only check, add `--show-dialog` to `preview` before `--`. It is
clearly marked DESIGN PREVIEW, has working Looks Good / Needs Changes buttons and
cannot launch UAC or execute the command. A `preview_approved` response only rates
the design; it is not execution consent. Do not confuse preview with queued `run`.

## Interrupted Owners And Metadata

No timeout, lease expiry, low CPU heuristic or stale lockfile steals a ticket.
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

Install the family with `python families/windows-elevation-gate/scripts/install.py`.
It deploys one content-addressed runtime under the local application-data Tools
directory and identical personal skills for Codex, agents and Claude. No global
application settings, models, schedules or UAC policies change. The launcher
resolves the installed runtime; explicit `AGENT_TOOLBELT_HOME` selects a development
checkout. A missing runtime is an actionable error, not clearance for raw RunAs.
Existing tasks must explicitly reread this installed file; installation is not
proof of immediate active-session skill registry discovery.
