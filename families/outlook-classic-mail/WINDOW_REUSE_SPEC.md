# Outlook existing-window reuse

User authorized fixing duplicate Outlook windows and placement on 2026-11-04.
W1: recognize an existing titled/enabled minimized Outlook desktop even though its
client rectangle is empty; preserve its minimized state, position and size.
W2: retain actual rendered-window readiness for a genuine cold launch; untitled
support windows must not become ready. Launch requests reuse an existing Explorer.
W3: preserve the existing single-lane COM FIFO, accounts, drafts and user windows.
No extra instance/parallel mailbox access or arbitrary window repositioning.
W4: focused regression and native minimized-window checks; installed versioned
Coordinator release, pinned client and source synchronization; clean owned scratch.

| Stage | Status | Acceptance |
| --- | --- | --- |
| Window reuse | COMPLETE | W1–W3: minimized native HWND recognized without launch; rendered cold readiness still excludes zero-area windows; /recycle regression; original windows and placement unchanged |
| Delivery | ACTIVE | W4 packaged and installed verification |

Root cause: generic desktop detection rejects zero-sized minimized client areas,
then invokes Outlook without /recycle. The existing process creates another
Explorer using Outlook's placement. Preserve current windows rather than guess
which historical window can be closed. No mailbox read/write is needed for tests.
Scratch D:/Temp/outlook-window-reuse-20261104 for native/build I/O.

Source acceptance: D:/Tools/llm-coordinator/verification/outlook-window-startup-20261104/source.json.
Native check used an existing minimized Outlook window; no test mutation of user
windows. Refactoring assessment: reuse detection and cold-start readiness share
the same predicate with an explicit minimized policy; no new queue or service.
