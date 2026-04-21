# Outlook Classic Mail

Use this family when an agent needs local mailbox access through Microsoft Outlook Classic on Windows.

## What it does

- discovers a standalone Outlook Classic COM client project from an explicit override or default local project root
- launches that client through `uv run --project ...`
- normalizes JSON results for Codex-facing wrappers
- exposes fast folder discovery before message search for rule-managed Outlook folders
- exposes deterministic response lookup from the original recipient account's Sent and Drafts folders
- exposes explicit folder move previews and confirmed message moves
- forwards optional send-account selection for reply and forward drafts

## What it does not do

- it does not implement COM directly inside the repo package
- it does not reproduce Gmail query syntax, labels, or archive semantics
- it does not manage Outlook rules or automatic future filtering

## Prerequisites

- Outlook Classic installed and configured with the accounts you want to use
- `uv` available on `PATH`
- local client project available through `OUTLOOK_CLASSIC_MAIL_HOME`, `--client-home`, or the default compatibility project root

## CLI

```bash
agent-toolbelt-outlook-classic-mail accounts
agent-toolbelt-outlook-classic-mail find-folders --query lettre24 --all-accounts
agent-toolbelt-outlook-classic-mail search --account demo@example.com --folder inbox --query "approval" --days 7 --limit 10
agent-toolbelt-outlook-classic-mail search --all-folders --query lettre24 --all-accounts --folder-limit 10 --per-folder-limit 5
agent-toolbelt-outlook-classic-mail read-thread --account demo@example.com --message-id <entry-id>
agent-toolbelt-outlook-classic-mail find-response --account demo@example.com --message-id <entry-id>
agent-toolbelt-outlook-classic-mail move-message --account demo@example.com --message-id <entry-id> --target-folder custom:Inbox/Projects
agent-toolbelt-outlook-classic-mail move-message --account demo@example.com --message-id <entry-id> --target-folder custom:Inbox/Projects --confirm
agent-toolbelt-outlook-classic-mail triage --all-accounts --days 7 --limit 20
agent-toolbelt-outlook-classic-mail draft-reply --account demo@example.com --message-id <entry-id> --instruction "Confirm Tuesday works."
agent-toolbelt-outlook-classic-mail draft-reply --account anchor@example.com --send-using-account reply@example.com --message-id <entry-id> --instruction "Confirm Tuesday works."
```

The family bridge uses the external client root in this order:

1. `--client-home`
2. `OUTLOOK_CLASSIC_MAIL_HOME`
3. the legacy `%LOCALAPPDATA%\Tools\outlook-classic-mail` compatibility project root

For sender or service lookups such as "latest emails from X", prefer `find-folders` first. Outlook rules often move mail out of Inbox, and folder discovery is much cheaper than recursively scanning messages.

For response lookups such as "find my response to this email", use `find-response` first. It resolves the anchor message, inspects its original recipients, checks the matching account/store's Sent and Drafts folders, and broadens only when `--fallback-all-accounts` is requested.

For folder moves such as "move this email to X", use `find-folders` first when the destination is ambiguous, then run `move-message` without `--confirm` to preview the source and target. Add `--confirm` only after explicit user approval.

For draft replies or forwards, `--account` resolves the original message. Use `--send-using-account` when the outgoing draft should be sent from a different configured Outlook account.
