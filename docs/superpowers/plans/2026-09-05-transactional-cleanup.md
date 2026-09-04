# Transactional Cleanup Implementation

Specification: `../specs/2026-08-03-transactional-cleanup-design.md`.
Authorization: already_authorized by the request to realize the skill.

## Release Decisions

Windows 10/11 and Python 3.11+ are supported. Deletion requires Windows handle-based
identity and disposition; unsupported platforms remain read-only. The first release
uses explicit registration, workspace baselines and known-temp-root inventory.
USN and ETW are optional future discovery lanes as allowed by the specification;
every report identifies them as unavailable. No host-wide tracking claim is made.
State defaults to LOCALAPPDATA/Tools/transactional-cleanup/state. Detailed state is
removed on terminal completion; only the newest 100 compact summaries are retained.
The public family includes Codex and Claude skills and a bundled independent runtime.
Pre-existing generated roots require explicit regenerated-output registration and a
concrete provenance explanation; ordinary modified baseline files remain protected.

## Stages

1. Discovery, identity and protection: begin/register/review; baseline comparison,
   repository and dangerous-path guards, immutable reviewed manifests. Verify real
   Windows identities, generated classification and exclusions.
2. Ticket/application: host-bound signed state, snapshot-only ticket issuance,
   handle-based exact deletion, dry runs, concurrent replacement/new-file behavior,
   item-local failures/retries, revoke, terminal cleanup. Verify real disposable trees.
3. CLI, skills and deployment: bounded JSON, self-contained wrappers, Codex/Claude
   installation, root wiring and documentation, full reconciliation and GitHub sync.

## Reconciliation

| Stage | State | Blockers | Deferrals | Evidence |
| --- | --- | --- | --- | --- |
| 1 | passed | 0 | 0 | Windows identity, baseline/external registration, Git/protected roots and junction/hard-link exclusions tested. |
| 2 | passed | 0 | 0 | 26 tests pass, including concurrent writes/new files/replacements, actual sharing violations, journal replay, signed host-bound tickets, dry run, revoke, and terminal detail removal. |
| 3 | pending | - | 0 | CLI, skills, installed behavior and repo synchronization |

All specification sections and acceptance criteria map to these stages. Completion
requires zero blockers and zero deferrals. The previously reported proxy build folder
is a separate live cleanup operation; implementation tests use owned disposable trees.

Public preflight inspected the suggested legal-review and Prisma adapter skills;
neither implements Windows snapshot cleanup. Narrowed scout recommended creating a
new skill. The broad query's lexical legal-review match was rejected after body review.
