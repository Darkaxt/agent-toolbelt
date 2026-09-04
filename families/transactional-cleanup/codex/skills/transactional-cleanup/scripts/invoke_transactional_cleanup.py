from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
PACKAGE = "agent_toolbelt_transactional_cleanup"


def source_root():
    override = os.environ.get("AGENT_TOOLBELT_HOME")
    if override:
        source = Path(override) / "families/transactional-cleanup/src"
        if not (source / PACKAGE / "cli.py").is_file():
            raise RuntimeError("AGENT_TOOLBELT_HOME lacks transactional-cleanup")
        return source
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    active = base / "Tools/transactional-cleanup/active.json"
    if active.is_file():
        source = Path(json.loads(active.read_text(encoding="utf-8"))["source"])
        if (source / PACKAGE / "cli.py").is_file():
            return source
        raise RuntimeError("Installed cleanup runtime is incomplete; rerun the installer")
    for parent in Path(__file__).resolve().parents:
        source = parent / "families/transactional-cleanup/src"
        if (source / PACKAGE / "cli.py").is_file():
            return source
    raise RuntimeError("Install the transactional-cleanup family runtime before use")


def main():
    try:
        sys.path.insert(0, str(source_root()))
        from agent_toolbelt_transactional_cleanup.cli import main as run
        return run()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(json.dumps({"ok": False, "failure_kind": "runtime_unavailable", "errors": [str(error)]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
