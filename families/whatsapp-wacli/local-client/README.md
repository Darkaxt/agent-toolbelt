# WhatsApp wacli Agent Adapter

Local experimental adapter around `wacli`.

This adapter exposes curated commands only. It does not provide raw `wacli` passthrough. WhatsApp-visible mutations such as send, react, and presence require `--confirm`.

The adapter resolves `wacli` from `WHATSAPP_WACLI_PATH`, then `PATH`, then the legacy `%LOCALAPPDATA%\Tools\wacli\wacli.exe` compatibility fallback. The message store can be set with `WHATSAPP_WACLI_STORE`; otherwise the adapter uses its default local runtime store.

Normal `sync-once` refreshes the local store, but older per-chat history may require targeted backfill:

```powershell
uv run --project <path-to-whatsapp-wacli-agent> whatsapp-wacli-agent backfill --chat "Demo Contact"
uv run --project <path-to-whatsapp-wacli-agent> whatsapp-wacli-agent latest --chat "Demo Contact" --limit 100
```

`latest` auto-runs one bounded backfill when fewer messages are stored than requested. Use `--no-backfill` to inspect only the current local store.

`find-chat` searches local chat rows first, then falls back to `wacli contacts search` so contacts with WhatsApp profile names or aliases can resolve even when no chat row is stored yet.

WhatsApp may store one-to-one chats under either phone-number JIDs or LID JIDs. The adapter reads the configured `wacli` session store read-only, records `contact_jid`, `resolved_jid`, and `resolution_source`, then chooses history/backfill JIDs from a fallback chain instead of blindly preferring the mapped LID. When the local store already has messages under the phone JID, reads prefer that chat JID first; if `wacli` returns `messages:null` or a seed-missing backfill result, the adapter retries alternate JIDs automatically.

If a contact has neither local messages nor a PN-to-LID mapping, targeted backfill may fail because `wacli` needs an existing anchor message. In that case `latest` reports `backfill_seed_missing` instead of returning empty history as if it were complete.

QR login should be launched in a separate Windows console so the terminal QR is not clipped by agent debug panes:

```powershell
uv run --project <path-to-whatsapp-wacli-agent> whatsapp-wacli-agent auth-login --popup
```
