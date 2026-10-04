# Gradle Retirement Compatibility Correction

## Scope And Root Cause

User reports Gradle 8.6 source-mode compilation fails before sending shutdown.
Inspection of installed 8.6 jars confirms the idle state is DaemonStateControl.State,
not the later DaemonState class; FileLockContentionHandler.start requires Gradle
Action, not the later Consumer. Python discards compiler stderr. Correct both
without replacing authenticated StopWhenIdle or weakening build protection.

## Acceptance

- C1: Adapter compiles against installed Gradle 8.6 and newer distributions.
  Use enum name comparison and explicit Action/Consumer callback overloads;
  unsupported interfaces still fail closed, never select a killing fallback.
- C2: Preserve registry idle checks, PID/start identity, target JVM validation,
  authenticated StopWhenIdle and supervised native exit. Busy targets cannot
  receive shutdown. Racing work must complete before graceful exit.
- C3: Preserve actionable bounded compiler/runtime diagnostics in structured
  failure output. Do not emit authentication tokens, registry objects or raw
  arbitrary exception messages. Identify compilation failure separately from
  idle/identity/protocol rejection.
- C4: Exercise real Gradle 8.6 graceful retirement under the shared gate with
  fresh idle evidence. Do not launch an unrelated Gradle build or force-kill
  active/ambiguous/external processes. Use isolated protocol fixtures for busy,
  racing and identity negative cases. Record if real retirement is blocked.
- C5: Deploy a single verified runtime to Codex, agents and Claude; sync GitHub.

## Stage Mapping

Compatibility is COMPLETE as stage 3 of specs/gradle-fifo-queue.md. C1-C4 belong
to that stage; C5 belongs to final delivery. No concurrent implementation stage.

## Evidence

Installed-distribution compilation matrix passes from 8.6 through the locally
installed newer versions. Isolated 8.6 handshake confirms authenticated
StopWhenIdle/Finished and native exit; Busy is rejected and simulated racing work
completes before exit. Real confirmed-idle 8.6 retirement also completed while
holding the shared gate. Compiler fixtures preserve missing symbols/signatures,
drop arbitrary sensitive stderr/path text, and CLI returns structured diagnostics.
The combined v0.3.0 runtime and all three skill installs match source. GitHub
synchronization remains a final task action reported from actual Git evidence.
