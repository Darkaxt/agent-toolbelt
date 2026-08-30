from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping


FAMILY_NAME = "context-transfer"
PACKAGE_NAME = "agent_toolbelt_context_transfer"


def default_codex_home(env: Mapping[str, str] | None = None) -> Path:
    active = env or os.environ
    return Path(active.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def runtime_root(codex_home: Path) -> Path:
    return codex_home / "tools" / FAMILY_NAME


def releases_root(codex_home: Path) -> Path:
    return runtime_root(codex_home) / "releases"


def active_manifest_path(codex_home: Path) -> Path:
    return runtime_root(codex_home) / "active.json"


def runtime_python_candidates(release_root: Path) -> list[Path]:
    return [
        release_root / ".venv" / "Scripts" / "python.exe",
        release_root / ".venv" / "bin" / "python",
    ]


def resolve_runtime_python(release_root: Path) -> Path | None:
    return next((path.resolve() for path in runtime_python_candidates(release_root) if path.is_file()), None)


def is_agent_toolbelt_repo(path: Path) -> bool:
    return (
        (path / "pyproject.toml").is_file()
        and (path / "families" / FAMILY_NAME / "pyproject.toml").is_file()
        and (path / "families" / FAMILY_NAME / "src" / PACKAGE_NAME).is_dir()
    )


def discover_repo_root(script_path: Path) -> Path | None:
    for candidate in script_path.resolve().parents:
        if is_agent_toolbelt_repo(candidate):
            return candidate
    return None


def resolve_active_runtime(codex_home: Path) -> dict[str, Any] | None:
    manifest_path = active_manifest_path(codex_home)
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        release_root = Path(str(payload["release_root"])).expanduser().resolve()
    except (KeyError, OSError, ValueError, json.JSONDecodeError):
        return None
    runtime_python = resolve_runtime_python(release_root)
    if runtime_python is None or not (release_root / "src" / PACKAGE_NAME).is_dir():
        return None
    return {
        "mode": "runtime",
        "release_root": str(release_root),
        "runtime_python": str(runtime_python),
        "active_manifest": str(manifest_path.resolve()),
    }


def resolve_execution_target(
    *,
    script_path: Path,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    active = env or os.environ
    override = active.get("AGENT_TOOLBELT_HOME")
    if override:
        repo = Path(override).expanduser().resolve()
        if not is_agent_toolbelt_repo(repo):
            raise RuntimeError(f"AGENT_TOOLBELT_HOME is not an agent-toolbelt checkout: {repo}")
        return {"mode": "repo", "repo_root": str(repo)}

    repo = discover_repo_root(script_path)
    if repo is not None:
        return {"mode": "repo", "repo_root": str(repo)}

    codex_home = default_codex_home(active).resolve()
    runtime = resolve_active_runtime(codex_home)
    if runtime is not None:
        return runtime

    standard_repo = Path(r"D:\Downloads\Public\agent-toolbelt")
    if is_agent_toolbelt_repo(standard_repo):
        return {"mode": "repo", "repo_root": str(standard_repo.resolve())}

    raise RuntimeError(
        "Could not locate context-transfer. Set AGENT_TOOLBELT_HOME or run "
        "install_context_transfer_runtime.py to create a staged private runtime."
    )


def execute_cli(
    target: Mapping[str, Any],
    args: list[str],
    env: Mapping[str, str] | None = None,
) -> int:
    if target["mode"] == "repo":
        source = Path(str(target["repo_root"])) / "families" / FAMILY_NAME / "src"
        sys.path.insert(0, str(source.resolve()))
        from agent_toolbelt_context_transfer import cli

        return cli.main(args)

    if target["mode"] == "runtime":
        release_root = Path(str(target["release_root"]))
        runtime_env = dict(env or os.environ)
        source = str((release_root / "src").resolve())
        runtime_env["PYTHONDONTWRITEBYTECODE"] = "1"
        runtime_env["PYTHONPATH"] = os.pathsep.join(
            filter(None, (source, runtime_env.get("PYTHONPATH")))
        )
        process = subprocess.Popen(
            [
                str(target["runtime_python"]),
                "-m",
                "agent_toolbelt_context_transfer.cli",
                *args,
            ],
            env=runtime_env,
        )
        try:
            return process.wait()
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            raise

    raise RuntimeError(f"Unsupported context-transfer execution mode: {target['mode']}")
