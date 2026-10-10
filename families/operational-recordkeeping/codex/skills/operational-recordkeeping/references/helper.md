# Reconciliation Helper

Run the installed `scripts/invoke_operational_recordkeeping.py` with Python.
It reads business records only. `prepare` exclusively creates a packet at the
requested new path; `check --output` optionally creates a new result file.
Outputs cannot overwrite an existing file. Relative evidence paths resolve
against the event JSON; record paths against the profile JSON.

```powershell
python scripts/invoke_operational_recordkeeping.py inspect --profile company
python scripts/invoke_operational_recordkeeping.py prepare --profile company --event event.json --output packet.json
python scripts/invoke_operational_recordkeeping.py check --packet packet.json --output result.json
```

Run `prepare` after the domain action has produced real evidence, but before
updating durable bookkeeping. It is not a pre-send or pre-payment permission gate.
`inspect` reports binding/readability issues. `prepare` requires evidence whose
checks already pass, but allows record checks to be unmet before an update.
`check` rereads required records and evidence. Exit 0 means checks passed, 1 means
unreconciled records, 2 means invalid input/read failure. JSON always states the
limited verification scope. No locks, processes, mail or financial actions occur.

Example event (fictional, text/JSON version):

```json
{
  "event_id": "invoice-A123-payment",
  "kind": "payment.confirmed",
  "summary": "Payment confirmed; retain receipt and close unpaid obligation",
  "facts": {"record_key": "A123", "state": "paid", "amount": 95, "currency": "EUR"},
  "extra_records": [],
  "evidence": [{
    "path": "payment-result.json", "format": "json",
    "checks": [
      {"fact": "record_key", "at": ["invoice"]},
      {"fact": "state", "at": ["status"]},
      {"fact": "amount", "at": ["amount"]},
      {"fact": "currency", "at": ["currency"]}
    ]
  }],
  "checks": {
    "ledger": [
      {"fact": "record_key", "sheet": "Payments", "header_row": 1, "key_column": "Invoice", "key_fact": "record_key", "column": "Invoice"},
      {"fact": "state", "sheet": "Payments", "key_column": "Invoice", "key_fact": "record_key", "column": "Status"},
      {"fact": "amount", "sheet": "Payments", "key_column": "Invoice", "key_fact": "record_key", "column": "Amount"},
      {"fact": "currency", "sheet": "Payments", "key_column": "Invoice", "key_fact": "record_key", "column": "Currency"}
    ],
    "tracker": [
      {"fact": "record_key", "section": "## Invoice A123"},
      {"fact": "state", "section": "## Invoice A123"},
      {"fact": "amount", "section": "## Invoice A123"},
      {"fact": "currency", "section": "## Invoice A123"}
    ]
  }
}
```

Text checks look for a bounded shared fact string in exactly one Markdown heading's
section; add `mode: "absent"` to reject an obsolete statement, using another
declared fact such as `obsolete_pending`. `paid` cannot match `unpaid`, nor 95
match 195. Text numbers require the same literal representation (use structured
proofs for formatted amounts). Literal matching is not a semantic audit:
choose a distinctive full status sentence when an isolated word is ambiguous.
Missing/duplicate sections are errors, not successful absence checks.

JSON checks use an exact `at` list of object keys/array indices, with typed
equality by default. For existing narrative string fields use `mode: "contains"`
or `mode: "absent"`, with the same bounded literal matching as text. Do not rewrite
a whole correspondence JSON schema just to introduce status fields for the helper.
XLSX checks find exactly one row by header and stable key, then compare
the named column to the shared fact with typed equality. Duplicate headers/keys
fail. Formula cells are rejected: cached results may be stale; verify an actual
input/status cell or use the workbook's recalculated external verification.

Every record and the combined evidence must cover the route's required facts
(default `record_key`, `state`) with positive checks. Optional facts may be checked
where applicable; do not force every record to hold the entire email body or all
invoice fields. Use explicit evidence for claimed state, not a self-written
"verified" note. Evidence changes after preparation require a new packet. New
business updates do not invalidate the packet by themselves; current expectations
must still match. Check results are point-in-time, not a promise against later
concurrent edits.

Keep packets/results next to working evidence, not in public source control.
For PDF receipts or other binary originals, add an evidence entry such as
`{"path": "receipt.pdf", "source_only": true}` alongside checked extracted
text/JSON. The original is hashed and must remain unchanged; the helper does not
extract it or certify extraction fidelity. Review the extraction against the
original with the document tool. A source-only file cannot by itself satisfy
required fact coverage. A normalized summary without a retained source is not
independent payment or send evidence.

If action outcome differs from the prepared expectations, prepare a new event
with the actual supported facts rather than loosening checks to fabricate success.
