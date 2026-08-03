# Transactional Cleanup Design

## Purpose

Add a repo-backed `transactional-cleanup` skill and package helper that lets
agents remove generated files after builds, deployments, browser runs, media
processing, and other disk-intensive work without constructing recursive
PowerShell, `cmd.exe`, or cross-shell deletion commands.

The helper is a narrow cleanup authority, not a general filesystem deletion
tool. It separates discovery, review, ticket issuance, and application into
distinct invocations. The separation is intended to prevent accidental broad
deletion and to avoid command-policy rejection of ad hoc recursive shell
syntax.

The workspace identifies task and repository context, but it is not the
cleanup boundary. A transaction may identify generated artifacts under the
workspace, user temporary directories, tool caches, explicitly registered
output locations, or other local volumes.

## Public Interface

Proposed names:

- family: `families/transactional-cleanup`
- package: `agent-toolbelt-transactional-cleanup`
- executable: `agent-toolbelt-transactional-cleanup`
- skill: `transactional-cleanup`

Proposed commands:

```powershell
agent-toolbelt-transactional-cleanup begin --workspace <path>
agent-toolbelt-transactional-cleanup register --transaction <id> --path <path> --kind <kind>
agent-toolbelt-transactional-cleanup review --transaction <id>
agent-toolbelt-transactional-cleanup ticket --transaction <id>
agent-toolbelt-transactional-cleanup apply --ticket <ticket-id> --dry-run
agent-toolbelt-transactional-cleanup apply --ticket <ticket-id>
agent-toolbelt-transactional-cleanup status --transaction <id>
```

All commands emit one bounded JSON document. There is no command that combines
discovery and deletion. Ticket issuance is non-destructive, and `apply` cannot
accept arbitrary paths.

## Transaction Model

`begin` records a transaction before disk-intensive work starts. The
transaction contains:

- a random transaction identifier;
- host and user identity metadata;
- UTC start time;
- normalized workspace and repository metadata;
- selected local volumes and supported tracking mechanisms;
- free-space baselines;
- configured temporary and cache roots;
- an initially empty explicit-path registry.

The transaction is host-scoped. The workspace is used for Git protection,
classification, and reporting, not to exclude artifacts written elsewhere.

`register` lets an agent or wrapper record a known generated output as soon as
it is created. Registration records provenance and expected artifact kind but
does not make the path automatically deletable.

`review` closes discovery for the current snapshot and writes an immutable
candidate manifest. It reports detected changes, exclusions, safety decisions,
and estimated reclaimable bytes. Review does not delete or issue authority to
delete.

`ticket` reads the reviewed manifest and creates a helper-managed, single-use
deletion ticket. It cannot add paths, broaden directories, or recompute the
candidate set.

`apply` operates only on exact objects listed in the ticket. It supports a
non-mutating dry run and a real application using the same validation path.

## Artifact Discovery

Discovery should combine evidence rather than assume every tool writes below
its working directory:

1. Before-and-after workspace inventory for repository-local outputs.
2. Explicit paths registered by the agent or package wrapper.
3. Known volatile roots such as `%TEMP%`, `%LOCALAPPDATA%\Temp`, `D:\Temp`,
   `E:\Temp`, and configured tool-specific cache roots.
4. NTFS USN journal changes on selected local volumes when available.
5. Optional Windows ETW file events associated with a launched build or
   deployment process tree when supported and authorized.

USN journal evidence provides broad volume coverage but does not by itself
prove which process created a file. ETW may provide process attribution but
must be treated as optional because availability and privilege requirements
vary. Explicit registration and known-root classification remain valid when
neither mechanism is available.

The review report must state which discovery lanes were active and which were
unavailable. It must not claim complete host coverage when only workspace or
known-root scanning was performed.

## Candidate Classification

The review manifest may describe every detected change, but deletion authority
is narrower. Default candidates are objects created during the transaction and
classified as generated or temporary with concrete evidence.

Each entry records:

- canonical path;
- volume identity and filesystem type;
- Windows file identifier where available;
- object type;
- size and timestamps at review;
- discovery source;
- artifact kind;
- creation or pre-existence status;
- Git status when inside a repository;
- reparse-point and hard-link diagnostics;
- candidate or exclusion decision;
- human-readable decision reason.

Pre-existing files that were modified during the transaction are reported but
protected by default. A pre-existing output directory may be considered
replaceable only when explicitly registered as a regenerated output and when
repository and dangerous-path checks pass.

Suggested artifact kinds include `temporary`, `compiler-output`,
`package-cache`, `browser-artifact`, `media-intermediate`, `test-output`,
`generated-report`, and `explicit-generated-output`.

## Ticket Contract

A ticket binds deletion authority to one reviewed snapshot. It contains or
references:

- transaction identifier;
- manifest SHA-256;
- random helper-managed nonce;
- host identity;
- safety-policy version;
- exact candidate identifiers;
- issue timestamp;
- state: `issued`, `partially_applied`, `applied`, or `revoked`.

The ticket identifier is opaque. A caller cannot construct a valid ticket from
a path or hash alone. Tickets are stored in helper-owned state and are valid
only on the originating host.

The two-step contract is procedural rather than interactive: ticket issuance
does not ask the user for another approval. It forces the agent to obtain and
inspect a review artifact before a separate invocation can receive deletion
authority.

There is no ticket expiry by default. Object identity and snapshot membership,
not elapsed time, determine whether an entry can still be applied.

## Snapshot Deletion Semantics

Application is item-granular. A change to one candidate never invalidates the
entire ticket.

- Only objects present in the reviewed candidate manifest are eligible.
- Files created after review are never added to the ticket.
- A ticketed file that changes size or content but retains the same filesystem
  identity remains eligible because it is the same generated object.
- If a ticketed path now refers to a different filesystem identity, the entry
  is skipped as `replaced_after_scan`.
- If stable identity is unavailable, the helper uses conservative metadata
  checks and skips ambiguous replacements.
- Missing objects are recorded as `already_missing`.
- Locked objects are recorded as `locked` and remain retryable.
- Other failures are item-local and do not prevent safe entries from being
  applied.

The helper must never recursively delete a ticketed directory. It deletes exact
ticketed files first, then attempts to remove exact ticketed directories in
bottom-up order only when they are empty and retain their reviewed identity.
Files that appeared concurrently therefore remain untouched, and their parent
directories remain in place.

Each entry finishes in one of these states:

- `deleted`
- `already_missing`
- `locked`
- `replaced_after_scan`
- `protected`
- `failed`

A partially applied ticket may be retried. Retries operate only on unresolved
entries from the original snapshot and never discover or include new files.

## Dangerous-Path Policy

The helper permanently rejects deletion authority for broad or critical
locations, including:

- drive roots;
- Windows, boot, recovery, and system directories;
- `Program Files`, `Program Files (x86)`, and `ProgramData` roots;
- the `Users` root and user-profile root;
- repository roots and `.git` directories;
- helper installation, policy, and ticket-state roots;
- filesystem metadata and volume-management paths.

Protected ancestors do not prohibit exact known descendants. For example,
`%LOCALAPPDATA%` is protected as a broad path while `%LOCALAPPDATA%\Temp` may
be inventoried and ticketed at item level.

Additional rules:

- Never follow reparse points, junctions, mount points, or symlink targets.
- Reject reparse-point deletion by default.
- Detect multiple hard links and protect ambiguous objects.
- Never delete tracked or modified repository files.
- Never delete a repository-untracked file solely because it is untracked;
  generated provenance is still required.
- Never kill processes to release locked files.
- Never create backups or quarantine copies by default.
- Never accept shell globs, wildcards, or path expressions in `apply`.

Policy overrides, if introduced later, must be explicit during review and
ticket issuance. `apply` must never broaden authority through an override flag.

## Filesystem Application

Deletion is implemented inside the package using Windows/Python filesystem
APIs after canonical-path and identity validation. The skill must not construct
`Remove-Item -Recurse`, `cmd.exe /c`, cross-shell pipelines, or string-built
deletion commands.

The package should open or inspect each object as narrowly as Windows permits,
confirm identity immediately before deletion, delete exact files, and remove
only empty exact directories. A failure returns structured diagnostics rather
than falling back to another shell.

This design does not attempt to bypass Codex command policy. It replaces
ambiguous shell-level destructive expressions with a typed helper whose own
authority is narrower and auditable.

## State And Logging

Proposed state root:

```text
%LOCALAPPDATA%\Tools\transactional-cleanup\state
```

Transaction and ticket files contain paths and metadata but never source-file
contents. Logs contain operation identifiers, counts, byte totals, decisions,
and failure kinds.

After a ticket reaches a terminal state, the helper removes detailed temporary
inventory data and retains a small metadata-only audit summary. The summary
contains transaction and ticket identifiers, workspace, timestamps, counts,
bytes, result classes, and policy version. It must not retain an indefinite
second copy of the full path inventory.

The helper must clean its own staging files after successful completion and
surface residual helper state in `status` after interrupted operations.

## Skill Workflow

The skill should trigger for builds, deployments, package installations,
browser automation, media processing, extracted archives, generated reports,
temporary worktrees, and other operations likely to leave substantial local
artifacts.

Agent workflow:

1. Start a transaction before disk-intensive work when practical.
2. Register output paths when tools reveal or create them.
3. Complete and validate the primary task before cleanup.
4. Run `review` and inspect candidates, exclusions, and byte estimates.
5. Issue a ticket only when the reviewed candidate set is justified.
6. Optionally run `apply --dry-run` for high-impact tickets.
7. Apply the ticket and report bytes reclaimed and residual entries.
8. Never retry a rejected helper operation using ad hoc recursive shell
   deletion.

For work that started without a transaction, a future retrospective inventory
mode may produce a review-only report. It must not infer creation provenance or
issue a deletion ticket without stronger evidence.

## JSON Results

Every command should include:

- `ok`
- `operation`
- `transaction_id`
- `ticket_id` when applicable
- `workspace`
- `discovery_coverage`
- `candidate_count`
- `candidate_bytes`
- `excluded_count`
- `result_counts`
- `deleted_bytes`
- `warnings`
- `errors`
- `failure_kind`

`review` additionally returns the manifest path and SHA-256. `ticket` returns
ticket state and the bound manifest hash. `apply` returns per-state counts and
bounded item diagnostics without printing file contents.

## Test Plan

Unit tests must cover:

1. Workspace, known-temp-root, explicit-path, and mocked USN discovery.
2. Honest diagnostics when a discovery lane is unavailable.
3. Created-file candidates versus protected pre-existing modified files.
4. Git tracked, modified, repository-root, and `.git` protection.
5. Dangerous path rejection for drive, system, profile, and broad AppData
   paths while allowing exact safe temporary descendants.
6. Ticket binding to host, transaction, policy version, nonce, and manifest
   hash.
7. Rejection of forged, unknown, revoked, and already-applied tickets.
8. Snapshot semantics when new files appear after review.
9. Same-identity files remaining eligible after size or content changes.
10. Replacement-path identity changes producing `replaced_after_scan`.
11. Item-local failure handling without whole-ticket cancellation.
12. Locked-entry retry using the same ticket.
13. Exact-file deletion and empty-directory-only removal with no recursive
    directory operation.
14. Reparse-point, junction, symlink, mount-point, and hard-link protection.
15. Dry run and real apply sharing the same eligibility checks.
16. Partial application retaining only unresolved original entries.
17. State cleanup and bounded metadata-only audit retention.
18. JSON output containing no file contents.

Integration tests should create a disposable tree on `D:\Temp` when available,
modify it concurrently between review and apply, and prove that:

- reviewed objects are removed when still eligible;
- new concurrent files survive;
- replaced paths survive;
- non-empty parent directories survive;
- unrelated paths are untouched;
- reported deleted bytes match observable disk changes within filesystem
  accounting limits.

Root tests must validate family CLI wiring, family isolation, monorepo layout,
Codex/Claude skill bundles, and skills.sh discovery if the skill is made public.

## Acceptance Criteria

1. Agents can clean generated artifacts outside the workspace without
   constructing recursive shell deletion commands.
2. No deletion can occur in the same invocation that discovers candidates.
3. A ticket authorizes only the immutable reviewed candidate set.
4. Concurrently created files are never deleted and never invalidate safe
   ticket entries.
5. Directories are never recursively deleted; only reviewed files and empty
   reviewed directories are removed.
6. Dangerous paths, repository metadata, tracked files, reparse targets, and
   ambiguous hard links fail closed.
7. Partial and locked failures do not cancel deletion of independent safe
   entries.
8. Ticket retries never expand their candidate set.
9. The helper reports discovery coverage honestly and does not claim complete
   host tracking when only partial evidence is available.
10. Detailed transaction state is cleaned after completion without creating
    indefinite backup or audit growth.
11. Focused, root, and installed-skill validation pass before publication.
12. Repository and installed skill state are synchronized after implementation.

## Deferred Decisions

The implementation plan should resolve these points using Windows prototypes:

- minimum supported Windows and Python versions;
- direct USN journal implementation versus an optional Windows helper;
- whether ETW process attribution belongs in the first release;
- exact Windows file-identity API and behavior on non-NTFS volumes;
- default known temporary/cache roots;
- audit-summary retention count or size budget;
- whether the first release is local-only or published through skills.sh.

The recommended first-release boundary is explicit registration, workspace and
known-root inventory, immutable tickets, and exact snapshot application. USN
and ETW coverage should be added only after the core ticket and identity model
is proven end to end.
