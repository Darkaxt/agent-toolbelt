# UI Diagnostic Contract: <Current Feature>

Adapt this template into existing project notes. The names below are logical
capabilities, NOT a shipped CLI or mandatory RPC protocol. Keep only fields that
serve the current feature; retain explicit unknowns instead of fabricating evidence.

## Binding And Scope

- Feature/specification criteria: <IDs and the complete workflow being verified>.
- Actual renderer and route: <framework; existing inspector/test/debug mechanism>.
- Runtime binding: <app/package, build fingerprint, instance, device, window/display>.
- Viewport: <measured width/height, units, density/font scale, insets, scroll scope>.
- Allowed actions: <real UI controls; ordinary mutation authority still applies>.
- Debug exposure: <debug/test-only, local transport, session auth, release exclusion>.
- Evidence limits/redaction: <unsupported nodes, private data, pagination/truncation>.

## Action And Snapshot Contract

An action request identifies the instance, stable target, action ID and expected
screen/data revision. Validate against the current tree before dispatch. Reject
stale or unavailable targets without execution; dispatch through the real UI event
path, not a backend shortcut. Acknowledgment is not completion. Associate the
observed effect and resulting snapshot with that same action and revision.

A snapshot exports actual instantiated/measured nodes: stable ID, parent ID, role,
text, bounds and units, visibility, enabled/selected/focused state and actions.
Include provenance and coverage. When a property is not observable, record null
and a limitation. Do not substitute a planned layout or model object graph.

## Timing And Readiness Contract

- Origin: <a named action/navigation dispatch event on one monotonic clock>.
- Data ready: <required query/load work completed for this data generation>.
- First layout: <actual first measured layout boundary for the resulting view>.
- Items resolved: <required metadata and assets resolved within explicit scopes>.
- Ready state/frame: <required predicate; exact observable render/frame boundary>.
- Phase durations: <separately measured intervals; do not add overlapping milestones>.
- Measurement sources: <actual hooks/events and precision/coverage limitations>.

Milestones are elapsed milliseconds from the declared origin, not durations of
successive phases. Independent work can overlap. Record cache hits/reused views;
do not reuse an old milestone as a fresh measurement. Unsupported timestamps are
null with a reason, not zero. Frame callbacks alone do not prove paint/presentation.
Do not mix host/remote clocks or count synthetic test-clock advances as real load
times. Separate transport latency from measured application intervals.

Separate dataset counts from mounted/visible nodes and their required assets.
Define which pending/failed items prevent acceptance. A settled error is terminal,
not successful readiness. Accepted placeholders/fallbacks require explicit product
criteria; do not silently count failed assets as successfully resolved content.
Do not force off-screen virtualized items to render solely to claim completeness.

Wait on the original action and feature-specific events. Diagnostic intervals may
report progress; they must not cancel work or manufacture readiness. An external
observation timeout leaves completion unknown and does not authorize another click.

## Illustrative Response

Synthetic values below demonstrate semantics, not live runtime evidence. The
actual project must define and implement the observation sources before using them.

```json
{
  "schema_version": 1,
  "runtime": {
    "app_id": "example.catalog",
    "build_id": "debug-build-fingerprint",
    "instance_id": "authorized-instance",
    "window_id": "main",
    "viewport": {"width": 1080, "height": 1920, "unit": "px"}
  },
  "action": {
    "id": "refresh-17",
    "target": "library.refresh",
    "dispatch_path": "real_ui_event",
    "status": "completed",
    "before_revision": "view-42",
    "after_revision": "view-43",
    "observed_effect": "required visible items updated"
  },
  "timing": {
    "clock": "app_monotonic",
    "origin": "refresh-17 dispatch",
    "milestones_ms": {"data_ready": 182, "first_layout": 205, "items_resolved": 347, "ready_layout": 363, "presented_frame": null},
    "durations_ms": {"layout_pass": 11},
    "measurement_sources": {"data_ready": "required load completion", "first_layout": "layout instrumentation", "items_resolved": "required binding/asset completion", "ready_layout": "post-resolution measured layout"},
    "limitations": ["physical frame presentation not measured"]
  },
  "resolution": {
    "dataset": {"expected": 40, "resolved": 40, "pending": 0, "failed": 0},
    "rendered_items": {"scope": "mounted visible items", "expected": 8, "resolved": 8, "pending": 0, "failed": 0},
    "required_assets": {"scope": "mounted visible items", "expected": 8, "resolved": 8, "pending": 0, "failed": 0}
  },
  "readiness": {"status": "ready", "predicate": "required data, measured layout and visible assets resolved", "reasons": []},
  "snapshot": {
    "revision": "view-43",
    "coverage": "action target excerpt; not the entire hierarchy",
    "truncated": true,
    "nodes": [
      {"id": "library.refresh", "parent_id": null, "role": "button", "text": "Refresh", "bounds": {"x": 900, "y": 32, "width": 120, "height": 64, "unit": "px"}, "visible": true, "enabled": true, "selected": false, "focused": false, "actions": ["click"]}
    ]
  }
}
```

`ready` here describes the scoped application predicate, NOT complete visual
validation or whole-tree coverage. This truncated excerpt cannot prove that all
controls exist or fit. Obtain the required complete/scoped nodes before those claims.

## Acceptance Evidence

Execute the complete feature's required real workflow once integrated. Reconcile
its observed transitions, rendered scope, counts and timings against the feature's
criteria. Retain targeted visual evidence for the properties diagnostics cannot
establish. Reuse applicable current evidence rather than restarting a per-edit loop.
Record remaining measurement gaps and unresolved required work honestly.
