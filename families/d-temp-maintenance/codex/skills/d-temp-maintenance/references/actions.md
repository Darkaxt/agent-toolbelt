# Target Decisions And Exact Cleanup Routes

Resolve all actual paths and ancestors before executing a route. Do not traverse
junctions/symlinks. A filename, zero-byte marker or location alone is not authority.

| Target | Evidence required | Action / preservation |
| --- | --- | --- |
| Build output, temporary extraction, disposable downloaded inputs, captures, logs | Creating command/task, reproducible source if needed, no active consumer and no remaining verification/recovery need | Register exact generated subtree through transactional-cleanup. Retain user inputs, requested APKs/reports and required diagnostic evidence even if generated. Delete only reviewed members. |
| Standalone validation clone | Explicit temporary validation provenance; clean status including untracked files; no unique/unpushed branch/tag commits, stashes, local-only objects needed for recovery, linked worktrees or consumers | Use helper's disposable-repository authority on that exact clone only. A clean clone alone is insufficient. Needed fixes must reach the authoritative repository and have retention/sync proof before removal. |
| Linked Git worktree | Actual Git common directory and worktree list; owner inactivity; clean status; all commits and task evidence retained at the authoritative destination | Use Git's worktree lifecycle from its owning repository without force. Never generic disposable-repository authority for a linked worktree or delete its main repository metadata. Policy rejection stops removal. |
| Dirty/unpushed checkout, patch, test corpus, handoff or recovery archive | Explicit retention/removal decision and verifiable replacement/recovery if applicable | Preserve; coordinate exact owner. Do not auto-commit, push or force-delete another task's work to make it removable. |
| JDK, SDK, NDK, compiler, browser profile or running service under Temp | Installed/runtime references, environment/config consumers, active processes, offline requirements | Not ordinary litter. Native lifecycle or separately authorized verified relocation; account sessions/signing material are never generic cache. |
| Hardlinks, symlinks, junctions | Exact link name/object, creator and disposable provenance, no consumer | Read specialized transactional-cleanup support; allow only reviewed link names/leaf objects when authorized. No traversal, target removal or link breaking; logical bytes may not equal physical reclaimed bytes. |
| Mixed / unknown / unreadable tree | Partial target classification and explicit coverage gaps | Clean independently proven output children, preserve the rest. Do not sweep the containing root. |

## Generated Output

Set `$cleanup` to the **installed** transactional-cleanup wrapper's absolute path.
Use the owning project as workspace where available; a non-Git workspace is
supported. `$target` is an exact disposable child, never all D:/Temp. Variables
below are real operator inputs/results, not text to copy literally.

```powershell
python -B $cleanup begin --workspace $workspace --scan-root $target
python -B $cleanup register --transaction $transaction --path $target --kind explicit-generated-output --regenerated --evidence $verifiedProvenance
python -B $cleanup review --transaction $transaction
python -B $cleanup inspect --transaction $transaction --offset 0 --limit 100
# Page further when needed; inspect exclusions as well as candidates.
python -B $cleanup ticket --transaction $transaction --manifest-sha256 $reviewedHash
python -B $cleanup apply --ticket $ticket --dry-run
# Recheck consumers, then apply this same ticket, not a new ticket.
python -B $cleanup apply --ticket $ticket
python -B $cleanup status --transaction $transaction
```

Use multiple explicit scan roots for a bounded batch, then register each exact
target. Disjoint targets can run concurrently under the helper's own locks. Do
not hold a shared build resource while manifest checks run. If `target_busy` is
returned, identify the overlapping operation and wait for completion; do not
cancel its owner, steal locks or invent a timeout.

## Disposable Validation Clone

Only after the clone evidence above passes, begin with the clone as an exact
explicit scan root. Register its root using:

```powershell
python -B $cleanup register --transaction $transaction --path $clone --kind disposable-repository --regenerated --allow-disposable-repository --evidence $verifiedCloneProvenance
```

Then review/inspect/ticket/apply exactly as above. The helper requires a standalone
Git top-level with an internal ordinary `.git` directory beneath a recognized
temporary root. It rejects active workspace roots, linked worktrees and symlinked
repositories. Keep that protection; do not edit `.git` to imitate a disposable
clone. Empty cache markers use the helper's existing generated-output rules.

## Repository And Consumer Evidence

Use exact-path `git status --porcelain=v1 --untracked-files=all`, `git worktree
list --porcelain`, branch/upstream state and `git stash list` as applicable. Check
local-only branch/tag commits, not just the current branch. Remote-tracking refs
can be stale: verify authoritative remote/object retention before deleting a clone
whose recovery depends on remote state. No implicit fetch result or clean status
is universal proof that all valuable work has been preserved.

Check current command lines/parent trees and build/service/task ownership for the
exact project/output, not merely directory age or low CPU. Path-based process
inspection has coverage limits and does not enumerate every open handle. Ambiguity
about a consumer blocks that target, not every unrelated target in Temp.

## Partial Or Rejected Cleanup

Record the helper failure kind and exact residual names. Use its status/inspect
and current ACL/handle evidence. No process killing, ownership takeover, link
conversion, direct Remove-Item fallback or ticket revocation solely to hide a
failure. A revoked ticket needs a fresh review; a still-valid partial ticket may
be retried after the diagnosed condition is resolved. Preserve new/replaced files.
