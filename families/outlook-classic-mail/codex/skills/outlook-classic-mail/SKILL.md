---
name: outlook-classic-mail
description: Use Outlook Classic on Windows as the default local mail path for inbox triage, mailbox search, thread reads, response lookup, folder moves, follow-up analysis, reply drafting, forwarding, and explicit mailbox actions.
license: MIT
compatibility: Windows Outlook Classic COM workflow. Mailbox actions require explicit user confirmation.
metadata:
  version: "0.1.0"
---

# Outlook Classic Mail

## Overview

Use `scripts/invoke_outlook_mail.py` for local mailbox access through Outlook Classic. The wrapper delegates into the `outlook-classic-mail` family package in this repo, which then bridges into a standalone COM client project resolved by `--client-home`, `OUTLOOK_CLASSIC_MAIL_HOME`, or the legacy local compatibility project root.

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
- Use the metadata cache for repeated contact/sender/subject lookups. It stores message identifiers, contacts, subjects, timestamps, and folder locations, but not full message bodies.
- Use `cache-refresh --all-accounts --days 90` to populate or refresh the cache; use `cache-status` and `cache-show --query <text>` to inspect cache coverage.
- Run `sync-mail` before searching for very recent sent or received mail when Outlook folders may lag behind Send/Receive.
- Outlook COM-backed calls are single-lane. Never launch parallel Outlook searches or parallel wrapper invocations for `search`, `search --all-folders`, `find-folders`, `find-response`, `read-thread`, `triage`, `inspect-domains`, or `scan-domain-refs`.
- Do not use `multi_tool_use.parallel`, background jobs, `Start-Job`, `Start-Process`, shell `&`, or command chaining such as `cmd1; cmd2` to fan out Outlook searches across folders, accounts, queries, or message ids. Run one Outlook command at a time and wait for its JSON result before deciding the next command.
- If multiple accounts or folders must be searched, use one bounded helper command such as `--all-folders`, `--all-accounts`, or cache-guided candidates, or run narrower commands sequentially.
- The local FIFO queue is not permission to start parallel searches. It is a last-line guard for accidental concurrency and timeout isolation.
- If a previous Outlook command is still running, wait for it or inspect diagnostics; do not start another Outlook search to speed things up.
- If the client returns `queue_timeout`, the call never got a turn before the queue budget expired. If the client returns `outlook_busy`, queue admission succeeded but COM acquisition still failed unexpectedly.
- Read `wrapper_diagnostics` on every response. It identifies the access model as local Outlook Classic COM, reports that no cloud connector was used, shows the resolved client-home source, and labels wrapper-level failures such as missing client, missing `uv`, timeout, invalid JSON, or process start failure.
- When scheduled or background tasks report Outlook COM unavailable, run `diagnostics-probe` and then `diagnostics-log --limit 20`. These commands collect safe local runtime/COM metadata only; they do not read mailbox content.
- For "find my response/reply" tasks tied to a received message, use `find-response` first; fall back to manual Sent/Drafts searches only if the command fails or the anchor message cannot be resolved.
- For domain age or blocklist evidence, use `inspect-domains` for one message or `scan-domain-refs` for a bounded folder scan; these commands are read-only.
- Use `blocklists status` to inspect the local DNS blocklist cache and `blocklists refresh` only when cache maintenance is explicitly needed.
- For reply or forward drafts, prefer `draft-reply` or `draft-forward`; do not use generic `apply-action --action create-draft` for replies because it has no original thread anchor to quote.
- For threaded drafts, `--account` resolves the original message. Add `--send-using-account` when the outgoing draft should use another configured Outlook account, especially when the original recipient account differs from the anchor store.
- Treat `--instruction` as guidance only. It is never the saved draft body. Generate or obtain the final reply/forward text first and pass that exact text in `--body` when using `--create-draft --confirm`.
- If `draft-reply` or `draft-forward` returns `draft_status: needs_body`, produce the final body text in chat or rerun with `--body`; do not claim a draft was created and do not reuse the instruction text as the body.
- After creating a reply/forward draft, inspect `draft_content.thread_content_included`, `draft_content.thread_content_source`, `draft_placement.actual_send_using_account`, and `draft_placement.placement_verified` before telling the user the draft is correctly threaded and using the intended sender.
- If `draft_content.warnings` contains `thread_quote_fallback_used`, mention that Outlook did not provide a usable native quote and the helper added a manual quoted block from the anchor message. If it contains `thread_content_missing`, warn that the thread content could not be included.
- Use generic `apply-action --action create-draft` only for standalone new drafts; it saves in the selected account's Drafts folder but does not include reply/forward thread content.
- For "move/file/put this email in folder X" tasks, use `find-folders` first when the target is ambiguous, run `move-message` without `--confirm` as a preview, and run `move-message --confirm` only after explicit user approval.
- If folder discovery finds nothing, search Inbox and state that the scope was Inbox-only unless a bounded all-folder search is explicitly needed.
- Use `search --all-folders` as a bounded fallback. It uses cache-guided folder candidates by default; add `--bypass-cache --broad-scan` when the user suspects the cache/rules missed something or explicitly asks to scan broadly.
- Use `--no-update-cache` for repeated read-only direct-folder searches when cache freshness is not needed.
- Treat draft creation, send, move, delete, category changes, and mark-read changes as explicit actions that require confirmation.
- Remember that Gmail-backed accounts are accessed through Outlook stores, not through Gmail-native APIs.
- Mention Outlook Object Model Guard prompts when they materially affect an action.

## Script Interface

```bash
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] accounts
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] sync-mail [--refresh-cache] [--account <smtp|store>|--all-accounts] [--days <n>] [--force]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] diagnostics-probe
python scripts/invoke_outlook_mail.py diagnostics-log [--limit <n>]
python scripts/invoke_outlook_mail.py cache-status [--query <text>]
python scripts/invoke_outlook_mail.py cache-show --query <text> [--account <smtp|store>] [--days <n>] [--limit <n>]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] cache-refresh [--account <smtp|store>|--all-accounts] [--days <n>] [--force]
python scripts/invoke_outlook_mail.py cache-clear [--query <text>] --confirm
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] find-folders --query <text> [--account <smtp|store>|--all-accounts] [--limit <n>]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] search --account <smtp|store> [--folder inbox|sent|drafts|trash|custom:<path>] [--query <text>] [--unread] [--from <email>] [--to <email>] [--days <n>] [--limit <n>] [--no-update-cache]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] search --all-folders --query <text> [--account <smtp|store>|--all-accounts] [--folder-limit <n>] [--per-folder-limit <n>] [--bypass-cache] [--broad-scan] [--no-update-cache]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] read-thread --account <smtp|store> --message-id <entry-id>
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] find-response --account <anchor-store> --message-id <entry-id> [--limit <n>] [--fallback-all-accounts] [--exclude-drafts]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] inspect-domains --account <smtp|store> --message-id <entry-id> [--with-rdap] [--young-days <n>] [--rdap-cache <sqlite-path>] [--with-blocklists] [--blocklist-profile threat|debug-all] [--blocklist-cache <sqlite-path>]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] scan-domain-refs --account <smtp|store> --folder inbox|custom:<path> [--days <n>] [--limit <n>] [--with-rdap] [--young-days <n>] [--rdap-cache <sqlite-path>] [--with-blocklists] [--blocklist-profile threat|debug-all] [--blocklist-cache <sqlite-path>]
python scripts/invoke_outlook_mail.py blocklists status|refresh [--blocklist-profile threat|debug-all] [--blocklist-cache <sqlite-path>] [--force]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] move-message --account <smtp|store> --message-id <entry-id> --target-folder <folder-selector> [--confirm]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] triage [--account <smtp|store> | --all-accounts] [--days <n>] [--limit <n>]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] draft-reply --account <smtp|store> [--send-using-account <smtp|store>] --message-id <entry-id> --instruction "<guidance>" [--body "<final draft text>" --create-draft --confirm]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] draft-forward --account <smtp|store> [--send-using-account <smtp|store>] --message-id <entry-id> --to "<recipient>" --instruction "<guidance>" [--body "<final draft text>" --create-draft --confirm]
python scripts/invoke_outlook_mail.py [--queue-timeout-sec <n>] apply-action --account <smtp|store> --message-id <entry-id> --action <create-draft|send|move|delete|category|mark-read> --confirm
```
