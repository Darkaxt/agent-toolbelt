# Gradle Daemon Retirement

## Authorized Scope

Extend the existing shared Windows build gate to retire previous unused Gradle
daemons before a different version or heap profile starts. Install the verified
helper for Codex and Claude and sync the repository. Do not change the separate
120-minute cleanup task, kill Java broadly, interrupt builds, alter project/global
settings, or change Kotlin compilation strategy.

## Requirements

- D1: Retirement runs while the supervising thread holds the existing mutex,
  only after active/ambiguous activity has finished. Reinspect before each request.
- D2: Default `incompatible` retires idle daemons with a different wrapper version
  or maximum heap. `all-idle` retires every confirmed-idle Gradle daemon; `none`
  preserves the old behavior. Matching reusable daemons remain reusable by default.
- D3: Use each daemon's installed Gradle protocol and authenticated registry entry
  to request `StopWhenIdle`, never immediate `Stop`, taskkill, or process terminate.
  Verify PID/start identity and registry idle state. A nonparticipating launcher
  racing the request may finish its build; retirement must not cancel it.
- D4: Wait for actual process exit, without cleanup age limits, sleeps, or added
  cancellation deadlines. Unknown version/distribution/registry/JDK protocol blocks
  retirement and the build. Missing processes are reported already exited.
- D5: Report target version, policy, candidate identity, reason, and verified exit;
  never expose registry authentication tokens. Status remains read-only. Kotlin,
  workers, unrelated Java, and the independent cleanup task remain untouched.
- D6: Preserve gate/profile behavior; installed runtime includes the Java source
  adapter, which uses an existing JDK and the candidate distribution's local jars.
  No downloads, new tasks, services, or unrelated project builds for verification.

## Stages

1. Retirement contracts -- COMPLETE. D1-D5: regression tests first; selection,
   non-idle rejection, fresh identity checks, and gate ordering.
   Evidence: selection/unknown-state/pinned-wrapper focused regressions pass.
2. Protocol and integration -- COMPLETE. D1-D6: source-mode Java adapter,
   inspection metadata, CLI, runtime reporting; focused tests and read-only registry
   probes plus a synthetic local protocol server for shutdown handshake evidence.
   Evidence: focused family tests pass including authenticated synthetic
   StopWhenIdle/Finished handshake and actual target-process exit, PID-change
   rejection, new active-build rejection, and mutex ordering. Read-only registry
   probes pass for live Gradle 8.12.1, 8.14, 9.1.0, and 9.4.1. No real daemon stopped.
3. Deployment and delivery -- COMPLETE. D6: docs, installed parity, validators,
   commit/sync; reconcile all requirements. No live build or unrelated daemon stop.
   Evidence: family regressions, root wiring checks, canonical/installed skill and
   Claude marketplace validators pass. Runtime 0.2.0 (release 9afed03b6c721671) and
   Codex/agents/Claude skills match canonical hashes. Commit/sync follows this
   verification as final delivery, not as acceptance evidence.

## Verification Boundary

Read-only probes of installed Gradle distributions validate registry/protocol
compatibility. Synthetic protocol tests validate handshake and real process exit;
they do not claim a real project's build was run. The next required build verifies
the integrated live retirement. Do not silently fallback to forceful shutdown.

## Reconciliation

D1-D6 satisfied for helper delivery; no unresolved blockers or tracked deferrals.
The separate periodic cleaner and 3 GB heap defaults are unchanged. No real build
or real Gradle daemon was interrupted for verification. Synthetic fixtures and
their temporary registries were removed automatically after testing.
