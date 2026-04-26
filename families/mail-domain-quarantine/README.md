# mail-domain-quarantine

Local Outlook Classic quarantine tool for recent messages that reference newly
registered domains. Phase 1 is intentionally reversible: dry-run is the default,
and apply mode only moves messages to each account's `Inbox\Quarantine` folder.

## Usage

```powershell
uv run --project families/mail-domain-quarantine agent-toolbelt-mail-domain-quarantine scan --dry-run
uv run --project families/mail-domain-quarantine agent-toolbelt-mail-domain-quarantine scan --dry-run --with-blocklists --blocklist-profile threat --days 7 --limit 20
uv run --project families/mail-domain-quarantine agent-toolbelt-mail-domain-quarantine scan --dry-run --with-reputation
uv run --project families/mail-domain-quarantine agent-toolbelt-mail-domain-quarantine scan --dry-run --with-reputation --reputation-profile full
uv run --project families/mail-domain-quarantine agent-toolbelt-mail-domain-quarantine scan --apply
```

The tool calls the reusable `outlook-classic-mail-client scan-domain-refs`
command, reads RDAP-backed domain ages plus optional local DNS blocklist hits,
and writes reports under `reports/`. Its local state lives under `state/`,
including `domain_cache.sqlite`, `blocklist_cache.sqlite`, `trust.sqlite`, and
`quarantine_ledger.sqlite`.

The first Phase 2 evaluation path should use `--with-blocklists` without
`--with-reputation`. That compares local blocklist evidence alongside RDAP
without making external OSINT API calls.

`--with-reputation` enriches reports through the separate
`observable-reputation` utility after the RDAP/blocklist pass. Reputation
evidence is report-only in this phase and does not create additional move
decisions.

External reputation lookups are constrained to quarantine candidate messages.
The default `--reputation-profile light` checks only young-domain candidate
domains. `--reputation-profile full` also checks typed domain, IP, and exact URL
observables from those same candidate messages. Allowed messages, non-young
blocklist-only findings, and unrelated tracking URLs are not sent to external
reputation providers.

When the installed `observable-reputation` supports v2 reports, quarantine
reports consume normalized values, provider summaries, explanations,
diagnostics, and rejected-observable details. These fields are evidence only;
they do not change apply-mode selection.

Set `MAIL_DOMAIN_QUARANTINE_HOME` to redirect state and report output during
tests or disposable scans. Apply mode moves mail and should only be used after a
dry-run report has been reviewed.
