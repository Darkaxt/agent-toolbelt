# Transactional Cleanup

The helper inventories generated output, freezes a reviewed snapshot and issues an
opaque deletion ticket. Apply processes only original ticket members. Concurrent
new files survive; replaced objects are skipped; locked entries can be retried.
Windows open handles bind deletion to verified file identity and protect ancestor
directories from substitution. No recursive directory deletion is used.

## Install

From this family run `python scripts/install.py`. It deploys a shared dependency-free
runtime under LOCALAPPDATA/Tools/transactional-cleanup and skills to the personal
Codex, agents and Claude skill roots. No virtual environment or downloaded package
is required. Python 3.11+ and Windows with stable NTFS/ReFS identities are required
for deletion. Unsupported filesystems are reported as protected.

## Commands

```text
agent-toolbelt-transactional-cleanup begin --workspace <repo> --scan-root <temp-root>
agent-toolbelt-transactional-cleanup register --transaction <id> --path <output> --kind compiler-output --evidence <provenance>
agent-toolbelt-transactional-cleanup review --transaction <id>
agent-toolbelt-transactional-cleanup inspect --transaction <id> --decision candidate --offset 0 --limit 100
agent-toolbelt-transactional-cleanup ticket --transaction <id> --manifest-sha256 <reviewed-hash>
agent-toolbelt-transactional-cleanup apply --ticket <id> --dry-run
agent-toolbelt-transactional-cleanup apply --ticket <id>
agent-toolbelt-transactional-cleanup status [--transaction <id>]
agent-toolbelt-transactional-cleanup revoke --ticket <id>
```

`--state-root` is a global option for isolated test state. `begin --workspace`
inventories only the workspace. For targeted generated output, supply
`--scan-root <exact-output>`; repeated explicit roots replace the workspace scan.
Known host Temp roots are added only with `--include-known-temp-roots`. Broad Temp and critical
roots remain protected from registration; a bounded generated output root can be
registered with evidence. Existing transactions keep their original coverage.
`--scan-root D:\Temp` intentionally inventories the entire Temp tree, twice across
begin/review. Registering a small set of outputs afterwards does not narrow it.
For multiple known outputs, repeat `--scan-root` for those exact output folders.
Registration matching uses ancestor lookup instead of an inventory-by-registration
cross-product. Inventory and review rows stream into bounded SQLite batches instead
of full JSON snapshots. `status` is lock-free, accepts no transaction for the active
or latest operation, and reports phase/count/byte progress. `state_busy` means
another mutating operation owns the lock; inspect status rather than launching a
parallel review. A completed `reviewed` transaction should not be reviewed again.
For pre-existing known
generated output, registration requires `--regenerated` with explicit provenance.
Without it, pre-existing modified files are protected. New untracked source files
are not automatically considered generated. Known cache directories are classified
only when the baseline proves they are new. Root inventories never traverse reparse
points. Git failure protects repository files. Hard links and leaf reparse objects
remain protected unless their explicit registration adds `--allow-hardlinks` or
`--allow-leaf-reparse`. These flags authorize only exact ticketed names: other hard
links and symlink/junction targets remain intact.

## State And Limits

Normalized SQLite/WAL metadata and manifest rows are HMAC-bound to a local helper
key, host identity, policy version and reviewed member set. Tickets reference exact
candidate rows instead of copying them. Mutations serialize through an OS-owned
lock, while status remains readable. Apply commits result/progress batches of 256
items rather than synchronizing once per object. A crash before the next batch commit
can turn an already deleted item into `already_missing` on retry, but can never add
authority. There is no ticket expiry or command cancellation timeout. Terminal state
retains at most 100 compact summaries and removes detailed rows.

Reports cap item diagnostics at 100. Use paginated `inspect` for detailed review.
`deleted_bytes` counts observed logical file sizes, not filesystem allocation savings;
after a crash between disposition and journal write a missing file is not credited
as deleted by the retry. Nonempty directories are retryable `not_empty` results.
Dry runs test the present filesystem without pretending that children were removed.

V2 implements workspace and known/explicit-root snapshots and registration. USN and
ETW are honestly reported as unavailable. This release does not claim complete host
or process attribution. The helper is subject to Codex/tool execution policy and
does not provide a policy bypass.
