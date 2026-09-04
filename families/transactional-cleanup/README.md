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
agent-toolbelt-transactional-cleanup ticket --transaction <id> --manifest-sha256 <reviewed-hash>
agent-toolbelt-transactional-cleanup apply --ticket <id> --dry-run
agent-toolbelt-transactional-cleanup apply --ticket <id>
agent-toolbelt-transactional-cleanup status --transaction <id>
agent-toolbelt-transactional-cleanup revoke --ticket <id>
```

`--state-root` is a global option for isolated test state. For pre-existing known
generated output, registration requires `--regenerated` with explicit provenance.
Without it, pre-existing modified files are protected. New untracked source files
are not automatically considered generated. Known cache directories are classified
only when the baseline proves they are new. Root inventories never traverse reparse
points. Git failure protects repository files.

## State And Limits

Metadata manifests and tickets are HMAC-bound to a local helper key, host identity,
policy version and reviewed member set. This is a procedural guard for accidental
misuse; a program already able to alter the helper/key has the same user authority.
Operations serialize through an OS-owned lock, returning `state_busy` for overlap.
An append-only signed item journal supports interrupted retries. There is no ticket
expiry and no command cancellation timeout. Terminal state retains at most 100 small
transaction summaries and removes detailed manifests and journals. Partial tickets
retain unresolved members until retried or explicitly revoked.

Reports cap item diagnostics at 100 and expose a manifest path for detailed review.
`deleted_bytes` counts observed logical file sizes, not filesystem allocation savings;
after a crash between disposition and journal write a missing file is not credited
as deleted by the retry. Nonempty directories are retryable `not_empty` results.
Dry runs test the present filesystem without pretending that children were removed.

V1 implements workspace and known/explicit-root snapshots and registration. USN and
ETW are honestly reported as unavailable. This release does not claim complete host
or process attribution. The helper is subject to Codex/tool execution policy and
does not provide a policy bypass.
