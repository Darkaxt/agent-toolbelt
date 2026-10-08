"""Install verified source into a stable shared runtime and personal skills."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


FAMILY = Path(__file__).resolve().parents[1]


def install(runtime_root, skill_roots):
    source = FAMILY / "src/agent_toolbelt_gradle_build_gate"
    files = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix in (".py", ".ps1", ".gradle", ".java"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(source)).replace("\\", "/").encode())
        digest.update(path.read_bytes())
    release = digest.hexdigest()[:16]
    destination = runtime_root / "releases" / release / source.name
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != path.read_bytes():
            raise RuntimeError("Existing content-addressed runtime differs from source")
        if not target.exists():
            shutil.copy2(path, target)
    pointer = runtime_root / "active.json"
    pending = runtime_root / "active.pending.json"
    pending.write_text(json.dumps({"schema": 1, "release": release, "version": "0.4.3"}) + "\n", encoding="utf-8")
    os.replace(pending, pointer)
    skill = FAMILY / "codex/skills/gradle-build-gate"
    for root in skill_roots:
        for path in skill.rglob("*"):
            if path.is_file() and path.suffix in (".py", ".md", ".yaml"):
                target = root / "gradle-build-gate" / path.relative_to(skill)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    return {"ok": True, "runtime": str(destination.parent), "skills": [str(root / "gradle-build-gate") for root in skill_roots]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    default_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Tools/gradle-build-gate"
    parser.add_argument("--runtime-root", type=Path, default=default_root)
    parser.add_argument("--skills-root", type=Path, action="append")
    args = parser.parse_args()
    roots = args.skills_root or [Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills",
                                Path.home() / ".agents/skills", Path.home() / ".claude/skills"]
    print(json.dumps(install(args.runtime_root, roots), indent=2))
