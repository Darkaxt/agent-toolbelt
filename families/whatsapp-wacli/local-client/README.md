# WhatsApp wacli Agent Adapter

Local experimental adapter around `wacli`.

This adapter exposes curated commands only. It does not provide raw `wacli` passthrough. WhatsApp-visible mutations such as send, react, and presence require `--confirm`.

The default backend path is `%LOCALAPPDATA%\Tools\wacli\wacli.exe`; the default store is `%LOCALAPPDATA%\Tools\wacli\store`.

Normal `sync-once` refreshes the local store, but older per-chat history may require targeted backfill:

```powershell
uv run --project "$env:LOCALAPPDATA\Tools\whatsapp-wacli-agent" whatsapp-wacli-agent backfill --chat "Demo Contact"
uv run --project "$env:LOCALAPPDATA\Tools\whatsapp-wacli-agent" whatsapp-wacli-agent latest --chat "Demo Contact" --limit 100
```

`latest` auto-runs one bounded backfill when fewer messages are stored than requested. Use `--no-backfill` to inspect only the current local store.

`find-chat` searches local chat rows first, then falls back to `wacli contacts search` so contacts with WhatsApp profile names or aliases can resolve even when no chat row is stored yet.

WhatsApp may store one-to-one chats under LID JIDs even when contacts resolve by phone-number JID. The adapter reads `%LOCALAPPDATA%\Tools\wacli\store\session.db` read-only and maps phone-number JIDs such as `15551234567@s.whatsapp.net` to LID JIDs such as `900001234567@lid` for history operations. Results include `contact_jid`, `resolved_jid`, and `resolution_source` so agents can see which identity was used.

If a contact has neither local messages nor a PN-to-LID mapping, targeted backfill may fail because `wacli` needs an existing anchor message. In that case `latest` reports `backfill_seed_missing` instead of returning empty history as if it were complete.

QR login should be launched in a separate Windows console so the terminal QR is not clipped by agent debug panes:

```powershell
uv run --project "$env:LOCALAPPDATA\Tools\whatsapp-wacli-agent" whatsapp-wacli-agent auth-login --popup
```
