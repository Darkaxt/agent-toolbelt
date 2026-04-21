# WhatsApp wacli

Bridge for local WhatsApp access through [`steipete/wacli`](https://github.com/steipete/wacli) and the local curated adapter at `%LOCALAPPDATA%\Tools\whatsapp-wacli-agent`.

This family is intentionally local-first and experimental. Do not publish or install it as a normal plugin until the local acceptance workflow succeeds on the target machine.

## Scope

- Read local synced WhatsApp data through `wacli` JSON output.
- Find chats, list latest messages, search, fetch message context, and draft replies.
- Support sending text, reacting, and presence only through explicit `--confirm` gates in the local adapter.
- No raw `wacli` passthrough.

## Local Client

The family package only bridges into the local client:

```powershell
uv run --project "$env:LOCALAPPDATA\Tools\whatsapp-wacli-agent" whatsapp-wacli-agent status
```

Set `WHATSAPP_WACLI_AGENT_HOME` to override the client location.

The sanitized local client source is included under `local-client/` for backup and installation. Install it under `%LOCALAPPDATA%\Tools\whatsapp-wacli-agent` or point `WHATSAPP_WACLI_AGENT_HOME` at another checkout. The repo does not include `wacli`, WhatsApp sessions, message stores, or local database files.

## CLI

```powershell
agent-toolbelt-whatsapp-wacli auth-login --popup
agent-toolbelt-whatsapp-wacli auth-status
agent-toolbelt-whatsapp-wacli sync-once
agent-toolbelt-whatsapp-wacli find-chat --query "Demo Contact"
agent-toolbelt-whatsapp-wacli backfill --chat "Demo Contact"
agent-toolbelt-whatsapp-wacli latest --chat "Demo Contact" --limit 100
agent-toolbelt-whatsapp-wacli send-text --chat "<jid-or-name>" --message "..." --confirm
```

Without `--confirm`, WhatsApp-visible mutations are blocked by the local adapter.

`sync-once` refreshes the current local store. Older per-chat history may require `backfill`; `latest` auto-runs one bounded backfill when the stored result count is below the requested limit. Use `--no-backfill` for current-store-only reads.

`find-chat` searches stored chats first, then contact metadata, which covers WhatsApp profile names and local aliases when a contact has no chat row yet.

WhatsApp can store direct-message history under LID JIDs even when a contact resolves through a phone-number JID. The local adapter reads the `wacli` session store read-only, maps phone-number JIDs to LID JIDs for history operations, and returns `contact_jid`, `resolved_jid`, and `resolution_source` metadata. If no local anchor message or mapping exists, `latest` reports `backfill_seed_missing` rather than silently treating the empty result as complete.
