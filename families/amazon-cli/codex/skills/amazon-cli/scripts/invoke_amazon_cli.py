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
    # Installed skill copies live outside the repository, so walking the
    # script's parents alone cannot find the workspace; try known roots first.
    current = Path(__file__).resolve()
    for candidate in candidate_repo_roots(current):
        repo_root = candidate.resolve()
        pyproject = repo_root / "pyproject.toml"
        core_src = repo_root / "packages" / "core" / "src"
        family_src = repo_root / "families" / "amazon-cli" / "src"
        if pyproject.exists() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            if not (family_src / "agent_toolbelt_amazon_cli").is_dir():
                continue
            for path in (core_src, family_src):
                if str(path) not in sys.path:
                    sys.path.insert(0, str(path))
            return
    raise RuntimeError("Could not locate the agent-toolbelt amazon-cli package.")


bootstrap_family_package()

from agent_toolbelt_amazon_cli import cli  # noqa: E402


def main() -> int:
    return cli.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
