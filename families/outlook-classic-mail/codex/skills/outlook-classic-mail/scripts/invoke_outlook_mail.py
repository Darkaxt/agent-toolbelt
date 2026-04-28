import os
import sys
from pathlib import Path


WORKSPACE_MARKER = "[tool.uv.workspace]"


def workspace_candidates(current: Path) -> list[Path]:
    candidates: list[Path] = []
    env_home = os.getenv("AGENT_TOOLBELT_HOME")
    if env_home:
        candidates.append(Path(env_home).expanduser())

    for start in (current, Path.cwd().resolve()):
        for parent in (start, *start.parents):
            candidates.append(parent)
            candidates.append(parent / "agent-toolbelt")
    return candidates


def bootstrap_core_src() -> Path:
    current = Path(__file__).resolve()
    seen: set[str] = set()
    for candidate in workspace_candidates(current.parent):
        root = candidate.resolve()
        root_key = str(root).lower()
        if root_key in seen:
            continue
        seen.add(root_key)
        pyproject = root / "pyproject.toml"
        core_src = root / "packages" / "core" / "src"
        if pyproject.exists() and WORKSPACE_MARKER in pyproject.read_text(encoding="utf-8"):
            if str(core_src) not in sys.path:
                sys.path.insert(0, str(core_src))
            return root
    raise RuntimeError("Could not locate the repository packages/core/src directory.")


REPO_ROOT = bootstrap_core_src()

from agent_toolbelt_core.bootstrap import bootstrap_family_package  # noqa: E402

bootstrap_family_package(
    REPO_ROOT / "families" / "outlook-classic-mail",
    family_name="outlook-classic-mail",
    package_dir_name="agent_toolbelt_outlook_classic_mail",
)

from agent_toolbelt_outlook_classic_mail import cli  # noqa: E402


def main() -> int:
    return cli.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
