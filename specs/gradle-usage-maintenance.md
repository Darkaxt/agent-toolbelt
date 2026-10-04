# Gradle Usage And Maintenance Policy

## Authorized Outcome

User approved a standing Gradle skill rule plus helper usage tracking and reviewed
cleanup proposals, avoiding repeated instructions to individual tasks. Deploy the
verified helper/skill for Codex, agents and Claude and sync GitHub. Do not upgrade
any Android project, delete existing caches, or create background automation here.

## Requirements

- U1: During authorized Android build-tool maintenance, agents prefer an existing
  newer compatible baseline, verify with required focused builds through the gate,
  and commit the wrapper/toolchain changes. Routine builds never trigger upgrades.
  Incompatibility or unrelated scope is recorded, not bypassed. Compatibility
  evidence must cover actual AGP/Kotlin/plugins/JDK; highest installed is not proof.
- U2: Normal `run` automatically records the current project's wrapper version and
  Gradle home without changing the wrapper. Local catalog stores paths, versions,
  explicit keep-version reservations and diagnostic timestamps, not URLs/tokens,
  commands, config content, or credentials. Metadata updates are atomic and
  interprocess-serialized. Catalog failure must not replace the actual build result.
- U3: Explicit register/unregister commands support projects not recently built
  and deliberate rollback/offline version reservations. Read-only inventory
  re-reads known wrappers, protecting missing/unreadable/unknown references rather
  than treating them as unused. Never scan whole drives or all repositories.
- U4: Inventory reports known project references, installed distribution and
  version-specific cache sizes, and stable baseline candidates explicitly NOT
  compatibility-verified. Shared caches, user configuration, JDKs, daemon registries,
  links/reparse content and incomplete inventories cannot become cleanup candidates.
- U5: `cleanup-plan` returns exact-root proposals and estimates only. Referenced,
  reserved or live-daemon versions are protected. Active/ambiguous build activity
  blocks cleanup proposals. "Not referenced by known projects" is not proof of
  global non-use; manual review and transactional cleanup are required. It never
  authorizes deletion, retires a daemon, or infers inactivity from age.
- U6: Preserve FIFO tickets, shared build mutex, event waiting, retirement, resource
  defaults, confirmation/cleanup boundaries and read-only status. No automatic
  upgrades, deletes, background scanning, periodic task, or new dependencies.
- U7: Source and installed Codex/Claude/agents bundles match, validators and focused
  contracts pass; commit and sync the verified change to GitHub.

## Stages

1. Usage catalog -- COMPLETE. U2-U3/U6: regression fixtures for registration,
   reservations, atomic concurrent updates and wrapper changes; implement catalog.
2. Inventory and integration -- COMPLETE. U2-U6: read-only inventory/proposals,
   exact bounded roots, conservative references/activity checks, CLI/run wiring.
3. Standing policy and delivery -- ACTIVE. U1/U6-U7: docs, regression review,
   actual installed read-only smoke, parity, validation, commit and sync.

## Verification Boundaries

Stage 1: native concurrent registration, reservation retention, wrapper refresh,
credential omission and corrupt-catalog preservation passed in isolated fixtures.
Stage 2: reference refresh, reservations, activity/link/incomplete-scan protection,
CLI routing and build-result preservation passed. Integrated family verification
also passed native FIFO and authenticated graceful retirement regression checks.

Use isolated synthetic wrapper/cache fixtures and native metadata locking. No
unrelated Gradle build or live cache deletion is needed to prove this extension.
Real inventory validates installed read behavior but is not cleanup authorization.
Catalog covers registered/observed project paths, not historical branches or
unregistered repositories. An upgrade requires its own in-scope project evidence.

## Primary References

- https://docs.gradle.org/current/userguide/directory_layout.html
- https://docs.gradle.org/current/userguide/compatibility.html
