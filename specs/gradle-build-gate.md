# Windows Gradle Build Gate

## Authorized Outcome

Create and install a small shared Gradle helper skill for Codex and Claude.
Standing instruction Section 42 is authoritative. No existing build, daemon,
Android Studio configuration, repository settings, or global Gradle configuration
may be interrupted or modified. Sync the verified repository implementation.

## Requirements

- R1: All helper instances acquire `Local\Darka.AndroidGradleBuildGate` on the
  supervising thread before activity inspection and hold it through command exit.
  Windows abandoned ownership requires reinspection, not lock stealing.
- R2: Inspect wrapper clients, Gradle launchers/daemons, native process identity,
  client connections and current daemon lifecycle logs. Missing or inaccessible
  evidence is ambiguous, never inferred idle from CPU or age.
- R3: Subscribe to lifecycle/log events before inspection; wait on real changes
  without sleeps, cancellation deadlines or killing existing builds. Subscription
  failure blocks launch. The mutex only coordinates cooperating session launchers;
  external launchers remain an explicitly documented coordination limitation.
- R4: Use the project wrapper, two workers, no parallel projects, Gradle/Kotlin
  maximum heaps initially 3 GB, preserving existing other JVM arguments. Do not
  silently select Kotlin in-process; explicit selection requires project assessment.
  Larger heaps require a recorded memory diagnosis. Constrain test forks and set
  native environment budgets, explicitly distinguishing observed native limits.
- R5: Stream output to a local log and report real exit status, gate acquisition,
  requested profile, Gradle-observed profile if available, memory failure evidence
  and verification gaps. Never claim unobserved compiler/native limits as verified.
- R6: No shell injection from command arguments; hidden observer processes; no
  persistent daemon/task, no secret/session material in installed skill bundles.
- R7: Self-contained installed copies for Codex, agents, Claude; identical mutex
  across installs, no dependency on a mutable checkout. Skills document long waits
  and require waiting instead of bypassing. No unrelated real Gradle build for tests.

## Stages

1. Gate/profile behavioral contracts -- COMPLETE. R1-R4: regression tests for
   idle/active/ambiguous evidence, profile preservation, invalid arguments and
   genuine Windows mutex ownership/abandonment. No real Gradle launches.
   Evidence: focused contract suite passed, including Windows cross-process
   exclusion and abandoned-owner recovery; no Gradle command was started.
2. Supervised runtime and skill bundles -- COMPLETE. R1-R7: implement event
   watcher, execution, reporting and frontend skills; synthetic wrapper workflow.
   Evidence: actual Windows event subscription and synthetic wrapper with a
   space-containing path/arguments verified; CLI activity inspection classified
   the three observed daemons idle using lifecycle and client-connection evidence.
3. Install, reconcile and verify -- COMPLETE. R1-R7: family/root tests, skill
   validators, installed parity and read-only host inspection. Commit/sync follow
   verified stage closure as final delivery, not as a substitute for verification.
   Evidence: family suite, root CLI/isolation/layout checks, skills.sh discovery,
   Codex/Claude validators and Claude marketplace validation passed. Installed
   runtime plus all three personal skill copies match canonical source hashes.

## Final Delivery

Commit and sync the verified scope to GitHub; leave a clean main tracking origin.
Repository branch protection must remain intact. Deployment is explicitly
authorized for personal Codex, agents and Claude skill roots only.

## Boundaries

No arbitrary timeout or sleep is synchronization. Tool wait/yield periods are
monitoring only. `status` is read-only, not proof of gate acquisition. External
Studio launches cannot be prevented solely by our mutex. No unrelated actual
Gradle build is run; the next required project build validates the real profile.

## Reconciliation

R1-R7 satisfied for helper/skill delivery. No blockers or tracked deferrals.
Actual project Gradle/Kotlin/native budget verification deliberately belongs to
the next already-required focused project build, as Section 42 requires. Synthetic
tests do not claim real Gradle configuration-cache/compiler/plugin validation.
No current builds, daemons, project settings or global settings were changed.
