---
name: adb-archive-transfer
description: Use for reliable bulk ADB file transfer to Android devices when many tiny files should be packed together without compression, larger files should remain unchanged, multiple connected endpoints must be disambiguated, or a reviewed manifest should bind source files, destination, device identity, hashes, staging, and cleanup.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows/local CLI oriented. Requires ADB; tiny-file bundling requires 7-Zip or NanaZip with a 7z-compatible command.
---

# ADB Archive Transfer

Use `scripts/invoke_adb_archive_transfer.py` for endpoint-bound, manifest-driven transfers. The helper never selects arbitrarily among multiple ready ADB endpoints and never merges into or replaces an existing destination.

## Required Workflow

1. Run `devices` and inspect every connected endpoint, state, model, identity hash, and transfer capability.
2. Run `plan` with the intended source and previously absent destination. Add `--serial` whenever more than one endpoint is ready.
3. Review the returned manifest path and its device, destination, file partition, bundle count, hashes, and capacity evidence.
4. Run `apply --manifest <path> --confirm-transfer` only after that manifest is approved. Existing user authorization to execute the reviewed transfer counts; do not ask again for the same scope.
5. Inspect `verified`, `placed`, and cleanup fields before claiming success.

Do not combine planning and application into one opaque command. Planning is read-only on the device. Applying mutates only the manifest-bound destination and staging roots.

## File Policy

- Files at or below 64 MiB are tiny-file bundle candidates.
- A lone tiny file transfers directly because an archive has no batching value.
- Tiny files are grouped into bounded TAR archives created by 7-Zip with `-ttar` and no compression option.
- Files above 64 MiB and below 1 GiB transfer directly.
- Files at or above 1 GiB always transfer unchanged and directly.
- The default uncompressed bundle cap is 4 GiB.
- TAR is used because Android Toybox can extract it without requiring 7-Zip on the device.

Do not add compression unless the user explicitly changes the contract. Packaging is for tiny-file transfer efficiency, not size reduction.

## Endpoint Safety

- Never guess a device when multiple endpoints are in `device` state. Stop with `ambiguous_device`, show candidates, and require `--serial`.
- Treat `offline` and `unauthorized` endpoints as not ready.
- Every device-specific ADB command must use the manifest serial through `adb -s <serial>`.
- The manifest binds stable device identity fields, not only transient `transport_id`.
- If endpoint identity changes before apply or cleanup, fail closed.
- Do not run `adb kill-server`, restart a device, dismiss authorization UI, or use `taskkill` as recovery.

## Transaction Safety

- The destination must be an absolute non-protected path, its parent must exist and be writable, and the destination itself must not exist.
- The manifest records only files present during planning. Files created later are ignored rather than silently added.
- If a listed file is missing or changed, application fails before remote staging or push.
- Direct files and extracted bundles stay in a transfer-specific staging directory until all listed files pass SHA-256 verification.
- Placement happens only after complete verification.
- `cleanup --confirm-cleanup` removes only the exact manifest-owned local and remote staging roots. It never removes the source or final destination.
- Do not use symlinks/reparse points, generic recursive cleanup roots, wildcards, or unbounded timeouts.

## Commands

```powershell
python scripts\invoke_adb_archive_transfer.py devices

python scripts\invoke_adb_archive_transfer.py plan `
  --source "<source-path>" `
  --destination "<absolute-device-destination>" `
  --serial <serial>

python scripts\invoke_adb_archive_transfer.py apply `
  --manifest "<manifest-path>" `
  --confirm-transfer

python scripts\invoke_adb_archive_transfer.py cleanup `
  --manifest "<manifest-path>" `
  --confirm-cleanup
```

Use `--keep-manifest` on apply only when retaining the completed transaction record is useful. Runtime manifests and TAR files belong under the helper's local temp root, not in the repository or skill folder.

## Result Interpretation

- `ambiguous_device`: more than one ready endpoint; rerun the same plan with an explicit serial.
- `device_not_ready` or `device_identity_changed`: do not push; resolve the endpoint state first.
- `source_changed`: create a new plan. Do not weaken snapshot validation.
- `destination_exists`: select a new absent destination; v1 intentionally does not merge or replace.
- `insufficient_space`: reduce scope or free space before making a new plan.
- `remote_hash_mismatch` or `verification_failed`: final placement did not occur; retain the manifest for diagnosis or exact staging cleanup.

Do not claim success from `adb push` output alone. The supported completion contract is a verified payload placed at the exact destination with staging cleanup reported.
