from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_bootstrap


CommandRunner = Callable[[Sequence[str], dict[str, str] | None], object]
VALIDATION_THREAD_ID = "codex-thread-recall-install-validation"


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


def release_root_for_install(codex_home: Path, *, release_stamp: str | None = None) -> Path:
    stamp = release_stamp or datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S-%fZ")
    return runtime_bootstrap.releases_root(codex_home) / stamp


def runtime_python_path(release_root: Path) -> Path:
    for candidate in runtime_bootstrap.runtime_python_candidates_from_root(release_root):
        if candidate.parent.name == "Scripts":
            return candidate
    return runtime_bootstrap.runtime_python_candidates_from_root(release_root)[0]


def build_install_commands(
    *,
    repo_root: Path,
    release_root: Path,
    python_executable: Path,
) -> list[list[str]]:
    runtime_python = runtime_python_path(release_root)
    core_source = (repo_root / "packages" / "core").resolve()
    family_source = (repo_root / "families" / "codex-thread-recall").resolve()

    if not core_source.is_dir():
        raise RuntimeError(f"Missing agent-toolbelt-core source: {core_source}")
    if not family_source.is_dir():
        raise RuntimeError(f"Missing agent-toolbelt-codex-thread-recall source: {family_source}")

    return [
        [str(python_executable), "-m", "venv", str(release_root / ".venv")],
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


def default_runner(command: Sequence[str], env: dict[str, str] | None = None) -> object:
    return subprocess.run(command, check=True, env=env)


def write_release_manifest(*, release_root: Path, repo_root: Path) -> Path:
    release_root.mkdir(parents=True, exist_ok=True)
    manifest_path = release_root / "release.json"
    manifest_path.write_text(
        json.dumps(
            {
                "family": "codex-thread-recall",
                "installed_at": datetime.now(tz=UTC).isoformat(),
                "repo_root": str(repo_root),
                "release_root": str(release_root),
                "python": str(runtime_python_path(release_root)),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def write_active_manifest(*, codex_home: Path, release_root: Path, repo_root: Path) -> Path:
    manifest_path = runtime_bootstrap.active_runtime_manifest_path(codex_home)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "family": "codex-thread-recall",
                "activated_at": datetime.now(tz=UTC).isoformat(),
                "repo_root": str(repo_root),
                "release_root": str(release_root),
                "python": str(runtime_python_path(release_root)),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def build_validation_home(parent: Path) -> Path:
    codex_home = parent / "validation-home"
    rollout_path = codex_home / "sessions" / "validation" / "rollout.jsonl"
    rollout_path.parent.mkdir(parents=True, exist_ok=True)
    rollout_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-04-25T00:00:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "text": "Validate staged codex-thread-recall runtime."},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    conn = sqlite3.connect(codex_home / "state_5.sqlite")
    try:
        conn.execute(
            """
            create table threads (
                id text primary key,
                title text,
                cwd text,
                rollout_path text,
                created_at integer,
                updated_at integer
            )
            """
        )
        conn.execute(
            "insert into threads (id, title, cwd, rollout_path, created_at, updated_at) values (?, ?, ?, ?, ?, ?)",
            (
                VALIDATION_THREAD_ID,
                "Runtime Validation",
                r"C:\ThreadRecall\Validation",
                str(rollout_path),
                1777077000,
                1777077300,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return codex_home


def validate_staged_runtime(
    *,
    release_root: Path,
    runner: CommandRunner | None = None,
) -> None:
    command_runner = runner or default_runner
    runtime_python = runtime_python_path(release_root)
    with tempfile.TemporaryDirectory() as temp_dir:
        validation_home = build_validation_home(Path(temp_dir))
        command_runner(
            [
                str(runtime_python),
                "-m",
                "agent_toolbelt_codex_thread_recall.cli",
                "--codex-home",
                str(validation_home),
                "--thread-id",
                VALIDATION_THREAD_ID,
                "status",
            ],
            dict(os.environ),
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
    release_root = release_root_for_install(codex_home, release_stamp=release_stamp)
    release_root.mkdir(parents=True, exist_ok=False)

    for command in build_install_commands(
        repo_root=repo_root,
        release_root=release_root,
        python_executable=python_executable,
    ):
        command_runner(command, None)

    write_release_manifest(release_root=release_root, repo_root=repo_root)
    active_manifest_path = runtime_bootstrap.active_runtime_manifest_path(codex_home)
    validate = validator or validate_staged_runtime
    validate(release_root=release_root, runner=command_runner)
    return write_active_manifest(codex_home=codex_home, release_root=release_root, repo_root=repo_root)


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
    print(json.dumps({"ok": True, "active_manifest": str(manifest_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
