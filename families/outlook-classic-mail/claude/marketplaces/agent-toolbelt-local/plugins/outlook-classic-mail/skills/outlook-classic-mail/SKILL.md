---
name: outlook-classic-mail
description: Use Outlook Classic on Windows as the default local mail path for generic email, inbox, multi-account mailbox, triage, search, thread read, response lookup, reply draft, forward draft, folder move, and explicit mailbox action requests.
version: 0.1.0
---

# Outlook Classic Mail

Use `scripts/invoke_outlook_mail.py` for local mailbox access through Outlook Classic. The wrapper delegates into the Outlook Classic Mail family package, which then bridges into the standalone local COM client under the user's local Tools directory.

## Routing

- Prefer Outlook Classic for generic local mail tasks.
- Use Gmail only when the user explicitly asks for Gmail or needs Gmail-only semantics such as labels, archive behavior, or Gmail query syntax.
- Treat Gmail-backed accounts in Outlook as Outlook stores, not Gmail-native accounts.
- Do not use this skill when Outlook Classic is unavailable or the account is not configured in the local Outlook profile.

## Workflows

- For "latest emails from X" or similar service/sender lookups, run `find-folders` first, then search matching folders.
- If folder discovery finds nothing, search Inbox and state the scope unless a bounded all-folder search is needed.
- Use `search --all-folders` only as a bounded fallback, and report `matched_folders`, `searched_folders`, and `scope` when relevant.
- For "find my response/reply" tasks tied to a received message, use `find-response` before manual Sent/Drafts searches.
- For "move/file/put this email in folder X" tasks, run `find-folders` when the target is ambiguous, then run `move-message` without `--confirm` as a preview.
- Run `move-message --confirm` only after explicit confirmation from the user.

## Safety

- Reads, searches, thread reads, triage, and previews are non-mutating.
- Draft creation, send, move, delete, category changes, and mark-read changes require explicit confirmation.
- Mention Outlook Object Model Guard prompts when they affect an action.
- Do not silently approximate Gmail labels or archive semantics with Outlook folders.

## Script Interface

```bash
python scripts/invoke_outlook_mail.py accounts
python scripts/invoke_outlook_mail.py find-folders --query <text> [--account <smtp|store>|--all-accounts] [--limit <n>]
python scripts/invoke_outlook_mail.py search --account <smtp|store> [--folder inbox|sent|drafts|trash|custom:<path>] [--query <text>] [--unread] [--from <email>] [--to <email>] [--days <n>] [--limit <n>]
python scripts/invoke_outlook_mail.py search --all-folders --query <text> [--account <smtp|store>|--all-accounts] [--folder-limit <n>] [--per-folder-limit <n>]
python scripts/invoke_outlook_mail.py read-thread --account <smtp|store> --message-id <entry-id>
python scripts/invoke_outlook_mail.py find-response --account <anchor-store> --message-id <entry-id> [--limit <n>] [--fallback-all-accounts] [--exclude-drafts]
python scripts/invoke_outlook_mail.py move-message --account <smtp|store> --message-id <entry-id> --target-folder <folder-selector> [--confirm]
python scripts/invoke_outlook_mail.py triage [--account <smtp|store> | --all-accounts] [--days <n>] [--limit <n>]
python scripts/invoke_outlook_mail.py draft-reply --account <smtp|store> --message-id <entry-id> --instruction "<goal>"
python scripts/invoke_outlook_mail.py draft-forward --account <smtp|store> --message-id <entry-id> --to "<recipient>" --instruction "<context>"
python scripts/invoke_outlook_mail.py apply-action --account <smtp|store> --message-id <entry-id> --action <create-draft|send|move|delete|category|mark-read> --confirm
```
