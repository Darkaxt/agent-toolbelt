# Outlook sender reference assignment

## Requirements

The requested outcome is reliable sender assignment in the Outlook helper after
a saved LockSight reply reported its From account as unset. Do not modify or
recreate existing business drafts as part of helper verification; never send.

- Use COM object-reference assignment for SendUsingAccount on actual Outlook
  automation objects. Resolve its member ID by name, without a guessed account,
  hardcoded dispatch ID or model/UI fallback.
- Keep normal Python-object support for isolated tests. Do not fall back to the
  known ineffective value setter after a COM reference-assignment failure.
- Retain sanitized assignment errors and add the assignment method to diagnostics.
- Keep saved EntryID/store readback as the sender proof. Selecting an account,
  a successful COM call or pre-save readback does not prove persistence.
- Preserve body/thread content, recipients, attachments, placement, single-lane
  COM access and existing edit-draft sender-preservation semantics.
- Verify source and installed copies, then commit and synchronize the correction.

## Evidence and plan

One stage: correct sender assignment and verify all existing draft paths.
No required deferrals.

The affected creation result reports assignment write_succeeded=true and an
unset assignment_readback, followed by unset saved_item_readback. Installed and
repository client hashes match. Existing plain-Python fixtures do not exercise
COM dispatch semantics.

Use a queue/lock-protected unsaved Outlook probe to compare ordinary assignment
with DISPATCH_PROPERTYPUTREF, then add a COM-boundary regression and fix the
shared setter. Run sender/client and wrapper checks, deploy, verify parity and
record live probe evidence. Existing business drafts remain untouched.

## Reconciliation

Implementation stage: COMPLETE. No blockers or tracked deferrals remain in the
helper correction. Final delivery requires the commit and remote identity check.

- Root cause reproduced live: ordinary property assignment returned without
  error but did not select an account; reference assignment on the same unsaved
  object selected the expected account. The probe was discarded.
- COM regression cases reproduce the silent no-op and verify reference writes,
  named member resolution, error sanitization and no value-setter fallback.
- Sender and client tests pass; wrapper and root family wiring checks pass.
- The installed runtime used reference assignment, saved and reopened empty
  disposable probes in both affected Gmail accounts, and returned verified
  persisted sender matches. Each probe was removed from Drafts. Nothing was sent.
- Codex, agents and Claude skill copies were updated. Installed source parity,
  skill structure and runtime resolution are verified before final delivery.
- The initial source probe created scratch queue/lock files in the checkout.
  Those exact files were removed through transactional cleanup. The maintained
  probe now coordinates through the installed runtime's queue and lock instead.
- Existing business drafts were not edited or recreated. Their previously unset
  sender remains unresolved until separately corrected; this implementation
  must not be presented as repairing those saved drafts.

The focused shared-setter correction needs no additional refactoring stage.

References:
- https://github.com/mhammond/pywin32/issues/1862
- https://learn.microsoft.com/en-us/windows/win32/api/oaidl/nf-oaidl-idispatch-invoke
- https://learn.microsoft.com/en-us/office/vba/api/outlook.mailitem.sendusingaccount
