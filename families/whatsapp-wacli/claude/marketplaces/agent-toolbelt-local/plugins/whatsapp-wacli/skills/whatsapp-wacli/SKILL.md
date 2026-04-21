---
name: whatsapp-wacli
description: Use local WhatsApp access through the experimental wacli adapter for chat lookup, latest messages, search, context, reply drafting, and explicitly confirmed WhatsApp-visible actions.
version: 0.1.0
---

# WhatsApp wacli

Use `scripts/invoke_whatsapp_wacli.py` for local WhatsApp access through the curated local adapter under `%LOCALAPPDATA%\Tools\whatsapp-wacli-agent`. The adapter uses `steipete/wacli` with an explicit local store and JSON output.

This skill is experimental and local-first. Do not expose raw `wacli` command passthrough, local database files, auth state, or session artifacts.

## Routing

- Use this skill for WhatsApp chat lookup, recent conversation summaries, message search, message context, and reply drafting.
- Use this skill for sending text, reacting, or setting presence only when the user explicitly confirms the exact WhatsApp-visible action.
- Do not use this skill for WhatsApp Desktop database scraping, screenshots, browser token extraction, or unaudited raw CLI passthrough.

## Workflows

- For "latest conversation with X", run `auth-status`, then `sync-once` when needed, then `find-chat --query "<name-or-phone>"`, then `latest --chat "<name-or-jid>" --limit <n>`.
- Check `resolved_jid` and `resolution_source` because WhatsApp may store direct-message history under a LID JID even when contact lookup resolves to a phone-number JID.
- Allow bounded auto-backfill for `latest` unless the user asks for current synced data only.
- If `backfill_seed_missing` is returned, report that the local store lacks the anchor needed for targeted history backfill instead of implying there are no messages.
- For reply drafting, fetch latest messages or context, draft text in chat, and do not send unless the user explicitly confirms the exact outgoing message.

## Safety

- Read commands: `status`, `auth-status`, `sync-once`, `find-chat`, `latest`, `search`, `context`, `draft-reply`.
- Local-store sync commands: `sync-once` and `backfill`; these are not WhatsApp-visible actions.
- WhatsApp-visible commands: `send-text`, `react`, `presence`.
- `send-text`, `react`, and `presence` must include `--confirm`; otherwise the adapter blocks them.

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
