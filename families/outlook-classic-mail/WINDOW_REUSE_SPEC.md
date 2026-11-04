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
| Delivery | COMPLETE | W4: 0.20.3 / 2759d3a6c8bd71be independently packaged, extracted, installed and checked through two real helper calls; original process/window identities and all placements preserved; source mirrored and scratch cleaned |

Root cause: generic desktop detection rejects zero-sized minimized client areas,
then invokes Outlook without /recycle. The existing process creates another
Explorer using Outlook's placement. Preserve current windows rather than guess
which historical window can be closed. No mailbox read/write is needed for tests.
Scratch D:/Temp/outlook-window-reuse-20261104 for native/build I/O.

Source acceptance: D:/Tools/llm-coordinator/verification/outlook-window-startup-20261104/source.json.
Native check used an existing minimized Outlook window; no test mutation of user
windows. Refactoring assessment: reuse detection and cold-start readiness share
the same predicate with an explicit minimized policy; no new queue or service.

Delivery product commit/tag 42eaec25688f5e6e204933ed434e04f8d19b6915 / v0.20.3;
client source pin fb0cb128c8e0b69f56b5af2482b392da2f6916d8. Installed client
SHA256 c31f94a5a1acf3cdd19e72d406fe49f264a19dc1c206aaa49a3256e676619ec2.
Archive D:/Tools/llm-coordinator/releases/llm-coordinator-0.20.3-42eaec2.zip,
SHA256 4fcaf63775b19587ad3d6fa01f22704355cf7bdec67849b74c9a2a28e359803d.
Installed native checks used the user's already-minimized HWND without changing
it; two supported gate calls created no new window. Seven titled windows and
Outlook PID 81504 preserved; broker PID 17164 and settings preserved.
Startup lifecycle and startup diagnostics regressions passed. Cold readiness
checks still reject untitled/zero-area placeholders; ordinary launch uses /recycle.
Cleanup transaction ed533abc8dff4404429cc47572fb77eb applied with zero errors;
2028 exact members / 146702200 logical bytes removed. Task scratch absent.
No blockers or tracked deferrals remain; no historical user window was closed.
