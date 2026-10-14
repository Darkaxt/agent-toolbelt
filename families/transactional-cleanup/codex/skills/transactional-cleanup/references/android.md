# Android Task Cleanup

Read this reference before using the `adb-*` commands. These are a separate
backend in the installed transactional-cleanup helper; do not feed Android paths
to Windows `begin/register/apply`. No device changes are authorized merely by
installing or testing this capability.

## Authority And Scope

Use only for exact disposable files created or copied for the current task and
test apps installed for that task. Existing task authorization covers its
expendable test cleanup; the ticket is not a second user approval. Do not infer
authority for unrelated ROMs, saves, original APKs, user files or installed apps.
An unsupported mode is not a policy rejection. Do not use these commands to
evade a deletion that was actually denied by command policy.

Select the authorized endpoint explicitly with `--serial`; do not guess among
connected devices. The helper discovers SDK ADB or accepts `--adb-path`. Every
device command uses the bound serial and checks hardware serial, fingerprint and
model. A changed/offline/unauthorized endpoint blocks application.

Stop task-owned producers before review/application. Do not stop someone else's
process, restart ADB, request root, or race a concurrent installer. Stat/hash and
ancestor checks narrow ordinary races; ADB shell unlink is NOT Windows
handle-bound deletion and is not an adversarial filesystem sandbox. Report this
boundary honestly. A host mutex cannot prevent arbitrary Android-side writers.

## Exact File Tickets

Use one exact task-owned top-level directory under `/storage/emulated/0`, for
example `/storage/emulated/0/RShopS12Reference-20261014`. Broad roots, standard
user-data directories, Android app-data paths, traversal, links and special
objects are protected. The inventory is capped at 10,000 members; narrow scope
rather than scanning all storage. Only ordinary files and directories qualify.

Run these as separate invocations through the installed wrapper:

```text
adb-review --serial <serial> --root <task-directory> --owner-task "<operation>" --evidence "<producer command and disposable purpose>"
adb-inspect --transaction <id> --offset 0 --limit 100
adb-ticket --transaction <id> --manifest-sha256 <separately-inspected-review-hash>
adb-apply --ticket <id> --dry-run
adb-apply --ticket <id>
adb-status --transaction <id>
```

Page `adb-inspect` until all members have been reviewed. Review captures exact
paths, stat identity/metadata and SHA-256. Apply rechecks device, reviewed
directory ancestry, regular-file identity and content. Modified/replaced members
and new concurrent files survive independently; no recursive remove is used.
Only reviewed unchanged-identity empty directories are removed. Dry-run
`would_remove_if_empty` does not promise a directory will become empty.

Inspect structured `counts`, `deleted_bytes`, `state`, `failure_kind` and
`last_error`. A partial apply is not completion. Retry a valid ticket after its
concrete lock/consumer condition resolves; changed content needs a new review.
New concurrent files require their own attribution/review, never a directory sweep.
After abrupt termination, a checkpoint may undercount removed bytes; already
missing members are reported as missing, not newly reclaimed bytes.

Use `adb-revoke --ticket <id>` to abandon unresolved ticket work, or
`adb-discard --transaction <unissued-id> --reason "<why>"` for an unused
review/baseline. Terminal records retain compact summaries, not full inventories.
`state-inventory` includes Android state size and unresolved transactions.
Overlapping targets coordinate through cleanup's existing root claims; disjoint
targets can proceed independently. Never acquire the Gradle build gate.

## Task-Installed Test Apps

Before installing a temporary app, record its absence and the SHA-256 of EVERY
intended APK (repeat the hash flag for split APKs):

```text
adb-package-baseline --serial <serial> --package <exact.package.id> --apk-sha256 <sha256> --owner-task "<test>" --evidence "<temporary test installation purpose>"
```

The baseline checks all enumerated Android users, including retained/uninstalled
packages. Pre-existing packages/data are ineligible. Install the APK only under
the original task's device authority; this helper does not install apps.

After testing, stop task consumers and review:

```text
adb-package-review --transaction <baseline-id>
adb-inspect --transaction <baseline-id>
adb-ticket --transaction <baseline-id> --manifest-sha256 <reviewed-hash> --confirm-test-app-data
adb-apply --ticket <id> --dry-run
adb-apply --ticket <id>
```

The reviewed app must belong exclusively to user 0, be non-system, and match the
planned APK hashes. Installed APK paths, identities/hashes and install/update
metadata bind application; updates/reinstalls preserve the package instead of
silently removing it. Uninstall is scoped to user 0 and verifies absence from
that user's installed-package list. It deletes test app data; there is no backup,
restore, force-stop or separate data-clear operation.

If testing already installed an app WITHOUT a recorded absence baseline, do not
invent one retrospectively or claim task attribution from a package name alone.
Report the missing provenance and obtain a separately scoped removal decision
when the original task evidence cannot establish it. Do not erase an original
installation or upgrade to make a new baseline possible.
