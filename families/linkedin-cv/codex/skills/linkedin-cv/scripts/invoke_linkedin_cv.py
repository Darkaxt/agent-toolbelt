import os
import sys
from pathlib import Path


DEFAULT_AGENT_TOOLBELT_HOME = Path(r"D:\Downloads\Public\agent-toolbelt")


def bootstrap_agent_toolbelt() -> None:
    candidates: list[Path] = []
    env_home = os.getenv("AGENT_TOOLBELT_HOME")
    if env_home:
        candidates.append(Path(env_home).expanduser())
    candidates.append(DEFAULT_AGENT_TOOLBELT_HOME)

    for repo_root in candidates:
        repo_root = repo_root.resolve()
        pyproject = repo_root / "pyproject.toml"
        if not pyproject.is_file():
            continue
        if "[tool.uv.workspace]" not in pyproject.read_text(encoding="utf-8"):
            continue

        core_src = repo_root / "packages" / "core" / "src"
        family_src = repo_root / "families" / "linkedin-cv" / "src"
        for path in (core_src, family_src):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        return

    raise RuntimeError(
        "Could not locate agent-toolbelt. Set AGENT_TOOLBELT_HOME or restore "
        f"{DEFAULT_AGENT_TOOLBELT_HOME}."
    )


bootstrap_agent_toolbelt()

from agent_toolbelt_linkedin_cv import cli  # noqa: E402


def main() -> int:
    return cli.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
