# Cancel an owned Outlook request

A chat may intentionally cancel its own queued or running helper request without
asking the user again. Ownership is the current originating Codex/Claude session,
not the mailbox, project, thread title, an old PID or a slow response. This is
permission to end that request, not an automatic timeout or authority to stop
unrelated mail work. Continue normal supervision until cancellation is intentional.

## Bind the exact request

Retain its original managed tool session and Coordinator operation identity.
Check the recorded originating session against the current caller and inspect
the live wrapper/client ancestry and native creation identities. A renamed chat
still owns its original request; a matching title alone establishes nothing.
When old metadata lacks a session binding, the original retained launch session
plus verified live ancestry/creation identities can establish ownership. If
ownership cannot be established, preserve it and request a scoped user decision.

The Python virtual-environment redirector can create a child interpreter. The
Coordinator engine PID and the FIFO ticket PID may therefore differ. Bind that
actual parent/child relationship instead of assuming either PID identifies an
unrelated request or terminating every Python process.

## Cancel only the owned helper

Use the managed session's cancellation/termination support when it confirms exit
of the actual owned helper, not merely disconnection of its output observer.
If no request-cancellation command is exposed, exact helper-process termination
is permitted for this verified own-request case. Recheck identity immediately
before termination and observe actual native exit. Stop only the bound worker
and any still-live dedicated redirector/wrapper for that request. Do not terminate
a shared agent host, Coordinator service, Outlook process or unrelated descendants.
Never substitute a broad `python.exe`/`OUTLOOK.EXE` kill or ad hoc COM Quit.

For several explicitly selected cancellations, withdraw queued requests before
ending the active one so they cannot immediately acquire COM and reopen/reuse
Outlook. This does not grant permission to cancel other chats' queue entries.
The user may authorize those separately; identify the requests and interruption.

Keep the queue database intact. Its existing admission path reclaims a ticket
after native liveness proves the recorded worker is dead. A dead historical row
remaining before the next admission is not a live owner. Do not manually delete
queue rows, locks, database files or signing/state data, or use lease age to take
over another live request. Inspect actual liveness and the next result's
`queue.reclaimed_dead_tickets` when another authorized command is needed; do not
start a COM probe solely to force metadata cleanup during Outlook shutdown.

## Record the outcome without replay

Observe the original wrapper's exit and record the original operation/session,
whether it had queue admission, verified helper exit and any remaining consumers.
A forced worker exit may surface as invalid JSON in an older wrapper. Record it
as an intentional cancellation with the native receipt, not proof of a fresh
Outlook crash or successful mailbox operation.

Before admission, cancellation means that request was not dispatched. Once COM
work began, a send, draft save, move, deletion or other mutation may already have
occurred. Preserve an unknown outcome and reconcile the exact original item;
never automatically replay to obtain a cleaner result or declare it unexecuted.
A read-only cancellation does not prove a requested sync completed.

Stopping an owned request does not guarantee Outlook will close; add-ins, its
sync engine or other clients can retain it. Terminating/restarting shared Outlook
or cancelling another chat's request still requires explicit user authorization.
Preserve drafts and report the remaining application state separately.
