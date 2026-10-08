# Gradle Fail-Fast Supervision

## Authoritative Requirements

Authorization: user requested implementation of the proposed native fail-fast
default and explicit collection opt-out. This applies to subsequent invocations,
not processes already running.

- R1: Enable Gradle Test.failFast by default through the invocation-local init
  script. Use native test outcomes, never arbitrary ERROR/exception text to kill.
- R2: --collect-all-failures disables early test stopping, but test failures must
  still fail the build. Reject conflicting raw fail-fast options. Require the
  opt-out for --continue. Preserve unrelated options such as -m (dry-run).
- R3: Preserve FIFO and mutex ownership until wrapper exit. Do not add process
  killing, lock stealing, deadlines, or intervention in existing builds.
- R4: Report requested policy, observed configuration and bounded failure output
  evidence. Missing configuration markers must not imply verification. A hung
  test that never reports failure remains outside this change.
- R5: Document, verify, install for Codex/agents/Claude, and sync verified source.

## Staged Plan And Reconciliation

1. Native failure policy (COMPLETE): R1-R4. Test CLI routing, conflicting options,
   policy transport, native init settings, failed exit preservation, harmless
   error output and ownership through completion.
2. Verification and deployment (COMPLETE): R5 implementation. Run focused family/root checks,
   gated native fixture when available, validate skills, deploy identical runtime
   and skill files. Commit and GitHub sync follow stage closure as final delivery.
   Record actual integration evidence and gaps.

Stage 1 evidence: focused policy checks and family suite passed. A real offline
Gradle 9.8.0 fixture under production FIFO/mutex ran 21/51 separate failing tests
with fail-fast versus 51/51 with collection, both exit 1. Requested/effective
workers=2, parallel=false, Gradle heap=3 GiB, one 128 MiB test fork. No Kotlin or
native compilation in this Java-only fixture; no memory failures.

The first single-class fixture executed all 51 fast methods before cancellation
was processed. Revised verification checks scheduling across separate classes;
this documents native in-flight behavior, not an immediate kill guarantee.

No blockers or tracked deferrals. Existing unrelated builds were not interrupted.

Stage 2 evidence: family suite passed (61 checks; the opt-in native fixture was
run separately and passed); focused root family CLI/isolation/layout checks
passed. Canonical Codex/Claude skill validation passed. Installer deployed 0.4.3,
runtime release a85dbfd0682b2b1b. All nine runtime source/assets files and all
installed skill files matched source hashes in Codex, agents and Claude roots;
each installed launcher exposes --collect-all-failures and validates. Both native
fixture directories were confirmed absent after automatic test teardown.

Final reconciliation: R1-R4 verified; R5 documentation, validation and deployment
verified. No remaining implementation blockers or deferrals. GitHub sync is the
final delivery operation for this verified commit, not a claimed test result.
