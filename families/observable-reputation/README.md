# observable-reputation

Reusable passive reputation utility for URL, domain, and IP observables.

## Usage

```powershell
uv run --project families/observable-reputation agent-toolbelt-observable-reputation providers --status
uv run --project families/observable-reputation agent-toolbelt-observable-reputation normalize --input messy-observables.json --output normalized.json
uv run --project families/observable-reputation agent-toolbelt-observable-reputation classify --input observables.json --output report.json
uv run --project families/observable-reputation agent-toolbelt-observable-reputation classify --input messy-observables.json --auto-detect --output report.json --csv-output report.csv --stix-output indicators.json
```

The classifier is passive-only. It uses lookup, search, feed, and DNS query
interfaces, and intentionally does not submit URLs, files, phishing reports, or
fresh scans.

Use `normalize` before classification when input came from mail bodies, logs, or
mixed analyst notes. It accepts raw strings and typed records, canonicalizes
domains, URLs, and IPs, and reports malformed entries as
`rejected_observables` instead of failing the whole file.

`classify --auto-detect` applies the same tolerant parsing during classification.
Typed `domain`, `url`, and `ip` records remain compatible without the flag.

Reports include provider coverage diagnostics, cache hit/miss counts, rejected
observable counts, and per-observable explanations. CSV export writes one
summary row per classified observable. STIX 2.1 export includes only
`malicious` and `suspicious` observables as passive evidence indicators; clean,
unknown, skipped, and rejected records remain in JSON/CSV only.

Optional providers are enabled by environment variables:

- `SPAMHAUS_DQS_KEY`
- `URLHAUS_AUTH_KEY`
- `URLSCAN_API_KEY`
- `VIRUSTOTAL_API_KEY`
- `ABUSEIPDB_API_KEY`
