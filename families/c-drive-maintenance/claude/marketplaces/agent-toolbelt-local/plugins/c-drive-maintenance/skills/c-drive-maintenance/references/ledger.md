# Maintenance Ledger Template

Run scope / authority:
Export path and date (historical evidence only):
Free-space target and units:
Initial measured free bytes:
Known coverage gaps:

| Exact target / operation | Live bytes | Owner task / project | Consumers and preserved state | Authority and evidence | Status | Ticket / native receipt / commit | Prevention / exception |
| --- | --- | --- | --- | --- | --- | --- | --- |

Use operation statuses: needs_evidence, ready, executing, awaiting_owner,
verified, partial, blocked, preserved. A sent request is awaiting_owner, not
verified. Document the exact blocked condition and how it will be resolved.

For owner requests, deduplicate by task ID + project + toolchain + explicit
candidate version. Record dispatch receipt and inspect subsequent completion.

For each completed action include fresh membership/reference checks, verification
result, exact deleted bytes if known, and actual free-space delta separately.
Do not sum parent/child sizes, hardlink names, or export estimates as reclaimed.

Final reconciliation:
- Completed actions and preserved consumers.
- Compatibility exceptions with concrete evidence.
- Remaining required actions with explicit blockers/owner status.
- Retention/relocation changes and verified activation/recovery.
- Final measured free bytes and concurrent growth caveats.
