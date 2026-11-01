# Helper retention correction

Authorized 2026-11-01: no Coordinator rollback builds, no copying project files
into disk-maintenance installations, automatic cleanup-ticket expiry and trimming.

## Requirements

- RC1: cleanup authority expires after seven days without a mutating helper call.
  This internal default applies to open/reviewed inventories and issued/partial
  tickets, including inherited state. Read-only inspection does not renew it.
- RC2: each actual CLI invocation trims expired state before dispatch. Expiry
  removes detailed inventories, invalidates tickets and keeps bounded compact
  summaries. It never deletes target files, replays deletion or interrupts a live
  cleanup operation. Locks and original host/integrity checks remain binding.
- RC3: Windows, Android and legacy JSON routing cannot bypass expiry. Return a
  clear expired result requiring a new review. Existing current tickets still work.
- RC4: disk-maintenance guidance must forbid copying project files, reports,
  captures or backups into any helper/skill installation. Preserve originals;
  retain only a compact private ledger in an appropriate project/maintenance path.
- RC5: install matching skills/runtimes, verify real state reduction and publish
  the completed source and versioned local cleanup release. Do not remove unique
  historical project evidence merely because its location violates the new rule.

## Stages

| Stage | Status | Acceptance |
| --- | --- | --- |
| Cleanup and maintenance retention | COMPLETE | RC1–RC4 implemented. The affected cleanup family suite passed, including expiry/no target deletion/live-operation exclusion/current tickets, legacy routing and Android expiry. Canonical/Claude bundle parity checked. Installed delivery is the final stage. |
| Coordinator release retirement | COMPLETE | Manifest/hash-bound retirement, real consumers, idle CUA/console handling and bytecode ownership verified. Live installation reduced from 54 builds to one active build; 53 obsolete builds and both idle adapters retired, no rollback exemption. |
| Delivery and reconciliation | COMPLETE | Cleanup 0.8.0 and Coordinator 0.18.3 installed and read back; archives independently extracted/verified; matching GitHub branch/tags read back. Existing cleanup state shrank from about 706 MiB to 1.5 MiB without target deletion. Exact ticket removed 474,173,759 task-output bytes with no residuals. |

Temporary hot test databases/builds use exact D:/Temp/helper-retention-20261101
because sustained SQLite/native build I/O must stay on the internal drive.
No other active implementation stage. No approval checkpoint. No deferrals.
Stage-one closure review: lifetime is centralized in retention.py; existing native
root claims remain authoritative, with no alternate target deletion mechanism.
No additional architecture or debt-remediation stage is required.
Stage-two closure review: retirement uses the installer lifecycle and existing
native identity/ownership primitives. No schedule, service or generalized pruning
framework was introduced. Concrete old-runtime consumers are the only exception.
Delivery correction: the user's native startup-error screenshot requires fixing
the false Explorer job-membership rejection. Actual Explorer identity/session and
the detached Coordinator's job-free lifetime remain required; final Coordinator
delivery is 0.18.3. Real native scheduled activation passed on this desktop.

Final reconciliation: RC1–RC5 satisfied, no blockers or tracked deferrals. Unique
historical DualDex evidence was not copied or deleted. Changed bundle/discovery
checks passed; the unchanged context-transfer global lint failure and unexercised
background dashboard rendering are recorded without claiming broader validation.
