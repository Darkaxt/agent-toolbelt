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
- Use the metadata cache for repeated contact/sender/subject lookups. It stores message identifiers, contacts, subjects, timestamps, and folder locations, but not full message bodies.
- Use `cache-refresh --all-accounts --days 90` to populate or refresh the cache; use `cache-status` and `cache-show --query <text>` to inspect cache coverage.
- Run `sync-mail` before searching for very recent sent or received mail when Outlook folders may lag behind Send/Receive.
- Use `search --all-folders` as a bounded fallback. It uses cache-guided folder candidates by default; add `--bypass-cache --broad-scan` when the user suspects the cache/rules missed something or explicitly asks to scan broadly.
- If the client returns `outlook_busy`, another COM operation is active; report that and retry later instead of waiting until timeout.
- For "find my response/reply" tasks tied to a received message, use `find-response` before manual Sent/Drafts searches.
- For domain age or blocklist evidence, use `inspect-domains` for one message or `scan-domain-refs` for a bounded folder scan; these commands are read-only.
- Use `blocklists status` to inspect the local DNS blocklist cache and `blocklists refresh` only when cache maintenance is explicitly needed.
- For reply or forward drafts, `--account` resolves the original message. Add `--send-using-account` when the outgoing draft should use another configured Outlook account.
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
python scripts/invoke_outlook_mail.py sync-mail [--refresh-cache] [--account <smtp|store>|--all-accounts] [--days <n>] [--force]
python scripts/invoke_outlook_mail.py cache-status [--query <text>]
python scripts/invoke_outlook_mail.py cache-show --query <text> [--account <smtp|store>] [--days <n>] [--limit <n>]
python scripts/invoke_outlook_mail.py cache-refresh [--account <smtp|store>|--all-accounts] [--days <n>] [--force]
python scripts/invoke_outlook_mail.py cache-clear [--query <text>] --confirm
python scripts/invoke_outlook_mail.py find-folders --query <text> [--account <smtp|store>|--all-accounts] [--limit <n>]
python scripts/invoke_outlook_mail.py search --account <smtp|store> [--folder inbox|sent|drafts|trash|custom:<path>] [--query <text>] [--unread] [--from <email>] [--to <email>] [--days <n>] [--limit <n>]
python scripts/invoke_outlook_mail.py search --all-folders --query <text> [--account <smtp|store>|--all-accounts] [--folder-limit <n>] [--per-folder-limit <n>] [--bypass-cache] [--broad-scan] [--no-update-cache]
python scripts/invoke_outlook_mail.py read-thread --account <smtp|store> --message-id <entry-id>
python scripts/invoke_outlook_mail.py find-response --account <anchor-store> --message-id <entry-id> [--limit <n>] [--fallback-all-accounts] [--exclude-drafts]
python scripts/invoke_outlook_mail.py inspect-domains --account <smtp|store> --message-id <entry-id> [--with-rdap] [--young-days <n>] [--rdap-cache <sqlite-path>] [--with-blocklists] [--blocklist-profile threat|debug-all] [--blocklist-cache <sqlite-path>]
python scripts/invoke_outlook_mail.py scan-domain-refs --account <smtp|store> --folder inbox|custom:<path> [--days <n>] [--limit <n>] [--with-rdap] [--young-days <n>] [--rdap-cache <sqlite-path>] [--with-blocklists] [--blocklist-profile threat|debug-all] [--blocklist-cache <sqlite-path>]
python scripts/invoke_outlook_mail.py blocklists status|refresh [--blocklist-profile threat|debug-all] [--blocklist-cache <sqlite-path>] [--force]
python scripts/invoke_outlook_mail.py move-message --account <smtp|store> --message-id <entry-id> --target-folder <folder-selector> [--confirm]
python scripts/invoke_outlook_mail.py triage [--account <smtp|store> | --all-accounts] [--days <n>] [--limit <n>]
python scripts/invoke_outlook_mail.py draft-reply --account <smtp|store> [--send-using-account <smtp|store>] --message-id <entry-id> --instruction "<goal>"
python scripts/invoke_outlook_mail.py draft-forward --account <smtp|store> [--send-using-account <smtp|store>] --message-id <entry-id> --to "<recipient>" --instruction "<context>"
python scripts/invoke_outlook_mail.py apply-action --account <smtp|store> --message-id <entry-id> --action <create-draft|send|move|delete|category|mark-read> --confirm
```
