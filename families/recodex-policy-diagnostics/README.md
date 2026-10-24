# ReCodex Policy Diagnostics

Version 0.1.0. The canonical instruction-only bundle is
`codex/skills/recodex-policy-diagnostics`. Copy the same folder to the personal
Codex, shared-agent or Claude skill root. It requires the locally installed
ReCodex Policy Inspector and `approach-recovery-ledger` for durable rejection
records; neither application nor database is bundled.

The skill explains an observed blocked operation, uses the Inspector's headless
CLI for local PowerShell diagnostics, records cybersecurity rejections in the
existing private ledger, and preserves a concrete permitted next action. It does
not run submitted commands or install an automatic rejection/recovery hook.

See `SPECIFICATION.md` for acceptance and delivery status. Runtime reports and
real rejection records remain outside this public repository.
