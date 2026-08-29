# ADB Archive Transfer

Manifest-driven transfer of a reviewed local file tree to one explicitly identified Android endpoint. The helper packs only tiny files into uncompressed TAR bundles, transfers larger files unchanged, verifies staged content by SHA-256, and places a previously absent destination only after complete verification.

The implementation is intentionally fail-closed around ambiguous devices, source drift, unsafe destinations, insufficient capacity, existing destinations, missing device capabilities, and unconfirmed mutation.

## Usage

```powershell
uv run --project families/adb-archive-transfer agent-toolbelt-adb-archive-transfer devices

uv run --project families/adb-archive-transfer agent-toolbelt-adb-archive-transfer plan `
  --source "<source-path>" `
  --destination "<absolute-device-destination>" `
  --serial <serial>

uv run --project families/adb-archive-transfer agent-toolbelt-adb-archive-transfer apply `
  --manifest "<manifest-path>" `
  --confirm-transfer
```

`plan` inventories and hashes source files, selects or verifies the endpoint, checks destination capacity, and writes a manifest without creating remote content. `apply` revalidates the listed source files and endpoint before creating staging or pushing data.

Default transfer policy:

- Files up to 64 MiB may be grouped into uncompressed TAR bundles.
- A lone tiny file transfers directly.
- Files above 64 MiB transfer directly.
- Files at or above 1 GiB are always direct and unchanged.
- Bundles are capped at 4 GiB by default.

## Agent integrations

- Codex skill: `codex/skills/adb-archive-transfer`
- Claude marketplace: `claude/marketplaces/agent-toolbelt-local`

Runtime manifests and archives are written beneath `D:\Temp\adb-archive-transfer` by default and are not repository artifacts.
