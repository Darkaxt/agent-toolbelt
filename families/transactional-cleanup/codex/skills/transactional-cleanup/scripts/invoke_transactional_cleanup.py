from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
PACKAGE = "agent_toolbelt_transactional_cleanup"


def legacy_state_id(arguments):
    for flag in ("--transaction", "--ticket"):
        if flag in arguments and arguments.index(flag) + 1 < len(arguments):
            return arguments[arguments.index(flag) + 1]
    return None


def source_root(arguments=None):
    override = os.environ.get("AGENT_TOOLBELT_HOME")
    if override:
        source = Path(override) / "families/transactional-cleanup/src"
        if not (source / PACKAGE / "cli.py").is_file():
            raise RuntimeError("AGENT_TOOLBELT_HOME lacks transactional-cleanup")
        return source
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    active = base / "Tools/transactional-cleanup/active.json"
    if active.is_file():
        metadata = json.loads(active.read_text(encoding="utf-8"))
        arguments = list(sys.argv[1:] if arguments is None else arguments)
        state = Path(arguments[arguments.index("--state-root") + 1]) if "--state-root" in arguments else base / "Tools/transactional-cleanup/state"
        identifier = legacy_state_id(arguments)
        legacy = metadata.get("legacy_source")
        if identifier and legacy and (state / f"{identifier}.json").is_file():
            source = Path(legacy)
        else:
            source = Path(metadata["source"])
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
