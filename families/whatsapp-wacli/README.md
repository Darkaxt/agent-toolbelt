# WhatsApp wacli

Bridge for local WhatsApp access through [`steipete/wacli`](https://github.com/steipete/wacli) and a local curated adapter project.

This family is intentionally local-first and experimental. Install the Codex/Claude integrations only after the local adapter authenticates and returns structured chat data on the target machine.

## Scope

- Read local synced WhatsApp data through `wacli` JSON output.
- Find chats, list latest messages, search, fetch message context, and draft replies.
- Support sending text, reacting, and presence only through explicit `--confirm` gates in the local adapter.
- No raw `wacli` passthrough.

## Why use this adapter instead of raw `wacli`

Public raw-CLI skills can be useful when an agent already knows the exact
`wacli` command and identifier to use. This family is narrower on purpose: it
adds a structured helper layer so agents do not have to infer WhatsApp storage
details or safety policy from raw terminal output.

- JSON-first responses make chat lookup, latest-message reads, context windows,
  and draft generation easier to audit.
- Chat resolution returns `chat_jid`, `contact_jid`, `resolved_jid`,
  `resolution_source`, `used_jid`, and `attempted_jids` where applicable, so
  phone-number JID versus LID ambiguity is visible instead of hidden.
- `latest` uses bounded, explicit backfill behavior and reports
  `backfill_seed_missing` when the local store lacks an anchor for older
  history.
- When chat metadata is newer than readable message rows, `latest` fails
  closed with `message_store_lag` and `message_store_freshness.recovery`; the
  next step is recreating or relinking the `wacli` session into a fresh store,
  not more blind retries.
- Returned messages keep raw `wacli` fields and add `message.presentation` so
  agents can prefer resolved chat labels, edited-message display text, and
  media captions/placeholders without losing provenance.
- `latest`, chat-scoped `search`, `context`, and `draft-reply` can opt into
  bounded local media materialization with `--include-media`; downloaded paths
  are reported under `message.presentation.media` for multimodal inspection.
  If the store is locked but a safe `local_path` already exists in the local
  message DB, the media is still reported as `available: true` with
  `artifact_source: "existing_local_path"`.
- `draft-reply` is model-free: it returns a `draft_packet` with normalized
  compact context summary, media artifacts, and a `model_prompt`; the agent
  must generate the actual reply text in chat.
- WhatsApp-visible actions stay behind exact `--confirm` gates; local sync and
  backfill only update the local store.

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
agent-toolbelt-whatsapp-wacli latest --chat "Demo Contact" --limit 20 --include-media --media-limit 3
agent-toolbelt-whatsapp-wacli send-text --chat "<jid-or-name>" --message "..." --confirm
```

Without `--confirm`, WhatsApp-visible mutations are blocked by the local adapter.

`sync-once` refreshes the current local store. Older per-chat history may require `backfill`; `latest` auto-runs one bounded backfill when the stored result count is below the requested limit. Use `--no-backfill` for current-store-only reads.

During `auth-login --popup`, the separate QR/login PowerShell process may own
the local `wacli` store lock after authentication while the session settles.
Do not kill that process from an agent session to clear a lock. Poll
`auth-status`/`status`, wait for the process to exit or release the lock, and
ask the user before terminating any QR/login/sync process.

`find-chat` searches stored chats first, then local chat/message metadata, then
live WhatsApp session profile/phone metadata, then contact metadata. For
non-contact chats, the resolver can use live `whatsmeow_contacts` profile
labels and PN/LID mappings, including phone fragments such as `99041717` or
`041717`. If a fresh relink stores a chat under only its JID and live session
metadata is missing, the resolver can use read-only archived store chat names
as aliases, but only when that JID also exists in the current fresh store.

WhatsApp can store direct-message history under either phone-number JIDs or LID JIDs. The local adapter reads the `wacli` session store read-only, returns `contact_jid`, `resolved_jid`, and `resolution_source` metadata, and then uses a store-aware fallback chain for `latest`, `search`, and `backfill` instead of blindly preferring the mapped LID. If the local store already has messages under the phone JID, reads prefer that chat JID first; if `wacli` returns `messages:null` or a seed-missing backfill result, the adapter retries alternate JIDs automatically. If no local anchor message or mapping exists, `latest` reports `backfill_seed_missing` rather than silently treating the empty result as complete.

If `latest` returns `message_store_lag`, the chat table has newer activity than
the readable message rows. Normal sync/backfill did not recover the message
bodies, so the helper recommends recreating or relinking the `wacli` session
into a fresh store before treating the chat as current.

For summarization, prefer `message.presentation.chat_display_name` and
`message.presentation.text` over raw `ChatName`/`Text`; raw fields remain in the
payload for audit/debugging. Use `--include-media --media-limit <n>` only when
the returned rows contain media that should be saved locally for OCR or visual
analysis. Media download is not WhatsApp-visible, but it writes local artifact
files and is therefore explicit and bounded. If
`message.presentation.media.available` is true, the artifact is usable even when
`downloaded` is false; inspect `artifact_source` and
`download_attempt_error` to distinguish an existing local artifact from a fresh
download.

`draft-reply` is a context-packaging helper, not an LLM. It returns
`result.draft_packet.draft_status = "needs_model_generation"`, normalized
`context_summary`, concise `context_messages`, optional `media_artifacts`, and a
`model_prompt`. Codex or Claude should read `context_summary` first, inspect
`context_messages` only when needed, and use that packet to produce a
`draft_text` in the conversation.
Sending still requires a separate explicit `send-text --confirm`.
