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

The installed apartment profile deliberately leaves the current operational
register unbound until the owning task identifies its real existing source or
creates a minimal current register if none exists. `inspect` exposes this and
purchase/decision closure blocks until it is bound. This avoids inventing an
authority or reopening the archived roadmap during installation.

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
