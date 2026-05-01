# WhatsApp wacli Agent Adapter

Local experimental adapter around `wacli`.

This adapter exposes curated commands only. It does not provide raw `wacli` passthrough. WhatsApp-visible mutations such as send, react, and presence require `--confirm`.

The adapter resolves `wacli` from `WHATSAPP_WACLI_PATH`, then `PATH`, then the legacy `%LOCALAPPDATA%\Tools\wacli\wacli.exe` compatibility fallback. The message store can be set with `WHATSAPP_WACLI_STORE`; otherwise the adapter uses its default local runtime store.

Normal `sync-once` refreshes the local store, but older per-chat history may require targeted backfill:

```powershell
uv run --project <path-to-whatsapp-wacli-agent> whatsapp-wacli-agent backfill --chat "Demo Contact"
uv run --project <path-to-whatsapp-wacli-agent> whatsapp-wacli-agent latest --chat "Demo Contact" --limit 100
uv run --project <path-to-whatsapp-wacli-agent> whatsapp-wacli-agent latest --chat "Demo Contact" --include-media --media-limit 3
```

`latest` auto-runs one bounded backfill when fewer messages are stored than requested. Use `--no-backfill` to inspect only the current local store.

Returned messages preserve raw `wacli` fields and add a `presentation` object.
Agents should read `presentation.chat_display_name` and `presentation.text`
first, then fall back to raw fields only for provenance/debugging. `latest`,
chat-scoped `search`, `context`, and `draft-reply` accept
`--include-media --media-limit <n>` to materialize media from already-returned
rows into local artifact files for OCR or visual analysis; default reads do not
download media. If a media download attempt fails because the store is locked
but the local message DB already has a safe `local_path`, the normalized media
object reports `available: true`, `artifact_source: "existing_local_path"`, and
keeps the lock failure in `download_attempt_error` instead of treating the row
as a hard media error.

`draft-reply` remains model-free. It returns `result.draft_packet` with
`draft_status: "needs_model_generation"`, `context_summary`, concise normalized
`context_messages`, optional `media_artifacts`, and a `model_prompt`. The
calling agent should read `context_summary` first, inspect full
`context_messages` only when needed, and turn that packet into final reply text
in chat; sending still requires a separate confirmed `send-text` call.

`find-chat` searches local chat rows first, then falls back to `wacli contacts search` so contacts with WhatsApp profile names or aliases can resolve even when no chat row is stored yet.

For non-contact chats, `find-chat` also reads live session metadata from
`session.db` before using archived aliases. This covers WhatsApp profile labels
from `whatsmeow_contacts` and PN/LID phone mappings from `whatsmeow_lid_map`, so
queries like `+357 99 041717`, `99041717`, or `041717` can resolve to a live
LID-backed chat. Archived stale-store aliases remain a last-resort fallback and
are only used when the target JID exists in the current store.

WhatsApp may store one-to-one chats under either phone-number JIDs or LID JIDs, and both shards can contain different readable rows for the same conversation. For `latest` and chat-scoped `search`, the adapter reads every seeded PN/LID candidate shard, merges rows, dedupes by message id where possible, sorts by message timestamp, and then applies the requested limit. `used_jid` remains the newest returned row's JID for compatibility; `used_jids`, `history_selection.candidate_jids`, `history_selection.per_jid`, and `split_history_merged` expose shard aggregation. `backfill` still uses bounded fallback behavior and is not converted into an all-shard mutation.

`find-chat` enriches chat summary timestamps from the same shard set. A raw
chat-list `LastMessageTS` can therefore be updated to the newest local PN/LID
metadata timestamp, with details under `chat_metadata_selection`, without
reading message bodies.

If a contact has neither local messages nor a PN-to-LID mapping, targeted backfill may fail because `wacli` needs an existing anchor message. In that case `latest` reports `backfill_seed_missing` instead of returning empty history as if it were complete.

QR login should be launched in a separate Windows console so the terminal QR is not clipped by agent debug panes:

```powershell
uv run --project <path-to-whatsapp-wacli-agent> whatsapp-wacli-agent auth-login --popup
```

Do not kill the QR/login PowerShell process from an agent session to clear a
store lock. After the QR is scanned, that process may still own the local
`wacli` store lock while the session settles. Poll `auth-status`/`status`, wait
for the process to exit or release the lock, and ask the user before
terminating any QR/login/sync process.
