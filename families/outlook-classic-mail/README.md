# Outlook Classic Mail

Use this family when an agent needs local mailbox access through Microsoft Outlook Classic on Windows.

## What it does

- discovers a standalone Outlook Classic COM client under `%LOCALAPPDATA%\Tools\outlook-classic-mail`
- launches that client through `uv run --project ...`
- normalizes JSON results for Codex-facing wrappers

## What it does not do

- it does not implement COM directly inside the repo package
- it does not reproduce Gmail query syntax, labels, or archive semantics
- it does not ship a Claude plugin in v1

## Prerequisites

- Outlook Classic installed and configured with the accounts you want to use
- `uv` available on `PATH`
- local client project present at `%LOCALAPPDATA%\Tools\outlook-classic-mail`

## CLI

```bash
agent-toolbelt-outlook-classic-mail accounts
agent-toolbelt-outlook-classic-mail search --account demo@example.com --folder inbox --query "approval" --days 7 --limit 10
agent-toolbelt-outlook-classic-mail read-thread --account demo@example.com --message-id <entry-id>
agent-toolbelt-outlook-classic-mail triage --all-accounts --days 7 --limit 20
agent-toolbelt-outlook-classic-mail draft-reply --account demo@example.com --message-id <entry-id> --instruction "Confirm Tuesday works."
```

The family bridge uses the external client root in this order:

1. `OUTLOOK_CLASSIC_MAIL_HOME`
2. `%LOCALAPPDATA%\Tools\outlook-classic-mail`
