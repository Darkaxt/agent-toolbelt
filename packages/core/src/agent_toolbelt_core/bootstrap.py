import sys
from pathlib import Path


WORKSPACE_MARKER = "[tool.uv.workspace]"


def find_workspace_root(start: str | Path) -> Path:
    current = Path(start).resolve()
    for candidate in (current, *current.parents):
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        if WORKSPACE_MARKER in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError("Could not locate the agent-toolbelt workspace root.")


def prepend_sys_path(path: Path) -> None:
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def bootstrap_family_package(
    script_path: str | Path,
    *,
    family_name: str,
    package_dir_name: str,
) -> Path:
    repo_root = find_workspace_root(Path(script_path).resolve().parent)
    core_src = repo_root / "packages" / "core" / "src"
    family_src = repo_root / "families" / family_name / "src"

    if not (core_src / "agent_toolbelt_core").is_dir():
        raise RuntimeError("Could not locate packages/core/src/agent_toolbelt_core.")
    if not (family_src / package_dir_name).is_dir():
        raise RuntimeError(f"Could not locate {family_src / package_dir_name}.")

    prepend_sys_path(core_src)
    prepend_sys_path(family_src)
    return repo_root
