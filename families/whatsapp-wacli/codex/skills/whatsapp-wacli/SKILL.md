---
name: whatsapp-wacli
description: Use local WhatsApp access through the experimental wacli adapter for chat lookup, latest messages, search, context, reply drafting, and explicitly confirmed WhatsApp-visible actions.
license: MIT
compatibility: Experimental local WhatsApp adapter. WhatsApp-visible sends require explicit user confirmation.
metadata:
  version: "0.1.0"
---

# WhatsApp wacli

## Overview

Use `scripts/invoke_whatsapp_wacli.py` for local WhatsApp access through the curated local adapter project. The wrapper resolves the project through `--client-home`, `WHATSAPP_WACLI_AGENT_HOME`, or the legacy local compatibility project root. The adapter uses `steipete/wacli` with an explicit local store and JSON output.

This skill is experimental and local-first. Use the curated adapter and structured JSON output; do not expose raw `wacli` passthrough or package WhatsApp sessions, message stores, or local database files.

## Why This Wrapper

Use this wrapper instead of raw `wacli` when an agent needs reliable, auditable
WhatsApp context rather than direct terminal passthrough:

- It returns structured JSON for chat lookup, message reads, search, context,
  drafts, and visible-action safety failures.
- It exposes phone-number JID versus LID ambiguity through fields such as
  `chat_jid`, `contact_jid`, `resolved_jid`, `resolution_source`, `used_jid`,
  and `attempted_jids`.
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
- It keeps `draft-reply` model-free by returning `result.draft_packet`; Codex
  must generate the final reply text from that packet in chat when
  `draft_status` is `needs_model_generation`.
- It blocks WhatsApp-visible actions unless the exact action is confirmed with
  the adapter's `--confirm` flag.

## Routing Rules

Use this skill when:

- The user asks about WhatsApp chats, recent conversations, chat search, or message context.
- The user asks to draft a reply based on WhatsApp conversation context.
- The user explicitly asks to send a WhatsApp message, react, or set presence, and gives explicit confirmation for the exact visible action.

Do not use this skill when:

- The user asks for WhatsApp Desktop database scraping, screenshot automation, browser token extraction, or raw `wacli` passthrough.
- The task can be answered without accessing WhatsApp.
- A WhatsApp-visible mutation is requested without explicit confirmation of the exact outgoing action.

## Default Workflow

For `auth-login --popup` and new-session relinking:

1. Launch the popup and let the user scan the QR.
2. Do not kill the QR/login PowerShell process from Codex to clear a store lock. That process may own the local `wacli` store lock after authentication while the session settles.
3. Poll `auth-status` and `status`; run `sync-once` only after the popup process exits or the lock is released.
4. If a QR/login/sync process appears stuck, inspect status only and ask the user before terminating it.

For "latest conversation with X":

1. Run `auth-status`.
2. If authenticated but stale or empty, run `sync-once`.
3. Run `find-chat --query "<name-or-phone>"`; it searches chats first, then local chat/message metadata, then live WhatsApp session profile/phone metadata, then contact metadata/profile names. For non-contact chats, it can resolve live `whatsmeow_contacts` profile labels and PN/LID phone fragments such as `99041717` or `041717`; archived store aliases are fallback only when the same JID exists in the current fresh store. Check `chat_jid`, `resolved_jid`, and `resolution_source`, but let the adapter choose the actual history JID. The adapter now uses a fallback chain instead of blindly preferring the mapped LID.
4. Run `latest --chat "<name-or-jid>" --limit <n>` and allow bounded auto-backfill unless the user asks for current synced data only.
5. Prefer `message.presentation.chat_display_name` and `message.presentation.text` for summaries. Raw `ChatName`, `Text`, and `DisplayText` remain provenance/debug fields.
6. If returned rows contain media that matters for the task, rerun the same read with `--include-media --media-limit <n>` and inspect `message.presentation.media.available`, `artifact_source`, and `artifact_path` for OCR or visual analysis. `available=true` is usable even when `downloaded=false`; use `download_attempt_error` only as diagnostic context.
7. Answer only from structured JSON and state the observed sync scope when relevant. If `backfill_seed_missing` is returned, report that the local store lacks the anchor needed for targeted history backfill instead of implying there are no messages. If `message_store_lag` is returned, report that normal sync/backfill did not recover message bodies and the next recovery step is recreating or relinking the `wacli` session into a fresh store.

For reply drafting:

1. Run `draft-reply --chat "<name-or-jid>" --instruction "<goal>"`.
2. Read `result.draft_packet.context_summary` first, then inspect `context_messages`, `media_artifacts`, and `model_prompt` only as needed.
3. Generate the actual `draft_text` in chat from that packet when `draft_status` is `needs_model_generation`; do not expect the helper subprocess to produce LLM prose.
4. Do not send unless the user explicitly confirms the exact outgoing message, then use a separate `send-text --confirm`.

## Mutation Safety

- Read commands: `status`, `auth-status`, `sync-once`, `find-chat`, `latest`, `search`, `context`, `draft-reply`.
- WhatsApp-visible commands: `send-text`, `react`, `presence`.
- `send-text`, `react`, and `presence` must include `--confirm`; otherwise the adapter blocks them.
- `sync-once` writes only to the local `wacli` store; it is not WhatsApp-visible.
- `backfill` writes only to the local `wacli` store by requesting older per-chat history from the linked device; it is not WhatsApp-visible.
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

## Boundaries

- This uses an unofficial WhatsApp Web multi-device backend. Treat it as a local personal automation tradeoff.
- Do not expose raw `wacli` commands through the skill.
- Do not assume full chat history is present unless sync/backfill scope proves it.
- One-to-one chats may use phone-number JIDs for contact lookup and LID JIDs for stored history. Do not hard-code either one in the skill. Let the adapter fall back across `chat_jid`, `resolved_jid`, and `contact_jid`, and pay attention to `used_jid`, `attempted_jids`, and `messages_null_normalized` when reads look suspicious.
