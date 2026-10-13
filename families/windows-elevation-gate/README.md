# Windows Elevation Gate

A small stdlib Windows helper for cooperating Codex/Claude tasks. Requests join a
shared event-driven FIFO queue. A top-most modal explains the exact action and
returns Accept/Cancel plus optional feedback. Accept opens native UAC; Cancel
launches nothing. No passwords, policy changes, service or scheduled task.

## Install

```powershell
python families/windows-elevation-gate/scripts/install.py
```

This verifies a content-addressed shared runtime under
`%LOCALAPPDATA%/Tools/windows-elevation-gate` and deploys identical canonical
`codex/skills/windows-elevation-gate` folders to personal Codex, agents and Claude
skill roots. No Claude plugin/config changes are necessary. Existing tasks must
reread the installed instructions. New sessions discover the installed skill.

Read the [skill](codex/skills/windows-elevation-gate/SKILL.md) for exact invocation,
feedback semantics and interrupted-owner recovery. Use `preview` to inspect a
request without a popup or elevation; `status` never grants launch clearance.

`preview --show-dialog` displays a clearly marked non-elevating visual preview.
Its Looks Good / Needs Changes buttons only rate the design; they cannot authorize
execution. The real dialog uses separate readable cards,
selectable/scrollable command text, optional feedback and persistent buttons;
long content scrolls at smaller display sizes instead of hiding the actions.

`run` takes an absolute executable, argument array, working directory, actual
thread title, specific task, reason, expected changes, explicit targets and
optional bound input files. No shell expansion or command mutation from feedback.
Executable and declared input hashes are rechecked after dialog acceptance and
before elevated execution. Do not put credentials in commands or descriptions.

## Queue And Results

`Local\Darka.WindowsElevation.Queue` protects registration metadata;
`Local\Darka.WindowsElevation.Prompt` covers explanation and UAC. Both are distinct
from build coordination. FIFO registration uses native ticket events and exact
PID/start identity, not sleeps, polling, deadlines or stale-file stealing.

The prompt slot releases at verified launch, not administrative-job completion.
The supervisor still waits for its own worker exit and returns bounded output,
command/worker exit codes, actual elevation evidence and feedback. If concurrent
administrative jobs conflict, callers still need their domain-specific resource
coordination. Nonparticipating elevation launchers are not automatically blocked.

Cancellation returns `user_declined` (CLI exit 3); UAC denial returns `uac_declined`.
Neither is retried. Dead owners before UAC are reclaimable; ambiguous UAC owner
exit requires explicit user-confirmed recovery. Normal metadata is removed at
completion; the last 100 compact queue records remain. `finalize --request-id`
can remove verified finished orphan metadata after supervisor and worker exit.
Incomplete evidence remains available for diagnosis; never sweep active state.

This is an attribution/coordination aid for trusted same-user agents, NOT a new
security boundary against malicious modifications or a substitute for native UAC.

## Verify

```powershell
python -B -m unittest discover -s families/windows-elevation-gate/tests -v
```

Tests exercise injected full flows and real Windows cross-process FIFO/events.
They never invoke real UAC. Live tests require a user to dismiss the real dialog
and UAC for a harmless read-only command. Closing the dialog means Cancel.
