# Diagnostics-First UI Skill

## Scope And Authority

Already authorized: create the lightweight behavioral skill and diagnostic-contract
template discussed in this task, validate and install identical copies for Codex
and Claude, and synchronize through this repository's permitted GitHub path.
Do not modify another task's application, connect to devices, enable production
debugging, or change global agent/application settings as part of this delivery.

Public-alternative preflight was completed during the preceding discussion. Narrow
queries found `pablitoarango/android-skills/compose-testing`, inspected as useful
Android testing guidance, not a replacement for this cross-platform behavioral
contract. The earlier broad Browserbase recommendation did not cover the requested
app-owned diagnostics and was rejected. No third-party skill is installed.

## Acceptance Criteria

- U1: Instruction-only `ui-diagnostics-first`, with no helper, package, server,
  generalized automation framework, mandatory instrumentation platform or fake CLI.
  Explicitly describe behavioral guidance, not an enforcement/security boundary.
- U2: Inspect/reuse current diagnostics, then implement only missing app-owned,
  feature-relevant hooks in an authorized application task. Guide remote clicks
  through the real UI event/semantics path, with stable targets, revision checking,
  an observed effect and no speculative mutation retries.
- U3: Export the actual rendered hierarchy as structured JSON/template output:
  runtime/build/device/window provenance, stable IDs, parent relationships, text,
  bounds/units, visibility, interaction state and actions. Do not substitute a
  planned schema, ViewModel state or browser recreation for native rendering.
- U4: Define measured data-loading, layout, item-resolution and ready-state timings,
  a common monotonic origin, milestone/duration distinction and measurement sources.
  Unsupported measurements are null with a limitation, not invented zeroes.
- U5: Distinguish dataset resolution, mounted/visible items and required assets;
  include pending/failure counts and event-driven readiness. Terminal failures and
  off-screen virtualized items must not become fabricated successful rendering.
- U6: Preserve selective visual checks, native/web platform boundaries, accessibility,
  endpoint ownership, debug-only exposure and redaction. Avoid per-edit validation,
  arbitrary sleeps, screenshot polling, new approval gates and diagnostic overgrowth.
- U7: One self-contained canonical bundle with relevant platform guidance and a
  copyable project contract. Structural/resource/example checks, scenario review,
  skills.sh discovery and installed hash parity must pass for all three roots.
  Tests verify artifact contracts, not that an arbitrary agent obeys them.

## Compact Plan

| Stage | Status | Required Outcome |
| --- | --- | --- |
| Skill Delivery | COMPLETE | U1-U7 guidance, template, repo routing, artifact validation and identical installed copies verified. |

No tracked deferrals. Any unsatisfied criterion blocks stage acceptance, not
continued work within the stage. After acceptance, commit, merge through the normal
PR path and verify local main equals remote main before reporting delivery complete.

## Verification Ledger

Structural validator passed for the canonical skill and all installed copies.
Root CLI/layout/isolation checks passed, including resource links, JSON example
accounting, unknown presentation timing, matching action/snapshot revisions and
honest truncated coverage. Local skills.sh discovery reported 23 skills.
SHA-256 parity was verified in Codex, agents and Claude personal roots; global
Codex/Claude settings hashes are unchanged. No task scratch or runtime was created.

Manual scenario review (document interpretation, NOT live application tests):

| Scenario | Required Decision | Guidance Evidence |
| --- | --- | --- |
| Stale build or target revision | Reject stale evidence/target; reacquire the actual tree. Do not repeat an uncertain executed action. | SKILL: Efficient Investigation And Acceptance |
| Data ready but required images pending | Not successfully ready; pending assets remain visible in the report. | SKILL: Resolution accounting / Event-driven readiness |
| 40 dataset items, 8 mounted/visible | Resolve scoped data/assets separately; do not fabricate 40 rendered nodes. | Template: resolution example and timing/readiness contract |
| Click accepted, effect not observed | Acceptance is not completion; retain the same action and observe its real effect. | SKILL: Real actions; template action contract |
| All work terminal, one required item failed | Report failure, not successful readiness or an invented fallback acceptance. | Template: Timing And Readiness Contract |
| Contrast, artwork, occlusion or flashes | Keep targeted real visual evidence; a tree cannot prove these properties. | SKILL: Efficient Investigation And Acceptance |
| Compose virtual clock or unmeasured presentation | Label synthetic timing; unknown presentation remains null with a limitation. | Platform route; template timing example |

Final reconciliation: all criteria satisfied within instruction-only scope. No
Android/browser application was changed or connected, and no agent-enforcement or
performance-improvement claim is made. Publication and remote parity follow this
verified source checkpoint through the normal PR path.
