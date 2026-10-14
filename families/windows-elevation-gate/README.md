# Windows Elevation Gate

Session lifecycle: v0.2.1 starts the protected broker through desktop Explorer,
not inside the calling agent's job. The detached bootstrap still requests native
UAC; normal command approvals remain broker-owned. Startup rejects job membership
and reports `in_job: false`. Verify with
`python scripts/verify_broker_lifecycle.py --output-dir <fresh-task-Temp>/probe`
after graceful shutdown of any prior broker. The fixture closes only its own
kill-on-close launcher job and verifies the same installed broker survives;
it never closes Codex, kills a broker, creates a service or changes UAC policy.

A small stdlib Windows helper for cooperating Codex/Claude tasks. Requests join a
shared FIFO approval queue. Native UAC starts a compiled elevated broker once;
its own top-most dialog explains each exact action and returns Accept/Cancel plus
feedback. Clients can submit requests but cannot approve them. Cancel launches
nothing. No passwords, policy changes, service, scheduled task or automatic startup.

## Install

```powershell
python families/windows-elevation-gate/scripts/build_broker.py --output D:/Temp/<task>/WindowsElevationBroker.exe
python families/windows-elevation-gate/scripts/install.py --broker-exe D:/Temp/<task>/WindowsElevationBroker.exe --thread-name "Actual conversation title"
```

Protected installation uses the existing explained per-action/native-UAC path
before activating new client files; cancellation preserves the previous activation.
The broker is installed under `Program Files/Darka.WindowsElevationGate` with
administrator ownership and non-administrator read/execute-only ACLs. It has no
Python imports or user-writable code dependencies. The installed .NET Framework
compiler builds the standalone WinForms executable without downloaded packages.
The unprivileged client verifies protected installation ACLs/hash and the server's
actual process identity, not a user-writable active-process hint.

This also verifies a content-addressed shared client runtime under
`%LOCALAPPDATA%/Tools/windows-elevation-gate` and deploys identical canonical
`codex/skills/windows-elevation-gate` folders to personal Codex, agents and Claude
skill roots. No Claude plugin/config changes are necessary. Existing tasks must
reread the installed instructions. New sessions discover the installed skill.

Read the [skill](codex/skills/windows-elevation-gate/SKILL.md) for exact invocation,
feedback semantics and interrupted-owner recovery. Run `broker-start` once, then
`run` for each action, `status` for the broker queue and `broker-stop` to disable.
The shield tray icon also provides status and Disable administrator execution.
The tray uses a local monochrome white, transparent Defender-style shield, not
the multicolor default UAC icon or Windows Security branding/status.
Stop cancels pending approvals and drains started commands without killing them.
Use `preview` to inspect a
request without a popup or elevation; `status` never grants launch clearance.

`preview --show-dialog` displays a clearly marked non-elevating visual preview.
Its Looks Good / Needs Changes buttons only rate the design; they cannot authorize
execution. The real dialog uses separate readable cards,
selectable/scrollable command text, optional feedback and persistent buttons;
long content scrolls at smaller display sizes instead of hiding the actions.

`run` takes an absolute executable, argument array, working directory, actual
thread title, specific task, reason, expected changes, explicit targets and
optional bound input files. No shell expansion or command mutation from feedback.
The broker independently checks bindings and holds write/delete-excluding input
and ancestor handles through approval and command completion. Do not put credentials
in commands or descriptions. This protects declared input bytes, not every runtime
dependency of an approved command; it is not a sandbox or Windows secure desktop.

## Queue And Results

The normal broker owns its FIFO and approval state in memory. Current-account,
current-session named pipes accept only bounded submit/status/stop JSON, not
client-supplied consent or arbitrary execution-only operations. Pipe clients get
data/synchronize rights, not create-instance rights. Protected session PID/start
records and pipe-server PID checks bind clients to the installed elevated broker.
`Local\Darka.WindowsElevation.Prompt` serializes dialogs; it is not the Gradle gate.
Readiness and completion use actual events/processes, not sleeps or kill deadlines.

The prompt slot releases after its decision, not administrative-job completion.
The supervisor still waits for its own worker exit and returns bounded output,
command exit code, actual elevation evidence and feedback. `worker_exit_code` is
null in broker mode because there is no separate per-action elevation worker. If concurrent
administrative jobs conflict, callers still need their domain-specific resource
coordination. Nonparticipating elevation launchers are not automatically blocked.

Cancellation returns `user_declined` (CLI exit 3); startup UAC denial returns `uac_declined`.
Neither is retried. Client disconnect before approval cancels the request; response
loss returns `completion_unverified`, not proof of nonexecution or permission to
resubmit. Bound output/history and request receipts support diagnosis.

Explicit `run --one-shot` retains the prior per-action popup/UAC path for installation
or diagnosed recovery; it is never an automatic fallback. `one-shot-status`,
`recover` and `finalize` inspect that legacy queue. Dead owners before UAC are reclaimable; ambiguous UAC owner
exit requires explicit user-confirmed recovery. Normal metadata is removed at
completion; the last 100 compact queue records remain. `finalize --request-id`
can remove verified finished orphan metadata after supervisor and worker exit.
Incomplete evidence remains available for diagnosis; never sweep active state.

Broker code/ACL protection and broker-owned approval are a privileged authorization
boundary, not prevention of request submission. Any approved arbitrary command has
administrator authority and may load its own dependencies. The ordinary desktop
dialog does not have Windows secure-desktop guarantees. No current application is
elevated wholesale and Windows security policy remains unchanged.

## Verify

The v0.2.2 approval form implements the approved operator design: a persistent
thread-identity rail, distinct outcome/target sections, a selectable command panel,
disclosed full input hashes, feedback and a fixed decision footer. HTML is design
reference only; no browser engine runs in the elevated process. Visual previews
use that same native form without submitting an approval or requesting elevation.

`WindowsElevationBroker.exe --verify-ui <task-output>` measures the actual native
preview controls at normal/small sizes with normal/long content and emits bounded
layout evidence plus DrawToBitmap images. Those images are not proof of desktop
presentation (native rich-text pixels need a real window capture); inspect the
actual preview/live approval too. Verification never accepts an execution request.

For the installed broker's lifecycle test, stop it through its normal approved
interface first, then run:

```powershell
python -B families/windows-elevation-gate/scripts/verify_broker_lifecycle.py --output-dir D:/Temp/<task>/lifecycle-proof
```

This starts the installed broker from an isolated kill-on-close launcher job,
requires native UAC, verifies the actual broker is outside all jobs, then closes
only the fixture job and checks the same broker remains responsive. It does not
close Codex or approve commands. Explorer/UAC may create separate jobs; the fixed
protected bootstrap uses permitted breakaway, never changes job limits, and
rejects any final job-attached broker. On startup failure the fixture disarms its
own kill-on-close flag rather than risking an unclassified broker or UAC prompt.

```powershell
python -B -m unittest discover -s families/windows-elevation-gate/tests -v
```

Tests exercise injected full flows and real Windows cross-process FIFO/events.
They never invoke real UAC. Live tests require a user to dismiss the real dialog
and UAC for a harmless read-only command. Closing the dialog means Cancel.
