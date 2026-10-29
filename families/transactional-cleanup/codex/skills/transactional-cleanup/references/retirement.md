# Obsolete Checkout Retirement Evidence

Use only after an explicit user retirement request, not for ordinary cleanup of a
maintained repository. Keep this compact JSON outside the retired checkout:

```json
{
  "version": 1,
  "repository": "C:\\path\\obsolete-checkout",
  "authorization": "Actual user request authorizing this exact checkout retirement",
  "recovery_repository": "E:\\Recovery\\project.git",
  "recovery_instructions": "git clone E:\\Recovery\\project.git D:\\Projects\\restored-project; inspect preserved refs for any additional branches",
  "consumer_review": {
    "checked_at": "Actual ISO timestamp of these checks",
    "ownership": "Actual checkout ownership and retirement evidence",
    "schedulers_services": "Actual task/service reference inspection and results",
    "dependencies": "Actual project/worktree/build/release dependency inspection and results",
    "active_consumers": []
  }
}
```

Do not copy the placeholder attestations as evidence. The recovery repository must
already exist independently and contain HEAD, all refs and reflog-reachable commits,
with intact object closure and matching original named refs. Reflog-only commits
must remain reachable through explicit recovery refs so Git pruning cannot remove
them. A bare mirror may omit those commits: preserve them deliberately if required.
No recovery repository is created automatically.

```text
begin --workspace <separate-current-workspace> --scan-root <obsolete-checkout>
register --transaction <id> --path <obsolete-checkout> --kind retired-repository --regenerated --retirement-evidence <external-json> --confirm-retire-repository <obsolete-checkout> --evidence "<actual retirement purpose>"
review --transaction <id>
inspect --transaction <id> --offset 0 --limit 1000
ticket --transaction <id> --manifest-sha256 <inspected-review-hash>
apply --ticket <id> --dry-run
apply --ticket <id>
```

Retirement rejects dirty/ignored/untracked content, redirected paths, additional
worktrees, linked worktrees, submodules, shallow/alternate recovery storage and
visible process references. Preserve or resolve these conditions rather than
forcing them away. Concurrent edits/new files survive exact-member deletion.
This is not an execution-policy bypass, and not blanket source-deletion authority.
