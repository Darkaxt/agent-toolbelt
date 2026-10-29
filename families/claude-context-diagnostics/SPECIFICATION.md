# Claude Context Diagnostics 0.1.1

Authority: user request to create a helper skill so Claude can inspect the usage and compaction data previously measured for its own thread. Installation for Claude and a versioned usable local release are authorized. This is a local diagnostic delivery; do not publish unrelated commits from the current shared branch.

R1. Self-contained standard-library Python helper and concise Claude-compatible skill, installed in the personal Claude skill directory. Identify an exact UUID using the skill's current-session substitution or an explicit caller-provided ID. Resolve only that transcript; refuse ambiguous/missing IDs. No newest-session/title/cwd guess.
R2. Read a stable byte-length snapshot of the existing JSONL, tolerating a trailing incomplete append. Deduplicate UUIDs and assistant requests; follow the latest recorded non-sidechain parent ancestry, crossing compact boundaries through logicalParentUuid. Explicitly disclose missing ancestry, unsupported records and snapshot limitations. No session mutation, inference, networking, hooks, workers, settings, model or budget changes.
R3. Bounded JSON output: latest recorded input/cache/output usage, recent completed compaction boundaries and duration/cadence, first observed input after compaction, largest tool results by characters, and observed request-input growth following tool results. Do not equate characters with tokens, summed request usage with current context, or approximate growth attribution with exact tool tokens. Missing telemetry is unavailable, never invented zero headroom.
R4. Keep raw prompt, thinking, source, tool arguments/results and credentials out of output. Tool names, UUIDs and sanitized filename basenames are diagnostic metadata; full paths are not emitted. Do not read referenced files or settings. Retain no transcript cache. Output is historical telemetry as of the recorded response, not a live context meter or effective-window proof.
R5. Skill invocation must help reduce context churn: run on demand or at a meaningful workflow checkpoint, preserve required review coverage, use local exhaustive checks and targeted excerpts, concise existing checkpoints and targeted recovery. No diagnostic polling or new generic framework. State that running Claude sessions may need to load the newly installed SKILL.md explicitly; installation alone is not proof of use.
R6. Verify fictional branch/duplicate/cache/missing/partial/privacy cases, bounded output, source nonmutation, and a passive exact Skyrim transcript report. Produce a versioned bundle, commit only task changes, install Claude copy, compare hashes and independently run the installed helper. Preserve all unrelated files and existing fork/live service state.

## Stages and reconciliation

1. Implement and verify the complete diagnostic workflow (R1-R5, test portion of R6): COMPLETE. Focused behavioral fixtures, layout/portability checks, skill validator and passive exact-session report inspected. Attachment ancestry is supported; historical graph cycles are disclosed. Raw content is excluded and existing transcript remains read-only.
2. Commit, versioned local release, Claude installation and delivery verification (remaining R6): COMPLETE. installation-0.1.0.json and DELIVERY.md verify the original delivery; installation does not establish running-agent adoption.

## Independent validation repair, 29 October 2026

User explicitly requested fixing the three reproduced defects. The original
0.1.0 installation is verified by installation-0.1.0.json and DELIVERY.md; its
original delivery stage is complete. Preserve that immutable release for rollback.

R7: Invalid non-null parent references must be disclosed and selected invalid
ancestry must not be called complete. Unknown trailing record types must not
replace the supported mainline leaf or erase valid usage; disclose skipped types
and retain parent bridges needed by later supported records. Out-of-range UTC
timestamp conversion must produce unavailable timestamp metadata and a warning,
never an unhandled traceback or raw path output. Preserve R1-R6/privacy limits.

R8: Deliver 0.1.1 with regression coverage and an independently executed installed
helper. Upgrade only an existing bundle whose complete manifest and bytes match
the retained prior release; preserve local edits, extra files and concurrent
writers. No deletion of unknown files, settings changes or running-session restart.

1. Diagnostic correction and regression verification — COMPLETE (R7). The new
   regressions reproduced all defects before repair and now pass, including
   retained unknown ancestry bridges. The passive exact Skyrim report succeeds,
   retains usage and discloses its real historical cycle. Privacy/nonmutation and
   existing behavior pass. No required consolidation or tracked deferrals.
2. Verified local upgrade and delivery — COMPLETE (R8). Verified existing-file
   upgrade support passes exact-byte, local-edit, writer-lock and failed-write
   restoration checks. Release 0.1.1 is delivered from source
   92b5657db54e191540a71b3eedd7d0b1e5824aa9, installed and hash-verified. The
   installed CLI passes all three original failure probes and reads the actual
   exact Skyrim transcript, preserving its real historical cycle warning.
   Source/release/installed helper SHA-256 matches:
   ec5490549ff73098881024b5e84a746025378e69e6f391da8ef376cc6d60d0b1.
   installation-0.1.1.json, installed-regressions-0.1.1.json and
   installed-skyrim-report-0.1.1.json are retained under the private release root.
   Cleanup ce7079676d798b62912995879ff48292 is applied without errors;
   the exact repair scratch root is absent. No blockers, deferrals or required
   consolidation remain. No live Claude session was restarted or messaged.
   Only source commits belonging to this skill may be synchronized; preserve
   unrelated shared-branch work. Scratch: E:/Temp/claude-context-repair-20261029.

Verification limit: the repository-wide skills.sh wrapper stops on a pre-existing non-generic path in context-transfer/SKILL.md line 21, outside this task. Do not modify that unrelated skill. This does not invalidate the focused skill/frontmatter/layout/portability checks or the specified local delivery channel; no public default-branch release is claimed.

No blockers or tracked deferrals. Existing source repository is clean at task start on codex/android-cleanup-tickets; its 34 branch-only commits and one main-only commit are outside this task and must survive. Test scratch: E:/Temp/claude-context-diagnostics-20261029, expendable after focused verification and subject to transactional cleanup. The pinned skills CLI's small-file dependency cache uses D:/Temp/claude-context-diagnostics-20261029/npm-cache for active I/O, avoiding new C: cache data; clean it immediately after validation. Private release/receipt storage: D:/Tools/claude-context-diagnostics. No application restart or real inference is required.

Discovery: installed context-transfer/recall tools do not provide Claude usage diagnostics. Public scout results are retained privately with the originating investigation; broad matches concern other platforms, narrow compaction candidates were irrelevant or unavailable. No third-party skill installed.
