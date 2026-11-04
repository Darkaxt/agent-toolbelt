# Native search performance

Use cache-show for repeated subject/sender/contact metadata, then read exact IDs.
For a TIN, known word or phrase, use search --indexed with the smallest relevant
account/folder and --since YYYY-MM-DD, or --days N. --since is inclusive, accepts
ISO dates/times, and interprets a timezone-less date in the machine's local zone.
Neither cutoff is invented when the task needs older mail.

--indexed explicitly uses Outlook's ci_phrasematch semantics. It requires Instant
Search on that store. This is phrase/token search, not arbitrary substring search;
a miss is not proof that no longer word contains the text. The helper reports
unavailable indexing instead of silently running an expensive scan. Omit --indexed
only when literal substring matching is actually needed, keeping the scope narrow.

Native DASL Table filters apply dates, unread and text before materializing items.
Bodies are searched in full plain text; excerpts in returned summaries remain short.
No body content is added to the metadata cache. Quotes/wildcards are handled as
candidate supersets followed by literal checks, rather than executable filter input.

Inspect result.search (single folder), or searched_folders[].search (multi-folder):
backend, query_mode, instant_search_enabled, candidate_rows, rows_examined,
items_opened, elapsed_seconds and remaining_candidates. Remaining candidates mean
the result limit stopped enumeration. No matches in selected folders or an incomplete
inventory do not prove absence across every account. scope.limited and coverage
state the bounded search scope. --broad-scan selects the known inventory up to
--folder-limit; it never rediscovers folders or removes that explicit bound.

Coordinator records sanitized stage/count progress while a request runs. Retain
and observe its original session; use the request-cancellation reference to stop
only your own request if the chosen search is no longer needed. Keep COM calls
sequential. Do not switch connectors merely because one search is slow.

