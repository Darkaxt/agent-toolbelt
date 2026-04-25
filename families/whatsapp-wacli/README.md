# WhatsApp wacli

Bridge for local WhatsApp access through [`steipete/wacli`](https://github.com/steipete/wacli) and a local curated adapter project.

This family is intentionally local-first and experimental. Install the Codex/Claude integrations only after the local adapter authenticates and returns structured chat data on the target machine.

## Scope

- Read local synced WhatsApp data through `wacli` JSON output.
- Find chats, list latest messages, search, fetch message context, and draft replies.
- Support sending text, reacting, and presence only through explicit `--confirm` gates in the local adapter.
- No raw `wacli` passthrough.

## Local Client

The family package only bridges into the local client:

```powershell
uv run --project <path-to-whatsapp-wacli-agent> whatsapp-wacli-agent status
```

Set `WHATSAPP_WACLI_AGENT_HOME` to point the bridge at the client project.

The sanitized local client source is included under `local-client/` for backup and installation. Use `WHATSAPP_WACLI_AGENT_HOME` or `--client-home` for non-default locations. The legacy `%LOCALAPPDATA%\Tools\whatsapp-wacli-agent` project root remains a compatibility fallback. The repo does not include `wacli`, WhatsApp sessions, message stores, or local database files.

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

WhatsApp can store direct-message history under either phone-number JIDs or LID JIDs. The local adapter reads the `wacli` session store read-only, returns `contact_jid`, `resolved_jid`, and `resolution_source` metadata, and then uses a store-aware fallback chain for `latest`, `search`, and `backfill` instead of blindly preferring the mapped LID. If the local store already has messages under the phone JID, reads prefer that chat JID first; if `wacli` returns `messages:null` or a seed-missing backfill result, the adapter retries alternate JIDs automatically. If no local anchor message or mapping exists, `latest` reports `backfill_seed_missing` rather than silently treating the empty result as complete.
