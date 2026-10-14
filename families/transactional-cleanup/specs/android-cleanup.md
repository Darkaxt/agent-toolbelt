# Android Task Artifact Cleanup

Authorization: already_authorized by the user's request to implement the proposed
device-bound cleanup and task-installed app removal contracts. Deployment to
Codex/Claude and GitHub synchronization follow the existing repository authority.
This task does not authorize cleaning a connected device or uninstalling an app.

## Requirements

- A1: Provide separate ADB review, inspect, ticket, apply/dry-run, status and
  revoke commands. Windows transactions retain their existing behavior.
- A2: Bind every device command to an explicit serial and stable getprop identity;
  reject missing/offline/unauthorized or changed endpoints. Discover SDK ADB.
- A3: Snapshot only a specifically attributed task directory beneath Android
  emulated storage. Protect broad roots, ordinary user folders, Android app data,
  links, special objects and path traversal. No root access or recursive deletion.
- A4: Review exact regular files with stat identity and SHA-256. Apply checks
  ancestry, identity and unchanged content before each unlink. New/changed files
  survive independently. Remove only reviewed, unchanged-identity empty directories.
- A5: Authenticate persisted manifests/tickets and bind issuance to the separately
  inspected manifest digest. Coordinate overlapping device targets, not Gradle.
  Provide partial results, retries, terminal compaction and actionable diagnostics.
- A6: App removal requires a helper-recorded absence baseline before installation,
  including retained/uninstalled packages across users, then a post-install review
  with exact APK paths/hashes and install identity. Reject pre-existing/system apps
  and changed/reinstalled packages. Ticket issuance explicitly acknowledges loss
  of test app data. Verify absence after package-manager uninstall. Do not install,
  force-stop, clear data separately or modify other packages/users.
- A7: Document that shell stat/hash/unlink checks narrow ordinary concurrency
  races but are not Windows handle-bound deletion or an adversarial sandbox.
  Require stopped producers and no concurrent installer for app cleanup. Refuse
  unsupported capability/identity rather than relaxing checks.
- A8: Test real generated shell scripts in an isolated filesystem plus fake ADB
  transport/session tests, preserve host regressions, validate and compare installed
  Codex/agents/Claude copies and runtime, commit and sync verified source.

## Stages And Reconciliation

1. Android cleanup feature (A1-A7): COMPLETE. Implement both complete ticket flows,
   device transport, safeguards, tests and guidance. Acceptance: changed/new files,
   device substitution, linked paths, package replacement, tampering and retries
   are exercised; exact reviewed outputs alone are removed.
2. Delivery (A8): ACTIVE. Run focused family/root checks, structural validation,
   installer and installed-runtime smoke checks, then commit and sync. No device
   mutation is needed for delivery verification.

Blockers: remote delivery evidence pending in Stage 2.
Tracked deferrals: none.

Stage 1 evidence: focused Android checks passed (20, one POSIX symlink check
skipped on Windows); real generated shell scripts exercised using Git Bash over
isolated task fixtures, including exact unlink, unchanged/new-file preservation
and metacharacter-safe paths. The full Windows/family suite passed before the
final missing-root/ancestor retry adjustment (127 checks, one skip); the affected
Android checks were rerun after that adjustment. Root wiring checks passed (33).
Both source skill bundles passed quick_validate.py. No live-device mutation was
performed. Android user/app behavior is transport-fixture tested, not live-proven.
Stage-closure assessment: the backend reuses existing authenticated state key and
root coordination; no speculative refactoring or consolidation stage is needed.

Stage 2 evidence: installer activated v0.6.0 in runtime release
743e97a77886bd26a824a799efe7e286. Codex, agents and Claude installed skill files
and all active runtime Python files match the repository byte-for-byte. All three
installed skills passed structural validation and expose the new package baseline
flags. Installed Claude wrapper rejects a protected Android root before any device
access. All 20 Android checks were executed against the activated runtime (one
POSIX symlink case skipped on Windows). Existing legacy transactions were retained
by the installer with their previous recovery runtime. No deployment residuals.
Source diff/whitespace checks passed; scoped credential-pattern scan had no hits.
Commit and remote synchronization remain the final delivery gate.

## Discovery

skills-sh-scout inspected public ADB automation and repository teardown skills.
Neither inspected candidate provided reviewed, device-bound exact-file tickets or
task-install provenance. Broad query results were capped; no exhaustive absence
claim is made. Extend the existing helper rather than install either candidate.

## Platform References

- https://developer.android.com/tools/adb (package manager and explicit endpoints)
- https://android.googlesource.com/platform/external/toybox/ (stat, find, hash tools)
