---
name: mail-domain-quarantine
description: Dry-run or apply local Outlook Classic quarantine decisions based on young-domain checks, cached DNS blocklists, and passive domain-structure evidence.
version: 0.1.0
---

# Mail Domain Quarantine

Use `scripts/invoke_mail_domain_quarantine.py` to scan configured Outlook Classic Inbox and Spam/Junk folders. Dry-run is the default and does not move mail.

## Commands

```bash
python scripts/invoke_mail_domain_quarantine.py scan --dry-run
python scripts/invoke_mail_domain_quarantine.py scan --dry-run --with-blocklists --blocklist-profile threat --days 7 --limit 20
python scripts/invoke_mail_domain_quarantine.py scan --apply --with-blocklists --blocklist-profile threat
```

## Safety

- Use `--apply` only after explicit user confirmation.
- Do not pass `--with-reputation` unless external passive reputation enrichment is explicitly requested.
- Do not delete, report spam, unsubscribe, mark read/unread, or open message links.
- Reports rotate by default; `MAIL_DOMAIN_QUARANTINE_HOME` can redirect state and reports.
