# Lifecycle-Specific Actions

For every row below establish authority, current activity, exact membership,
preservation needs and verification. Execute supported operations when these
conditions pass; do not merely repeat the inventory in the final report.

| Area | Action | Preservation and completion evidence |
| --- | --- | --- |
| Generated build/temp/browser/media output | Review narrow inactive output with transactional-cleanup; apply its exact ticket | Preserve deliverables, inputs, source, signing material and needed diagnostics. Report partial members and actual deleted bytes. Never scan all Temp by default. |
| Gradle distributions and versioned caches | Use read-only gradle-build-gate inventory/cleanup-plan and project registrations; migrate compatible owners first | Recheck live references, reservations and daemon identities. Cleanup must NOT acquire the build mutex or join its queue. Use exact-target cleanup coordination and safe native lifecycle or owner coordination; skip active/ambiguous consumers and preserve shared targets if safe retirement cannot be established. Never blanket-delete modules, kill daemons or use gradle --stop. |
| Android SDK/NDK/platform/build-tools/system images | Map ndkVersion, compileSdk, buildToolsVersion, SDK paths, CI pins, native requirements and AVD image references. Verify compatible owner upgrades, then use sdkmanager --uninstall with exact package IDs | Installed newest is not universal compatibility. Preserve required platforms/images, licenses, offline needs and active consumers. Re-list installed packages and verify required focused builds/boots. |
| Emulator snapshots | Identify exact AVD and native snapshot list; confirm emulator inactive or use supported live management. Remove only reviewed obsolete snapshot through Android's supported UI/console lifecycle | Snapshot file age/size is not application-data expendability. Preserve userdata and required restore points. Review Quick Boot/save behavior to stop repeated growth. Whole AVD removal is separate authority; verify necessary boot behavior. |
| Project validation clones/worktrees | Inspect git status/worktree list and owner; remove only obsolete generated subtrees | Linked worktrees require Git removal with clean-state/ownership proof. Do not apply disposable-clone authority to an active worktree. Preserve validation receipts required for release proof. |
| npm/pnpm/uv/NuGet/Go/Playwright caches | Inspect active consumers, configured cache location and offline requirements; use manager-native prune/clean for confirmed unused content | Do not assume every cached package/browser is unused. Obtain current command semantics from installed help. If only whole-cache deletion is offered, explicitly assess reinstall/offline cost and authority first. Version directories need reference checks. |
| Scoop/download archives | Check current links, installed manifests, persistence and rollback needs; use supported cleanup of superseded versions and download cache | A directory timestamp or duplicate version is not proof. Do not remove persist or current targets. Verify installed executables and current resolution. |
| NVIDIA | Separate installer/download cache, shader cache, installed driver, CUDA toolkit and Nsight components | Installer leftovers may be reviewed with inactive-installer evidence. CUDA consumers require compatibility/owner migration before supported uninstall. Do not manually remove live driver directories or unify driver and toolkit versions. |
| Codex/Claude histories | Use context-transfer for verified off-drive archive and exact inactive source retirement with a summary ledger | Archive timestamp is not last activity. Include all resumed segments and children. Rollout offload does NOT remove paginated SQLite history. Unsupported database retirement remains explicitly blocked; no direct SQL delete/VACUUM on the running app. |
| Helper state | Use native status, finish/reconcile individually obsolete transactions and retain required recovery runtime | A large live database or old release is not automatically trash. Busy state is not a reason to revoke or unlink databases. Follow native compaction/retention; no repeated blind retries. |
| WSL VHD/persistent app data/mods | Prefer supported offline relocation/compaction or explicit user-content move to another drive | Preserve data/configuration and provide a tested recovery route. Do not move a running VHD manually. Installed Packages directories may legitimately be old. |
| Windows Installer/WinSxS/DriverStore/package repair cache | Supported servicing/uninstall tools only, under explicit applicable scope | Never generic cleanup. Do not turn OS access denial into guessed authority or take ownership of system stores. |

## Prevent Recurrence

Gradle activity is scoped to the exact version under review. An identified build
using one version does not require waiting before reviewing another obsolete
version. Migrate owners only when they actually reference the proposed retirement
target. Diagnose unbound clients or incomplete identity/connection inspection;
never invent global non-use from the helper's known-project catalog. Preserve
referenced/live artifacts and recheck immediately before ticket application.

For an authorized retention/relocation change, record the old and new settings,
consumers, activation boundary and verification. Prefer task-owned outputs on a
non-system drive, explicit cache-location settings and supported cache-retention
APIs over symlinks. A Gradle retention script must support the installed versions;
do not copy a newest-version API into older Gradle init scripts blindly. Do not
start a background cleaner or modify another task's project configuration.

Measure growth and free space again after required verification. A reclaimed
snapshot can refill on the next emulator exit; verify the applicable save policy,
not only that one deletion succeeded.

## Primary References

- [Gradle cache layout, configuration and cleanup](https://docs.gradle.org/current/userguide/directory_layout.html)
- [Android emulator snapshot lifecycle](https://developer.android.com/studio/run/emulator-snapshots)
- [Android sdkmanager package management](https://developer.android.com/tools/sdkmanager)
- [WSL virtual disk management](https://learn.microsoft.com/en-us/windows/wsl/disk-space)

Check installed versions and current official documentation before choosing an
operation; these references do not grant deletion authority.
