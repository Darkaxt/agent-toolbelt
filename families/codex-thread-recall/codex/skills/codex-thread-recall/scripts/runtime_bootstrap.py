from __future__ import annotations

import json
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


def releases_root(codex_home: Path) -> Path:
    return runtime_root(codex_home) / "releases"


def active_runtime_manifest_path(codex_home: Path) -> Path:
    return runtime_root(codex_home) / "active.json"


def runtime_python_candidates_from_root(root: Path) -> list[Path]:
    return [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python",
        root / ".venv" / "bin" / "python",
    ]


def runtime_python_candidates(codex_home: Path) -> list[Path]:
    return runtime_python_candidates_from_root(runtime_root(codex_home))


def resolve_runtime_python_from_root(root: Path) -> Path | None:
    for candidate in runtime_python_candidates_from_root(root):
        if candidate.is_file():
            return candidate.resolve()
    return None


def read_active_runtime_manifest(codex_home: Path) -> dict[str, Any] | None:
    manifest_path = active_runtime_manifest_path(codex_home)
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def resolve_active_runtime(codex_home: Path) -> dict[str, Any] | None:
    manifest = read_active_runtime_manifest(codex_home)
    if manifest is None:
        return None
    release_root_value = manifest.get("release_root")
    if not isinstance(release_root_value, str) or not release_root_value:
        return None
    release_root = Path(release_root_value).expanduser().resolve()
    runtime_python = resolve_runtime_python_from_root(release_root)
    if runtime_python is None:
        return None
    return {
        "mode": "runtime",
        "release_root": str(release_root),
        "runtime_python": str(runtime_python),
        "active_manifest": str(active_runtime_manifest_path(codex_home)),
    }


def resolve_legacy_runtime(codex_home: Path) -> dict[str, Any] | None:
    runtime_python = resolve_runtime_python_from_root(runtime_root(codex_home))
    if runtime_python is None:
        return None
    return {
        "mode": "runtime",
        "runtime_root": str(runtime_root(codex_home)),
        "runtime_python": str(runtime_python),
        "legacy_runtime": True,
    }


def is_agent_toolbelt_repo(repo_root: Path) -> bool:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    if "[tool.uv.workspace]" not in pyproject.read_text(encoding="utf-8"):
        return False
    return (
        (repo_root / "packages" / "core" / "src").is_dir()
        and (repo_root / "families" / FAMILY_NAME / "src").is_dir()
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


def execution_environment(target: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict[str, str]:
    active_env = dict(env or os.environ)
    active_env["CODEX_THREAD_RECALL_RUNTIME_MODE"] = str(target["mode"])
    active_env["CODEX_THREAD_RECALL_RUNTIME_PYTHON"] = str(target.get("runtime_python", sys.executable))
    active_env.pop("CODEX_THREAD_RECALL_RUNTIME_RELEASE_ROOT", None)
    active_env.pop("CODEX_THREAD_RECALL_RUNTIME_REPO_ROOT", None)
    if "release_root" in target:
        active_env["CODEX_THREAD_RECALL_RUNTIME_RELEASE_ROOT"] = str(target["release_root"])
    if "repo_root" in target:
        active_env["CODEX_THREAD_RECALL_RUNTIME_REPO_ROOT"] = str(target["repo_root"])
    return active_env


def resolve_execution_target(
    *,
    script_path: Path,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    active_env = env or os.environ
    codex_home = default_codex_home(active_env).resolve()

    repo_override = resolve_repo_override(active_env)
    if repo_override is not None:
        return {"mode": "repo", "repo_root": str(repo_override)}

    repo_root = discover_repo_root_from_script(script_path)
    if repo_root is not None:
        return {"mode": "repo", "repo_root": str(repo_root)}

    active_runtime = resolve_active_runtime(codex_home)
    if active_runtime is not None:
        return active_runtime

    legacy_runtime = resolve_legacy_runtime(codex_home)
    if legacy_runtime is not None:
        return legacy_runtime

    raise RuntimeError(
        "Could not locate codex-thread-recall runtime. "
        "Set AGENT_TOOLBELT_HOME to an agent-toolbelt workspace, run the "
        "install_codex_thread_recall_runtime.py helper to create a staged runtime under "
        f"{releases_root(codex_home)}, or restore a repo bundle around {script_path.resolve()}."
    )


def add_repo_sources(repo_root: Path) -> None:
    for candidate in (
        repo_root / "packages" / "core" / "src",
        repo_root / "families" / FAMILY_NAME / "src",
    ):
        resolved = str(candidate.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def execute_cli(target: Mapping[str, Any], args: list[str]) -> int:
    mode = target["mode"]
    runtime_env = execution_environment(target)
    if mode == "repo":
        original_env = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(runtime_env)
            add_repo_sources(Path(target["repo_root"]))
            from agent_toolbelt_codex_thread_recall import cli  # noqa: WPS433

            return cli.main(args)
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    if mode == "runtime":
        completed = subprocess.run(
            [str(target["runtime_python"]), "-m", "agent_toolbelt_codex_thread_recall.cli", *args],
            check=False,
            env=runtime_env,
        )
        return completed.returncode

    raise RuntimeError(f"Unsupported execution target mode: {mode}")
