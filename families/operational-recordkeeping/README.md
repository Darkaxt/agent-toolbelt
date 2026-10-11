# Operational Recordkeeping

Reconcile existing bills, payments, mail tracking and purchase/decision records
before claiming an operational action complete. This is not an accounting system.

Before financial drafting, inspect the request and existing records, distinguish
claims from requested documents, then read back the saved body/attachments before
calling it ready. See the bundle's `references/correspondence-preflight.md`.
This is instruction-level evidence review; helper success does not certify the
semantic truth or completeness of an email.

The canonical agent-neutral bundle is
`codex/skills/operational-recordkeeping`. Copy it to the personal Codex or Claude
skills directory. Its helper uses Python 3.11+ standard library only: no checkout,
package installation, credentials, COM or network required.

Private profiles live outside the bundle under
`%LOCALAPPDATA%/Tools/operational-recordkeeping/profiles` on Windows, or
`~/.config/operational-recordkeeping/profiles` elsewhere. Override the directory
with `OPERATIONAL_RECORDKEEPING_PROFILES`, or pass a JSON profile path.

See the skill's `references/helper.md` for the event/proof contract. Keep profile
and event data private. Tests use fictional records only:

```powershell
python -B -m unittest tests.test_operational_recordkeeping
```
