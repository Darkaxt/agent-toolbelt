# Gradle Task And Thread Name Display

Authorization: already_authorized by the request to change Task & Project to
Task & Thread Name. This refines the existing tray and silent notification.

## Requirements

- R1: Display Task (current operation) and Thread Name (actual conversation title)
  in owner details, queue details and silent notifications. Do not substitute a
  project directory for the thread name. Keep execution project metadata intact.
- R2: Add optional `run --thread-name` before `--`, route it through supervision
  to both observers, sanitize display text and show Unknown when omitted/blank.
  Legacy telemetry without that field must remain readable and honest.
- R3: Preserve the elephant icon, queue/usage/duration displays, observer-only
  authority, build mutex, release ordering and resource profile.
- R4: Verify CLI routing, persisted metadata, native tray text/legacy fallback,
  notification escaping and installed bundles. Install Codex/Claude copies and
  sync the verified commit without interrupting builds or deleting old runtimes.

## Stages

1. COMPLETE: implement R1-R3 with focused regression and native observer checks.
2. COMPLETE: verify installation and reconcile installed behavior against R1-R4.

Final delivery: commit and protected remote sync after verified stage closure.
Do not report the overall outcome complete until remote integration is confirmed.

No blockers or tracked deferrals.

## Verification

R1-R3 pass notification XML/transport checks, explicit/blank name handling,
CLI-to-both-observers routing, persisted metadata, native hover/queue/tooltip
checks and legacy-record fallback. Project paths remain execution metadata.
The family regression suite passed (103 checks, 3 opt-in skips), including native
observer singleton/concurrency tests and unchanged gate release ordering. Root
family/isolation/layout/portability checks passed; skill structure is valid.
No real Gradle build was launched for verification. Test fixtures self-cleaned.

R4 installation verification: v0.7.1 runtime 9c77139865b2fc1b matches all 16 source
files; Codex, agents and Claude bundles match canonical files and pass structural
validation. The installed Claude wrapper exposes --thread-name outside the repo.
The previous tray was stopped by its own event and its native process exit was
confirmed before starting the installed observer. Live status reports Task and
Thread Name without Project display; existing legacy requests show Unknown.
No build was stopped or requeued, and older runtime releases remain intact.
