# Persisted Outlook sender consistency

Authorization: the user reported the helper claiming a saved sender while an
independent read finds it unset, and requested handling this Outlook helper defect.
The existing clearance draft is evidence only: preserve its content and identity,
never send, recreate or modify it as part of qualification. No external test mail.

## Required outcome

- SP1: establish the cause using the exact saved-draft/readback pair and owned
  empty native fixtures. Distinguish account assignment, cached object readback,
  durable sender identity and account resolution. Never infer From from its folder.
- SP2: make creation, reply/forward, editing and independent reads use consistent
  persisted sender evidence. Correct actual native assignment/persistence when
  possible; a missing/unreadable/mismatched value must not become verified.
  Preserve existing drafts, recipients, body, attachment and private alias routing.
- SP3: fix the send path's silent assignment failure and store-account override.
  Sending requires existing explicit sending authority, the exact draft identity
  and verified intended transport immediately before dispatch. Test dispatch with
  fakes only; this task sends no message. An accepted Send call is submission,
  not independently verified delivery.
- SP4: reproduce the defect, then verify cross-process native persisted readback,
  relevant regressions and wrapper/client contracts. Use existing FIFO/COM locks;
  do not restart Outlook, bypass Coordinator, or inspect unrelated mail.
- SP5: deliver the established versioned local Coordinator release with updated
  dependency pins, installed client/skill parity and source mirrors. Preserve live
  broker, settings and other workflows. Verify delivered artifacts/activation and
  clean exact scratch. Private addresses/IDs/receipts stay outside repositories.

## Execution and reconciliation

1. Sender workflow correction (SP1-SP4) — COMPLETE. Exact original identity and
   paired results establish cached-only assignment. Empty native controls show
   ordinary Save/Close is insufficient; initializing the hidden compose editor
   and closing that owned editor with Save commits account properties. Corrected
   creation and editing survive separate processes with body/attachment bytes
   unchanged. Original user draft was read only. Full client regression suite
   passed; focused cached/stamp/ownership/send rejection checks passed. All six
   owned diagnostic/qualification drafts were removed from Drafts and Trash.
2. Final delivery (SP5) — ACTIVE. Package, installed verification, mirrors and
   scratch cleanup remain. No tracked deferrals.

Native verification requires the stored account name/stamp as corroboration of
the resolved Account object. Native stamp values are never synthesized, parsed
or logged. An existing user editor is preserved; missing committed evidence stays
unverified. Send uses the persisted account, never the store selector. Assignment
failure prevents the single Send dispatch; real sending was not used in testing.

Primary references:
https://learn.microsoft.com/en-us/office/vba/api/outlook.mailitem.sendusingaccount
https://learn.microsoft.com/en-us/office/client-developer/outlook/auxiliary/pidlidinternetaccountname
https://learn.microsoft.com/en-us/office/vba/api/outlook.inspector.close(method)

Scratch E:/Temp/outlook-sender-persistence-20261030; native/build I/O exception
D:/Temp/outlook-sender-persistence-20261030. Cleanup transaction
6caa7b954f915c611952d6b30ffb14ff. Retained evidence:
D:/Tools/llm-coordinator/verification/20261030/outlook-sender-persistence.
