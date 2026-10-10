---
name: operational-recordkeeping
description: Reconcile bills, payments, correspondence, decisions and purchases with existing durable records before reporting completion. Use for company management and apartment setup operations, especially after received invoices, sent emails, payment confirmations or changed decisions; not unrelated chat or a new accounting system.
license: MIT
metadata:
  version: "0.1.2"
  compatibility: Codex and Claude; Python 3.11+ standard library. Private local project profiles and existing text, JSON or XLSX records.
---

# Operational Recordkeeping

An operational action includes reconciling its affected records, not just producing
an email or answering the immediate question. Do not claim completion while a
required update or verification remains undone. No new authority to send, pay,
purchase, contact third parties or approve accounting treatment is granted.

## Apply To The Current Event

1. Load the project profile with the bundled helper's `inspect` command. Identify
   the authoritative ledger, current obligations/decisions, correspondence state
   and evidence locations. For the local Cyprus pilot use `company` or `apartment`.
   A missing operations binding MUST be resolved before operational work: reuse
   the current domain register or create and bind a separate minimal one if none
   exists. Do not leave it unbound as "intentional setup". Apartment operations
   belong in their own register, not the company financial ledger. Do not duplicate
   company accounting or treat file creation alone as reconciled business context.
   Follow the initialization gate in [references/profiles.md](references/profiles.md).
2. Identify the event using an invoice, order or mail identifier. State exactly
   what changed, the evidence, relevant amount/currency, dates and next action.
   Distinguish invoice issue date, service period, due date and payment date.
3. Determine affected records using the profile routes AND the actual request.
   Include conditional updates as `extra_records`: e.g. an email carrying a new
   reimbursement proposal affects correspondence, current obligations AND ledger.
   Establish shared facts and scoped read-back proofs. Do not infer a successful
   outcome merely because the action was planned.
4. Perform the authorized domain action if it has not already occurred, then
   inspect its actual evidence. Run `prepare` before changing durable records,
   not before the evidence-producing action: a sent-mail check needs actual sent
   evidence. For a recovered omission, prepare a repair event now; do not pretend
   an earlier packet existed. Update existing records. Preserve original evidence.
   Correct the current owning entry rather
   than append contradictory pending states. Do not overwrite another writer's
   changes: reread before editing, merge the intended fields, use the record
   tool's conflict controls where available, and reread after saving.
5. Run `check` against the packet. Resolve mismatches, then check again. Keep its
   compact JSON report with the event evidence. Already-consistent records need
   no cosmetic edit. Report a specific unresolved evidence/update gap honestly;
   do not report the operational outcome fully reconciled until it passes.

The helper checks the declared packet, not the entire business. You remain
responsible for correct evidence, complete impact mapping and interpretation.
It does not force invocation or provide atomic multi-file writes. Never present
an agent-authored note alone as independent proof that money moved or mail sent.

## Domain Boundaries

- Bills: received, paid, payment-proof retained, forwarded and acknowledged are
  separate facts. Keep outstanding document recovery separate from unpaid debt.
- Mail: drafted is not sent. User-reported sent is not independently verified
  sent. Use the authorized Outlook read path for the latter; preserve source
  mailbox/message IDs and actual attachments. Resolve only requests actually
  answered; keep the remainder open with a concrete owner/next action/deadline.
- Expenses: proposed allocation, accountant approval, reimbursement and payment
  are separate. Whole personal bills must not silently become company expenses.
- Purchases: shortlist, quote/checkout, ordered, shipped, delivered and returned
  are different states. Track exact configuration, currency, VAT basis and
  delivery route. A company-use purchase may require a linked company handoff,
  not automatic deductibility or duplicate costs in both profiles.
- Decisions: name the currently effective decision and explicitly supersede the
  previous one; preserve dated historical calculations as history. Do not leave
  incompatible amounts or obsolete pending tasks presented as current.
- Observations: save material findings and any coverage gap before claiming a
  monitoring check was recorded. A no-op is allowed; do not append daily noise
  merely to prove execution. Record inaccessible checks as unverified.

## Keep The Workflow Light

At task start or after context loss, reread the small manifest and current open
items. At event closure inspect only affected records, not every email, receipt
or worksheet. Read [references/profiles.md](references/profiles.md) for company
versus apartment routing and [references/helper.md](references/helper.md) before
using the helper. Do not reopen archived roadmaps because old rows say WAITING.

Completion reports should briefly state what changed, which records were
reconciled and any remaining business obligation. A pending external response is
not a missing bookkeeping update if its current state is accurately recorded.

## Pilot Feedback

Owning tasks should test one real authorized event and one previously missed
update. Report the event, profile, expected affected records, helper result and
specific friction or false positives. Keep private examples local; suggest a
narrow improvement instead of bypassing the check or adding universal ceremony.
