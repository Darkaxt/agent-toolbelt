---
name: observable-reputation
description: Classify URL, domain, and IP observables with passive reputation providers without submitting URLs, files, phishing reports, or fresh scans.
version: 0.1.0
---

# Observable Reputation

Use `scripts/invoke_observable_reputation.py` for passive reputation checks on observables from any source.

## Commands

```bash
python scripts/invoke_observable_reputation.py providers --status
python scripts/invoke_observable_reputation.py classify --input <observables.json> --output <report.json> [--quiet]
```

## Safety

- Lookup, search, feed, and DNS-query endpoints only.
- Do not submit URLs, files, malware samples, phishing reports, IP abuse reports, or fresh scans.
- Treat missing API keys as skipped provider evidence.
- Treat all reputation evidence as advisory unless a calling workflow has an explicit policy.

## Providers

- Spamhaus DQS, URLhaus, OpenPhish, urlscan.io, VirusTotal, and AbuseIPDB.
