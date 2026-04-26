import os
import sys
from pathlib import Path


def bootstrap_agent_toolbelt() -> None:
    candidates: list[Path] = []
    env_home = os.getenv("AGENT_TOOLBELT_HOME")
    if env_home:
        candidates.append(Path(env_home).expanduser())

    current = Path(__file__).resolve()
    candidates.extend(current.parents)

    for repo_root in candidates:
        pyproject = repo_root / "pyproject.toml"
        family_src = repo_root / "families" / "skills-sh-scout" / "src"
        if not pyproject.is_file() or not family_src.is_dir():
            continue
        if "[tool.uv.workspace]" not in pyproject.read_text(encoding="utf-8"):
            continue
        if str(family_src) not in sys.path:
            sys.path.insert(0, str(family_src))
        return

    raise RuntimeError("Could not locate agent-toolbelt. Set AGENT_TOOLBELT_HOME to the repo root.")


bootstrap_agent_toolbelt()

from agent_toolbelt_skills_sh_scout import cli  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(cli.main(sys.argv[1:]))
