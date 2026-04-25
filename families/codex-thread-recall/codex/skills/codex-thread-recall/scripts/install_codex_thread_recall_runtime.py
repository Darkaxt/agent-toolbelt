from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_bootstrap


def runtime_python_path(codex_home: Path) -> Path:
    for candidate in runtime_bootstrap.runtime_python_candidates(codex_home):
        if candidate.parent.name == "Scripts":
            return candidate
    return runtime_bootstrap.runtime_python_candidates(codex_home)[0]


def resolve_repo_root(*, agent_toolbelt_home: str | None = None) -> Path:
    override = agent_toolbelt_home or os.getenv("AGENT_TOOLBELT_HOME")
    if override:
        repo_root = Path(override).expanduser().resolve()
        if not runtime_bootstrap.is_agent_toolbelt_repo(repo_root):
            raise RuntimeError(f"Invalid agent-toolbelt workspace: {repo_root}")
        return repo_root

    repo_root = runtime_bootstrap.discover_repo_root_from_script(Path(__file__))
    if repo_root is not None:
        return repo_root

    raise RuntimeError(
        "Could not locate agent-toolbelt source. Set AGENT_TOOLBELT_HOME to a checkout "
        "before running this installer from an installed skill bundle."
    )


def build_install_commands(
    *,
    repo_root: Path,
    codex_home: Path,
    python_executable: Path,
) -> list[list[str]]:
    runtime_python = runtime_python_path(codex_home)
    core_source = (repo_root / "packages" / "core").resolve()
    family_source = (repo_root / "families" / "codex-thread-recall").resolve()

    if not core_source.is_dir():
        raise RuntimeError(f"Missing agent-toolbelt-core source: {core_source}")
    if not family_source.is_dir():
        raise RuntimeError(f"Missing agent-toolbelt-codex-thread-recall source: {family_source}")

    return [
        [str(python_executable), "-m", "venv", str(runtime_bootstrap.runtime_root(codex_home) / ".venv")],
        [str(runtime_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        [
            str(runtime_python),
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--upgrade",
            "--force-reinstall",
            "--no-deps",
            f"agent-toolbelt-core @ {core_source.as_uri()}",
            f"agent-toolbelt-codex-thread-recall @ {family_source.as_uri()}",
        ],
    ]


def write_runtime_manifest(*, repo_root: Path, codex_home: Path) -> Path:
    runtime_dir = runtime_bootstrap.runtime_root(codex_home)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = runtime_dir / "runtime.json"
    manifest_path.write_text(
        json.dumps(
            {
                "family": "codex-thread-recall",
                "installed_at": datetime.now(tz=UTC).isoformat(),
                "repo_root": str(repo_root),
                "python": str(runtime_python_path(codex_home)),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def install_runtime(
    *,
    repo_root: Path,
    codex_home: Path,
    python_executable: Path,
    runner: Callable[[Sequence[str]], object] | None = None,
) -> Path:
    runtime_bootstrap.runtime_root(codex_home).mkdir(parents=True, exist_ok=True)
    commands = build_install_commands(
        repo_root=repo_root,
        codex_home=codex_home,
        python_executable=python_executable,
    )
    command_runner = runner or (lambda command: subprocess.run(command, check=True))
    for command in commands:
        command_runner(command)
    return write_runtime_manifest(repo_root=repo_root, codex_home=codex_home)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or refresh the local Codex runtime for codex-thread-recall.")
    parser.add_argument("--codex-home", help="Override the default Codex home directory.")
    parser.add_argument("--agent-toolbelt-home", help="Point to an agent-toolbelt checkout to install from.")
    parser.add_argument("--python", dest="python_executable", help="Interpreter to use when creating the private runtime.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = resolve_repo_root(agent_toolbelt_home=args.agent_toolbelt_home)
    codex_home = runtime_bootstrap.default_codex_home(
        {"CODEX_HOME": args.codex_home} if args.codex_home else None
    ).resolve()
    python_executable = Path(args.python_executable).resolve() if args.python_executable else Path(sys.executable).resolve()
    manifest_path = install_runtime(
        repo_root=repo_root,
        codex_home=codex_home,
        python_executable=python_executable,
    )
    print(json.dumps({"ok": True, "runtime_manifest": str(manifest_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
