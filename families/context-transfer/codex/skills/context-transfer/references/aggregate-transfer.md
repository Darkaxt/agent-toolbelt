# Consolidate Several Chats Into One Activity

Read this for multiple selected source chats whose former distinctions (research,
implementation, tooling, operations) no longer need separate working contexts.
Keep the single-source preservation, activity, recall and retirement contracts in
SKILL.md. This mode coordinates them; it does not import/merge application rows,
rewrite lineage, resume sources, send prompts to other chats or introduce another
runtime. All commands below use the installed wrapper from SKILL.md.

## Select And Inventory The Group

Resolve the exact full source IDs and one independent destination ID through
supported task tools. Record the user's shared activity/objective, selected IDs
and exclusions in a private group ledger under the reviewed non-C recovery root.
Related title, cwd or repository alone is not selection authority. If the user
has not identified the sources sufficiently, resolve that selection before any
mutation; do not infer that every chat about the repository belongs to the group.
Use an independent normal destination, never a fork of any selected source or
its ancestors. A current chat can own the transfer only if inspection verifies
its independence from the entire group; never select the destination for deletion.

For each selected source, run `inspect` with the same destination and separate
explicit manifest/output paths, then `catalog` with bounded limits. Inspect every
source's child tree, all resumed segments, database scope, inherited owners and
surviving history dependents. Use bounded `read_thread` reads to resolve ambiguity
and verify current repository/artifact state. Do not ask source chats to summarize
themselves or paste all their transcripts into the destination.

Maintain one owner map alongside the source map:

| Map | Required information |
| --- | --- |
| Selected source | Exact ID, former purpose, inspected manifest/hash, evidence/catalog references, remaining objectives and retirement authority |
| History owner | Exact ID, sources relying on it, all segment identities/hashes, database table/ID scope, verified archive and receipt references |
| Protected dependent | Exact unselected ID and which owner it still needs; unknown activity/lineage remains unresolved |

Read [Schedule Reconciliation](schedules.md) and add associated automations to
the group ledger. Check each source, child and necessary ancestor's direct
bindings and explicit contextual references. An automation shared by several
sources has one exact identity record with all source links, not one new copy
per source. Scheduling is a continuation dependency, not conversation history.

A shared ancestor needs one verified preservation record referenced by all
dependent sources. A selected source already covered inside another selected
source's child archive can reuse that verified coverage; still inspect it and
produce its own objective mapping and acceptance. Reuse requires matching exact
owner IDs, every segment/hash and scoped database coverage, not merely a common
directory, title or archive filename. Record overlap rather than silently dropping
a source or counting copied archives as distinct requirements. If inspected
snapshots disagree, refresh the affected inventory and evidence.

Capture fresh owning-app inactivity evidence and reconcile each complete tree
before packaging. Necessary ancestors are separately inspected/preserved unless
their complete evidence is already covered by a verified selected tree archive.
For inactive owners blocked only by surviving history references, use
`pack --preserve-referenced-history`; these archives remain preservation-only.
Other blockers stay binding. A provisional group handoff may be written while
blocked, but it cannot authorize retirement or be presented as accepted migration.

## Build One Current Working Context

Use one bounded CONTEXT_TRANSFER.md with the exact sections required by SKILL.md.
Organize it around the shared activity and its current state, not one chronological
summary per source. Keep source IDs and exact evidence references with each
material conclusion so the destination can retrieve the underlying evidence.

In the group ledger, map every still-required source objective and acceptance
criterion to a consolidated requirement:

| Source requirement and evidence | Consolidated requirement | Current state and evidence | Owning stage / exact next action |
| --- | --- | --- | --- |
| Source A: catalogue research; Source B: catalogue implementation | Catalogue behavior required by the authoritative specification | Distinguish researched, implemented, integrated and verified | One named stage and its remaining acceptance work |

Equivalent requirements can share a target, but keep every originating reference
and preserve the full acceptance criteria. Keep useful decision reasons and failed
approaches. Clearly label historical evidence, cancelled work and optional ideas;
merging topics does not turn them into active implementation requirements.

Reconcile different branches, deployments, specifications and decisions against
live state and actual user authority. Newer timestamps or a worker's claim do not
automatically supersede a requirement. Record an authorized supersession with
its evidence and target requirement. An unresolved behavior/authority conflict,
unmapped required objective or missing necessary evidence blocks group acceptance.
Do not silently choose the easiest version, delete acceptance criteria or mark
conflicting work complete. Ask only when an essential user decision remains.

Derive one dependency-aware continuation order. Preserve all remaining blockers
and named deferrals and assign ownership within the consolidated plan. At most
one implementation stage is ACTIVE; ordinary implementable gaps keep it ACTIVE.
Other source work remains explicitly scheduled or genuinely parked under the
standing stage rules. Choosing the next stage does not discard other requirements.
Migration completion is distinct from completing the underlying activity.

In Database Evidence And Recall References, list every selected source/child and
necessary inherited owner's exact ID, archive/receipt references and important
database-only facts. Include the group ledger path and bounded `read-database`
commands. Explain that deleted rows/offloaded files do not provide automatic
normal recall fallback. Do not claim full source understanding from sampled
catalogs; record truncation and known coverage limits separately from complete
archive preservation.

Include schedule identities, source links, intended disposition, preserved
definition references and any unresolved authorization/target dependency in the
appropriate next-actions, blockers and recovery-reference sections. Preserve
necessary distinctions between schedules even when the chats' former purposes
are consolidated; consolidation alone does not authorize merging jobs or prompts.

## Preserve And Accept Every Source

Freeze the combined handoff using stable group-ledger and per-owner receipt paths
under the reviewed recovery root. The ledger records the exact resulting archive
paths and hashes; update that ledger without silently editing the accepted handoff.
Use the same handoff file for every selected source and ancestor archive.

For each selected source manifest, run:

```powershell
python <installed-wrapper> validate-handoff --manifest <source-inspection.json> --handoff <shared-CONTEXT_TRANSFER.md>
```

The union of all child IDs must appear in Child-Agent Contribution Map, each
starting its line with the exact ID and a colon. A child seen through overlapping
trees has one contribution record with all relevant source references. Include
all inherited owners in Database Evidence And Recall References. Successful
validation for one source does not validate the others.

Pack/verify every required owner using the existing commands and activity gates.
Inspect archive integrity, database digests, exact scope, source-snapshot policy,
extracted rollout hashes and absence of transient staging. Perform bounded offline
database read-back for each required owner that has database evidence, checking
query coverage/truncation; a zero-match query is not proof of missing history.
Keep independent archive and database references for recovery/recall. Never change
or handcraft manifests to hide missing sources, children or surviving references.

Write one `agent_toolbelt_context_transfer.destination_acceptance.v1` file per
selected source. Each uses its own exact source ID and inspected manifest, the
same destination ID and shared handoff SHA-256, and source-relevant mapped
requirements/evidence. Map a source with no remaining implementation objective
explicitly to its retained decision/evidence contribution; do not invent work to
fill a list. Record uncertainties honestly and keep `critical_unmapped_objectives`
empty only after semantic reconciliation. Run `validate-acceptance` separately
for every selected source using its matching file.

The group ledger records selected IDs, owner coverage, source-specific acceptance
paths/hashes and validation results, the shared handoff hash, unresolved conflicts,
unmapped objectives and the exact first continuation action. The destination may
declare the group accepted only when:

- Every selected source and necessary owner is accounted for with verified
  preservation, including database and all rollout segments.
- Every required objective has a supported consolidated mapping; no critical
  conflict or unmapped objective remains.
- Every source acceptance validates against the same destination and handoff.
- Current repository/artifact evidence supports the continuation state and the
  destination understands the recorded recall and uncertainty limits.
- Associated schedules are inventoried with an explicit disposition, evidence
  and authority; any pending authorized change is recorded as a retirement blocker.

The CLI checks handoff structure and acceptance bindings; it does not infer the
meaning of objectives or prove the group ledger complete. The destination owns
that reconciliation. A successful CLI call is not group-completion evidence by
itself. If the shared handoff changes, refresh all affected acceptance bindings
and archive handoff bindings before retirement; do not mix hashes from revisions.

## Retire Only Eligible Selected Chats

Require complete group acceptance before starting group retirement. Acceptance
does not grant deletion authority; reuse existing source-specific user authority
and never extend it to a newly discovered ancestor, child or unselected dependent.
Use SKILL.md's archive/ticket lifecycle for rollout offload, or thread-cleanup's
supported application deletion when permanent conversation retirement is requested.
Do not perform both as duplicate removal or treat rollout offload as database purge.

Order selected leaves before selected ancestors, including dependencies between
selected roots. Immediately before each deletion, refresh owning-app inactivity,
reconcile and verify the associated schedule dispositions,
re-plan the exact source after earlier removals, review its new inventory/hash and
apply only that source's permitted operation. Preservation-only receipts cannot
issue deletion tickets. Unselected forks keep their required owner non-deletable;
retain it and report the exact dependency without bypassing the application guard.

After each result, record actual database/file/recall residuals and refresh the
remaining dependency plan. On partial failure, preserve completed receipts and
the precise remaining source IDs, blocker and next action. Do not rerun completed
deletions, start a replacement operation while the original runs, or label the
whole group retired while required selected sources remain. Group handoff
acceptance and retirement completion are separate recorded outcomes.

Retained recovery archives and exports remain governed by their explicit retention
authority. This mode adds no age-based purge, schedule or automatic archive expiry.
