# Targeted ledger updates

A purchase/payment entry is a bounded update to an existing record system. Follow
the applicable spreadsheet skill for supported tools and preservation requirements;
this reference bounds the bookkeeping work and avoids false verification failures.

## Read, update, verify

Locate the authoritative ledger and match the event's stable order/invoice/record
ID before choosing append versus correction. Inspect the relevant headers, existing
record, nearby formatting/formula conventions, table bounds and directly affected
totals. Do not dump every worksheet or reopen the entire transaction investigation
when the necessary facts and their evidence are already available.

Batch the known facts into one cohesive update. Keep amounts numeric, currency
explicit and dates in the editor's supported native date representation (or an
Excel serial with the existing date format). An ISO string is not interchangeable
with a numeric Excel date. Keep user-reported payment distinct from independently
inspected proof; an outstanding invoice or delivery does not prevent recording the
known purchase and its actual pending obligations.

Validate the saved candidate before replacing the authoritative file. Read back
the event ID, amount/currency, payment state and date type/value, applicable table
coverage and affected totals. Use the existing concurrency/source-change checks
and event reconciliation. If the writer serializes the workbook, perform one
meaningful preservation comparison against the source. Restrict visual review to
the changed view and affected dependencies; reuse valid unchanged checks.

## Compare meaning, not serialization artifacts

Style IDs, shared-style indices, ZIP member ordering and serializer-generated
metadata can change without changing workbook behavior or appearance. Do not
count those differences as formatting regressions.

For openpyxl-based read-only comparison, cell font/fill/border/alignment/protection
attributes are StyleProxy wrappers. Comparing two proxies directly can report
different styles even when their properties are identical. Compare unwrapped
values, for example `copy.copy(first.font) == copy.copy(second.font)`, and compare
number-format strings directly. Check actual row heights, column widths, formulas,
table references, validations and other relevant features on their own merits.
Do not accept a genuine content or feature change just because style IDs are noisy.

If a check fails, identify the specific changed value/feature or invalid type and
distinguish a workbook defect from a comparator defect before rewriting. A broad
list of identical proxy mismatches is a reason to repair the check, not repeatedly
export the same workbook or restore thousands of unchanged cells. Do not replace
the authoritative workbook with an unreadable or malformed-date candidate.

Once typed saved-content verification, required preservation checks and record
reconciliation pass, finish. Another write/check is justified by new user facts,
changed source state or a meaningful failure, not by elapsed time or ceremony.
