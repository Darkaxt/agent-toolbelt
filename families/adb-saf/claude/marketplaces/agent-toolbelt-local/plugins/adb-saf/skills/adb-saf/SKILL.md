---
name: adb-saf
description: Read and change files inside Android apps' documents providers (Storage Access Framework, SAF) over ADB, such as launcher, emulator or file-manager app storage exposed as content://AUTHORITY/document/... Use before concluding that app-private or scoped storage is inaccessible over ADB; lists providers, roots and directories, hashes and pulls documents, and applies reviewed put/mkdir/rename/delete plans with backups and hash verification.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows host with ADB; Android 10 (API 29) or newer.
---

# ADB SAF

Many apps expose their private storage (for example `/data/user/0/<package>`)
through a documents provider. `run-as`, `adb pull` and `/sdcard` paths cannot
reach it, but the provider often answers the ADB shell user directly.

**Before saying app storage is inaccessible, try this helper.** Run `providers`
and `roots`/`ls` on the relevant authority. Report "inaccessible" only with the
actual `failure_kind` it returned (for example `permission_denied`). The
platform's own ExternalStorageProvider refuses the shell user by design. Shared
storage is reachable through plain `adb` paths, so this helper is for app-owned
providers.

## Addressing

Targets are `AUTHORITY:DOCUMENT_ID`, split at the first colon. Take document IDs
from `roots`/`ls` output; never build them by hand. `--path a/b` walks child
display names below a target. The helper URI-encodes IDs itself.

## Read-only commands

```powershell
python scripts\invoke_adb_saf.py providers            # authorities, component, access, roots
python scripts\invoke_adb_saf.py roots <authority>
python scripts\invoke_adb_saf.py ls <authority>:<document-id> [--path sub/dir]
python scripts\invoke_adb_saf.py stat <authority>:<document-id>
python scripts\invoke_adb_saf.py sha256 <authority>:<document-id>     # hashed on the device
python scripts\invoke_adb_saf.py pull <authority>:<document-id> --output D:\Temp\<task>\file
```

`pull` writes only to an absent path. It checks the host hash against the
device-side hash and the provider-reported size.

## Changes: plan, review, apply

```powershell
python scripts\invoke_adb_saf.py plan put --source <file> --target <authority>:<id> --manifest D:\Temp\<task>\put.json
python scripts\invoke_adb_saf.py plan put --source <file> --parent <authority>:<dir-id> --name <name> --manifest ...
python scripts\invoke_adb_saf.py plan mkdir --parent <authority>:<dir-id> --name <name> --manifest ...
python scripts\invoke_adb_saf.py plan rename --target <authority>:<id> --parent <authority>:<dir-id> --name <new> --manifest ...
python scripts\invoke_adb_saf.py plan delete --target <authority>:<id> --manifest ...
python scripts\invoke_adb_saf.py apply --manifest <same path> --confirm
```

- `plan` is read-only. It records the device identity, the source hash, the
  target's metadata and hash, and the absence of the new name. Review the JSON
  and its `warnings` before applying. Existing user authorization for the change
  covers `apply`; don't ask again for the same scope.
- `apply` refuses on any drift: a different device, a changed source, a changed
  target (metadata or hash), a name that has appeared, or a directory that is no
  longer empty. It applies once; a plan marked `applied` is spent.
- Overwrite and delete first pull the current content into
  `<manifest>.backup/` and verify it against the planned hash. Keep that backup
  until the user no longer needs it.
- `delete` removes files and empty directories only.
- The result is verified independently: content hash, new name, or absence.
  A failed create-then-write deletes only the document it created.
- Mutations run a small bundled client (`saf-client.dex`) through `app_process`
  as the shell user. It is staged in `/data/local/tmp/adb-saf-<plan>` and
  removed after every apply. It has no privileges beyond the shell user's.

Keep manifests, backups and pulls in a task-owned `D:\Temp\<task>` folder. The
helper never chooses a default location.

## Endpoint binding

With several ready devices, pass `--serial`; the helper never guesses. Inside a
Coordinator device reservation the gate binds the transport. Don't pass
`--serial` or `--adb` there.

## Coordinator device reservations

USB access keeps the existing task authorization. Wireless devices, and any
device another workflow holds, go through the Android device gate (installed
android-emulator-gate skill, references/physical-devices.md). Inside a
reservation, run this helper as `device.helper.start` with
`{"helper":"saf","arguments":["ls","<authority>:<id>"]}` and the same
subcommands as above. Inside an emulator lease, use `emulator.helper.start`
with the same parameters. The gate supplies the bound transport or serial. Never set the
lease environment variables yourself or bypass a rejection with direct ADB.
