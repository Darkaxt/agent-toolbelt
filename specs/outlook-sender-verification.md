# Outlook Saved-Draft Sender Verification

Already authorized: repair the helper's sender-diagnostic and verification gaps,
deploy verified source/skill updates and synchronize through the normal PR path.
Do not create, edit or send real mailbox items during this task. No GUI workaround,
ad hoc Outlook COM operation, speculative setter adapter or account-policy change.

## Requirements

- S1: Preserve sanitized assignment, account-property and SMTP-property failures;
  distinguish assignment failure, unset account, empty SMTP and failed readback.
- S2: For reply, forward and standalone creation, verify the saved item through
  GetItemFromID with its exact EntryID/store binding after Save. Never use an
  unsaved/in-memory value or Drafts-folder placement as persisted sender proof.
- S3: Add explicit requested/actual/status/verified/source/error metadata without
  breaking created=true (which means saved, not ready). Reopen failure, mismatch,
  missing identity and read errors must not claim verified sender success.
- S4: Exact draft reads expose observed sender metadata. Body/attachment edits
  preserve the original sender and check saved readback without selecting a new
  sender merely from the mailbox/store. Unknown expected sender stays unknown.
- S5: Sender-verification warnings get bounded, sanitized diagnostic-log evidence
  even when the draft was saved successfully. Do not log message content or IDs.
- S6: Preserve recipient derivation, quoting, body formatting, attachment handling,
  placement, confirmation and single-lane behavior. Never auto-recreate a saved
  unverified draft, retry mutations, or change the send command in this patch.
- S7: Focused regressions and local-client/wrapper/root checks pass. Verify deployed
  client and Codex/agents/Claude skill content, without claiming live mail validation.

| Stage | Status | Acceptance |
| --- | --- | --- |
| Persisted sender evidence | COMPLETE | S1-S7 implemented, verified and deployed; evidence below. |

No tracked deferrals. Delivery then requires commit, normal PR checks/merge and
clean local-main/remote parity. The cause of the user's specific account-binding
failure remains unconfirmed until the enhanced diagnostics observe that operation.

## Evidence

Root cause of the diagnostic gap: set_send_using_account discards setter errors,
safe_get discards getter errors, the target-store fallback repeats that same setter,
and placement_summary reads only the current object without reopening the saved
draft. The old regression deliberately accepted created=true plus an unset warning.
Installed client source initially matched the repository, so this is not install drift.

Final reconciliation: S1-S3 have saved-item identity/readback coverage, separate
assignment evidence, sanitized errors and non-success on unreadable/mismatching
senders. S4 preserves existing edit senders and labels exact reads as observations.
S5 logs sender warnings without account/identifier fields; logging failure cannot
turn a saved draft into a failed create. S6 retains existing quoting, recipients,
attachments and mutation boundaries. S7 evidence:

- Installed local-client suite: 127 checks passed, including 16 sender regressions.
- Wrapper and root family/layout checks: 65 passed.
- One source-suite run exposed a pre-existing queue timing flake: a holder sleeps
  200 ms while the waiter starts its 50 ms budget only after initialization. That
  isolated check and the final installed suite passed; queue code was not changed.
- Client/CLI files and deployed test sources hash-match canonical source.
- Codex and agents skill copies match the Codex bundle. Claude's enabled local
  marketplace and cached plugin copies match the Claude bundle; all four validate.
- Claude's installed launcher was stale despite its canonical copy already being
  repaired. Both plugin launchers were refreshed; Codex/Claude --help now succeed
  from the user home directory, outside repository-relative bootstrap context.
- Read-only diagnostics-log confirms the wrapper selects the installed local_tools
  client. No live mailbox creation, modification, sending or GUI operation occurred.

These checks establish verification/diagnostic behavior, not that the reported
Gmail account-binding failure has been reproduced or repaired. The next authorized
draft operation can expose its specific COM cause instead of hiding it.
