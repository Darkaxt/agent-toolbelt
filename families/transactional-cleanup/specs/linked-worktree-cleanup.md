# Finished task-owned linked worktrees

User authorization: support ordinary cleanup of the temporary worktree created
for completed work; do not ask for a routine exception to the helper's own gap.
This is the cleanup dependency of the Coordinator migration's ACTIVE Final
delivery stage, not a parallel implementation stage.

Extend the existing disposable-repository registration/ticket workflow to linked
worktrees. Verify the exact task-owned Temp root, normal filesystem identities,
clean tracked/untracked state, real Git top-level and bidirectional Git metadata
binding. Preserve common objects, refs, configuration, other worktrees and locks.
The target commit must remain reachable through a common branch/tag/remote ref.
No backup or stock download is needed. Reject an active consumer or replacement;
do not invent an additional user-permission checkpoint.

Review the worktree and only its derived private administrative directory as
signed exact members. Hash regular members; preserve concurrent edits/new files.
Apply working files first, then the root marker/root, then private registration
metadata only after the original worktree is gone. Never run recursive deletion,
force removal, broad prune, or delete shared refs/objects. Preserve/restore the
Git marker if concurrent new content prevents final root removal. Bind a
helper-created restored marker identity/content to the original ticket with a MAC;
never adopt an unrelated replacement. Keep partial cleanup recoverable and
retain the existing ticket expiry, exact-path locks and bounded traversal.

Acceptance: real disposable linked worktree removal and Git registration
settlement; main/sibling content and refs unchanged; dirty/locked/active and
replaced targets preserved; reviewed edits/new arrivals preserved; post-marker
arrival retains Git association; existing standalone and ordinary cleanup stay
compatible. Validate source and installed Codex/shared/Claude bundles and runtime,
then clean the actual completed publication worktree and publish verified source.
