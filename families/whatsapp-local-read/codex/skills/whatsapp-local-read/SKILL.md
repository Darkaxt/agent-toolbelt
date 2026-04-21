---
name: whatsapp-local-read
description: Use local WhatsApp Desktop read-only inspection for current conversation follow-up, visible chat summaries, and response suggestions without sending or typing.
---

# WhatsApp Local Read

## Overview

Use `scripts/invoke_whatsapp_local_read.py` for read-only WhatsApp Desktop follow-up support. The wrapper delegates into the `whatsapp-local-read` family package in this repo, which then bridges into the standalone local client under `%LOCALAPPDATA%\Tools\whatsapp-local-read`.

## Routing Rules

Use this skill when:

- The user asks about WhatsApp read-only lookup or follow-up assistance.
- The user wants a summary of the currently open WhatsApp conversation.
- The user wants response suggestions based on visible/current WhatsApp chat content.
- The user explicitly asks to probe whether local WhatsApp stores are usable.

Do not use this skill when:

- The user asks to send a WhatsApp message, type into WhatsApp, automate clicks, or mutate WhatsApp state.
- The task requires broad personal history search beyond the currently visible chat.
- The task requires contact export, local DB decryption, browser/session-token extraction, or reverse engineering.
- The task should use a business WhatsApp Cloud API integration rather than the personal desktop app.

## Behavior

- Keep v1 strictly read-only: no sending, no typing, no clicking, no mark-read actions, no contact export, and no local DB decryption.
- Use `status` to check installed package, detected storage, running app state, and usable backend.
- Use `probe-db` only for capability detection. It may inspect file names, sizes, and magic bytes, but it must not expose message content.
- Treat non-SQLite or encrypted `.db` files as `unsupported_encrypted_store`; do not attempt local DB decryption or reverse engineering.
- Prefer `visible-ui` for actual personal conversation content unless a readable non-encrypted local store is proven.
- For `current-chat`, inspect only text already visible in the open WhatsApp Desktop window and clearly state that capture scope.
- For `summarize` and `suggest-response`, use captured visible/current chat content and keep the result as suggestions only.
- If WhatsApp is closed, minimized, locked, or no chat is visible, report that limitation instead of broadening into private stores.

## Script Interface

```bash
python scripts/invoke_whatsapp_local_read.py status
python scripts/invoke_whatsapp_local_read.py probe-db
python scripts/invoke_whatsapp_local_read.py current-chat
python scripts/invoke_whatsapp_local_read.py summarize --source current-chat
python scripts/invoke_whatsapp_local_read.py suggest-response --instruction "<goal>"
```

## Output Contract

The wrapper returns JSON with:

- `ok`
- `operation`
- `backend`
- `result`
- `warnings`
- `stderr`
- `exit_code`
