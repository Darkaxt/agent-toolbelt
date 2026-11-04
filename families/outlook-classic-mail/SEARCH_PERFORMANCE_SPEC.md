# Outlook native search performance

Authorization: “Go fix them please”, 2026-11-04.

S1: native Outlook DASL filtering before materializing messages; dates/unread,
sender/recipient and full plain-text body queries. No 200-item sample or 500-char
search cutoff. Preserve literal substring/Unicode semantics and escape filters.
Provide explicit --indexed phrase semantics when the store supports Instant
Search; keep substring compatibility and never silently substitute query modes.
S2: lightweight Table rows, open only filtered candidates; exact --since ISO date
and relative --days are mutually exclusive. Existing metadata cache remains a
locator, not proof of complete mailbox/body coverage.
S3: structured progress and elapsed/candidate/opened counts; expose actual folder
and result limits/errors/partial coverage. Broad scan selects the bounded known
inventory, not just folders whose names match. No parallel COM searches.
S4: update guidance and test native filtering, beyond-old-window/body matches,
dates, literals, limits, cache and multi-folder scope. Bounded real read-only
search through Coordinator, with no mailbox mutation or folder rediscovery.
S5: verified versioned local Coordinator release, pinned client, preserved live
state, complete Codex/shared/Claude parity, mirrored source and scratch cleanup.

| Stage | Status | Acceptance |
| --- | --- | --- |
| Search integration and verification | COMPLETE | S1–S4: native tables, explicit indexed mode, full bodies, dates, scope/progress, client/wrapper regressions and bounded gated native qualification passed |
| Delivery | COMPLETE | S5: Coordinator 0.20.2 / 9d66134582d2ae2b packaged, independently extracted, installed and natively checked; client pin and three-agent skills verified; source mirrored; scratch and superseded candidate archive removed |

Implementation: Microsoft documents plain-text body DASL filters on GetTable;
use that native interface for this synchronous workflow rather than introduce an
asynchronous AdvancedSearch event service. Native LIKE builds a candidate superset;
full literal verification handles whitespace/wildcards without truncating bodies.
Native errors remain explicit, never silently become a slow per-item fallback.
Real qualification confirmed provider-native LIKE is still expensive on a large
store. The explicit indexed mode addresses exact word/identifier workflows;
literal substring mode remains available with honestly reported costs/coverage.
References: learn.microsoft.com/en-us/office/vba/outlook/how-to/search-and-filter/filter-the-body-of-a-mail-item
and unsupported-properties-in-a-table-object-or-table-filter in that same path.

Scratch D:/Temp/outlook-native-search-20261104 for native/build/database I/O;
compact private receipts D:/Tools/llm-coordinator/verification/outlook-search-20261104.
No new provider, service, schedule, persistent body index or global configuration.

Native evidence: source-native-indexed.json under the private receipt folder.
41,393-item Inbox: absent indexed query opened zero items (0.363 seconds engine
work); existing subject opened one (0.449 seconds). Total helper calls roughly
six seconds include startup/gate overhead. No comparative speedup ratio claimed.
One task-owned literal-substring qualification request was intentionally cancelled
with verified native ancestry/exit, preserving Outlook. Its private failure record
is not classified as an Outlook crash or failed indexed search.

Refactoring assessment: native table filtering replaces legacy enumeration for
search; existing metadata cache, FIFO, startup and exact-message readers remain.
Progress uses stderr and the existing operation journal. No extra service needed.
Legacy skill tests still asserted a blanket taskkill prohibition superseded by
the user's own-request cancellation policy; checks now assert that actual policy.
No unresolved implementation blockers or tracked deferrals.

Final product commit/tag: 45ac13c30f5acd4f73c1b40450db9558b66030df / v0.20.2,
agent-toolbelt source pin 93a452804582e50efbc07a757a89518355a2423c.
Installed client SHA256 027f053507d7b3625ddb490f9e0aaa3f55a26272faf2e44b75ae5edbcde45fe0.
Final archive: D:/Tools/llm-coordinator/releases/llm-coordinator-0.20.2-45ac13c.zip,
SHA256 9ec8c6e5639b0591b500b6ff26ee652bf232ac5ab754c41d80165368a4ba82e1.
Final native checks observed progress and took 0.318–0.557 seconds in Outlook's
indexed filter, 6–7 seconds for a complete helper call. Remaining startup overhead
is not reported as removed. Outlook PID 81504, broker PID 17164 and settings stayed.
Windows redirected-interpreter FIFO attribution was corrected and regression-tested
so an owned active search is not duplicated as queued/external work.

Cleanup transactions 1ff146c66dfa617560fc9903ae5c5bfc and
0daa3f63c24569b990c78201c6384457 applied with zero errors. Exact scratch root and
superseded candidate ZIP absent. Compact private native/package/deployment receipts
remain; no mailbox content was mutated and no folder hierarchy was rediscovered.
