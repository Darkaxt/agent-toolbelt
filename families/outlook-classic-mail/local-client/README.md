# outlook-classic-mail

Standalone Outlook Classic COM client for local mailbox access on Windows.

## Scope

- enumerate configured Outlook accounts and delivery stores
- list folders by account
- find likely folders by name or path
- search mail
- search matched folders with bounded all-folder fallback
- maintain a lightweight SQLite metadata cache for recent contacts, subjects, timestamps, folder locations, and message identifiers
- trigger Outlook Send/Receive All Folders when recent sent/received mail has not appeared locally yet
- read threads
- inspect sender, header, unsubscribe, body-link domain references, and header IP references
- add optional RDAP-backed domain age summaries for reusable security workflows
- add optional cached DNS blocklist hits alongside RDAP summaries
- find sent or draft responses to received messages
- preview or move messages between folders with confirmation gates
- triage inboxes
- preview or create reply/forward drafts
- preserve existing HTML reply/forward chains when creating drafts
- verify quoted thread content and sender-store placement for created reply/forward drafts
- create standalone new drafts in the selected account's Drafts folder
- apply explicit mailbox actions with confirmation gates

## Requirements

- Windows
- Outlook Classic installed and configured
- `uv` on `PATH`

## CLI

```bash
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 accounts
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 sync-mail --refresh-cache --all-accounts
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 diagnostics-probe
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client diagnostics-log --limit 20
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 cache-refresh --all-accounts --days 90
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client cache-status --query example-service
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client cache-show --query example-service --limit 10
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 find-folders --query example-service --all-accounts
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 search --all-folders --query example-service --all-accounts --folder-limit 10 --per-folder-limit 5
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 search --all-folders --query example-service --all-accounts --bypass-cache --broad-scan
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 triage --all-accounts --days 7 --limit 20
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 inspect-domains --account demo@example.com --message-id <entry-id> --with-rdap --rdap-cache C:\path\to\domain_cache.sqlite
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 inspect-domains --account demo@example.com --message-id <entry-id> --with-rdap --with-blocklists --blocklist-profile threat
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 scan-domain-refs --account demo@example.com --folder inbox --days 7 --limit 20 --with-rdap --with-blocklists --blocklist-profile threat --rdap-cache C:\path\to\domain_cache.sqlite --blocklist-cache C:\path\to\blocklist_cache.sqlite
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client blocklists status --blocklist-profile threat
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client blocklists refresh --blocklist-profile threat
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 find-response --account demo@example.com --message-id <entry-id>
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 move-message --account demo@example.com --message-id <entry-id> --target-folder custom:Inbox/Projects
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 move-message --account demo@example.com --message-id <entry-id> --target-folder custom:Inbox/Projects --confirm
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 draft-reply --account demo@example.com --message-id <entry-id> --instruction "Draft a concise confirmation." --body "Tuesday works for me." --create-draft --confirm
uv run --project families/outlook-classic-mail/local-client outlook-classic-mail-client --queue-timeout-sec 900 draft-reply --account anchor@example.com --send-using-account reply@example.com --message-id <entry-id> --instruction "Draft from reply@example.com." --body "Tuesday works for me." --create-draft --confirm
```

Folder hints are stored locally in `folder_hints.json` after successful discovery. They are used only as accelerators; discovery still runs so stale hints do not hide moved folders.

The mail metadata cache is stored under `state/mail_cache.sqlite`. It stores identifiers, contacts, subjects, timestamps, folder locations, and message flags for recent mail only; it does not store full message bodies. Search uses cache candidates as folder locators and confirms results through live Outlook COM.

COM-backed commands now enter a local FIFO queue before the existing execution lock. Do not compensate by launching multiple heavy Outlook queries in parallel or by inflating timeouts linearly; prefer targeted or batched lookups and let the queue serialize them.

The JSON result for queued commands includes `queue.used`, `queue.waited_seconds`, `queue.position_at_enqueue`, `queue.depth_at_enqueue`, and `queue.timeout_seconds`. `queue_timeout` means a command never reached its turn within `--queue-timeout-sec`; `outlook_busy` means queue admission succeeded but COM acquisition still failed unexpectedly.

For scheduled-task or background-session failures, run `diagnostics-probe` and
then inspect `diagnostics-log --limit 20`. The diagnostics log is stored at
`state/diagnostics/outlook_com_events.jsonl` and records safe runtime/COM
metadata such as Windows session, input-desktop accessibility, Outlook process
presence, COM stage, and structured failure kind. It does not log mailbox
content, account addresses, search queries, message IDs, or subjects.

If Outlook is still syncing, use `sync-mail` before looking for very recent sent or received messages. If cache or folder-hint writes hit a transient file lock, the command returns its mail results and reports the skipped local state update as a warning instead of failing the whole search. `--no-update-cache` is still useful for repeated read-only direct-folder searches when cache freshness is not needed.

For threaded drafts, use `draft-reply` or `draft-forward`. These commands build
from Outlook's native reply/forward item first, verify that the quoted original
thread is present, and add a manual quoted block from the anchor message when
Outlook returns an empty or signature-only draft body. Created draft payloads
include `draft_content.thread_content_included`,
`draft_content.thread_content_source`, and warnings such as
`thread_quote_fallback_used` or `thread_content_missing`.

`--instruction` is guidance only. It is preserved in the payload for audit/debug
context, but it is never written into the saved draft body. Use `--body` for the
final text that should be inserted into the draft. `--create-draft --confirm`
without a non-empty `--body` fails closed instead of creating an instruction
echo.

Sender placement is account-store first. If the requested sender cannot be
verified on Outlook's native reply/forward item, or if `--send-using-account`
points to another store, the client saves a replacement item directly under the
target account's default Drafts folder. Inspect `draft_placement.target_account`,
`actual_send_using_account`, `target_drafts_folder`, `actual_folder`, and
`placement_verified` before claiming the sender/folder is correct. Generic
`apply-action --action create-draft` is only for standalone new drafts; it uses
the selected account's Drafts folder but has no thread content to include.
Standalone drafts support explicit `--to`, `--cc`, `--bcc`, and repeated
`--attach` local file paths. Attachment paths are resolved and validated before
any draft item is saved.

Blocklist support is read-only. The `threat` profile uses threat-centered DNS
lists; `debug-all` adds broader ad/tracking/adult/platform lists for exploratory
dry runs.
