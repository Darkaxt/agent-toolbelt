from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


FAMILY_NAME = "codex-thread-recall"


def default_codex_home(env: Mapping[str, str] | None = None) -> Path:
    active_env = env or os.environ
    if active_env.get("CODEX_HOME"):
        return Path(active_env["CODEX_HOME"]).expanduser()
    return Path.home() / ".codex"


def runtime_root(codex_home: Path) -> Path:
    return codex_home / "tools" / FAMILY_NAME


def runtime_python_candidates(codex_home: Path) -> list[Path]:
    venv_root = runtime_root(codex_home) / ".venv"
    candidates = [
        venv_root / "Scripts" / "python.exe",
        venv_root / "Scripts" / "python",
        venv_root / "bin" / "python",
    ]
    return candidates


def resolve_runtime_python(codex_home: Path) -> Path | None:
    for candidate in runtime_python_candidates(codex_home):
        if candidate.is_file():
            return candidate.resolve()
    return None


def is_agent_toolbelt_repo(repo_root: Path) -> bool:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    if "[tool.uv.workspace]" not in pyproject.read_text(encoding="utf-8"):
        return False
    return (
        (repo_root / "packages" / "core" / "src").is_dir()
        and (repo_root / "families" / "codex-thread-recall" / "src").is_dir()
    )


def resolve_repo_override(env: Mapping[str, str]) -> Path | None:
    override = env.get("AGENT_TOOLBELT_HOME")
    if not override:
        return None
    repo_root = Path(override).expanduser().resolve()
    if not is_agent_toolbelt_repo(repo_root):
        raise RuntimeError(
            f"AGENT_TOOLBELT_HOME does not point to an agent-toolbelt workspace: {repo_root}"
        )
    return repo_root


def discover_repo_root_from_script(script_path: Path) -> Path | None:
    for parent in script_path.resolve().parents:
        if is_agent_toolbelt_repo(parent):
            return parent
    return None


def resolve_execution_target(
    *,
    script_path: Path,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    active_env = env or os.environ
    codex_home = default_codex_home(active_env).resolve()
    runtime_python = resolve_runtime_python(codex_home)

    repo_override = resolve_repo_override(active_env)
    if repo_override is not None:
        target: dict[str, Any] = {"mode": "repo", "repo_root": str(repo_override)}
        if runtime_python is not None:
            target["runtime_python"] = str(runtime_python)
        return target

    repo_root = discover_repo_root_from_script(script_path)
    if repo_root is not None:
        target = {"mode": "repo", "repo_root": str(repo_root)}
        if runtime_python is not None:
            target["runtime_python"] = str(runtime_python)
        return target

    if runtime_python is not None:
        return {
            "mode": "runtime",
            "runtime_root": str(runtime_root(codex_home)),
            "runtime_python": str(runtime_python),
        }

    raise RuntimeError(
        "Could not locate codex-thread-recall runtime. "
        "Set AGENT_TOOLBELT_HOME to an agent-toolbelt workspace, run the "
        "install_codex_thread_recall_runtime.py helper to create "
        f"{runtime_root(codex_home)}, or restore a repo bundle around {script_path.resolve()}."
    )


def add_repo_sources(repo_root: Path) -> None:
    for candidate in (
        repo_root / "packages" / "core" / "src",
        repo_root / "families" / "codex-thread-recall" / "src",
    ):
        resolved = str(candidate.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def execute_cli(target: Mapping[str, Any], args: list[str]) -> int:
    mode = target["mode"]
    if mode == "repo":
        add_repo_sources(Path(target["repo_root"]))
        from agent_toolbelt_codex_thread_recall import cli  # noqa: WPS433

        return cli.main(args)

    if mode == "runtime":
        completed = subprocess.run(
            [str(target["runtime_python"]), "-m", "agent_toolbelt_codex_thread_recall.cli", *args],
            check=False,
        )
        return completed.returncode

    raise RuntimeError(f"Unsupported execution target mode: {mode}")
