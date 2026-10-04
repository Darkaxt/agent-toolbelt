from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys


def bootstrap():
    configured = os.environ.get("AGENT_TOOLBELT_HOME")
    if configured:
        source = Path(configured) / "families/gradle-build-gate/src"
        if not (source / "agent_toolbelt_gradle_build_gate").is_dir():
            raise RuntimeError("AGENT_TOOLBELT_HOME does not contain gradle-build-gate")
        sys.path.insert(0, str(source))
        return
    for parent in Path(__file__).resolve().parents:
        source = parent / "families/gradle-build-gate/src"
        if (source / "agent_toolbelt_gradle_build_gate").is_dir():
            sys.path.insert(0, str(source))
            return
    root = Path(os.environ.get("GRADLE_BUILD_GATE_HOME", str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Tools/gradle-build-gate")))
    active = json.loads((root / "active.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"[0-9a-f]{16}", active["release"]):
        raise RuntimeError("Invalid Gradle gate runtime pointer")
    source = root / "releases" / active["release"]
    if not (source / "agent_toolbelt_gradle_build_gate/cli.py").is_file():
        raise RuntimeError("Installed Gradle gate runtime is incomplete")
    sys.path.insert(0, str(source))


if __name__ == "__main__":
    try:
        bootstrap()
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(json.dumps({"ok": False, "failure_kind": "runtime_unavailable", "error": str(exc)}))
        raise SystemExit(2)
    from agent_toolbelt_gradle_build_gate.cli import main
    raise SystemExit(main())
