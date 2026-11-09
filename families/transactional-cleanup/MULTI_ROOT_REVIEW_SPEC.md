# Exact-once multi-root review repair

Authority: standing proactive availability/data-integrity repair; this is a
cleanup dependency of Coordinator's active Rust parity stage, not a new active
implementation stage or authorization to remove additional files.

Observed failure: installed 0.9.0 returned SQLITE_CONSTRAINT_UNIQUE (2067) during
review when explicit leaf roots were followed by an ancestor registration.
Registration adds an uncovered path to the scan inventory; an ancestor therefore
overlaps existing roots. The streaming scanner emits those members twice, while
the signed manifest correctly requires one row per path. No ticket/deletion
occurred. The broadened unissued transaction was discarded through the helper.

Required correction and acceptance:

- Each canonical path is emitted once when roots overlap or have aliases, with
  memory bounded by the number of roots rather than inventory size.
- Preserve registration's existing root-extension semantics and actual coverage;
  do not silently narrow scope, ignore SQL uniqueness errors or weaken signatures.
- Registration/status/review coverage must show any newly added root. A focused
  reproduction confirmed that 0.9.0 kept reporting only the initial leaf roots.
- Enumeration failures must produce one excluded observation for that directory,
  rather than a metadata row followed by a duplicate error row.
- Preserve all identity/content, ancestry, Git, exact-member, reparse/hardlink,
  expiry and concurrent-new-file protections.
- Reproduce the overlap/scan-failure signatures first, run affected scanner/state
  checks plus the complete cleanup regression suite after correction, and verify
  the normal installed Codex/shared/Claude runtime and skill copies.
- Deliver a versioned local 0.9.1 helper through its established installer,
  commit/synchronize only this family repair through the existing toolbelt remote,
  record installed hashes and repeat the original bounded cleanup with exact
  leaf registrations. Preserve all unrelated dirty work and live transactions.

Task-owned intensive/SQLite scratch is under
D:/Temp/coordinator-rust-migration-20261107/cleanup-repair-tests. Retained repair
evidence belongs to D:/Tools/llm-coordinator/verification/20261107/rust-migration.
No new public destination, provider, global environment change or rollback copy
is required.

Verification: both original failure mechanisms were reproduced before the fix.
The complete cleanup regression suite passed (172 run, nine platform skips).
After correcting coverage reporting, the affected cleanup/state suite passed
(82). The normal installer activated 0.9.1; all installed runtime hashes and
Codex/shared/Claude skill/reference/launcher copies matched canonical content.
Actual launcher resolution and help succeeded from all three roots. The repaired
installed helper reviewed and applied the exact replacement leaf transaction:
43 signed members, 387,571 logical bytes, no exclusions or errors. The earlier
broadened transaction was discarded with no target deletion. Private installation,
inspection and source-delivery records are retained in the verification folder
above; source synchronization uses this family's existing Git/tag channel.
