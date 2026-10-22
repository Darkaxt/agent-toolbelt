# Repair an existing draft's From account

The user explicitly requested selecting their configured account in the existing
warranty draft's From field. This authorizes that sender correction, not sending,
recreation, mailbox movement or changes to its content.

## Requirements

- R1: `edit-draft --send-using-account` selects a configured Outlook account
  independently of `--account`, which binds the existing draft's store.
- R2: Require confirmation and the existing Drafts-folder check. Resolve the
  requested account before editing; use the existing COM reference setter and
  reopen the same saved EntryID in its original store for sender verification.
  Keep existing sender-preservation behavior when the option is absent.
- R3: Sender-only repair preserves body, subject, recipients, attachments and
  identity. An unsuccessful assignment or saved readback must retain the draft
  and expose diagnostics, never recreate, send or report a verified sender.
- R4: Update wrapper, client and installed guidance, verify regression and live
  saved-item evidence, commit and deliver a verified versioned local package.
  Keep business mail and identifiers out of the distributable.
- R5: Private local recipient-domain routes must select the configured transport
  account for replies/forwards, ahead of ordinary direct-account inference.
  Explicit sender selection remains authoritative; conflicting private routes
  fail closed. Alias identity is separate from the transport account: use the
  provider's verified per-contact reverse alias, never a guessed From header.
- R6: Store the user's real domain/account mapping and provider notes exclusively
  outside the checkout and release. Public skills describe generic configuration
  discovery and alias workflow only. Do not send mail to test this configuration.

## Execution and reconciliation

| Stage | Status | Acceptance |
| --- | --- | --- |
| Sender repair and private routing | COMPLETE | R1-R3, R5-R6: integrated CLI and regression verification, private account selection and alias guidance. |
| Delivery | COMPLETE | R4, R6: installed parity, local package digest/content/privacy verification and source commit. |

No tracked deferrals. Initial internal blocker: edit-draft has no sender option;
the shared setter already supports COM object-reference assignment.

Live operational change: the selected draft disappeared before any mutation;
its same subject/conversation was subsequently read in Sent Items. No mail was
edited, sent or recreated here. Repairing that now-absent draft is no longer
applicable; this does not establish its former From field or alias delivery.
The user's subsequent explicit requirements add private routing and provider
alias identity; no business metadata belongs in this specification.

## Verified implementation

- Client/sender regression suite and wrapper checks passed; installed sender/route
  checks passed. An independent CLI-read regression reproduced dropped sender
  evidence in dispatch and now verifies its preservation.
- Live installed preview selected the private transport account, recorded the
  matching intended alias and preserved the native reverse-alias destination.
  No business draft was created or edited and no mail was sent here.
- A recipient-free disposable local draft had an unset sender. The new sender-only
  edit retained its EntryID/content, assigned through dispatch_property_putref,
  reopened the saved item and returned verified=true. The exact probe was deleted.
- Runtime and three personal skill copies are deployed; the real policy exists
  exclusively in the private installed state directory, outside the repository.
- No material design debt requiring consolidation; existing sender assignment and
  saved-item verification are reused. No blockers or tracked deferrals.
- Repository-wide skills.sh validation was attempted and stops on an unchanged
  context-transfer absolute-path check. Focused Outlook skill validation and root
  family/layout checks pass; no claim is made that the unrelated global check passed.

## Final local delivery

Version 0.1.2 is delivered as a versioned usable local source/runtime bundle.
Its independently reopened ZIP/member digests match the release receipt; the
installed runtime and three personal skill/reference copies match source.
Private route values are absent from both source and every archive member.
A generic private-configuration filename is ignored by Git as an extra guard.
The source commit is recorded in the local receipt. No public push or release
was performed. Required blockers and tracked deferrals: zero. The unrelated
repository-wide validator limitation remains explicitly recorded above.
