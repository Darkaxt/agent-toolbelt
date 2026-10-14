# Elevated Approval Broker

Already authorized: implement, test, deploy to Codex/Claude and synchronize the
elevation gate upgrade. Native UAC and broker-owned test dialogs remain human
actions. Never automate Accept/UAC or change Windows policy. Clients submitting
requests is intended; execution without broker-owned approval is forbidden.

## Requirements

### Approved Operator Dialog Redesign

Authorized October 14 after three HTML alternatives and a refinement: implement
direction B from `D:/Downloads/Public/administrator-broker-design/index.html`.
HTML is a design reference only, not an elevated renderer or execution endpoint.

- U1: Native left identity rail with prominent complete thread name, distinct
  task heading, reason and clear privilege/preview state. No repeated text-box cards.
- U2: Separate Expected changes and Exact targets reading areas, stronger headings,
  prose outcome and contrasting monospace target values. Preserve full values.
- U3: Always-visible exact-command section and working directory; selectable,
  scrollable full command. Bound paths/digests remain inspectable via explicit
  disclosure; feedback remains a separate editable field returned unchanged.
- U4: Footer actions outside the content scroll area, legible contrast, keyboard
  access, Cancel initial focus, close/Escape decline, no Enter-to-auto-accept.
  Small-window and long-content layouts must remain usable.
- U5: Preserve B1-B7 and L1-L4: native approval ownership, immutable inputs, FIFO,
  white shield, no browser engine, policy/provider changes or automatic consent.
- U6: Verify measured native layout and render, focused regression checks, then
  protected deployment/installed parity, live human-approved read-only action,
  and cleanup. Commit and permitted GitHub synchronization are required delivery
  steps after installed-feature acceptance, not another implementation stage.

| UI Stage | Status | Reconciliation |
| --- | --- | --- |
| Approved native operator dialog | COMPLETE | U1-U6 pass: native layout/render, safety regression, protected install, live action and exact cleanup. |

UI evidence (v0.2.2): measured native controls at 940x730 and 640x480, both with
normal and long content; fixed usable footer buttons, initial Cancel focus, no
default AcceptButton, exact read-only command text and working disclosure all pass.
Native desktop capture confirmed rich-text rendering (unlike DrawToBitmap, which
does not paint the native rich-text content). Preview was acknowledged without
execution; the installed normal action then completed `whoami /groups` with exit
0 and High Mandatory Level, request `8dd0e8000256460a975082b53cedd976`.

Protected SHA-256: `80705e245d2c5f5096e0a86c98b753144833d1b9c82fdd7ffcf56ef6ae30139c`.
Installed client release: `b0a3d8be4f6f3e98`. Codex, agents and Claude skill copies
match canonical instructions and validate. The installed broker PID 8740 stayed
outside all jobs and responsive after fixture launcher PID 113520's job closed.
Focused helper/native and root CLI/isolation/layout verification pass. Final
scope/refactoring assessment: no required design debt, blockers or deferrals;
no browser engine, IPC execution or consent semantics were added/changed.
Task staging was removed through the reviewed cleanup ticket; the design source
is retained, and its task-owned preview server has exited. Commit and verified
GitHub synchronization remain delivery obligations, not inferred from this ledger.

- B1: A compiled standalone Windows broker in an administrator-owned/write-protected
  installation replaces per-command elevation for normal run. One native UAC
  starts an interactive-session broker; no service, schedule or application-wide
  elevation. Keep explicit one-shot compatibility for installation/recovery.
- B2: Session/user-restricted named-pipe IPC accepts bounded submit/status/stop
  messages, never client approval flags, code-loading directives or execution-only
  endpoints. Broker assigns FIFO tickets and owns the only approval decision.
- B3: Readable top-most Accept/Cancel/feedback UI shows exact task/thread, reason,
  effects, targets and command. Closing/Escape defaults to cancellation. Preview
  cannot execute. Preserve no silent retry and feedback never altering commands.
- B4: Freeze request data, independently validate executable/script bindings and
  hold write/delete-excluding file/ancestor handles from review through launch.
  No untrusted shell expansion or request-supplied environment. This is not a
  sandbox for approved command dependencies or a replacement for secure desktop.
- B5: Event-driven supervision without arbitrary deadlines. Distinguish decline,
  failed launch, command failure, owner disconnect and broker shutdown; bound
  output/history. Serialize approval dialogs, not all administrative workloads.
- B6: Visible tray stop/control and explicit CLI stop. Stop rejects new work,
  cancels pending approvals and drains already-started children without killing
  them. Exact broker PID/path identity verification; no broad process termination.
- B7: Protected install owner/DACL plus client verification, source/release hashes,
  tests including forged approval, input drift, FIFO/cancel/results and real
  human-reviewed admin smoke. Validate installed copies and retain rollback.

| Stage | Status | Acceptance |
| --- | --- | --- |
| Broker-backed approved execution | COMPLETE | B1-B7 verified through protected installation, installed parity, live accepted/cancelled actions, forged-consent rejection and graceful tray shutdown/restart. |

No deferrals. Delivery requires commit, PR checks/merge and remote parity. If a
live human dialog remains pending, retain that managed operation and do not claim
live verification or repeat the launch. No unrelated settings/projects are changed.

## Lifecycle Independence Correction

Authorized October 14: repair launch ownership, deploy to Codex and Claude, and
synchronize. The previous broker exited within the old Codex process teardown
wave during the app update. The precise termination caller was not logged. A
fresh native query proves the restarted v0.2.0 broker is still in a Windows job,
while the desktop Explorer process is not. Elevation alone did not detach it.

- L1: Delegate only the fixed protected broker startup to the current desktop
  Explorer automation object. A detached unelevated bootstrap requests native
  UAC and waits for actual broker readiness or process exit. No service, startup
  entry, schedule, arbitrary command dispatcher or UAC-policy change.
- L2: Preserve UAC cancellation, event/process-driven waits and exact installed
  identity checks. No direct-launch fallback, forced shutdown, timeout or polling
  loop. Report startup failure instead of claiming readiness from spawn alone.
- L3: The session broker must reject job membership and report its own actual
  job state in status. Client startup must verify the reported state.
- L4: Verify startup inside an isolated kill-on-close launcher job, then close
  only that fixture job and prove the installed broker remains responsive outside
  it. Preserve FIFO, approval, input binding, protected ACLs and installed parity.

| Correction Stage | Status | Acceptance |
| --- | --- | --- |
| Desktop-owned session launch | COMPLETE | L1-L4 pass: protected deployment, real fixture teardown, elevated command, installed parity and focused/root verification. |

No correction deferrals. The original B1-B7 acceptance evidence remains historical;
it did not establish restart independence and does not satisfy L1-L4.

Primary API reference: [Execute in Explorer](https://learn.microsoft.com/en-us/windows/win32/shell/samples-execinexplorer).

### Correction Evidence And Reconciliation

The first live fixture correctly rejected the bootstrap. Desktop Explorer was
the actual parent, but Windows assigned its child a separate job. A read-only
native probe found exactly the probe process in that job, with limit flags
`0x800` (`BREAKAWAY_OK`). Native UAC assigned another job at the elevated boundary;
the second fixture correctly rejected that broker before any command execution.
Both findings were launch-adapter defects, not permission or authentication errors.

The fixed protected executable now uses Windows-permitted breakaway at each of
those two boundaries, verifies the final elevated process's protected image,
creation identity and no-job state, then verifies actual IPC readiness. It neither
changes job limits nor accepts a job-attached final broker. This retains L1-L4.
See [Windows job semantics](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

- Protected deployed broker SHA-256:
  `3f8d447db82d97f66181b428a793edc46db13fac85e4bbac30288f533132557f`.
- Installed client release `61af16724dfffc4e`, version 0.2.1.
- Live fixture: launcher PID 48316 was job-attached; broker PID 75316 was outside
  all jobs. Closing the fixture's kill-on-close job ended only its launcher. The
  same broker remained accepting and responsive. Actual Codex was untouched.
- Subsequent normal approved `whoami /groups` completed with exit 0, High
  Mandatory Level and enabled Administrators through that same broker, with no
  per-command native UAC. Request `fabf2c92fa7d4573827c6cf88c773d43`.
- Focused helper/protocol checks and native self-tests pass. Historical B1-B7
  evidence below remains explicitly separate from this correction's evidence.
- Codex, agents and Claude installed skills match canonical instructions and pass
  structural validation; Claude's installed client reaches the same live broker.
  Root CLI/isolation/layout checks pass. Reviewed task staging was removed through
  an exact transactional cleanup ticket after evidence was recorded here.

Correction implementation has no blockers or deferrals. Remote synchronization
is the remaining delivery step; it is not established by local verification.

## Design Decisions

Use installed .NET Framework C# compiler and WinForms: a standalone compiled
broker avoids elevating user-writable Python/imports/Tk runtime. Existing Python
helper becomes an unprivileged IPC client. Protected broker code and approval
state are separate from user-writable client runtime/queue files. Named-pipe access
is restricted to the current Windows account/session; it intentionally allows
all cooperating tasks to submit requests. It does not authenticate a cosmetic
thread label as agent identity. Existing per-action UAC remains an explicit
one-shot path, never a silent broker-failure fallback.

Public preflight found no meaningful windows-elevation-gate alternative; extend
the existing skill, not install another privileged tool. Privileged installation
is bootstrapped through the currently installed one-shot gate and native UAC.

## Verification Ledger

Implemented source includes compiled broker-owned dialogs/FIFO/execution, restricted
framed IPC, protected install/identity checks, immutable input leases, tray/CLI drain
and unprivileged client routing with explicit legacy one-shot compatibility.

- Compiled with warnings-as-errors; 11 native self-checks pass, including forged
  consent rejection, bounded frames, real immutable file/ancestor leases and drift.
- 24 Python/helper checks pass, including client framing, partial writes, response
  loss retaining receipts, no automatic one-shot fallback and legacy FIFO behavior.
- Root CLI/isolation/layout checks: 33 pass. Installer PowerShell syntax, source
  skill validation and all three installed skill validators pass.
- The original setup request ended with `owner_exited` before deployment. Live
  inspection on October 14 confirmed the active client remains v0.1.0 and the
  protected broker activation file is absent. The user explicitly requested that
  deployment now be completed before restarting Codex.

- Protected binary release: `56c78bee10a31983`; SHA-256
  `56c78bee10a31983610ea9360cdaf921cdd2e84c04d4250fa82dd87b9ae49b6d`.
  Root, release, executable and pointer are administrator-owned; ordinary Users
  have read/execute-only access. Python verifies identity, ACL and digest.
- Installed client release: `d5e947a7731c1f53`, version 0.2.0. Codex, agents and
  Claude skill files match the source byte-for-byte.
- Live startup exposed a missing administrator server-instance pipe permission.
  An inert exact-ACL reproduction failed on the second instance. Fixed without
  granting ordinary clients server-instance creation; native regression checks
  cover the access split and listener failures retain diagnostic evidence.
- Live UI exposed inherited `SW_HIDE` from the legacy worker launcher. Broker
  startup now explicitly selects normal visibility while legacy workers remain
  hidden. The user stopped the old broker through its tray; both queued requests
  returned `broker_stopping`, `launched: false`, and process exit was verified.
- Corrected-session FIFO tickets 1 and 2 were submitted through Codex and Claude.
  Ticket 1 was accepted, ran `whoami /groups`, returned exit 0 and High Mandatory
  Level with enabled Administrators. Ticket 2 was cancelled, returning
  `user_declined` and `launched: false`. Both used the same elevated broker.
- Live client-supplied `accepted: true` was rejected as `invalid_request` without
  execution. Repeated status requests continue working after the pipe fix.
- The CLI stop test was declined with user feedback, which returned unchanged.
  It was not retried; the broker remained enabled. Graceful shutdown/restart was
  already verified through the tray. No further shutdown prompt is required.

All required implementation criteria are verified; no blockers or deferrals.
Commit and protected-main synchronization remain delivery steps, not permission
to repeat user-declined control requests or alter a running broker.

Task-owned compiled staging is registered for transactional cleanup but remains
required for installation/verification. No source projects, UAC policies, services,
schedules or global application configuration were changed. No tracked deferrals.
