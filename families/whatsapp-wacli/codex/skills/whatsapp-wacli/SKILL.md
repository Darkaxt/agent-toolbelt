---
name: whatsapp-wacli
description: Use local WhatsApp access through the experimental wacli adapter for chat lookup, latest messages, search, context, reply drafting, and explicitly confirmed WhatsApp-visible actions.
---

# WhatsApp wacli

## Overview

Use `scripts/invoke_whatsapp_wacli.py` for local WhatsApp access through the curated local adapter project. The wrapper resolves the project through `--client-home`, `WHATSAPP_WACLI_AGENT_HOME`, or the legacy local compatibility project root. The adapter uses `steipete/wacli` with an explicit local store and JSON output.

This skill is experimental and local-first. Use the curated adapter and structured JSON output; do not expose raw `wacli` passthrough or package WhatsApp sessions, message stores, or local database files.

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

For "latest conversation with X":

1. Run `auth-status`.
2. If authenticated but stale or empty, run `sync-once`.
3. Run `find-chat --query "<name-or-phone>"`; it searches chats first, then contact metadata/profile names. Check `chat_jid`, `resolved_jid`, and `resolution_source`, but let the adapter choose the actual history JID. The adapter now uses a fallback chain instead of blindly preferring the mapped LID.
4. Run `latest --chat "<name-or-jid>" --limit <n>` and allow bounded auto-backfill unless the user asks for current synced data only.
5. Answer only from structured JSON and state the observed sync scope when relevant. If `backfill_seed_missing` is returned, report that the local store lacks the anchor needed for targeted history backfill instead of implying there are no messages.

For reply drafting:

1. Fetch latest messages or context.
2. Draft response text in chat, not in WhatsApp.
3. Do not send unless the user explicitly confirms the exact outgoing message.

## Mutation Safety

- Read commands: `status`, `auth-status`, `sync-once`, `find-chat`, `latest`, `search`, `context`, `draft-reply`.
- WhatsApp-visible commands: `send-text`, `react`, `presence`.
- `send-text`, `react`, and `presence` must include `--confirm`; otherwise the adapter blocks them.
- `sync-once` writes only to the local `wacli` store; it is not WhatsApp-visible.
- `backfill` writes only to the local `wacli` store by requesting older per-chat history from the linked device; it is not WhatsApp-visible.

## Script Interface

```bash
python scripts/invoke_whatsapp_wacli.py status
python scripts/invoke_whatsapp_wacli.py auth-status
python scripts/invoke_whatsapp_wacli.py auth-login --popup
python scripts/invoke_whatsapp_wacli.py sync-once
python scripts/invoke_whatsapp_wacli.py find-chat --query "<name-or-phone>" [--limit <n>]
python scripts/invoke_whatsapp_wacli.py backfill --chat "<jid-or-query>" [--count <n>] [--requests <n>] [--wait-sec <n>]
python scripts/invoke_whatsapp_wacli.py latest --chat "<jid-or-query>" [--limit <n>] [--no-backfill] [--backfill-count <n>] [--backfill-requests <n>] [--backfill-wait-sec <n>]
python scripts/invoke_whatsapp_wacli.py search --query "<text>" [--chat "<jid-or-query>"] [--limit <n>]
python scripts/invoke_whatsapp_wacli.py context --message-id <id> [--before <n>] [--after <n>]
python scripts/invoke_whatsapp_wacli.py draft-reply --chat "<jid-or-query>" --instruction "<goal>"
python scripts/invoke_whatsapp_wacli.py send-text --chat "<jid-or-query>" --message "<text>" --confirm
python scripts/invoke_whatsapp_wacli.py react --chat "<jid-or-query>" --message-id <id> --reaction "<emoji>" --confirm
python scripts/invoke_whatsapp_wacli.py presence --chat "<jid-or-query>" --state typing|paused --confirm
```

## Boundaries

- This uses an unofficial WhatsApp Web multi-device backend. Treat it as a local personal automation tradeoff.
- Do not expose raw `wacli` commands through the skill.
- Do not assume full chat history is present unless sync/backfill scope proves it.
- One-to-one chats may use phone-number JIDs for contact lookup and LID JIDs for stored history. Do not hard-code either one in the skill. Let the adapter fall back across `chat_jid`, `resolved_jid`, and `contact_jid`, and pay attention to `used_jid`, `attempted_jids`, and `messages_null_normalized` when reads look suspicious.
