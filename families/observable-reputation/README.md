# observable-reputation

Reusable passive reputation utility for URL, domain, and IP observables.

## Usage

```powershell
uv run --project families/observable-reputation agent-toolbelt-observable-reputation providers --status
uv run --project families/observable-reputation agent-toolbelt-observable-reputation classify --input observables.json --output report.json
```

The classifier is passive-only. It uses lookup, search, feed, and DNS query
interfaces, and intentionally does not submit URLs, files, phishing reports, or
fresh scans.

Optional providers are enabled by environment variables:

- `SPAMHAUS_DQS_KEY`
- `URLHAUS_AUTH_KEY`
- `URLSCAN_API_KEY`
- `VIRUSTOTAL_API_KEY`
- `ABUSEIPDB_API_KEY`
