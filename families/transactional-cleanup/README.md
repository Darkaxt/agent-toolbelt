# Transactional Cleanup

Version 0.7.3 corrects the same false positive for nested package modules named
`boot`. Volume-root Boot/EFI/Recovery and the Windows tree stay protected;
unattributed user files, ancestry, Git, identity/content and signed-ticket checks
remain unchanged. The test scratch parent can be set through
`TRANSACTIONAL_CLEANUP_TEST_ROOT` without changing application/global settings.

Version 0.7.2 supports exact task-owned immediate children of Android Download.
The shared Download parent is identity-bound and rechecked but never ticketed;
normal endpoint, ancestry, content and signed-ticket protections remain in place.
See [Android Task Cleanup](codex/skills/transactional-cleanup/references/android.md).

Version 0.7.1 corrects a Recovery path false positive: volume-root `Recovery`
trees and the protected Windows tree remain excluded, while nested package
modules named `recovery` use the normal provenance, Git, identity/content and
signed-ticket checks. No file is eligible merely because of its directory name.

Version 0.6 adds a separate device-bound Android backend: exact task-file
review/inspect/ticket/apply, plus task-installed test-app cleanup with a pre-install
absence baseline and planned APK hashes. Read [Android Task Cleanup](codex/skills/transactional-cleanup/references/android.md).
No root access, recursive deletion, automatic device choice or host-only identity
claims are used. Android stat/hash/unlink checks are not Windows handle-bound
deletion; stop producers before cleanup. No existing device data is removed by
installation of this feature.

Empty regular `.git` files and empty `.git` directories in attributable generated
output can be included in exact-file tickets. This does not exempt real Git
metadata, tracked files, reparse points, or unproven/pre-existing user data.
`.gitignore` uses the ordinary provenance and tracked-file rules.

The helper inventories generated output, freezes a reviewed snapshot and issues an
opaque deletion ticket. Apply processes only original ticket members. Concurrent
new files survive; replaced objects are skipped; locked entries can be retried.
Windows open handles bind deletion to verified file identity and protect ancestor
directories from substitution. No recursive directory deletion is used.

## Source Versus Artifact Routing

Git-tracked source in a maintained working repository remains protected by the
helper. Removing an obsolete source template within the user's authorized scope
is a normal reviewed, verified and committed source change, not a cleanup ticket
or a reason to add a tracked-file override. Preserve unrelated local changes.
Unused wrapper templates are not downloaded Gradle distributions or caches.

Untracked generated output inside a repository remains eligible with verified
provenance. Inspect exact `git_tracked` exclusions and continue independent eligible
cleanup rather than treating the whole repository or batch as blocked. Report
removed output, preserved source and actual residual blockers separately.
Verified disposable validation clones use the explicit contract below, including
their tracked members; this does not authorize removal of maintained repositories.

## Scratch Placement

Create agent-owned disposable clones, staging, logs and captures beneath exact task
folders in D:/Temp or E:/Temp. Configure child TEMP/TMP and tool scratch directories
where supported, without changing global settings. Record unavoidable external
outputs explicitly. Maintained checkouts, deliverables, installations and durable
ticket state keep their intentional locations. The helper does not intercept agent
writes; placement is an execution rule, not a claim of host-wide enforcement.
Existing attributable output outside Temp remains eligible for scoped cleanup.

## Install

From this family run `python scripts/install.py`. It deploys a shared dependency-free
runtime under LOCALAPPDATA/Tools/transactional-cleanup and skills to the personal
Codex, agents and Claude skill roots. No virtual environment or downloaded package
is required. Python 3.11+ and Windows NTFS/ReFS or the content-bound exFAT mode
below are required for deletion. Other filesystems remain protected.

## exFAT Generated Output

Ordinary generated files and empty directories on exFAT use the same reviewed
manifest/ticket workflow. When FileIdInfo is unsupported, the helper confirms
exFAT through the open handle and records its volume serial, 64-bit index and
creation time. It never substitutes 64-bit IDs on NTFS/ReFS. Every eligible exFAT
regular file also receives SHA-256, size and write-time proof at review. Apply
checks that proof through the same write/delete-guarded handle used to delete it.
Modified/replaced files and new concurrent files survive. Changes need a fresh
review; simply retrying an old ticket does not authorize new content. This is
stricter than NTFS/ReFS same-identity generated-output edits. Locked/unreadable
review members are excluded independently; apply sharing failures remain retryable.
Hashing streams content and adds I/O only for exFAT candidates, not every NTFS file.

No recursive deletion, alternate deletion mechanism or global maintenance mutex
is used. Special disposable-repository, checkout-retirement and generated Git
workflow-marker contracts remain NTFS/ReFS-only. A historical discarded review
must be replaced with begin/register/review/inspect and a new ticket.

## Commands

```text
agent-toolbelt-transactional-cleanup begin --workspace <repo> --scan-root <temp-root>
agent-toolbelt-transactional-cleanup register --transaction <id> --path <output> --kind compiler-output --evidence <provenance>
agent-toolbelt-transactional-cleanup register --transaction <id> --path <temp-clone> --kind disposable-repository --evidence <provenance> --regenerated --allow-disposable-repository
agent-toolbelt-transactional-cleanup review --transaction <id>
agent-toolbelt-transactional-cleanup inspect --transaction <id> --offset 0 --limit 1000
agent-toolbelt-transactional-cleanup ticket --transaction <id> --manifest-sha256 <reviewed-hash>
agent-toolbelt-transactional-cleanup apply --ticket <id> --dry-run
agent-toolbelt-transactional-cleanup apply --ticket <id>
agent-toolbelt-transactional-cleanup status [--transaction <id>]
agent-toolbelt-transactional-cleanup revoke --ticket <id>
agent-toolbelt-transactional-cleanup state-inventory
agent-toolbelt-transactional-cleanup discard --transaction <unissued-id> --reason <abandonment-reason>
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
or latest operation, and reports phase/count/byte progress. `target_busy` means a
live operation owns the same target root or an ancestor/descendant; inspect status
rather than launching an overlapping operation. Operations on disjoint explicit
roots may run concurrently. `state_busy` is reserved for a pre-upgrade runtime that
still owns the legacy global lock. A completed `reviewed` transaction should not be
reviewed again.
Large-manifest inspection supports 1,000 members per call. Follow next_offset,
inspect each needed page once and serialize access to the same transaction,
including read-only inspect calls. Capture large JSON outside the conversation
instead of spawning small-page processes. Candidate/deletion byte totals exclude
directory sizes; do not add directory metadata sizes to an independent census.
For pre-existing known
generated output, registration requires `--regenerated` with explicit provenance.
Without it, pre-existing modified files are protected. New untracked source files
are not automatically considered generated. Known cache directories are classified
only when the baseline proves they are new. Root inventories never traverse reparse
points. Git failure inside a real repository protects repository files. An empty
abandoned `.git` directory is not treated as a repository and does not block an
explicitly registered non-repository generated output. Hard links and leaf reparse objects
remain protected unless their explicit registration adds `--allow-hardlinks` or
`--allow-leaf-reparse`. These flags authorize only exact ticketed names: other hard
links and symlink/junction targets remain intact.

An exact standalone Git clone created only for validation may be authorized with
`--kind disposable-repository --regenerated --allow-disposable-repository`. The
repository must be an exact explicit scan root, a strict descendant of a recognized
Temp root, and contain a real internal `.git` directory. Linked worktrees, the
workspace repository, broad Temp roots, repositories outside Temp, and repositories
whose root identity changes after review remain protected. Review includes the
tracked files and `.git` metadata as exact ticket members. New files created after
review survive; no recursive repository deletion is used.

## Explicit Obsolete Checkout Retirement

An explicitly authorized whole obsolete checkout may be outside Temp. Use
`--kind retired-repository --regenerated --retirement-evidence <external-json>
--confirm-retire-repository <exact-root>` with an exact scan root and a separate
workspace. See [the evidence contract](codex/skills/transactional-cleanup/references/retirement.md).

The helper verifies a clean standalone checkout, no additional worktrees/submodules,
independent existing bare recovery with original refs and anchored reflog history,
object integrity, stable identities and visible process references. Owner evidence
must record explicit authorization and actual ownership/service/scheduler/dependency
checks. No automatic backup, blanket tracked-file override, recursive delete or
Gradle execution gate is introduced. Ordinary maintained source remains protected.
Retired regular files are content-hashed: edits, replacements and new files survive.
First apply revalidates Git state; a partial retry tolerates removed Git metadata.
This feature must not be used to evade a tool's actual deletion-policy rejection.

## State And Limits

Normalized SQLite/WAL metadata and manifest rows are HMAC-bound to a local helper
key, host identity, policy version and reviewed member set. Tickets reference exact
candidate rows instead of copying them. Root claims serialize overlapping filesystem
operations while allowing disjoint roots to run concurrently; stale claims are
reclaimed through OS-owned lock state. SQLite serializes only its short write
transactions, while status remains readable. Apply commits result/progress batches of 256
items rather than synchronizing once per object. A crash before the next batch commit
can turn an already deleted item into `already_missing` on retry, but can never add
authority. There is no ticket expiry or command cancellation timeout. Terminal state
retains at most 100 compact summaries and removes detailed rows.

Unissued open/reviewed snapshots otherwise remain durable; they are not pruned by
age. `state-inventory` reports their rows, file sizes and live root claims without
scanning cleanup targets. Explicit `discard --transaction --reason` abandons an
unissued inventory, not target files, and reclaims its database pages. Live target
operations and issued tickets block discard; use completion or explicit revocation
for tickets. Legacy open v1 snapshots are authenticated with bounded reads and
replaced by compact signed summaries only when no overlapping operation is active;
already running disjoint operations remain independent.
Close/discard unused snapshots after cancellation or a strategy change. Never delete
the state key/database or put durable authorization state in routinely purged Temp.

Version 0.4.2 exhausts indexed, bounded read pages before filesystem deletion or
result commits. This prevents a disjoint writer from invalidating a retained WAL
read snapshot between apply batches. It rechecks signed rows as they are paged and
checks full ticket membership before reporting success. Disjoint operations remain
concurrent; no whole-operation database lock, timeout increase or retry loop is used.
SQLite errors return `state_database_busy` or `state_database_error` with extended
error code/name rather than a traceback. Inspect status and diagnose before retrying
a still-valid ticket; do not assume a current lock owner or revoke automatically.
Already removed members may be undercounted if their result batch was not committed.
Revoked tickets cannot resume; residual work requires a fresh review and ticket.

Reports cap item diagnostics at 100. Use paginated `inspect` for detailed review.
`deleted_bytes` counts observed logical file sizes, not filesystem allocation savings;
after a crash between disposition and journal write a missing file is not credited
as deleted by the retry. Nonempty directories are retryable `not_empty` results.
Dry runs test the present filesystem without pretending that children were removed.

V2 implements workspace and known/explicit-root snapshots and registration. USN and
ETW are honestly reported as unavailable. This release does not claim complete host
or process attribution. The helper is subject to Codex/tool execution policy and
does not provide a policy bypass.

## Generated Git Markers

Exact generated `.git/<namespace>-workflow-tree` pointer files have a dedicated
`generated-git-marker` registration kind, requiring `--regenerated`,
`--confirm-git-marker <exact-path>` and producer provenance. Normal review and
ticket gates apply, with ancestor identities and reviewed content hashes.
Source, tree objects, refs and other Git metadata remain protected.
This exception does not override execution policy or authorize retrying a denied
deletion. Put new task-local markers under D:/Temp instead.
