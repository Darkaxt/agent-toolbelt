# Aggregate Context Transfer

## Scope and authority

The user authorized improving context-transfer so several selected chats with
different purposes within one activity can become one independent working chat.
This is a skill workflow extension using the existing single-source CLI; it does
not merge live databases or create a new migration subsystem. Existing permission,
activity, preservation and retirement gates remain unchanged. No live migration,
thread deletion, archive expiry or live schedule change is part of implementing
this update. The user's subsequent explicit answer authorizes adding schedule
inventory/reconciliation guidance to this skill update for both transfer modes.
Skill deployment and repository synchronization follow this repository's existing
delivery path. No new third-party skill is installed.

## Requirements and acceptance criteria

- A1: Discover aggregate mode from the skill entrypoint and UI metadata. Keep
  normal single-source transfer available and route aggregate detail to one
  supporting reference. Explain that commands still take one source at a time.
- A2: Resolve the exact selected source set and independent destination, inspect
  every source tree and inherited owner, and retain a source/evidence map.
  Shared ancestors and overlapping trees cannot disappear or be counted as
  independent completion; reuse verified coverage only when owner identities,
  segments and database scope match. Unselected dependents stay protected.
- A3: Produce one current activity handoff, not concatenated transcripts. Map
  every required source objective/acceptance criterion into a consolidated
  requirement with evidence, current state and next action. Equivalent items
  may share a target while retaining all source references. Supersession needs
  actual authority; unresolved conflicts and unmapped objectives block acceptance.
  Historical suggestions/cancelled work do not become new active requirements.
  One implementation stage may be ACTIVE; other work is explicitly planned or
  genuinely parked according to standing rules, not declared completed.
- A4: Validate the shared handoff against every selected source manifest; issue
  source-specific destination acceptance files bound to the same handoff hash.
  Preserve/verify every required history owner, database evidence and rollout
  segment, including bounded offline read-back, before accepting the group.
  Record all receipts and exact archive references in one compact group ledger.
  Document that CLI validators check structure/bindings, not semantic completeness.
- A5: Source-specific retirement follows complete group acceptance and explicit
  authority, leaf-first with fresh status and re-planning after each deletion.
  Preservation-only archives never become deletion tickets. Partial failure
  leaves a precise resumable ledger and protects every not-yet-eligible source;
  migration or skill-edit authority alone cannot authorize deletion/expiry.
- A6: Demonstrate the documented workflow on isolated real archive/database
  fixtures with two differently purposed roots, a child and shared ancestor,
  while preserving an unselected dependent. Exercise common-handoff acceptance,
  missing-child and wrong-source/changed-handoff rejection. No real chats are
  mutated by verification. Deploy identical complete bundles to the existing
  Codex/agents installations, verify the selected runtime supports the workflow,
  validate installed files and clean task scratch through transactional-cleanup.
  Commit and synchronize the completed change without unrelated changes.
- A7: Before single-source or aggregate retirement, inventory associated scheduled
  tasks/automations through supported tools and local metadata as applicable.
  Record exact identity, source linkage, prompt/scope, target, schedule/timezone,
  status and notification policy with an explicit keep/retarget/pause/delete
  disposition and authority. Preserve private schedule evidence in the handoff's
  recovery records. Unresolved source-target dependencies block retirement.
  Use supported automation tooling for separately authorized changes and verify
  read-back; skill editing itself changes no schedules, target bindings or prompts.

## Execution and reconciliation

Single implementation stage: Aggregate migration skill upgrade — COMPLETE.
Mapped requirements: A1–A7. Stage acceptance covers the integrated instructions,
fixture workflow, focused verification, installed parity and scratch cleanup.
Commit and remote synchronization are the required final delivery actions after
verified stage closure; their exact result is reported at delivery.

Reconciliation:
- A1: v0.3.0 entrypoint/UI and family/root discovery documentation expose the
  aggregate mode; detailed procedures are linked references. Single-source CLI
  behavior and package source are unchanged.
- A2–A5: Aggregate guidance specifies exact group selection, owner overlap,
  independent destination, requirement/provenance mapping, semantic conflict
  resolution, one ACTIVE stage, common handoff hash, every-source acceptance,
  archive/database coverage and separately authorized dependency-ordered retirement.
  No acceptance/deletion claim follows solely from CLI success.
- A6: The real CLI fixture passed against both the repository wrapper and the
  deployed Codex wrapper/selected private runtime. It preserves two source
  purposes, a child, shared ancestor/database-only evidence and an unselected
  dependent; it rejects wrong-source acceptance, missing-child coverage and a
  changed accepted handoff. Fixture databases remain byte-identical. Focused
  handoff/skill checks and repository layout checks passed. Both installed
  Codex/agents bundles match source hashes, official skill validators pass and
  local Markdown reference links resolve. Selected runtime Python/package
  identity was verified; no runtime refresh is needed for instruction-only changes.
- A7: Both modes route to schedule reconciliation. Explicit source bindings,
  contextual dependencies and independent jobs have distinct dispositions;
  definitions are separately preserved because the archive helper does not copy
  them. Unsupported retargeting or outstanding execution blocks retirement;
  supported authorized changes require full-field preservation and read-back.
  Manual scenario review covered direct heartbeat retargeting, independent cron
  preservation, one shared automation with multiple source links, paused jobs
  retaining old bindings and an in-flight execution. No live schedule was changed
  or live retargeting represented as tested. A bounded metadata check found no
  direct Codex automation targets for the three previously retired source IDs;
  this was not a claim about every scheduler/contextual reference.

Scratch cleanup completed through reviewed transactional-cleanup; the exact
task-owned scratch root is absent. Retained source and installed skills are
intentional outputs. No blockers or required deferrals remain in the stage.
Stage/final refactoring assessment: existing single-source commands already
support the verified workflow; a new multi-root database subsystem would add
unnecessary machinery. No required consolidation/refactoring was identified.

Discovery: the first broad scout was capped and returned generic Codex wrappers.
A second narrow search was uncapped and inspected
gord1y/countersign-skills/context-transfer. Its useful emphasis is current state,
decision reasons and a self-contained handoff; it does not cover aggregate
ownership, archives, database evidence or retirement. Retain the local workflow.
