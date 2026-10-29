---
name: f3d-viewer
description: Prefer F3D for read-only visual inspection and previews of existing 3D models. Use gated Blender for native scene evaluation, rig or animation measurements, and editing.
license: MIT
metadata:
  version: "0.1.1"
  compatibility: Installed F3D; examples use its Windows console frontend. Blender analysis requires the existing blender-gate skill.
---

# Inspect existing 3D models

For appearance, shape, textures, orientation or a quick preview, use **F3D first**.
Do not start Blender merely to look at a supported mesh. For native `.blend`
evaluation, procedural geometry, rig/constraint diagnosis, measured animation
analysis or edits, use the installed `blender-gate` instead. Read
[measured Blender inspection](references/blender-inspection.md) for those cases.

Resolve the existing executable with `Get-Command f3d-console.exe`; on Windows
also check `%ProgramFiles%/F3D/bin/f3d-console.exe`. The console frontend returns
usable diagnostics; `f3d.exe` is the GUI frontend. Check `--version`, `--help`
and `--list-readers` for the installed build; format support varies by plugins.
Use the existing installation, not a project-vendored DLL or a new downloaded tool.

For automated reading, prefer load-only diagnostics or an offscreen PNG:

```powershell
$f3d = Join-Path $env:ProgramFiles 'F3D/bin/f3d-console.exe'
& $f3d --no-config --no-cache --no-render --verbose=info '<model.glb>'
& $f3d --no-config --no-cache --resolution=1280,720 --output='<preview.png>' '<model.glb>'
```

These flags are available in F3D 4.0; verify older builds before invoking them.
Use new explicit output paths in task scratch, retain the native process through
exit, inspect diagnostics and actually view the PNG before making visual claims.
**Exit code 0 is not proof of success:** F3D 4.0 can return it for missing inputs.
Confirm each intended input exists before launch. Missing inputs or reader errors
mean failure regardless of the exit code. Load-only checks need positive evidence
that the intended model loaded. For previews, require a newly created, nonempty,
decodable image at the exact requested path; an old image is not evidence of this
run. Inspect that image and report relevant texture/scene warnings as incomplete
coverage rather than an unqualified pass.
Use another camera angle when the question cannot be answered from one view.
Keep source models and their relative texture/material dependencies intact.
Missing textures, reader errors or incomplete scene support are limitations to
report, not proof of a broken source asset. A preview is not a rig/physics test.

Open the GUI only when interactive viewing is wanted. `--no-config` and
`--no-cache` isolate these inspections from saved viewer preferences. Do not
overwrite models, export conversions or change global file associations as part
of reading. Use normal owned-artifact cleanup after the viewer exits. If F3D
cannot answer the question, explain the specific gap and use the existing Blender
gate; do not add Flue/MCP services or bypass gate ownership.

Official [options](https://f3d.app/docs/user/OPTIONS/) and
[reader/format coverage](https://f3d.app/docs/user/SUPPORTED_FORMATS/).
