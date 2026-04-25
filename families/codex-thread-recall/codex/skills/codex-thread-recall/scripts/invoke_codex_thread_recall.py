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

        family_src = repo_root / "families" / "codex-thread-recall" / "src"
        if str(family_src) not in sys.path:
            sys.path.insert(0, str(family_src))
        return

    raise RuntimeError(
        "Could not locate agent-toolbelt. Set AGENT_TOOLBELT_HOME or restore "
        f"{DEFAULT_AGENT_TOOLBELT_HOME}."
    )


bootstrap_agent_toolbelt()

from agent_toolbelt_codex_thread_recall import cli  # noqa: E402


def main() -> int:
    return cli.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
