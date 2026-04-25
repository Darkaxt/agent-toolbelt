---
name: observable-reputation
description: Classify URL, domain, and IP observables with passive reputation providers. Use when Codex needs safe OSINT enrichment, provider status checks, or reusable reputation evidence for mail, logs, security triage, or other sources without submitting URLs, files, phishing reports, or fresh scans.
license: MIT
compatibility: Passive OSINT only. Does not perform active scans, URL submissions, file uploads, or phishing reports.
metadata:
  version: "0.1.0"
---

# Observable Reputation

## Overview

Use `scripts/invoke_observable_reputation.py` for passive reputation checks on observables from any source. Treat provider output as advisory evidence unless the calling workflow has an explicit policy that acts on it.

## Commands

```powershell
python scripts/invoke_observable_reputation.py providers --status
python scripts/invoke_observable_reputation.py classify --input <observables.json> --output <report.json> [--quiet]
```

Input JSON:

```json
{
  "observables": [
    { "type": "domain", "value": "example.com", "source": "sender", "context": {} },
    { "type": "url", "value": "https://example.com/path", "source": "body-url", "context": {} },
    { "type": "ip", "value": "203.0.113.7", "source": "received", "context": {} }
  ]
}
```

## Safety Rules

- Use lookup, search, feed, and DNS query interfaces only.
- Do not submit URLs, files, malware samples, phishing reports, or IP abuse reports.
- Do not trigger urlscan fresh scans, Cloudflare URL Scanner submissions, browser visits, or target URL fetches.
- Missing API keys should be treated as `skipped`, not failure.
- Provider errors, rate limits, and unknown results must not create mailbox or system mutations by themselves.

## Providers

- Spamhaus DQS: domain DBL/ZRD DNS queries only; requires `SPAMHAUS_DQS_KEY`.
- URLhaus: URL or host lookup endpoints only; requires `URLHAUS_AUTH_KEY`.
- OpenPhish: community feed download and local exact URL match.
- urlscan.io: Search API and existing result metadata only; requires `URLSCAN_API_KEY`.
- VirusTotal: existing URL/domain/IP object lookups only; requires `VIRUSTOTAL_API_KEY`.
- AbuseIPDB: IP check endpoint only; requires `ABUSEIPDB_API_KEY`.

## Integration Notes

- For mail quarantine, use `mail-domain-quarantine scan --dry-run --with-reputation` to enrich reports without changing move decisions.
- Keep reputation-only actions report-only unless the user explicitly asks to change policy.
