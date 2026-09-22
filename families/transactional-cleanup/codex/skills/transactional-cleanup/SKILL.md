---
name: transactional-cleanup
description: Clean generated build, deployment, browser, media and temporary artifacts through reviewed snapshots and exact-file deletion tickets. Use when a task leaves local output to reclaim, including output outside its workspace.
license: MIT
metadata:
  version: "0.4.0"
  compatibility: Windows 10/11, Python 3.11+, NTFS/ReFS identity. Codex and Claude; installed local helper required.
---

# Transactional Cleanup

Use `scripts/invoke_transactional_cleanup.py` for attributed generated artifacts.
Read the JSON results and inspect the review before issuing a ticket. An issued
ticket is a procedural review gate, not a request for another user approval.

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

All commands accept `--state-root <directory>` before the command for test isolation.
Keep normal installed commands on their default helper state.

If an operation returns `target_busy`, its root overlaps a live operation; use
lock-free `status` to observe it and retry after that operation completes. Disjoint
explicit roots may run concurrently. `state_busy` is reserved for a pre-upgrade
runtime that still owns the legacy global lock. Do not infer a hang solely from
elapsed time. Broad inventories still require filesystem traversal, but
state is streamed in bounded batches. Once a
review has completed, inspect its existing manifest instead of running it again.

## Existing Build Leftovers

When a build started without a transaction, first inspect the exact folder and
verify its generated provenance and whether an installed application depends on it.
Begin with `--workspace <repo> --scan-root <exact-output-folder>` so unrelated
workspace and Temp trees are not traversed. Then register that bounded output with
`--regenerated --kind explicit-generated-output --evidence "<verified provenance>"`.
This is the specification's explicitly registered pre-existing generated-output
path. Ordinary pre-existing modified files remain protected. Never use
`--regenerated` on a whole temp/profile/repository root.
Non-Git output is supported. An empty abandoned `.git` marker does not make a path
a repository, while failure to inspect a real repository remains fail-closed.

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
  The only tracked-file exception is an exact ticketed member of an explicitly
  authorized disposable validation repository as defined above.
- Exact hard-link names or leaf symlink/junction objects may be enabled only on an
  explicit registration with `--allow-hardlinks` or `--allow-leaf-reparse`. These
  options never authorize another link name or traversal/deletion of a link target.
- Directories are removed only when empty. No recursive directory deletion occurs.
- USN/ETW tracking is unavailable in v2; never claim complete host coverage.
- No expiry or execution cancellation timeout. No process killing, backups or quarantine.
- Terminal transactions retain a compact summary; detailed inventories are removed.
- This helper remains subject to command policy. If its invocation is rejected,
  report the rejection; do not switch shells or methods to bypass it.

## Installation

Run the repository family installer `scripts/install.py` to deploy both skills
and the shared local runtime. The installed wrapper reads
`LOCALAPPDATA/Tools/transactional-cleanup/active.json`. Use
`AGENT_TOOLBELT_HOME` only for explicit development against a checkout.
