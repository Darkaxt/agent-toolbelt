# FIFO Gradle Execution Tickets

## Authoritative Scope

User explicitly requests a ticket system rather than an unspecified mutex order.
Extend the installed shared Gradle helper. Preserve daemon retirement, active-build
protection, resource defaults and the existing production mutex. Install for Codex
and Claude and sync GitHub. No scheduled task or periodic polling is added.

## Requirements

- Q1: `run` automatically registers a durable monotonic ticket, in registration
  order, before waiting for execution. Only the live queue head may attempt the
  production build mutex. Hold the ticket until build/retirement supervision ends.
- Q2: Metadata updates use one Windows queue-metadata mutex (not a project lock
  or lockfile). Keep the original build mutex for existing launchers and safety.
- Q3: Wait on native turn events and the head owner's process-exit handle with no
  polling, sleeps, age expiry, deadlines, or timeout-based ownership stealing.
- Q4: Reclaim abandoned tickets only using owner PID plus exact native creation
  identity and proven exit/mismatch. Access-denied/unknown identity blocks rather
  than being classified dead. Surviving builds still pass normal activity checks.
- Q5: Emit ticket number/id in progress and final JSON. Status reads the queue
  without enqueueing, pruning, or giving launch clearance. Corrupt state blocks.
- Q6: Guarantee FIFO only among updated participating helper instances in this
  Windows session; older launchers and Studio do not automatically join the queue.
  Metadata contains identities, not command bodies, credentials, or project data.

## Stages

1. Ticket contracts -- COMPLETE. Q1-Q4: native multi-process FIFO and dead-owner
   regressions with isolated mutexes/events and temporary metadata.
2. Runtime integration -- COMPLETE. Q1-Q6: queue, `run`, status/reporting,
   existing safety/profile regressions.
3. Gradle 8.6 compatibility -- COMPLETE. Newly authorized defect correction in
   specs/gradle-retirement-compatibility.md, preserving all queue contracts.
4. Delivery -- COMPLETE. Q5-Q6: Codex/Claude docs, installed parity, validation
   and final reconciliation. No unrelated Gradle build for tests. Commit/GitHub
   synchronization follow verified stage closure; report their actual results.

## Verification Ledger

- Ticket stage: actual isolated Windows processes verify FIFO, native completion
  wakeup, dead head reclamation, PID reuse, unknown-identity refusal, cancellation,
  and head transition while the prior owner remains alive. No timer synchronizes.
- Integration: native queue tests and gate/profile regressions pass. Ordered
  supervisor test verifies ticket -> build mutex -> inspection/retirement/build
  -> mutex release -> ticket release. Status does not mutate queue metadata.
- Compatibility: adapter compiles against every installed distribution, including
  8.6. Busy 8.6 fixture is rejected; racing-work fixture survives the authenticated
  request until explicit completion and supervisor waits for native exit.
- Real 8.6: fresh idle process/registry evidence under the shared build mutex;
  authenticated StopWhenIdle completes with process_exit_verified. No extra
  Gradle build was launched, and no active/ambiguous build was stopped.
- Delivery: v0.3.0 installed for Codex, agents and Claude; every runtime/skill file
  matches canonical source by SHA-256. Installed validators, marketplace validation,
  installed CLI diagnostics and root family wiring checks pass. Generated fixture
  directories were removed by test cleanup. No unresolved blockers/deferrals.
- Final source verification: focused family suite includes native/protocol and
  sanitization regressions. No test launched an extra real Gradle build. GitHub
  sync is the final authorized delivery action, not inferred from local tests.
