from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from typing import Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_bootstrap


CommandRunner = Callable[[Sequence[str], dict[str, str] | None], object]


def resolve_repo_root(value: str | None = None) -> Path:
    configured = value or os.getenv("AGENT_TOOLBELT_HOME")
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if runtime_bootstrap.is_agent_toolbelt_repo(candidate):
            return candidate
        raise RuntimeError(f"Invalid agent-toolbelt checkout: {candidate}")
    discovered = runtime_bootstrap.discover_repo_root(Path(__file__))
    if discovered is not None:
        return discovered
    standard = Path(r"D:\Downloads\Public\agent-toolbelt")
    if runtime_bootstrap.is_agent_toolbelt_repo(standard):
        return standard.resolve()
    raise RuntimeError("Set AGENT_TOOLBELT_HOME to the agent-toolbelt checkout.")


def release_root_for_install(codex_home: Path, release_stamp: str | None = None) -> Path:
    stamp = release_stamp or datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S-%fZ")
    return runtime_bootstrap.releases_root(codex_home) / stamp


def runtime_python(release_root: Path) -> Path:
    return runtime_bootstrap.runtime_python_candidates(release_root)[0]


def default_runner(command: Sequence[str], env: dict[str, str] | None = None) -> object:
    return subprocess.run(command, check=True, env=env)


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_active_manifest(*, codex_home: Path, release_root: Path, repo_root: Path) -> Path:
    path = runtime_bootstrap.active_manifest_path(codex_home)
    _write_json_atomic(
        path,
        {
            "schema": "agent_toolbelt_context_transfer.active_runtime.v1",
            "family": "context-transfer",
            "activated_at": datetime.now(tz=UTC).isoformat(),
            "release_root": str(release_root),
            "repo_root": str(repo_root),
            "python": str(runtime_python(release_root)),
        },
    )
    return path


def validate_staged_runtime(*, release_root: Path, runner: CommandRunner | None = None) -> None:
    command_runner = runner or default_runner
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str((release_root / "src").resolve())
    command_runner(
        [
            str(runtime_python(release_root)),
            "-m",
            "agent_toolbelt_context_transfer.cli",
            "--help",
        ],
        environment,
    )


def install_runtime(
    *,
    repo_root: Path,
    codex_home: Path,
    python_executable: Path,
    runner: CommandRunner | None = None,
    validator: Callable[..., None] | None = None,
    release_stamp: str | None = None,
) -> Path:
    command_runner = runner or default_runner
    release_root = release_root_for_install(codex_home, release_stamp)
    source_package = repo_root / "families" / "context-transfer" / "src" / "agent_toolbelt_context_transfer"
    if not source_package.is_dir():
        raise RuntimeError(f"Missing context-transfer package source: {source_package}")
    release_root.mkdir(parents=True, exist_ok=False)
    try:
        command_runner(
            [str(python_executable), "-m", "venv", str(release_root / ".venv")],
            None,
        )
        destination_package = release_root / "src" / "agent_toolbelt_context_transfer"
        destination_package.parent.mkdir(parents=True)
        shutil.copytree(
            source_package,
            destination_package,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        _write_json_atomic(
            release_root / "release.json",
            {
                "schema": "agent_toolbelt_context_transfer.runtime_release.v1",
                "family": "context-transfer",
                "installed_at": datetime.now(tz=UTC).isoformat(),
                "release_root": str(release_root),
                "repo_root": str(repo_root),
                "python": str(runtime_python(release_root)),
            },
        )
        validate = validator or validate_staged_runtime
        validate(release_root=release_root, runner=command_runner)
        return write_active_manifest(
            codex_home=codex_home,
            release_root=release_root,
            repo_root=repo_root,
        )
    except Exception:
        if release_root.is_dir() and release_root.parent == runtime_bootstrap.releases_root(codex_home):
            shutil.rmtree(release_root)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install the private staged context-transfer runtime.")
    parser.add_argument("--codex-home")
    parser.add_argument("--agent-toolbelt-home")
    parser.add_argument("--python", dest="python_executable")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = resolve_repo_root(args.agent_toolbelt_home)
    codex_home = runtime_bootstrap.default_codex_home(
        {"CODEX_HOME": args.codex_home} if args.codex_home else None
    ).resolve()
    python_executable = (
        Path(args.python_executable).resolve()
        if args.python_executable
        else Path(sys.executable).resolve()
    )
    active = install_runtime(
        repo_root=repo_root,
        codex_home=codex_home,
        python_executable=python_executable,
    )
    print(json.dumps({"ok": True, "active_manifest": str(active)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
