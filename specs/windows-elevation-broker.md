# Elevated Approval Broker

Already authorized: implement, test, deploy to Codex/Claude and synchronize the
elevation gate upgrade. Native UAC and broker-owned test dialogs remain human
actions. Never automate Accept/UAC or change Windows policy. Clients submitting
requests is intended; execution without broker-owned approval is forbidden.

## Requirements

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
