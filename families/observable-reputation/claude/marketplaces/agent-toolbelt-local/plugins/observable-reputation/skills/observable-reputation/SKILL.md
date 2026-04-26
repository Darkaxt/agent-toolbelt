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
python scripts/invoke_observable_reputation.py normalize --input <observables.json> [--output <normalized.json>]
python scripts/invoke_observable_reputation.py classify --input <observables.json> --output <report.json> [--quiet]
python scripts/invoke_observable_reputation.py classify --input <observables.json> --auto-detect --output <report.json> [--csv-output <report.csv>] [--stix-output <bundle.json>]
```

Use `normalize` first for messy mail, log, or analyst input. It accepts raw
strings and typed records, canonicalizes domains/URLs/IPs, extracts email
domains, strips URL credentials/fragments, and reports malformed entries as
`rejected_observables` without failing the whole file.

Use `classify --auto-detect` when raw strings or omitted/`auto` types are
expected. Reports include additive diagnostics, provider summaries, explanations,
and optional CSV/STIX exports. STIX output intentionally includes only
malicious/suspicious indicators as passive evidence.

## Safety

- Lookup, search, feed, and DNS-query endpoints only.
- Do not submit URLs, files, malware samples, phishing reports, IP abuse reports, or fresh scans.
- Treat missing API keys as skipped provider evidence.
- Treat all reputation evidence as advisory unless a calling workflow has an explicit policy.

## Providers

- Spamhaus DQS, URLhaus, OpenPhish, urlscan.io, VirusTotal, and AbuseIPDB.
