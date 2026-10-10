# Profile Responsibilities

## Company

Use the existing payment/expense workbook as financial source of truth. The
operational tracker owns current obligations and decisions; mail state owns
notification/response tracking. Working notes explain proposals and evidence,
not a separate authoritative balance.

When a proposal changes, update its current tracker entry and applicable workbook
rows, not just the draft. When an email is sent, update the correspondence state
and affected obligations; a sent attachment does not prove its contents are
current. Verify the attachment version when material. Keep pending evidence
retrieval, payment and accountant approval separate.

The installed company profile binds existing files. Add affected working notes
through an explicit profile binding if needed. Do not infer a bank balance from
old projections or convert a historical target into the current one.

## Apartment

Use the current buying baseline for market observations only. Archived move-in
roadmaps are historical. Do not store orders in a price-observation table just
because it is the only configured file.

### Required Initialization Gate

If no real current operations register exists, the owning agent MUST create a
separate apartment register and bind `records.operations` to it before continuing
operational work. Use [assets/apartment-operations.md](../assets/apartment-operations.md)
as a minimal starting point. Reuse a verified existing register instead of
creating duplicates. Creation and binding are normal bookkeeping setup, not a
new purchase/payment authorization or an extra user approval checkpoint.

The local pilot's separate register is bound in the private apartment profile.
An unbound/missing file must be repaired, not described as permanently intentional.
`inspect` checks readability and declared readiness, not the completeness of the
business review: an empty register is not reconciled context.

Before the first operational event, review the owning task's current decisions,
orders, correspondence and bill evidence; populate confirmed current items and
record exactly which uncertain items need verification. Preserve source IDs,
evidence links and next actions. Do not blindly import old roadmap WAITING rows.
Change initialization state to `current_context_reconciled` only after this review,
recording the reviewed sources and actual open items. The private profile's
`ready_when` guard requires `State: current_context_reconciled` in `## Initialization`.
The helper blocks `prepare` and closure for that record until this holds; `inspect`
reports readability separately from readiness. This is a declared review gate,
not automatic proof that the owning agent performed a sufficient context review.
Do not claim zero obligations
just because the newly created register has no entries. Pure market observations
may continue through the baseline without treating initialization as completed.

Use one heading per stable item ID. Track exact item/configuration, supplier,
amount/currency/VAT basis, personal/company-use classification, order/delivery
state, payment state, invoice/receipt evidence, correspondence state, owner,
next action/deadline, last verification and superseded decisions as applicable.
Unknown values stay explicitly unverified. Update current fields; preserve a
short dated history for material changes. A supplier's draft/quote is not an order.

Link a company-related purchase to its company evidence/expense candidate with
the same order identifier. Only mark the cross-project handoff complete after
the destination record exists; merely mentioning another task is not delivery.

## Profile Shape

Paths are absolute or relative to the profile file. Do not commit private
profiles. Each event route lists mandatory records and optional required facts;
all mandatory and `extra_records` must have proofs. Profile omission is not a
waiver of a genuinely affected record. Preserve existing routing unless correcting
it on evidence, not just to make a failed check pass.

```json
{
  "profile_id": "example-company",
  "records": {
    "ledger": {"path": "records/ledger.xlsx", "format": "xlsx"},
    "tracker": {"path": "records/current.md", "format": "text"}
  },
  "routes": {
    "payment.confirmed": {
      "records": ["ledger", "tracker"],
      "facts": ["record_key", "state", "amount", "currency"]
    }
  }
}
```
