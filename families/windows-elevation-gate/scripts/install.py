"""Deploy immutable runtime and identical agent-neutral personal skill folders."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

FAMILY = Path(__file__).resolve().parents[1]


def install(runtime_root, skill_roots):
    source = FAMILY / "src/agent_toolbelt_windows_elevation_gate"
    files = sorted(p for p in source.rglob("*.py") if "__pycache__" not in p.parts)
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(source).as_posix().encode())
        digest.update(path.read_bytes())
    release = digest.hexdigest()[:16]
    destination = runtime_root / "releases" / release / source.name
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != path.read_bytes():
            raise RuntimeError("Existing immutable runtime differs; refusing overwrite")
        if not target.exists():
            shutil.copy2(path, target)
        if target.read_bytes() != path.read_bytes():
            raise RuntimeError("Runtime copy verification failed")
    pending = runtime_root / (uuid.uuid4().hex + ".pending.json")
    try:
        pending.write_text(json.dumps({"schema": 1, "release": release, "version": "0.1.0"}), encoding="utf-8")
        os.replace(pending, runtime_root / "active.json")
    finally:
        pending.unlink(missing_ok=True)
    skill = FAMILY / "codex/skills/windows-elevation-gate"
    for root in skill_roots:
        for path in skill.rglob("*"):
            if path.is_file() and path.suffix in (".py", ".md", ".yaml"):
                target = root / skill.name / path.relative_to(skill)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                if target.read_bytes() != path.read_bytes():
                    raise RuntimeError("Installed skill copy verification failed")
    return {"ok": True, "release": release, "runtime": str(destination),
            "skills": [str(root / skill.name) for root in skill_roots]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path,
                        default=Path(os.environ["LOCALAPPDATA"]) / "Tools/windows-elevation-gate")
    parser.add_argument("--skills-root", type=Path, action="append")
    args = parser.parse_args()
    roots = args.skills_root or [Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills",
                                Path.home() / ".agents/skills", Path.home() / ".claude/skills"]
    print(json.dumps(install(args.runtime_root, roots), indent=2))
