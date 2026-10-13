# Windows Elevation Gate

## Authorized Scope

Create/install a small shared skill/helper for Codex and Claude, test it with
read-only elevation, and sync verified source. No UAC-policy changes, credential
storage, service, scheduled task, persistent administrator broker or Gradle changes.
Public preflight inspected skills.sh Windows/UAC results: the WinUI-app candidate
scaffolds applications, not queued elevation. Exact elevation/UAC queries found no
applicable inspected implementation; broad Windows results were capped. Reuse native
Windows APIs and the proven event-driven FIFO design, not a new general framework.

## Requirements

- E1: One FIFO registration queue per Windows login session, shared by Codex/Claude.
  A distinct process-owned named prompt mutex covers explanation and UAC decision.
  Wait on native events/process exits, without polling/relaunch, sleeps, expiry or
  timeout-based stealing. Never acquire the Gradle gate.
- E2: Top-most modal explanation with actual task/thread name, reason, expected
  changes, exact targets, working directory and exact executable/arguments. Include
  optional feedback plus Accept/Cancel. Wait for dismissal. Close/Escape means Cancel.
- E3: Cancel returns user_declined with feedback and launches nothing. Accept is
  acknowledgement before native Windows UAC, not an elevation bypass. Feedback
  never modifies the command; the dialog tells users to Cancel for requested changes.
  UAC denial is distinct, with no automatic retry or alternative execution route.
- E4: Bind request bytes and executable/explicit input-file hashes. Recheck after
  the dialog and in the elevated worker; changed input fails without execution.
  Use argument arrays/no shell expansion, no credentials in descriptions/arguments.
  This is coordination for trusted user-owned processes, not a new security boundary
  against same-user tampering; Windows UAC remains the privilege boundary.
- E5: Release the queue/prompt mutex after denial or confirmed worker launch, not
  after a long administrative job. Supervise the original elevated worker to exit;
  return exit status and bounded stdout/stderr with feedback. No silent detached work.
- E6: Owner exit before UAC is safely reclaimable by PID/start identity. Exit during
  ambiguous UAC is fail-closed: report recovery required, never assume mutex abandonment
  proves no prompt. Explicit recovery requires dead-owner verification and the user's
  confirmation that the old dialog/UAC is settled. Never kill another owner's process.
- E7: Status is diagnostic, not launch clearance. Keep bounded terminal history,
  no immortal payload/log piles. Keep active request evidence until supervised exit;
  finalize exact helper-owned request metadata through its lifecycle, and clean
  expendable test/build scratch through transactional-cleanup. Stable versioned
  runtime and identical Codex/agents/Claude skills, current help and validators.
- E8: Mocked full-flow and real process/event tests must demonstrate FIFO, single
  prompt ownership, feedback/cancel, tamper rejection, UAC denial, launch-time release
  and orphan recovery. Live test: two queued requests with harmless identity output;
  user interacts with the real dialogs/UAC. No destructive/system changes for testing.
- E9: User-requested readability polish: high-contrast task heading, separate reason,
  expected-change and exact-command cards, optional feedback clearly distinguished
  from executable instructions, and persistent action buttons. Clamp initial size
  to the display, reflow text at narrower widths, scroll long content rather than
  clipping it. Verify the actual native dialog at normal and compact dimensions.
  Native UAC and FIFO semantics must remain unchanged. Visual-only previews cannot
  authorize execution and must explicitly say no command or UAC will run. Use
  active Looks Good / Needs Changes design-rating buttons, never a confusing
  disabled Accept. Navy/blue/white must replace the rejected green/gray palette.

## Stages

| Stage | Status | Acceptance |
| --- | --- | --- |
| 1 | COMPLETE | E1-E6 integrated workflow verified by injected whole flows and actual Windows two-process FIFO, denial, binding, feedback and orphan-recovery tests. |
| 2 | COMPLETE | E7 installed parity, E8 live accepted/cancelled paths, E9 native UI review; consistency review and exact temporary-output cleanup passed. |

Missing required work is an advancement blocker; no required deferrals.

After implementation stages pass, delivery requires the normal verified commit,
repository-permitted PR merge, fast-forwarded local main and remote-SHA equality.
These remain mandatory delivery actions, not additional implementation stages or
deferred feature work. Overall delivery is not complete until they succeed.

## Verification Ledger

- Stage 1: `python -B -m unittest discover -s families/windows-elevation-gate/tests -v`
  passed on Windows. No real UAC is invoked by automated tests.
- Root family CLI, isolation and layout checks passed; canonical skill validator
  passed and local skills.sh discovery reported exactly 22 skills.
- Stage 2: shared runtime and three identical personal skill folders installed;
  live request 1 was accepted and its exact read-only identity command returned
  elevated=true with command/worker exit 0. Request 2 was cancelled with feedback
  returned intact, launched=false, and no retry. The queue then had no pending
  requests. Their live dismissal order did not leave an observed simultaneous
  queue; actual overlapping FIFO admission is independently proven by the native
  two-process test, not inferred from the two live requests.
- User confirmed the live flow works and requested clearer UI. E9 now has separate
  task/reason/change/command/feedback cards, readable typography and fixed actions.
  Actual native screenshot inspection at 850x890 and 600x500 confirmed hierarchy,
  legible paths, bounded scrolling and the footer within the window. No extra UAC
  requests were made for visual inspection. The user rejected the disabled preview
  Accept button and green/gray colors: preview now has active design-rating buttons
  and a higher-contrast navy/blue/white palette. The final installed preview returned
  preview_approved=true while accepted=false and launched=false, with feedback intact.
- Installed source/runtime parity passed for all three personal roots and shared
  release `85c210ea4c1d694b`; validators and installed help passed. No Codex/Claude
  configuration file changed. Reused root-family evidence remains applicable;
  final affected full-flow tests passed including definite launch-failure cleanup
  and preview approval isolation.
- Transactional cleanup removed all six reviewed screenshot artifacts/directory
  (136,969 bytes). Live queue is empty and normal request payloads were finalized.
  Publication/remote parity is verified after this source checkpoint.
