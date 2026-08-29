# ADB Archive Transfer Design

## Goal

Provide a deterministic, manifest-driven helper for transferring a directory tree to one explicitly identified Android endpoint. Reduce per-file ADB overhead by packing only tiny files into uncompressed TAR bundles, transfer larger files unchanged, verify every payload on-device, and clean only helper-owned staging after successful placement.

## Public Commands

- `devices`: inventory connected ADB endpoints and report readiness, stable identity, transport metadata, and extraction/hash capabilities.
- `plan`: scan one source file or directory, resolve exactly one destination endpoint, classify files, validate the remote parent and capacity, and write a transfer manifest.
- `apply`: revalidate the manifest, endpoint, source snapshot, destination, and capacity; stage and verify the transfer; then place the destination.
- `cleanup`: remove only the local and remote staging roots named by a manifest after endpoint identity validation.

`plan` is read-only except for its local manifest file. `apply` requires `--confirm-transfer`. `cleanup` requires `--confirm-cleanup`.

## Endpoint Contract

The helper runs `adb devices -l` and never relies on the first endpoint, `ANDROID_SERIAL`, `adb -d`, or `adb -e`.

- Zero ready devices returns `device_unavailable`.
- One ready device may be selected automatically.
- More than one ready device requires `--serial` or a configured explicit alias; otherwise return `ambiguous_device` with candidates.
- Every ADB command includes `-s <serial>`.
- The manifest records ADB serial, Android `ro.serialno`, model, product/device, build fingerprint, state, and transport id.
- The stable identity hash excludes transport id so an ordinary reconnect does not invalidate the physical endpoint, but `apply` must reproduce the stable identity hash before mutation.

## File Classification

Defaults use binary units:

- Tiny: `size <= 64 MiB`; eligible for uncompressed TAR packing.
- Medium: `64 MiB < size < 1 GiB`; transfer directly.
- Large: `size >= 1 GiB`; always transfer directly and unchanged.

A single tiny file transfers directly because packing provides no per-file benefit. Multiple tiny files are sorted by normalized relative path and split into TAR bundles capped at 4 GiB of source payload. TAR is created with 7-Zip (`7z a -ttar`) and no compression. The helper must not create `.7z`, gzip, xz, bzip2, or compressed TAR payloads.

Symlinks, junctions, tabs/newlines in relative paths, duplicate case-insensitive relative paths, and files escaping the source root are rejected.

## Manifest

The JSON manifest contains:

- schema version, transfer id, creation time, source root, source kind, and source snapshot hash;
- selected endpoint identity and stable identity hash;
- normalized absolute remote destination, parent, and helper-owned staging root;
- thresholds and archive mode;
- every file's relative path, size, mtime nanoseconds, SHA-256, transfer mode, classification reason, and optional bundle name;
- bundle membership and estimated TAR bytes;
- capacity estimate and capability diagnostics;
- local manifest and staging locations under `D:\Temp\adb-archive-transfer` by default.

`apply` hashes the canonical manifest content and rechecks every source file's size, mtime, and SHA-256. Files created after planning are ignored because they are absent from the manifest. Changed or missing listed files fail closed before device mutation.

## Remote Transaction

The destination must be absolute, have an existing writable parent, and must not be a protected root such as `/`, `/system`, `/vendor`, `/product`, `/data`, `/storage`, `/sdcard`, or `/mnt`. The destination must not already exist in v1.

`apply` performs these phases:

1. Revalidate endpoint identity, extraction/hash capabilities, destination absence, and free space.
2. Create a unique sibling staging directory named `.adb-archive-transfer-<transfer-id>`.
3. Build uncompressed TAR bundles under the local staging root.
4. Push direct files and TAR bundles into the remote staging root.
5. Verify each pushed TAR SHA-256 before extraction.
6. Extract TARs with `toybox tar --restrict -xf` into the staged payload.
7. Push a verification manifest and verify every staged file with `toybox sha256sum -c`.
8. Move the verified staged payload to the absent final destination.
9. Remove the now-empty helper-owned remote stage, local archives, and manifest unless retention was explicitly requested.

No source file is deleted or modified. A failure before final placement leaves the exact helper-owned stage and reports recovery paths. A failure after final placement must never remove the destination.

## Capacity

Planning estimates remote peak usage as direct bytes plus packed source bytes plus estimated TAR bytes. Applying recalculates with actual TAR sizes before the first push. Insufficient capacity fails before remote staging creation.

## Process Model

No cancellation timeout is used. Long-running subprocesses run to completion while progress messages may be emitted to stderr as heartbeats; stdout remains one final JSON document.

## Public-Skill Preflight

The skills.sh scout found generic ADB command/reference skills but no inspected candidate implementing endpoint-bound manifests, uncompressed tiny-file bundling, transactional staging, extracted-file hash verification, and helper-owned cleanup. This family is therefore differentiated rather than a duplicate public install.
