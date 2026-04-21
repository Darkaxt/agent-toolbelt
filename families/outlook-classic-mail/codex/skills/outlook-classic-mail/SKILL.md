---
name: outlook-classic-mail
description: Use Outlook Classic on Windows as the default local mail path for inbox triage, mailbox search, thread reads, follow-up analysis, reply drafting, forwarding, and explicit mailbox actions.
---

# Outlook Classic Mail

## Overview

Use `scripts/invoke_outlook_mail.py` for local mailbox access through Outlook Classic. The wrapper delegates into the `outlook-classic-mail` family package in this repo, which then bridges into the standalone COM client under `%LOCALAPPDATA%\Tools\outlook-classic-mail`.

## Routing Rules

Use this skill when:

- The user asks about email, inbox, unread mail, follow-ups, thread summaries, reply drafting, or forwarding.
- The task is a local multi-account mailbox task and Outlook Classic is available.
- The request should span the accounts configured in the local Outlook profile, including Gmail-backed stores that Outlook already syncs.

Do not use this skill when:

- The user explicitly asks for Gmail or Gmail query syntax.
- Outlook Classic is unavailable on this machine.
- The task depends on Gmail-only semantics such as labels or archive behavior.

## Behavior

- Prefer Outlook Classic for generic local mail tasks.
- Fall back to the Gmail connector only when the user explicitly asks for Gmail, Outlook Classic is unavailable, or the request truly depends on Gmail-only behavior.
- Keep mailbox reads and triage non-mutating by default.
- For "latest emails from X" or similar sender/service lookups, run `find-folders` first, then search matching folders.
- For "find my response/reply" tasks tied to a received message, identify the original recipient account first and check that account/store's Sent and Drafts folders before searching other accounts.
- If folder discovery finds nothing, search Inbox and state that the scope was Inbox-only unless a bounded all-folder search is explicitly needed.
- Use `search --all-folders` only as a bounded fallback, and report `matched_folders`, `searched_folders`, and `scope` when relevant.
- Treat draft creation, send, move, delete, category changes, and mark-read changes as explicit actions that require confirmation.
- Remember that Gmail-backed accounts are accessed through Outlook stores, not through Gmail-native APIs.
- Mention Outlook Object Model Guard prompts when they materially affect an action.

## Script Interface

```bash
python scripts/invoke_outlook_mail.py accounts
python scripts/invoke_outlook_mail.py find-folders --query <text> [--account <smtp|store>|--all-accounts] [--limit <n>]
python scripts/invoke_outlook_mail.py search --account <smtp|store> [--folder inbox|sent|drafts|trash|custom:<path>] [--query <text>] [--unread] [--from <email>] [--to <email>] [--days <n>] [--limit <n>]
python scripts/invoke_outlook_mail.py search --all-folders --query <text> [--account <smtp|store>|--all-accounts] [--folder-limit <n>] [--per-folder-limit <n>]
python scripts/invoke_outlook_mail.py read-thread --account <smtp|store> --message-id <entry-id>
python scripts/invoke_outlook_mail.py triage [--account <smtp|store> | --all-accounts] [--days <n>] [--limit <n>]
python scripts/invoke_outlook_mail.py draft-reply --account <smtp|store> --message-id <entry-id> --instruction "<goal>"
python scripts/invoke_outlook_mail.py draft-forward --account <smtp|store> --message-id <entry-id> --to "<recipient>" --instruction "<context>"
python scripts/invoke_outlook_mail.py apply-action --account <smtp|store> --message-id <entry-id> --action <create-draft|send|move|delete|category|mark-read> --confirm
```
