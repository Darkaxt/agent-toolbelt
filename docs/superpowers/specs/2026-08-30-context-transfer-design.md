# Codex Context Transfer And Recovery Archive

## Purpose

Create a Codex-only `context-transfer` skill and helper that allow a fresh destination task to take ownership of useful context from an oversized source task, preserve the complete source task tree in a verified recovery archive on another drive, archive the source in Codex, and remove the exact local rollout payloads that consumed the disk space.

The destination task owns analysis, acceptance, and retirement. The source task must not summarize or retire itself.

## Verified Acceptance Fixture

The first live acceptance fixture is the task currently shown as `Beacon`, originally created from the Apollo installation troubleshooting request.

- Root thread ID: selected from the live local Codex index at execution time and never committed to the public repository
- Root rollout size: `685,637,841` bytes
- Child agents: `101`, all recorded as `closed`
- Complete spawn tree: `102` readable rollouts
- Complete rollout size: `8,000,165,603` bytes (`7.451 GiB`)
- Source task archive state at design time: not archived
- Recovery drive free space at design time: approximately `2.40 TiB`
- Recovery root: `E:\Codex\ThreadArchives`

These values are test evidence, not hardcoded production assumptions. The helper must discover every task tree from the live read-only Codex index.

## Requirements

### CT-1: Destination-Owned Transfer

The workflow must run from the fresh destination task. It receives an explicitly selected source thread ID and must reject the destination task itself as a source.

The destination task must inspect and understand the source before any archive or deletion mutation. It must not ask the source task to produce its own handoff.

### CT-2: Exact Task-Tree Inventory

Read Codex thread metadata in SQLite read-only mode and traverse `thread_spawn_edges` recursively from the selected root.

Inventory every resolved thread row and rollout path with:

- thread ID and parent/child relationship;
- title, working directory, timestamps, and archive state;
- child status;
- original absolute rollout path;
- file size, modification time, and SHA-256;
- repository metadata recorded by Codex when present.

Require every child agent to be terminal before retirement. Report active, running, missing, unreadable, duplicate, or cyclic entries and block destructive phases.

### CT-3: Compact Continuation Handoff

The destination task must create a bounded `CONTEXT_TRANSFER.md` that contains only continuation-relevant information:

- current objective and product direction;
- authoritative specifications and plans;
- completed work with evidence;
- active stage and exact next actions;
- unresolved blockers and required deferrals;
- durable decisions and user constraints;
- failed approaches that should not be repeated;
- repositories, branches, commits, pull requests, deployments, and local artifacts;
- child-agent contribution map;
- uncertain or unavailable evidence requiring later verification.

The destination must verify live repository and artifact state instead of copying old thread claims blindly.

### CT-4: Bounded Source Analysis

Do not load the complete raw task tree into the destination model context.

Use a combination of:

- Codex task retrieval for recent and selected older turns;
- a bounded evidence catalog derived from source rollouts;
- existing compact recall/index components where reusable;
- live repository, Git, filesystem, and deployment verification.

Do not create another permanent full-text copy of the rollout corpus. Any temporary analysis index belongs under the transaction staging root on `E:` and is removed after the recovery archive and handoff are verified.

### CT-5: Recovery Archive Layout

Create each transaction under:

`E:\Codex\ThreadArchives\<year>\<root-thread-id>--<safe-slug>\<timestamp>\`

The transaction contains:

- `thread-tree.7z.partial` while packing;
- `thread-tree.7z` only after successful verification;
- `manifest.json` outside and inside the archive;
- `CONTEXT_TRANSFER.md` outside and inside the archive;
- `threads.json` with selected source-tree metadata rows;
- `spawn-edges.json` with selected relationships;
- `verification.json` with 7-Zip version, exact arguments, archive hash, test result, and timestamps;
- `deletion-ticket.json` only after archive and handoff acceptance.

Archive payload paths must preserve a manifest mapping to the original locations without embedding unrelated Codex state.

### CT-6: Maximum 7-Zip Compression

Use 7-Zip format with maximum LZMA2 and solid compression. The default policy is:

- `-t7z`
- `-mx=9`
- `-m0=lzma2`
- `-mfb=273`
- `-ms=on`
- `-mmt=on`
- the largest explicitly supported dictionary that remains safe for the detected machine, with the chosen value recorded in `verification.json`

Do not silently downgrade compression. If the installed 7-Zip build cannot satisfy the selected settings, stop before deletion and report the exact incompatibility.

Run without a cancellation timeout. Long operations report progress heartbeats without terminating the compressor.

Do not stage the multi-gigabyte archive on `C:`. Build the partial archive directly under the transaction root on `E:` and atomically rename it after verification.

### CT-7: Archive Verification

Before issuing a deletion ticket:

1. Confirm every manifest-bound rollout was read at its reviewed size and hash.
2. Run `7z t` successfully against the complete archive.
3. Compute and record the archive SHA-256.
4. Verify the internal manifest and handoff hashes against the external copies.
5. Perform a bounded extraction check of representative metadata and rollout entries.
6. Confirm the destination task accepted the handoff as sufficient to continue.

Any failure leaves the original files untouched.

### CT-8: Destination Acceptance Gate

The destination task writes a structured acceptance record with:

- `handoff_ready`;
- mapped active requirements;
- evidence sources inspected;
- repository state verified;
- unresolved uncertainties;
- first continuation action.

Retirement is blocked unless `handoff_ready = true`, the archive is verified, all child agents are terminal, and there are no critical unmapped objectives.

### CT-9: Codex Archive Before Local Deletion

After destination acceptance and archive verification, archive the source root through the Codex task API and verify its archived state.

Do not interpret Codex archival as compression, offload, or proof that rollout files are recoverable. It is only the task lifecycle mutation that precedes local payload deletion.

### CT-10: Manifest-Bound Deletion Ticket

Generate a single-use deletion ticket bound to:

- source root and descendant IDs;
- reviewed absolute rollout paths;
- original size, modification time, and SHA-256 for each file;
- recovery archive path and SHA-256;
- accepted handoff hash;
- source archived-state evidence;
- ticket creation time and nonce.

Applying the ticket may delete only files listed in that ticket that still match their reviewed identity. Newly created files are ignored. Changed files are skipped and reported, not deleted.

Delete exact task-tree recall-cache artifacts only when ownership is proven. Never delete shared cache databases, unrelated threads, source repositories, worktrees, build artifacts, or user files.

The retirement remains incomplete until residual source rollout and owned cache files are zero. A later apply may handle skipped changed files through a fresh reviewed ticket.

### CT-11: Lightweight Metadata Retention

Do not delete or directly mutate selected rows in `state_5.sqlite`. The small thread rows and spawn edges remain as recovery pointers while the large rollout files are offloaded.

Export selected rows into the recovery archive for forensic reference, but do not implement arbitrary SQLite row restoration in v1.

### CT-12: Conflict-Safe Restore

Provide a `restore` command that:

- reads and verifies the external and internal manifests;
- runs `7z t` before extraction;
- checks free space at the original destination volume;
- extracts into a transaction staging directory;
- verifies every restored rollout hash;
- places files at their exact original paths only when absent;
- skips byte-identical existing files;
- fails closed on conflicting existing files;
- never overwrites a newer or different rollout;
- reports when retained metadata rows are missing instead of rewriting SQLite.

After file restoration succeeds, Codex can unarchive the source task through the task API.

### CT-13: Recovery And Safety Boundaries

- No source task deletion before verified recovery archive and destination acceptance.
- No direct mutation of Codex SQLite databases.
- No deletion based on wildcards, directory age, title, working directory, or estimated ownership.
- No recursive deletion of a broad sessions, archived-sessions, cache, project, or user root.
- No source repository or worktree content in the archive unless explicitly added by a future specification revision.
- No authentication material, session cookies, or unrelated Codex state added intentionally.
- Archive content may contain historical secrets already present in conversations; report that privacy property clearly.
- No symlinks or reparse-point traversal.
- No hard execution timeouts.

### CT-14: Public Alternative Preflight

The skills.sh scout produced only generic Codex delegation and design-skill lexical matches. No inspected candidate implemented destination-owned task-tree analysis, verified recovery packaging, archive-state mutation, and manifest-bound local deletion. A new local/public `context-transfer` family is justified.

## Public Interface

Family and package:

- Family: `families/context-transfer`
- Package: `agent-toolbelt-context-transfer`
- Skill: `context-transfer`
- Codex-only v1

Proposed helper commands:

```powershell
agent-toolbelt-context-transfer inspect `
  --source-thread-id <thread-id> `
  --archive-root "E:\Codex\ThreadArchives"

agent-toolbelt-context-transfer pack `
  --manifest <inspection-manifest> `
  --handoff <CONTEXT_TRANSFER.md>

agent-toolbelt-context-transfer verify --archive <thread-tree.7z>

agent-toolbelt-context-transfer issue-deletion-ticket `
  --verification <verification.json> `
  --acceptance <destination-acceptance.json>

agent-toolbelt-context-transfer apply-deletion --ticket <deletion-ticket.json>

agent-toolbelt-context-transfer restore --archive <thread-tree.7z>
```

The skill coordinates Codex task retrieval, destination analysis, source archival, and helper invocation. The helper owns filesystem inventory, packaging, integrity verification, ticketing, exact deletion, and restore.

## Acceptance Criteria

- The helper discovers the Apollo/Beacon fixture as 102 readable rollouts with 101 closed child edges and exactly `8,000,165,603` source bytes.
- A dry-run inventory performs no archive, task, database, or file mutation.
- The destination handoff maps every active objective and required continuation item or blocks retirement.
- Maximum-compression 7z packaging runs directly under `E:\Codex` without a cancellation timeout.
- `7z t`, archive SHA-256, internal/external manifest comparison, and representative extraction checks pass before ticket issuance.
- The deletion ticket cannot delete new, changed, unlisted, shared, or unrelated files.
- Source task archival occurs only after handoff acceptance and archive verification.
- Applying a valid ticket reclaims all unchanged manifest-bound rollout files and reports any residuals.
- Restore recreates absent original rollout paths with matching hashes and refuses conflicts.
- Codex and repository tests prove no SQLite writes and no broad recursive deletion.
- The skill is validated, installed locally, committed, merged, and synced only after all staged requirements pass with zero blockers and zero tracked deferrals.

## Authorization State

Design and planning were authorized on August 30, 2026. The user subsequently issued an explicit `continue`, authorizing the unchanged complete staged implementation without repeating design approval. Destructive retirement of a live source task remains a separate operational gate under CT-8 through CT-10.
