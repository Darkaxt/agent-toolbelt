"""Resolve the shared installed runtime; no automatic installation or elevation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys


def bootstrap():
    configured = os.environ.get("AGENT_TOOLBELT_HOME")
    if configured:
        source = Path(configured) / "families/windows-elevation-gate/src"
        if not (source / "agent_toolbelt_windows_elevation_gate/cli.py").is_file():
            raise RuntimeError("AGENT_TOOLBELT_HOME lacks windows-elevation-gate")
        sys.path.insert(0, str(source))
        return
    for parent in Path(__file__).resolve().parents:
        source = parent / "families/windows-elevation-gate/src"
        if (source / "agent_toolbelt_windows_elevation_gate/cli.py").is_file():
            sys.path.insert(0, str(source))
            return
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Tools/windows-elevation-gate"
    active = json.loads((root / "active.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"[0-9a-f]{16}", active["release"]):
        raise RuntimeError("Invalid elevation runtime pointer")
    source = root / "releases" / active["release"]
    if not (source / "agent_toolbelt_windows_elevation_gate/cli.py").is_file():
        raise RuntimeError("Installed elevation runtime is incomplete; run the family installer")
    sys.path.insert(0, str(source))


if __name__ == "__main__":
    try:
        bootstrap()
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(json.dumps({"ok": False, "failure_kind": "runtime_unavailable", "error": str(exc)}))
        raise SystemExit(2)
    from agent_toolbelt_windows_elevation_gate.cli import main
    raise SystemExit(main())
