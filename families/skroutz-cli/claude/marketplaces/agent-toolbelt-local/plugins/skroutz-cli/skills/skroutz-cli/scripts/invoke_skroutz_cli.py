import os
import sys
from pathlib import Path


def candidate_repo_roots(current: Path) -> list[Path]:
    candidates: list[Path] = []
    env_home = os.getenv("AGENT_TOOLBELT_HOME")
    if env_home:
        candidates.append(Path(env_home).expanduser())
    candidates.append(Path(r"D:\Downloads\Public\agent-toolbelt"))
    candidates.extend(current.parents)
    return candidates


def bootstrap_family_package() -> None:
    current = Path(__file__).resolve()
    for candidate in candidate_repo_roots(current):
        repo_root = candidate.resolve()
        pyproject = repo_root / "pyproject.toml"
        core_src = repo_root / "packages" / "core" / "src"
        family_src = repo_root / "families" / "skroutz-cli" / "src"
        if pyproject.exists() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            if not (family_src / "agent_toolbelt_skroutz_cli").is_dir():
                continue
            if str(core_src) not in sys.path:
                sys.path.insert(0, str(core_src))
            if str(family_src) not in sys.path:
                sys.path.insert(0, str(family_src))
            return
    raise RuntimeError("Could not locate the agent-toolbelt skroutz-cli package.")


bootstrap_family_package()

from agent_toolbelt_skroutz_cli import cli  # noqa: E402


def main() -> int:
    return cli.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
