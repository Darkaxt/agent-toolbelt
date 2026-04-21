# WhatsApp Local Read

Use this family when an agent needs read-only personal WhatsApp follow-up support from the local Windows desktop app.

## What it does

- discovers a standalone local client under `%LOCALAPPDATA%\Tools\whatsapp-local-read`
- launches that client through `uv run --project ...`
- probes WhatsApp Desktop storage with magic-byte and schema-safe checks only
- reports encrypted or non-SQLite stores as unsupported instead of attempting decryption
- falls back to read-only visible UI capture for the currently open WhatsApp chat
- helps summarize the visible/current chat and suggest response text without writing into WhatsApp

## What it does not do

- it does not send messages or type into WhatsApp
- it does not mark messages read intentionally
- it does not export contacts
- it does not decrypt or reverse engineer local WhatsApp stores
- it does not extract browser sessions, tokens, cookies, or keys
- it does not provide business Cloud API history access; that API is webhook/event oriented
- it does not ship a Claude plugin in v1

## Prerequisites

- Windows with WhatsApp Desktop installed
- `uv` available on `PATH`
- local client project present at `%LOCALAPPDATA%\Tools\whatsapp-local-read`
- WhatsApp Desktop must be open with a harmless chat visible before `current-chat`, `summarize`, or `suggest-response` can inspect visible content

## CLI

```bash
agent-toolbelt-whatsapp-local-read status
agent-toolbelt-whatsapp-local-read probe-db
agent-toolbelt-whatsapp-local-read current-chat
agent-toolbelt-whatsapp-local-read summarize --source current-chat
agent-toolbelt-whatsapp-local-read suggest-response --instruction "Acknowledge and ask for the deadline."
```

The family bridge uses the external client root in this order:

1. `WHATSAPP_LOCAL_READ_HOME`
2. `%LOCALAPPDATA%\Tools\whatsapp-local-read`

## Behavior Notes

- `status` and `probe-db` are capability checks; they should not expose message content.
- `db-read` is intentionally disabled unless a store is trivially readable without decryption and a safe message schema is implemented.
- `visible-ui` only captures text already visible in the open WhatsApp Desktop window. Always state that scope when answering.
- If WhatsApp is closed, minimized, locked, or no chat is visible, return a clear unavailable result instead of broadening into private stores.
- Official personal-service terms and business API docs are treated as boundaries: this family is for local personal follow-up assistance, not automated unauthorized extraction or business API history sync.
