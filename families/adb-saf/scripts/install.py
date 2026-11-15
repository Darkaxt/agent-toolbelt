"""Install the adb-saf skill with its own copy of the package.

Usage: python -B scripts/install.py [--home <user profile>] [--dry-run]

Installs into <home>/.codex/skills/adb-saf (the path LLM Coordinator's device
gate runs) and <home>/.claude/skills/adb-saf. Each skill gets lib/ with the
package, so it never depends on a checkout's current branch. An existing
install is replaced only if it carries this installer's marker.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

FAMILY = Path(__file__).resolve().parents[1]
PACKAGE = FAMILY / "src" / "agent_toolbelt_adb_saf"
SKILLS = {
    ".codex/skills": FAMILY / "codex" / "skills" / "adb-saf",
    ".claude/skills": FAMILY / "claude" / "marketplaces" / "agent-toolbelt-local" / "plugins" / "adb-saf" / "skills" / "adb-saf",
}
MARKER = ".adb-saf-install.json"


def version() -> str:
    for line in (PACKAGE / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("package version missing")


def install(root: Path, source: Path, dry_run: bool) -> dict:
    destination = root / "adb-saf"
    if destination.exists() and not (destination / MARKER).is_file():
        raise SystemExit(f"{destination} exists without an adb-saf install marker; not replacing it")
    if dry_run:
        return {"destination": str(destination), "replace": destination.exists()}
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".adb-saf-", dir=root))
    try:
        tree = staging / "adb-saf"
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(PACKAGE, tree / "lib" / PACKAGE.name, ignore=shutil.ignore_patterns("__pycache__", "*.java"))
        (tree / MARKER).write_text(json.dumps({"version": version()}) + "\n", encoding="utf-8", newline="\n")
        previous = root / ".adb-saf-previous"
        if previous.exists():
            shutil.rmtree(previous)
        if destination.exists():
            destination.rename(previous)
        tree.rename(destination)
        if previous.exists():
            shutil.rmtree(previous)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"destination": str(destination), "version": version()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    results = [install(Path(args.home) / relative, source, args.dry_run) for relative, source in SKILLS.items()]
    print(json.dumps({"installed": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
