---
name: transactional-cleanup
description: Clean task-generated Windows or Android artifacts through reviewed snapshots and exact-file tickets, including temporary test apps with recorded installation provenance.
license: MIT
metadata:
  version: "0.11.0"
  compatibility: Windows 10/11, Python 3.11+, NTFS/ReFS or content-bound exFAT; Android cleanup requires ADB and device shell tools. Codex and Claude.
---

# Transactional Cleanup

Delete task-generated files with `scripts/invoke_transactional_cleanup.py`. Every
route snapshots the targets and deletes only reviewed members: Git-tracked files,
links, protected roots, replaced files and files created after the snapshot always
survive. A ticket is a procedural gate, not a request for another user approval.

## Task scratch under Temp: one call

For a folder your task created below `D:/Temp`, `E:/Temp` or a user Temp root,
once its last consumer has exited:

```text
remove --path <folder> [--path <folder2> ...] --evidence "<what created it and why it is spent>"
```

Use `--kind disposable-repository` for a clean disposable clone or linked worktree
there, and `--dry-run` only to resolve a real doubt (`finish` later resumes that
ticket). The result reports per-path counts, `deleted_bytes` and `excluded`.
`remove` refuses targets outside Temp with `use_prepare`.

## Anything else: two calls

```text
prepare --path <output> [--path ...] --evidence "<verified provenance>" [--kind compiler-output] [--workspace <repo>]
finish --transaction <id> --manifest-sha256 <hash from prepare>
```

Read `paths` and `excluded` from `prepare` before calling `finish`; its `next`
field holds the exact finish command. If nothing is eligible, `next` is a
`discard`. Kinds: `temporary` (default), `compiler-output`, `package-cache`,
`browser-artifact`, `media-intermediate`, `test-output`, `generated-report`,
`explicit-generated-output`, `disposable-repository`.

## Core rules

- Place scratch under an exact task folder in `D:/Temp` or `E:/Temp` from the start.
  Maintained source, deliverables, installed runtimes and helper state are not scratch.
- Never delete source to "clean up". `git_tracked` exclusions are preserved source;
  report them and proceed with the eligible members. Removing tracked source is a
  normal reviewed Git change, not a cleanup ticket.
- Cleanup never takes the Gradle build gate and never stops another build. Skip
  outputs a running build still uses.
- `target_busy` means an overlapping operation holds the root: check lock-free
  `status`, then retry. `partially_applied` (locked files) is retried with the same
  `finish` command; do not report completion while it remains.
- A policy-denied deletion is reported, never bypassed with another shell or tool.
- Abandon an unused snapshot with `discard --transaction <id> --reason "<why>"`;
  revoke an issued, unfinished ticket with `revoke --ticket <id>`.

## Special cases

Read [Detailed Procedures](references/procedures.md) for step-by-step commands,
existing build leftovers, Git workflow markers, disposable-repository safeguards,
the snapshot/retry contract, credentials and ACLs, helper state and
installation. Whole-checkout retirement: [retirement](references/retirement.md).
CMake `_deps` clones: [generated dependencies](references/generated-dependencies.md).
Android test files and apps: [Android](references/android.md), with the `adb-*` commands.
