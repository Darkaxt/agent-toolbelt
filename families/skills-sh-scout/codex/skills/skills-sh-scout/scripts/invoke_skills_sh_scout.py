import sys
from pathlib import Path


def bootstrap_family_package() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        pyproject = parent / "pyproject.toml"
        family_src = parent / "families" / "skills-sh-scout" / "src"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            if str(family_src) not in sys.path:
                sys.path.insert(0, str(family_src))
            return
    raise RuntimeError("Could not locate the agent-toolbelt skills-sh-scout package.")


bootstrap_family_package()

from agent_toolbelt_skills_sh_scout import cli  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(cli.main(sys.argv[1:]))
