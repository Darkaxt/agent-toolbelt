---
name: ui-diagnostics-first
description: Guide app-owned UI debugging hooks, remote control actions, rendered hierarchy exports and measured readiness instead of repeated screenshot polling. Use when implementing, debugging or validating interactive UI, especially Android, with source or existing diagnostic access.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Instruction-only guidance for Codex and Claude; application-specific instrumentation and authorized runtime access are separate.
---

# Diagnostics-First UI

Make the UI explain its state and behavior. Prefer structured evidence over a loop
of click, screenshot, visual guess and repeat. This skill is behavioral guidance,
not an enforcement boundary or a universal automation helper. It installs no bridge;
project tests can verify a diagnostic contract only after that project implements it.

## Inspect Before Adding Hooks

Identify the actual UI framework, build, endpoint/device and current feature's
acceptance risks. Reuse existing debug actions, test semantics, inspectors and state
events. Select the applicable [platform route](references/platform-routing.md).
Do not enable remote debugging, attach to an arbitrary device/profile, rebuild a
production app or implement a second browser UI merely to satisfy this skill.

For an authorized source change, add only missing hooks needed to understand and
validate the current feature, alongside that feature's cohesive implementation.
Adapt the [project diagnostic contract](templates/UI_DIAGNOSTICS_CONTRACT.md) into
the project's existing specification/test notes; don't create a new document for
every screen or small edit. Reuse the project's transport and test stack.

Do not build a general RPC platform, driver library, permanent daemon or exhaustive
telemetry system before the first required workflow. A read-only snapshot plus a
few real UI actions and readiness events may be enough. If instrumentation is not
authorized/available, use supported inspectors and report the evidence limits;
don't pretend the bridge exists or invent invocation flags.

## Required Diagnostic Capabilities

- **Real actions:** target stable control IDs and invoke the same event/semantics
  path as user interaction. Run on the framework's UI dispatcher. Do not bypass
  listeners, navigation, validation or lifecycle by directly calling backend or
  ViewModel operations and presenting that as a button click. Return the action ID,
  accepted/completed/failed status, before/after revisions and observed effect.
- **Rendered template output:** export a structured JSON tree from the actual
  instantiated/measured UI. Include runtime/build/device/window provenance, units,
  stable IDs, parents, roles, text, bounds, visibility, enabled/selected/focused
  states and available actions. Distinguish app-state diagnostics from renderer
  evidence; planned component definitions are not a rendered snapshot. Report
  coverage gaps, truncation, missing properties and the snapshot revision.
- **Measured timings:** return data loading, layout, required item/asset resolution
  and ready-state milestones from a declared monotonic origin. Distinguish elapsed
  milestones from phase durations, cached work and reused views. Name each actual
  observation boundary. A frame callback is not proof that pixels were presented;
  unsupported measurements are null plus a reason, never an invented zero. Keep
  host transport latency separate and never present synthetic test-clock advances
  as real application loading/performance measurements.
- **Resolution accounting:** identify the data scope and report expected, resolved,
  pending and failed counts. Separate the full dataset from mounted/visible nodes
  and their required images/metadata. Virtualization is not missing rendering, and
  resolved data is not proof that off-screen items were laid out or painted.
- **Event-driven readiness:** complete against a named feature-specific predicate,
  including required data, current layout and visible content/assets. A click
  acknowledgment, empty request queue, first layout or terminal error alone is not
  successful readiness. Ignore unrelated ongoing analytics/animations rather than
  requiring the whole application/network to become idle. Report failures as
  failures, even when all operations have terminated.

## Efficient Investigation And Acceptance

During implementation, use a diagnostic only to answer a concrete question. Once
the complete feature is integrated, execute its required real workflow and collect
the action result, rendered snapshot, timings, counts and relevant errors together.
Do not turn every hook or edit into a separate build/device/validation checkpoint.

Reuse a persistent authorized session and wait for the original operation's
completion/state event. Do not resubmit a click because its result is still pending,
use arbitrary sleeps or repeatedly capture screenshots to guess completion. An
externally mandated wait timeout reports incomplete observation; it does not prove
failure or authorize repeating a mutating action.

Capture on demand or at relevant action transitions, not by continuously dumping
the entire UI tree on every frame. Keep instrumentation bounded and disable unused
observation. Diagnostics must not become the new performance or disk-space problem.

Verify runtime identity and freshness before acting and before accepting evidence.
Reject stale targets/revisions and reacquire the actual tree. Rejected-before-dispatch
is different from an uncertain action that might already have executed. Do not
automatically retry the latter. Remote buttons retain their ordinary authorization:
a debugging session is not consent to send mail, buy, delete or change accounts.

Use snapshots to check required controls, state transitions, measured viewport fit,
scroll reachability, touch/focus behavior and spec-defined layout relationships.
Do not classify all overlapping bounds as defects: dialogs, overlays and nesting
can be intentional. Visibility flags alone do not prove lack of occlusion.

Retain targeted screenshots or short recordings for typography, colors/contrast,
artwork, actual clipping/occlusion, animation flashes and final visual hierarchy.
Inspect representative states at the actual target sizes, not a stale preview.
Structured diagnostics reduce visual guessing; they do not replace visual judgment.

Report proven behavior, applicable timings, unresolved required items and the
remaining visual/measurement limits. Missing evidence for a required criterion
blocks its acceptance; implementable gaps remain active work under standing stage
rules. Don't weaken the criterion or substitute a mock for required integration.

## Exposure And Evidence Hygiene

Keep new action hooks debug/test-only and absent or disabled in release builds.
Use app-private/local transports; for Android, prefer an explicit authorized ADB
forward/session rather than a remotely reachable listener. Restrict actions to the
debug contract, bind the intended instance and reject arbitrary code/command input.
Use session authentication when exposing a new endpoint; loopback alone is not an
authorization mechanism. Preserve accessibility and existing device/session leases.

Collect only feature-relevant data. Redact credentials and private content, bound
tree/log output, and mark incomplete coverage. Store expendable captures/dumps in
exact task-owned scratch, then use the applicable cleanup workflow. No new global
settings, persistent monitor or automatic external evidence upload is implied.
