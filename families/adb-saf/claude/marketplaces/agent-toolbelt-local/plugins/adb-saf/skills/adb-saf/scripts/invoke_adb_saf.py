from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_NAME = "agent_toolbelt_adb_saf"


def candidate_sources() -> list[Path]:
    here = Path(__file__).resolve()
    # Installed skill: <skill>/lib/<package>. Checkout: families/adb-saf/src/<package>.
    candidates = [here.parents[1] / "lib"]
    candidates += [parent / "families" / "adb-saf" / "src" for parent in here.parents]
    configured = os.getenv("AGENT_TOOLBELT_HOME")
    if configured:
        candidates.append(Path(configured).expanduser() / "families" / "adb-saf" / "src")
    return candidates


def bootstrap() -> None:
    for candidate in candidate_sources():
        if (candidate / PACKAGE_NAME / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise RuntimeError("adb-saf package not found next to this skill; reinstall it with "
                       "families/adb-saf/scripts/install.py.")


bootstrap()

from agent_toolbelt_adb_saf import cli  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(cli.main(sys.argv[1:]))
