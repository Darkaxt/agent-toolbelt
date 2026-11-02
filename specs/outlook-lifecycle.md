# Outlook lifecycle reliability

The user requests debugging and fixing persistent "Outlook is closing" behavior.
This follows separately completed request-cancellation guidance. Preserve mail,
profiles, accounts, add-ins, drafts, settings and other applications. No test send,
mailbox modification, AV exclusion, blanket process kill or automatic retry.

## Requirements

- OL1: Capture the actual stuck application's native state before changing
  production behavior. Distinguish a blocked native app, client references,
  startup readiness and ordinary queue serialization. Establish evidence for the
  changed cause; do not blame loaded add-ins from their presence alone.
- OL2: Correct a demonstrated helper lifecycle defect while preserving managed
  execution/FIFO, no-UI/auto-launch choices, sender/attachment behavior and explicit
  cancellation rules. Normal startup and shutdown must not leave helper-owned
  COM references or race duplicate activation. No arbitrary execution deadline.
- OL3: Verify the changed complete lifecycle against native Outlook and focused
  client/Coordinator contracts. Preserve already-running user instances and do not
  equate process existence with usable COM or taskbar-closing state with cause.
- OL4: Commit/sync both maintained sources and deliver the established verified
  local Coordinator release with exact dependency pins/installed skill/client
  parity. Preserve live broker and independent gate work. Clean task scratch.

## Stages

| Stage | Status | Acceptance |
| --- | --- | --- |
| Establish lifecycle cause | COMPLETE | OL1: captured original native/managed stacks before recovery. Cold original-helper startup launches normal Outlook then a competing DCOM -Embedding process 85 ms later. Normal recovered instance closes with native exit0. This demonstrates an unsequenced startup defect; original internal mailbox-store wait is recorded separately, without blaming add-ins or claiming its precise internal cause. |
| Correct and verify lifecycle | COMPLETE | OL2-OL3: enabled, titled real desktop readiness precedes one COM binding. Native existing-instance and cold accounts calls succeeded; both normal closes exited0. A transient COM activation process exited while the original desktop survived; transient activation is not a second persistent app. Native qualification rejected untitled support windows and GetActiveObject-only attachment (MK_E_UNAVAILABLE). Complete client contracts passed, including no-UI/probe, FIFO, sender/attachments; added support-window/readiness regressions pass. Guidance matches the corrected startup boundary. |
| Deliver | COMPLETE | OL4: synchronized toolbelt0205df3 and Coordinator20f7b7c/v0.18.4; installed release7e7f41e1228d8163 and exact client/three agent bundles verified. Independent ZIP extraction verified all manifest members. Installed native cold startup succeeded, normal close exited0 with no Outlook residual; stopped diagnostics remain launch-free. Existing broker/settings and startup verified. Exact task scratch cleaned through reviewed transactional tickets; compact private qualification receipts retained. |

Exact native/process identities and private evidence are outside the public
repository. D: scratch is required for native debugger, possible symbol I/O and
native/frontend release builds; small reviewable scripts use task-owned E: scratch.
No blocker/deferral is being used to advance past unverified cause.
