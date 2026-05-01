---
name: whatsapp-wacli
description: Use local WhatsApp access through the experimental wacli adapter for chat lookup, latest messages, search, context, reply drafting, and explicitly confirmed WhatsApp-visible actions.
version: 0.1.0
---

# WhatsApp wacli

Use `scripts/invoke_whatsapp_wacli.py` for local WhatsApp access through the curated local adapter project. The wrapper resolves the project through `--client-home`, `WHATSAPP_WACLI_AGENT_HOME`, or the legacy local compatibility project root. The adapter uses `steipete/wacli` with an explicit local store and JSON output.

This skill is experimental and local-first. Do not expose raw `wacli` command passthrough, local database files, auth state, or session artifacts.

## Why This Wrapper

Use this wrapper instead of raw `wacli` when an agent needs reliable, auditable
WhatsApp context rather than direct terminal passthrough:

- It returns structured JSON for chat lookup, message reads, search, context,
  drafts, and visible-action safety failures.
- It exposes phone-number JID versus LID ambiguity through fields such as
  `chat_jid`, `contact_jid`, `resolved_jid`, `resolution_source`, `used_jid`,
  `used_jids`, `attempted_jids`, and `history_selection`.
- It keeps history expansion bounded and reports `backfill_seed_missing` when
  the local store lacks the anchor needed for targeted history backfill.
- It fails closed with `message_store_lag` when chat metadata is newer than
  readable message rows and reports a recreate/relink session recovery step.
- It preserves raw `wacli` message payloads while adding
  `message.presentation` fields for resolved chat labels, edited-message text,
  and media captions/placeholders.
- It can explicitly materialize media from already-returned rows with
  `--include-media --media-limit <n>` so images/documents can be inspected as
  local artifacts when needed. If a fresh media download cannot acquire the
  store lock but a safe existing `local_path` is present, the media reports
  `available: true` and `artifact_source: "existing_local_path"`.
- It keeps `draft-reply` model-free by returning `result.draft_packet`; Claude
  must generate the final reply text from that packet in chat when
  `draft_status` is `needs_model_generation`.
- It blocks WhatsApp-visible actions unless the exact action is confirmed with
  the adapter's `--confirm` flag.

## Routing

- Use this skill for WhatsApp chat lookup, recent conversation summaries, message search, message context, and reply drafting.
- Use this skill for sending text, reacting, or setting presence only when the user explicitly confirms the exact WhatsApp-visible action.
- Do not use this skill for WhatsApp Desktop database scraping, screenshots, browser token extraction, or unaudited raw CLI passthrough.

## Workflows

- For `auth-login --popup` and new-session relinking, launch the popup and let the user scan the QR. Do not kill the QR/login PowerShell process from an agent session to clear a store lock; it may own the local `wacli` store lock after authentication while the session settles. Poll `auth-status` and `status`, run `sync-once` only after the popup exits or releases the lock, and ask the user before terminating any QR/login/sync process.
- For "latest conversation with X", run `auth-status`, then `sync-once` when needed, then `find-chat --query "<name-or-phone>"`, then `latest --chat "<name-or-jid>" --limit <n>`. `find-chat` searches chats, local chat/message metadata, live WhatsApp session profile/phone metadata, contact metadata, and read-only archived store aliases for non-contact chats when the same JID exists in the current fresh store.
- Check `chat_jid`, `resolved_jid`, and `resolution_source`, but let the adapter choose the actual history shards. For `latest` and chat-scoped `search`, it reads seeded PN/LID shards, merges rows, dedupes by message id where possible, sorts by timestamp, and then applies the requested limit.
- Treat `find-chat` `LastMessageTS`/`last_message_ts` as shard-aware helper metadata. If `chat_metadata_selection.split_history_detected` is true, the timestamp may come from a linked PN/LID shard rather than the raw chat-list row.
- Allow bounded auto-backfill for `latest` unless the user asks for current synced data only.
- If `resolution.used_jids` contains multiple JIDs or warnings include `split_history_merged`, treat the result as one merged conversation. Use `history_selection.per_jid` only as diagnostics.
- Prefer `message.presentation.chat_display_name` and `message.presentation.text` for summaries. Raw `ChatName`, `Text`, and `DisplayText` remain provenance/debug fields.
- If returned rows contain media that matters for the task, rerun the same read with `--include-media --media-limit <n>` and inspect `message.presentation.media.available`, `artifact_source`, and `artifact_path` for OCR or visual analysis. `available=true` is usable even when `downloaded=false`; use `download_attempt_error` only as diagnostic context.
- If `backfill_seed_missing` is returned, report that the local store lacks the anchor needed for targeted history backfill instead of implying there are no messages.
- If `message_store_lag` is returned, report that normal sync/backfill did not recover message bodies and the next recovery step is recreating or relinking the `wacli` session into a fresh store.
- For reply drafting, run `draft-reply --chat "<name-or-jid>" --instruction "<goal>"`, read `result.draft_packet.context_summary` first, inspect `context_messages`, `media_artifacts`, and `model_prompt` only as needed, then generate the actual `draft_text` in chat when `draft_status` is `needs_model_generation`. Do not expect the helper subprocess to produce LLM prose, and do not send unless the user explicitly confirms the exact outgoing message through a separate `send-text --confirm`.

## Safety

- Read commands: `status`, `auth-status`, `sync-once`, `find-chat`, `latest`, `search`, `context`, `draft-reply`.
- Local-store sync commands: `sync-once` and `backfill`; these are not WhatsApp-visible actions.
- WhatsApp-visible commands: `send-text`, `react`, `presence`.
- `send-text`, `react`, and `presence` must include `--confirm`; otherwise the adapter blocks them.
- `--include-media` writes local media artifact files only for messages already returned by `latest`, `search`, `context`, or `draft-reply`; it is not WhatsApp-visible, but keep it explicit and bounded.

## Script Interface

```bash
python scripts/invoke_whatsapp_wacli.py status
python scripts/invoke_whatsapp_wacli.py auth-status
python scripts/invoke_whatsapp_wacli.py auth-login --popup
python scripts/invoke_whatsapp_wacli.py sync-once
python scripts/invoke_whatsapp_wacli.py find-chat --query "<name-or-phone>" [--limit <n>]
python scripts/invoke_whatsapp_wacli.py backfill --chat "<jid-or-query>" [--count <n>] [--requests <n>] [--wait-sec <n>]
python scripts/invoke_whatsapp_wacli.py latest --chat "<jid-or-query>" [--limit <n>] [--no-backfill] [--backfill-count <n>] [--backfill-requests <n>] [--backfill-wait-sec <n>] [--include-media] [--media-limit <n>]
python scripts/invoke_whatsapp_wacli.py search --query "<text>" [--chat "<jid-or-query>"] [--limit <n>] [--include-media] [--media-limit <n>]
python scripts/invoke_whatsapp_wacli.py context --message-id <id> [--before <n>] [--after <n>] [--include-media] [--media-limit <n>]
python scripts/invoke_whatsapp_wacli.py draft-reply --chat "<jid-or-query>" --instruction "<goal>" [--include-media] [--media-limit <n>]
python scripts/invoke_whatsapp_wacli.py send-text --chat "<jid-or-query>" --message "<text>" --confirm
python scripts/invoke_whatsapp_wacli.py react --chat "<jid-or-query>" --message-id <id> --reaction "<emoji>" --confirm
python scripts/invoke_whatsapp_wacli.py presence --chat "<jid-or-query>" --state typing|paused --confirm
```
