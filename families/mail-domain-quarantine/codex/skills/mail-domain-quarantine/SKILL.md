---
name: mail-domain-quarantine
description: Dry-run or apply local Outlook Classic quarantine decisions based on RDAP young-domain checks, cached DNS blocklists, and passive domain-structure evidence. Use when Codex needs mailbox domain-risk reports or explicitly confirmed quarantine moves.
license: MIT
compatibility: Windows Outlook Classic workflow. Dry-run by default; mailbox moves require explicit user confirmation.
metadata:
  version: "0.1.0"
---

# Mail Domain Quarantine

## Overview

Use `scripts/invoke_mail_domain_quarantine.py` to scan configured Outlook Classic stores for recent Inbox and Spam/Junk messages that reference young or blocklisted domains. Dry-run is the default and does not mutate mail.

## Commands

```powershell
python scripts/invoke_mail_domain_quarantine.py scan --dry-run
python scripts/invoke_mail_domain_quarantine.py scan --dry-run --with-blocklists --blocklist-profile threat --days 7 --limit 20
python scripts/invoke_mail_domain_quarantine.py scan --dry-run --with-blocklists --blocklist-profile threat --days 90 --limit 1000 --outlook-timeout-seconds 1200
python scripts/invoke_mail_domain_quarantine.py scan --dry-run --with-reputation --reputation-profile light
python scripts/invoke_mail_domain_quarantine.py scan --dry-run --with-reputation --reputation-profile full
python scripts/invoke_mail_domain_quarantine.py scan --apply --with-blocklists --blocklist-profile threat
```

## Safety Rules

- Prefer `--dry-run`; use `--apply` only after explicit user confirmation.
- Do not pass `--with-reputation` unless the user asks for external passive reputation enrichment.
- Normal runs use RDAP and local cached blocklists only.
- `--reputation-profile light` checks only young-domain quarantine candidate domains.
- `--reputation-profile full` also checks typed domain, IP, and exact URL observables from those same candidate messages only.
- Report-only evidence includes domain structure and rotating-domain clusters.
- Reputation v2 fields such as normalized values, provider summaries, explanations, diagnostics, and rejected observables are evidence only.
- Apply mode moves only messages selected by young-domain or non-suppressed `threat` blocklist policy.
- Never delete, report spam, unsubscribe, mark read/unread, or open message links.

## Output

- JSON and Markdown reports are written under the tool state home.
- Reports rotate by default with `--report-retention-days 30` and `--report-max-mb 100`.
- Use `MAIL_DOMAIN_QUARANTINE_HOME` to redirect state/reports during tests or sandboxed runs.
