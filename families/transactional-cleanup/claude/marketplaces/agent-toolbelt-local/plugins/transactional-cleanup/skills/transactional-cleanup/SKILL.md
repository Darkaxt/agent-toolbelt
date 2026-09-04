---
name: transactional-cleanup
description: Clean generated build, deployment, browser, media and temporary artifacts through reviewed snapshots and exact-file deletion tickets. Use when a task leaves local output to reclaim, including output outside its workspace.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows 10/11, Python 3.11+, NTFS/ReFS identity. Codex and Claude; installed local helper required.
---

# Transactional Cleanup

Use `scripts/invoke_transactional_cleanup.py` for attributed generated artifacts.
Read the JSON results and inspect the review before issuing a ticket. An issued
ticket is a procedural review gate, not a request for another user approval.

## Workflow

1. Before disk-intensive work, run `begin --workspace <repo>`. Known temporary
   roots are also inventoried; use repeated `--scan-root <path>` to select them
   explicitly. Reports state the actual discovery coverage.
2. Register specific outputs with `register --transaction <id> --path <output>
   --kind compiler-output --evidence "<command or tool that creates this output>"`.
   Register before creation when possible. A registration cannot authorize a
   repository root, tracked file, helper installation, or protected system path.
3. Finish and verify the primary task, then run `review --transaction <id>`.
   Inspect the candidate/exclusion diagnostics, byte estimate and signed manifest
   at `manifest_path`. The full manifest is available when diagnostics are capped.
4. In a separate invocation run `ticket --transaction <id>
   --manifest-sha256 <reviewed hash>`. No paths can be added after review.
5. Use `apply --ticket <opaque id> --dry-run` if useful, then
   `apply --ticket <opaque id>`. Read result counts and reclaimed bytes.
6. Use `status --transaction <id>` for residuals. Retry the same ticket after
   locks release. Do not report completion while `partially_applied` remains.
   `revoke --ticket <id>` explicitly abandons unresolved cleanup without deleting it.

All commands accept `--state-root <directory>` before the command for test isolation.
Keep normal installed commands on their default helper state.

## Existing Build Leftovers

When a build started without a transaction, first inspect the exact folder and
verify its generated provenance and whether an installed application depends on it.
Begin a transaction, then explicitly register that bounded output with
`--regenerated --kind explicit-generated-output --evidence "<verified provenance>"`.
This is the specification's explicitly registered pre-existing generated-output
path. Ordinary pre-existing modified files remain protected. Never use
`--regenerated` on a whole temp/profile/repository root.

## Snapshot And Retry Contract

- Apply accepts only an opaque helper-issued ticket, never a path, wildcard or shell expression.
- New concurrent files survive. Their nonempty directories remain and are reported.
- A modified generated file with the same Windows identity remains eligible.
- A replacement at the same path is skipped as `replaced_after_scan`.
- Locked files are retryable; other eligible files are processed independently.
- Junctions, symlinks, hard links, tracked files and critical roots are protected.
- Directories are removed only when empty. No recursive directory deletion occurs.
- USN/ETW tracking is unavailable in v1; never claim complete host coverage.
- No expiry or execution cancellation timeout. No process killing, backups or quarantine.
- Terminal transactions retain a compact summary; detailed inventories are removed.
- This helper remains subject to command policy. If its invocation is rejected,
  report the rejection; do not switch shells or methods to bypass it.

## Installation

Run the repository family installer `scripts/install.py` to deploy both skills
and the shared local runtime. The installed wrapper reads
`LOCALAPPDATA/Tools/transactional-cleanup/active.json`. Use
`AGENT_TOOLBELT_HOME` only for explicit development against a checkout.
