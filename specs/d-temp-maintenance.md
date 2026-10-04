# D-Temp Maintenance Specification

Authorization: create the focused skill using the existing maintenance/deletion
infrastructure; deploy the personal skill for Codex and Claude and sync the source
as required by the standing task history. This is not a live bulk cleanup request.

## Requirements

- R1: On-demand active maintenance focused on D:/Temp agent-generated leftovers.
  Inventory is a means to verified action, not a passive monitor or age-based purge.
- R2: Start with shallow discovery and indexed size evidence when available. Deep
  inspection, hashing and cleanup snapshots use exact selected roots only. State
  incomplete coverage and inclusive sizes without treating estimates as receipts.
- R3: Resolve provenance, current consumers, repository/worktree state and recovery
  needs. Dirty, unpushed, unique, active or ambiguous work stays protected. A clean
  clone, old folder or stopped task is not sufficient deletion authority.
- R4: Separate generated output, disposable validation clones, linked worktrees,
  persistent dependencies, deliverables and unknown content. Apply the existing
  transactional-cleanup or appropriate native lifecycle, never a new deletion engine.
- R5: Inspect exact manifests before ticket/application; preserve newly created
  files, diagnose partial/database/ACL failures and never bypass policy rejection.
  Cleanup neither joins the Gradle queue nor holds its build mutex.
- R6: Coordinate only verified existing owners when needed, without resurrecting
  work or broadcasting. Record exact evidence, action, receipt, residuals and
  recurrence prevention in a private ledger outside the cleanup root/source repo.
  User clarification: finish the named current round, then sweep all project-owned
  temporary folders/files, retain required work in GitHub and remove disposable
  leftovers. Do not keep reproducible clones solely because they are repositories;
  document concrete local-only retention exceptions without publishing secrets.
- R7: Package one canonical cross-agent instruction-only skill with supporting
  action/ledger references, integrate skills discovery, validate and deploy identical
  copies to Codex, agents and Claude personal roots. No scheduler, fake runtime,
  symlink deployment or sensitive local state in Git.

## Compact Stages

| Stage | Requirements | Acceptance | Status |
| --- | --- | --- | --- |
| 1: Canonical operating contract | R1-R6 | Skill and references express executable bounded cleanup routes, retention decisions and failure handling; scenario reconciliation and frontmatter validation pass | COMPLETE |
| 2: Repository integration | R7 | Instruction-only layout, discovery and documentation checks pass without adding a runtime package | COMPLETE |
| 3: Deployment and verification | R3-R7 | Installed copies match canonical bytes; an isolated disposable-output trial deletes only reviewed members and preserves non-target source; source committed and synced | ACTIVE |

No blockers or tracked deferrals at initialization. Existing D:/Temp contents are
not test fixtures. The verification trial creates only task-owned disposable data.

## Discovery

Broad scout results were capped and its top recommendation had no inspectable
SKILL.md; that is not a trustworthy replacement. A narrower exact-name and
transactional-cleanup scout returned no meaningful public alternative and no
capped queries. Local c-drive-maintenance and transactional-cleanup provide the
mechanics; this skill adds the agent-output provenance and repository retirement
decision workflow without duplicating their helpers.

## Stage 1 Reconciliation

Frontmatter validation passed. Reviewed operating scenarios against original intent:
generated output uses exact scan roots and tickets; a clean clone with unique
work is retained until source is preserved; a reproducible validation clone uses
the helper's tracked-file exception rather than remaining forever; an active owner
receives an end-of-round sweep rather than interruption; a mixed tree is split so
unknown/retained children do not block unrelated proven output. Missing helper,
policy rejection and partial cleanup are reported, not bypassed. No required
deferrals or blockers remain for this stage.

## Stage 2 Reconciliation

Focused monorepo layout, isolation and CLI wiring passed. Local skills.sh discovery
lists all 20 public skills including d-temp-maintenance; frontmatter/path checks
passed. The new family is instruction-only, with one canonical bundle and no new
runtime dependencies or deletion engine. No blockers or tracked deferrals remain.

## Stage 3 Verification Before Source Delivery

Identical canonical bytes deployed and frontmatter validated in Codex, agents and
Claude personal roots. An isolated live trial using the installed Claude cleanup
wrapper reviewed an explicit output root, issued a ticket, dry-ran and applied it.
The two fixture files and their output directories were removed; the non-target
source sentinel remained. A separate reviewed ticket then removed the expendable
fixture remainder. Both tickets reached applied with no residuals. No existing
project folders or live work were removed, and no build/mutex/scheduler was used.

These checks prove the installed instructions' cleanup route and bounded helper
integration, not universal agent reasoning or complete host consumer coverage.
Owner sweep decisions were reconciled through the Stage 1 scenarios; no requests
were dispatched to DualDex/DualSouls during this skill-creation task. Source commit
and synchronization remain the final Stage 3 delivery requirements.
