---
name: transactional-cleanup
description: Clean generated build, deployment, browser, media and temporary artifacts through reviewed snapshots and exact-file deletion tickets. Use when a task leaves local output to reclaim, including output outside its workspace.
license: MIT
metadata:
  version: "0.5.0"
  compatibility: Windows 10/11, Python 3.11+, NTFS/ReFS identity. Codex and Claude; installed local helper required.
---

# Transactional Cleanup

Use `scripts/invoke_transactional_cleanup.py` for attributed generated artifacts.
Read the JSON results and inspect the review before issuing a ticket. An issued
ticket is a procedural review gate, not a request for another user approval.

## Prevent Litter Before Creation

Create task-owned scratch beneath an exact task folder in `D:/Temp` or `E:/Temp`:
disposable clones/worktrees, captures, downloaded verification copies, logs,
packaging intermediates and evidence staging. Set child-process `TEMP`/`TMP` or
tool-specific scratch options when supported; do not change global environment
settings or pretend every tool honors them. Record unavoidable outside-Temp output
and register its exact generated path for cleanup. Do not scatter scratch beside
maintained checkouts or in Documents, Downloads, C: user Temp or helper installations.

Maintained source, requested deliverables, installed runtimes and durable ticket
state are NOT temporary scratch. Keep their intentional paths; do not move an
existing checkout into Temp merely to obtain deletion authority. Clean attributable
existing leftovers outside Temp using their proper contract below. The helper
does not intercept arbitrary filesystem writes; agents must enforce placement.

Cleanup MUST NOT acquire the Gradle build mutex, join its execution queue, or be
wrapped in the Gradle build launcher. Use this helper's own exact-target locks.
Gradle-produced files are not automatically shared build resources: review exact
ownership and skip outputs still used by a build. Shared cache/version retirement
requires current consumer evidence and safe native lifecycle or owner coordination;
ambiguous targets are preserved, not a reason to reserve the host build gate for
an entire mixed cleanup batch. Captures, old APKs and manifest hashing do not need
the Gradle gate. Never stop another build to obtain cleanup clearance.

## Route Source Changes And Cleanup Separately

Git tracking protects working source from accidental artifact cleanup; it is not
a blanket refusal to remove anything inside a repository. Classify each target:

- Generated output: review exact provenance and current consumers, then use the
  normal ticket workflow (or Existing Build Leftovers for pre-existing output).
  A repository ancestor does not make untracked build output untouchable.
- Disposable validation clone: use Disposable Validation Repositories only when
  that exact clone satisfies its contract; tracked members can then be ticketed.
- Entire obsolete checkout, including outside Temp: use Explicit Repository
  Retirement below, not the disposable-validation shortcut.
- Obsolete tracked source or templates: removal is a normal source change, not a
  cleanup ticket. If removal is within the user's authorized scope, inspect
  references, build/package consumers and local changes, make the narrow reviewed
  deletion, verify the affected behavior and commit it through normal Git review.
  Do not force-remove local edits, untrack source just to bypass this helper, or
  interpret an artifact-cleanup request as permission to delete source. If source
  removal is outside scope, preserve it and report that decision separately.

When a review reports `git_tracked`, inspect the exact excluded members; do not
abandon independent eligible artifacts. Apply their reviewed ticket and separately
report removed output, preserved source and genuine residual blockers. Do not
describe the whole cleanup as blocked because a few tracked files are excluded.
An unused wrapper template is not a downloaded Gradle distribution or cache;
deleting the template does not reclaim those dependencies.

## Workflow

1. Before disk-intensive work, run `begin --workspace <repo>`. It inventories only
   that workspace. For targeted work, repeated `--scan-root <path>` replaces the
   workspace scan. Add known Temp roots only with `--include-known-temp-roots`.
   Include the workspace explicitly only when its inventory is wanted.
   Reports state actual coverage; existing transactions retain their original roots.
   Do not choose an entire Temp root for a known list of build leftovers: repeat
   `--scan-root` for each exact output folder. Registration does not narrow scans.
2. Register specific outputs with `register --transaction <id> --path <output>
   --kind compiler-output --evidence "<command or tool that creates this output>"`.
   Register before creation when possible. A normal registration cannot authorize a
   repository root, tracked file, helper installation, or protected system path.
   Use the separate disposable-validation-repository contract below only when all
   of its safeguards apply.
3. Finish and verify the primary task, then run `review --transaction <id>`.
   Inspect candidate/exclusion diagnostics and byte estimate. When diagnostics are
   capped, page the signed manifest with `inspect --transaction <id> --offset <n>
   --limit 100`, optionally filtering with `--decision candidate|excluded`.
4. In a separate invocation run `ticket --transaction <id>
   --manifest-sha256 <reviewed hash>`. No paths can be added after review.
5. Use `apply --ticket <opaque id> --dry-run` if useful, then
   `apply --ticket <opaque id>`. Read result counts and reclaimed bytes.
6. Use `status --transaction <id>` for residuals, or bare `status` to observe the
   active/latest operation. It is lock-free and reports phase/count/byte progress.
   Retry the same ticket after
   locks release. Do not report completion while `partially_applied` remains.
   `revoke --ticket <id>` explicitly abandons unresolved cleanup without deleting it.
   If no ticket was issued, use `discard --transaction <id> --reason "<why the
   snapshot is no longer needed>"`. This abandons the inventory, not the target
   files; future cleanup requires a fresh snapshot. Close snapshots after task
   completion, failure or a change of strategy; do not leave abandoned inventories.

All commands accept `--state-root <directory>` before the command for test isolation.
Keep normal installed commands on their default helper state.

If an operation returns `target_busy`, its root overlaps a live operation; use
lock-free `status` to observe it and retry after that operation completes. Disjoint
explicit roots may run concurrently. `state_busy` is reserved for a pre-upgrade
runtime that still owns the legacy global lock. Do not infer a hang solely from
elapsed time. Broad inventories still require filesystem traversal, but
state is streamed in bounded batches. Once a
review has completed, inspect its existing manifest instead of running it again.

SQLite failures are distinct from target ownership: `state_database_busy` reports
`sqlite_error_code` and `sqlite_error_name`, including `SQLITE_BUSY_SNAPSHOT`.
That code can mean a stale read snapshot, not an ongoing filesystem lock. Inspect
saved status and diagnose the database failure before retrying a still-valid
ticket. Do not blindly retry, kill an assumed owner, auto-revoke, or bypass the
helper. Apply may have removed exact members before its last result checkpoint;
committed `deleted_bytes` may undercount those removals. Revoked tickets remain
unusable: any residual cleanup needs a fresh reviewed snapshot and ticket.

## Existing Build Leftovers

When a build started without a transaction, first inspect the exact folder and
verify its generated provenance and whether an installed application depends on it.
Begin with `--workspace <repo> --scan-root <exact-output-folder>` so unrelated
workspace and Temp trees are not traversed. Then register that bounded output with
`--regenerated --kind explicit-generated-output --evidence "<verified provenance>"`.
This is the specification's explicitly registered pre-existing generated-output
path. Ordinary pre-existing modified files remain protected. Never use
`--regenerated` on a whole temp/profile/repository root.
Non-Git output is supported. Empty regular `.git` files and empty `.git`
directories inside attributable generated output may be reviewed and ticketed.
Zero bytes alone is not deletion authority: provenance, pre-existing-file
authority, ancestor Git tracking, stable identity and exact-file checks apply.
Nonempty or linked markers and real repositories remain protected. `.gitignore`
is governed by attribution and Git tracking, not its filename. Failure to inspect
a real repository remains fail-closed.

## Disposable Validation Repositories

For an exact standalone Git clone created only for temporary validation, begin with
that clone as an explicit scan root and register the root itself:

```text
begin --workspace <real-workspace> --scan-root <recognized-temp>\validation-clone
register --transaction <id> --path <recognized-temp>\validation-clone --kind disposable-repository --evidence "<command and purpose that created this disposable clone>" --regenerated --allow-disposable-repository
```

Use this authority only when the clone is independently reproducible and the
evidence establishes why it is disposable. The helper requires the path to be the
exact scan root, a strict descendant of a recognized Temp root, a normal NTFS/ReFS
directory, and an exact Git top-level with an internal `.git` directory. It rejects
the active workspace, linked worktrees, symlinked repositories, broad Temp roots,
repositories outside Temp, and roots replaced after authorization. Review includes
tracked files and `.git` metadata as exact members. New concurrent files still
survive and produce `partially_applied`; retry or start a new review rather than
deleting them outside the helper.

## Snapshot And Retry Contract

- Apply accepts only an opaque helper-issued ticket, never a path, wildcard or shell expression.
- New concurrent files survive. Their nonempty directories remain and are reported.
- A modified generated file with the same Windows identity remains eligible.
- A replacement at the same path is skipped as `replaced_after_scan`.
- Locked files are retryable; other eligible files are processed independently.
- Junctions, symlinks, hard links, tracked files and critical roots are protected.
  Tracked-file exceptions require an exact authorized disposable validation
  repository or the separately evidenced obsolete-checkout retirement contract.
- Exact hard-link names or leaf symlink/junction objects may be enabled only on an
  explicit registration with `--allow-hardlinks` or `--allow-leaf-reparse`. These
  options never authorize another link name or traversal/deletion of a link target.
- Directories are removed only when empty. No recursive directory deletion occurs.
- USN/ETW tracking is unavailable in v2; never claim complete host coverage.
- No expiry or execution cancellation timeout. No process killing, backups or quarantine.
- Terminal transactions retain a compact summary; detailed inventories are removed.
- This helper remains subject to command policy. If its invocation is rejected,
  report the rejection; do not switch shells or methods to bypass it.

## Explicit Repository Retirement

Whole maintained or legacy checkouts are not ordinary generated trash. When the
user explicitly authorizes retirement, use an exact scan root, a separate workspace,
and an external evidence document matching [the retirement contract](references/retirement.md).
Register with `--kind retired-repository --regenerated --retirement-evidence <json>
--confirm-retire-repository <exact-checkout-root> --evidence "<retirement purpose>"`.

The helper verifies a clean standalone checkout, absence of additional worktrees
and submodules, all local/ref/reflog history in an independent existing bare
recovery repository, object integrity, stable identities and visible process
references. Record ownership, scheduler/service and dependency checks; command
lines do not prove universal inactivity. Preserve dirty work or recover missing
history before retrying. Never manufacture attestations or create an unnecessary
backup automatically. Existing remote-tracking refs alone do not prove recovery.

Review, inspect and ticket normally. Retired regular files additionally receive
content hashes: new, replaced or edited members survive; retry tolerates already
removed Git metadata. No recursive delete or Gradle gate is used. An unsupported
helper mode is not a tool rejection. A rejected direct shell command does not
establish that the helper was attempted or rejected, but must not be evaded.

## Keep Helper State Small

Run `state-inventory` to see retained files, unfinished transactions and live
root claims without scanning the targets. Distinguish large active manifests from
abandoned unissued inventories; age, low CPU or a recorded PID is not ownership
proof. Explicit `discard` checks the target locks, rejects issued tickets, removes
SQLite detail and reclaims database pages while retaining a compact reasoned
summary. It also authenticates and compacts unissued v1 open snapshots using
bounded reads. Legacy compaction rejects overlapping live operations and leaves
already running disjoint operations alone.
Issued/partial tickets require completion or an explicit `revoke`, never discard.

Do not delete the state directory/key/database, prune pending tickets by age, or
move durable state into routinely purged Temp. Do not call VACUUM a cure for live
inventory rows. Report remaining valid state separately from reclaimed metadata.

## Installation

Run the repository family installer `scripts/install.py` to deploy both skills
and the shared local runtime. The installed wrapper reads
`LOCALAPPDATA/Tools/transactional-cleanup/active.json`. Use
`AGENT_TOOLBELT_HOME` only for explicit development against a checkout.
