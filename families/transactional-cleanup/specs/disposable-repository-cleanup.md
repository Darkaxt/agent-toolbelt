# Disposable Repository Cleanup Specification

## Objective

Allow transactional cleanup to remove exact, reviewed members of a verified
temporary standalone Git clone used for validation or testing, while preserving
the default protection for repositories and Git-tracked files everywhere else.

## Required Contract

- Add `disposable-repository` as an artifact kind and
  `register --allow-disposable-repository` as explicit authority.
- Authority is valid only when all of these conditions hold:
  - the registration path is an existing standalone Git working-tree root;
  - `.git` is a real directory inside that root, not a linked-worktree file or
    reparse point;
  - Git reports that exact path as the top-level working tree;
  - the path is a strict descendant of a recognized Windows Temp root;
  - the path is an exact transaction scan root, not merely beneath a broader
    scanned parent;
  - the path is not the transaction workspace;
  - kind is `disposable-repository`, `--regenerated` is present, and concrete
    provenance is supplied.
- Review must enumerate the repository root, tracked/untracked files, and local
  `.git` metadata without following reparse targets. Every candidate remains
  bound to its reviewed Windows file identity and the signed manifest.
- Apply may bypass only `repository_root`, `filesystem_or_repository_metadata`,
  and `git_tracked` for members under the exact authorized root. All other
  protections remain effective.
- Before the first destructive apply, revalidate the Git top-level and root
  identity. Retries after a partial apply may rely on the preserved root identity
  because reviewed `.git` entries may already have been removed.
- Concurrent new files, replacement objects, hard links, and leaf reparse points
  retain the existing snapshot and explicit-authority behavior. No recursive
  deletion is introduced.

## Acceptance Criteria

1. A verified disposable validation clone can be reviewed, ticketed, and removed
   through the normal two-step ticket workflow, including tracked files and
   `.git` metadata.
2. The same repository remains protected without the new explicit authority.
3. Authority is rejected for a broader scan root, a workspace root, a non-Temp
   path, a linked worktree, invalid Git state, or missing kind/regeneration gates.
4. A file created after review survives and leaves its directory nonempty.
5. Replaced reviewed objects survive through existing identity checks.
6. Existing repository, tracked-file, critical-root, link, concurrency, and
   ticket-integrity tests remain green.
7. Codex, agents, and Claude installations expose the documented workflow and
   the deployed runtime successfully removes at least one real disposable
   validation clone when such a residue is available.
