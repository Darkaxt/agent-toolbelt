# Per-artifact Gradle maintenance

Authority: user requested the next improvement after identifying blanket cache
protection during an unrelated active build. This is a maintenance bug fix, not
new skill discovery, automatic deletion, toolchain migration or a Gradle build.

## Requirements

- R1: An identified live Gradle version protects its distributions and version
  caches, including idle daemons. An active/ambiguous identified version must not
  suppress unrelated, otherwise eligible versions.
- R2: Unattributed activity, unavailable connection inspection and incomplete
  identity evidence remain protected. Never infer non-use from age or low CPU.
- R3: Attribute wrapper clients using observed reciprocal loopback connections
  to identified daemons. Attribute explicit batch launchers through live child
  identities, checking parent/child creation order. Never guess from a matching
  version elsewhere, a shared Gradle home or a nearby process.
- R4: Reports expose per-artifact activity evidence and exact protection reasons.
  Project references/reservations, unknown project coverage, links and inventory
  failures remain protected. Eligible for review is not deletion authorization.
- R5: Cleanup/inventory never acquire the Gradle build gate or queue. The build
  launch/retirement exclusion protocol is unchanged. Recheck exact targets and
  ownership before application; the report cannot prevent a future external build.
- R6: Update both agent bundles and install verified copies for Codex, agents and
  Claude. Preserve active supervisors and runtime releases. Commit and sync.

## Stages and reconciliation

| Stage | Acceptance | Status |
| --- | --- | --- |
| 1: Reproduction | Tests demonstrate unrelated-version overprotection and missing client attribution; existing safety contracts recorded | COMPLETE |
| 2: Correction | R1-R5 implemented with regression evidence and matching guidance | COMPLETE |
| 3: Delivery | Focused/root checks, isolated installed smoke, deployed parity, commit and GitHub sync satisfy R6 | ACTIVE |

No live cache deletion or build is required to validate this change. Use synthetic
process, catalog and filesystem fixtures; a live read-only report may supplement
them. No required deferrals. Verification evidence is recorded below at closure.

Stage 1: focused regression tests reproduced suppression of caches/8.13 during an
identified 9.8.0 build, missing activity evidence and missing client attribution.
Existing catalog, reservations, link and no-build-mutex contracts remain required.

Stage 2: per-version proposals pass for active, ambiguous and idle identified
versions; hidden/unbound clients, invalid versions and incomplete observations
remain protected. Reciprocal client/daemon attribution rejects one-way evidence,
changed identities, hidden commands, cross-session matches and reused parent PIDs.
Focused build/queue contracts passed without changing launch or retirement logic.
Both agent bundles agree. A live read-only snapshot attributed a batch launcher,
wrapper and daemon to 9.8.0 while safe_to_start remained false. No build or cache
deletion was performed. Isolated installed wrappers passed the per-version report
contract in all three skill roots, with no repository bootstrap or build mutex.

Stage 3 verification: focused usage, gate/queue and maintenance regressions passed;
root family wiring and skills.sh validation passed. Personal skill files matched
canonical hashes and validated in all three installed roots. Installed versions
are gradle-build-gate 0.4.2 and c-drive-maintenance 0.1.1. A real installed status
call from outside the repository returned gate_acquired=false, safe_to_start=false
and scoped launcher/client/daemon evidence for 9.8.0 with stable process identities.
Active previous runtimes are retained; disposable test directories were removed by
their test lifecycle. Retirement adapter code is unchanged and its separate live
retirement tests were not rerun. No live cache deletion or migration is claimed.
Commit and remote synchronization are the remaining delivery postconditions.
