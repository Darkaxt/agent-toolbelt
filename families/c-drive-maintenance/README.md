# C-Drive Maintenance

Gradle cleanup is evaluated per version: an identified active version does not
block review of unrelated obsolete artifacts. Unknown consumers remain protected;
review/ticket checks never acquire the Gradle build mutex or queue.

On-demand, active Windows maintenance for Codex and Claude. The agent executes
verified cleanup, sends bounded compatible toolchain requests to existing owners,
and verifies retirement and recurrence prevention. No scheduled monitor.

The standard-library-only helper provides:
- Streaming RidNacs triage, including unquoted comma-containing paths and inclusive rollup accounting.
- Structured owner request construction; delivery uses the agent's existing task API.
- Two-step generated-output cleanup through the installed transactional-cleanup wrapper.

Shared/native-managed directories are intentionally routed to their correct
lifecycle, not this generated-output adapter. This is not a new deletion engine,
automatic project upgrader, or Codex database purge implementation.

## Install

```powershell
python families/c-drive-maintenance/scripts/install.py
```

Installs the self-contained runtime and the same skill into `~/.codex/skills`,
`~/.agents/skills` and `~/.claude/skills`. No cookies, tokens, ledgers, exports or
user state are included. The runtime has no repository-path dependency.

## Commands

```powershell
python scripts/invoke_c_drive_maintenance.py inventory --csv <RidNacs.csv> --limit 30 --target-free-gib 200
python scripts/invoke_c_drive_maintenance.py request --project <checkout> --task-id <owner-id> --toolchain gradle --current-version 8.6 --target-version 9.8.0
python scripts/invoke_c_drive_maintenance.py cleanup-prepare --workspace <checkout> --target <exact-generated-output> --evidence "Verified obsolete build output; owner inactive" --confirm-disposable
python scripts/invoke_c_drive_maintenance.py cleanup-apply --transaction <id> --manifest-sha256 <inspected-hash> --dry-run
```

After dry-run use transactional-cleanup's returned ticket to apply, not a second
ticket issuance. `--cleanup-state-root <isolated-path>` precedes the command when
testing. No subprocess timeout or detached deletion process is used.

The inventory covers known lifecycle anchors rather than every arbitrary folder.
Unknown large user content still needs direct review. The 200 GiB default is a
configurable prioritization target, never blanket authorization.

## Verification

```powershell
python -B -m unittest discover -s families/c-drive-maintenance/tests -p "test_*.py"
```

The installed cleanup integration test uses only disposable fixtures. It skips
when transactional-cleanup is not installed; record that gap instead of claiming
real integration proof. No live caches/snapshots/projects are modified by tests.

See [specification and stage reconciliation](SPECIFICATION.md).
