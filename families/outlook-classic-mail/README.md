# Outlook Classic Mail

Use this family when an agent needs local mailbox access through Microsoft Outlook Classic on Windows.

## What it does

- discovers a standalone Outlook Classic COM client project from an explicit override or default local project root
- launches that client through `uv run --project ...`
- normalizes JSON results for Codex-facing wrappers
- exposes fast folder discovery before message search for rule-managed Outlook folders
- maintains a lightweight SQLite metadata cache for recent contacts, subjects, timestamps, folder locations, and message identifiers
- triggers Outlook Send/Receive All Folders when recent sent or received mail has not appeared locally yet
- serializes COM-backed operations through a client-wide FIFO queue
- exposes deterministic response lookup from the original recipient account's Sent and Drafts folders
- exposes explicit folder move previews and confirmed message moves
- forwards optional send-account selection for reply and forward drafts

## What it does not do

- it does not implement COM directly inside the repo package
- it does not reproduce Gmail query syntax, labels, or archive semantics
- it does not cache full email bodies
- it does not manage Outlook rules or automatic future filtering

## Prerequisites

- Outlook Classic installed and configured with the accounts you want to use
- `uv` available on `PATH`
- local client project available through `OUTLOOK_CLASSIC_MAIL_HOME`, `--client-home`, or the default compatibility project root

## CLI

```bash
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 accounts
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 sync-mail --refresh-cache --all-accounts
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 cache-refresh --all-accounts --days 90
agent-toolbelt-outlook-classic-mail cache-status --query lettre24
agent-toolbelt-outlook-classic-mail cache-show --query lettre24 --limit 10
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 find-folders --query lettre24 --all-accounts
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 search --account demo@example.com --folder inbox --query "approval" --days 7 --limit 10 --no-update-cache
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 search --all-folders --query lettre24 --all-accounts --folder-limit 10 --per-folder-limit 5
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 search --all-folders --query lettre24 --all-accounts --bypass-cache --broad-scan
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 read-thread --account demo@example.com --message-id <entry-id>
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 find-response --account demo@example.com --message-id <entry-id>
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 move-message --account demo@example.com --message-id <entry-id> --target-folder custom:Inbox/Projects
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 move-message --account demo@example.com --message-id <entry-id> --target-folder custom:Inbox/Projects --confirm
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 triage --all-accounts --days 7 --limit 20
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 draft-reply --account demo@example.com --message-id <entry-id> --instruction "Confirm Tuesday works."
agent-toolbelt-outlook-classic-mail --queue-timeout-sec 900 draft-reply --account anchor@example.com --send-using-account reply@example.com --message-id <entry-id> --instruction "Confirm Tuesday works."
```

The family bridge uses the external client root in this order:

1. `--client-home`
2. `OUTLOOK_CLASSIC_MAIL_HOME`
3. the legacy `%LOCALAPPDATA%\Tools\outlook-classic-mail` compatibility project root

For sender or service lookups such as "latest emails from X", prefer `find-folders` first. Outlook rules often move mail out of Inbox, and folder discovery is much cheaper than recursively scanning messages.

For repeated contact or subject searches, use the metadata cache as a locator. `cache-refresh --all-accounts --days 90` builds a rolling cache of message IDs, contacts, subjects, timestamps, and folder paths. Search confirms cache candidates through live Outlook COM before returning messages. Use `--bypass-cache --broad-scan` when the user suspects a stale cache or asks to scan broadly.

COM-backed commands enter a local FIFO queue before they touch Outlook. Do not launch many heavy Outlook queries in parallel expecting linear timeout inflation; queueing is the concurrency control layer. Use `--queue-timeout-sec` to control how long a call waits for its turn. Result payloads report `queue.used`, `queue.waited_seconds`, `queue.position_at_enqueue`, `queue.depth_at_enqueue`, and `queue.timeout_seconds`.

Wrapper responses also include `wrapper_diagnostics` so callers can distinguish
local Outlook Classic COM/client failures from cloud connector availability. The
diagnostics report `access_model: local_outlook_classic_com`,
`cloud_connector_used: false`, the client-home source/path, timeout budgets, and
wrapper-level `failure_kind` values such as `client_unavailable`,
`uv_unavailable`, `wrapper_timeout`, `invalid_json`, or
`process_start_failed`.

For very recent sent or received mail, run `sync-mail` first. It triggers Outlook Send/Receive through SyncObjects when available and falls back to `SendAndReceive(False)`.

If a command returns `queue_timeout`, it never reached execution before the queue budget expired. If it returns `outlook_busy`, queue admission succeeded but the underlying COM execution lock still failed unexpectedly.

For response lookups such as "find my response to this email", use `find-response` first. It resolves the anchor message, inspects its original recipients, checks the matching account/store's Sent and Drafts folders, and broadens only when `--fallback-all-accounts` is requested.

For folder moves such as "move this email to X", use `find-folders` first when the destination is ambiguous, then run `move-message` without `--confirm` to preview the source and target. Add `--confirm` only after explicit user approval.

For draft replies or forwards, `--account` resolves the original message. Use `--send-using-account` when the outgoing draft should be sent from a different configured Outlook account.

Cache and folder-hint writes are best-effort. If the local state files are temporarily locked, the client returns the search results and reports the skipped update as a warning. Use `--no-update-cache` for repeated read-only direct-folder searches when cache freshness is not needed.
