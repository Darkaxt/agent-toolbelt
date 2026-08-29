from __future__ import annotations

import os
import sys
from pathlib import Path


FAMILY_NAME = "adb-archive-transfer"
PACKAGE_NAME = "agent_toolbelt_adb_archive_transfer"


def candidate_repositories() -> list[Path]:
    candidates: list[Path] = []
    configured = os.getenv("AGENT_TOOLBELT_HOME")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(Path(r"D:\Downloads\Public\agent-toolbelt"))
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidates.append(parent)
    return candidates


def bootstrap_family_src() -> None:
    for candidate in candidate_repositories():
        family_src = candidate / "families" / FAMILY_NAME / "src"
        package_dir = family_src / PACKAGE_NAME
        if package_dir.is_dir():
            sys.path.insert(0, str(family_src))
            return
    raise RuntimeError(
        "Could not locate agent-toolbelt. Set AGENT_TOOLBELT_HOME or keep the checkout at "
        r"D:\Downloads\Public\agent-toolbelt."
    )


bootstrap_family_src()

from agent_toolbelt_adb_archive_transfer import cli  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(cli.main(sys.argv[1:]))
