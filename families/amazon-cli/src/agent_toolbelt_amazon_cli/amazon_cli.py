import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agent_toolbelt_core.common import merge_messages, run_process, windows_local_tools_dir


CLIENT_HOME_ENV = "AMAZON_INTENT_CLI_HOME"
CLIENT_FOLDER_NAME = "amazon-intent-cli"
CLIENT_ENTRYPOINT = "amazon-cli"
DEFAULT_TIMEOUT_SEC = 600
BUNDLED_RUNTIME_CLIENT_FOLDER_NAME = "agent-toolbelt-amazon-cli-client"
BUNDLED_VENV_FOLDER_NAME = "agent-toolbelt-amazon-cli-venv"


def package_root() -> Path:
    return Path(__file__).resolve().parent


def bundled_client_home() -> Path:
    return package_root() / "assets" / "amazon-intent-cli"


def bundled_runtime_client_root() -> Path:
    tools_dir = windows_local_tools_dir()
    if tools_dir is not None:
        return tools_dir / BUNDLED_RUNTIME_CLIENT_FOLDER_NAME
    return Path.home() / ".agent-toolbelt" / BUNDLED_RUNTIME_CLIENT_FOLDER_NAME


def bundled_runtime_venv() -> Path:
    tools_dir = windows_local_tools_dir()
    if tools_dir is not None:
        return tools_dir / BUNDLED_VENV_FOLDER_NAME
    return Path.home() / ".agent-toolbelt" / BUNDLED_VENV_FOLDER_NAME


def should_exclude_bundled_client_path(path: Path) -> bool:
    excluded_names = {
        ".venv",
        ".pytest_cache",
        "__pycache__",
        "Cookies",
        "Local State",
        "todo.md",
        "derived_todo.md",
    }
    excluded_suffixes = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".ldb", ".log"}
    return (
        any(part in excluded_names or part.endswith(".egg-info") for part in path.parts)
        or path.name in excluded_names
        or path.suffix.lower() in excluded_suffixes
    )


def bundled_client_fingerprint(source: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in source.rglob("*") if candidate.is_file()):
        relative = path.relative_to(source)
        if should_exclude_bundled_client_path(relative):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def prepare_bundled_runtime_client() -> Path | None:
    source = bundled_client_home().resolve()
    if not (source / "pyproject.toml").is_file():
        return None

    fingerprint = bundled_client_fingerprint(source)
    root = bundled_runtime_client_root().resolve()
    target = root / fingerprint
    if (target / "pyproject.toml").is_file():
        return target

    root.mkdir(parents=True, exist_ok=True)
    temp_target = root / f".{fingerprint}.{os.getpid()}.tmp"
    if temp_target.exists():
        shutil.rmtree(temp_target)
    shutil.copytree(
        source,
        temp_target,
        ignore=shutil.ignore_patterns(
            ".venv",
            ".pytest_cache",
            "__pycache__",
            "*.egg-info",
            "*.pyc",
            "*.pyo",
            "*.db",
            "*.sqlite",
            "*.sqlite3",
            "*.ldb",
            "*.log",
            "Cookies",
            "Local State",
            "todo.md",
            "derived_todo.md",
        ),
    )
    try:
        temp_target.rename(target)
    except FileExistsError:
        shutil.rmtree(temp_target)
    return target


def is_bundled_runtime_client(client_home: Path) -> bool:
    root = bundled_runtime_client_root().resolve()
    try:
        client_home.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def make_result(
    *,
    ok: bool,
    operation: str,
    result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    stderr: str = "",
    exit_code: int = 0,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "operation": operation,
        "result": result or {},
        "warnings": warnings or [],
        "stderr": stderr,
        "exit_code": exit_code,
    }


def resolve_client_home(explicit_home: str | None = None) -> Path | None:
    if explicit_home:
        candidate = Path(explicit_home).expanduser().resolve()
        if candidate.is_dir():
            return candidate

    env_value = os.getenv(CLIENT_HOME_ENV)
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        if candidate.is_dir():
            return candidate

    bundled_home = prepare_bundled_runtime_client()
    if bundled_home is not None:
        return bundled_home

    tools_dir = windows_local_tools_dir()
    if tools_dir is None:
        return None

    candidate = (tools_dir / CLIENT_FOLDER_NAME).resolve()
    if candidate.is_dir():
        return candidate
    return None


def resolve_uv_executable() -> str | None:
    return shutil.which("uv.exe") or shutil.which("uv")


def build_client_command(
    *,
    client_home: Path,
    operation_args: list[str],
    uv_executable: str,
) -> list[str]:
    return [
        uv_executable,
        "run",
        "--project",
        str(client_home),
        CLIENT_ENTRYPOINT,
        *operation_args,
    ]


def build_client_env(*, client_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    if is_bundled_runtime_client(client_home):
        env["UV_PROJECT_ENVIRONMENT"] = str(bundled_runtime_venv())
    return env


def parse_payload(stdout: str) -> dict[str, Any] | None:
    stripped = stdout.strip()
    if not stripped:
        return None
    parsed = json.loads(stripped)
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def normalize_payload(
    *,
    payload: dict[str, Any] | None,
    raw_stdout: str,
    operation: str,
    stderr: str,
    exit_code: int,
) -> dict[str, Any]:
    if payload is None:
        result = {"raw_stdout": raw_stdout.strip()} if raw_stdout.strip() else {}
    else:
        result = payload

    return make_result(
        ok=exit_code == 0,
        operation=operation,
        result=result,
        warnings=[],
        stderr=stderr,
        exit_code=exit_code,
    )


def invoke_client(
    *,
    operation_args: list[str],
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    client_home: str | None = None,
) -> dict[str, Any]:
    operation = operation_args[0] if operation_args else "unknown"
    resolved_home = resolve_client_home(explicit_home=client_home)
    if resolved_home is None:
        return make_result(
            ok=False,
            operation=operation,
            stderr=(
                "Amazon CLI client not available. "
                f"Set {CLIENT_HOME_ENV} or install it under %LOCALAPPDATA%\\Tools\\{CLIENT_FOLDER_NAME}."
            ),
            exit_code=127,
        )

    uv_executable = resolve_uv_executable()
    if uv_executable is None:
        return make_result(
            ok=False,
            operation=operation,
            stderr="uv is not available on PATH.",
            exit_code=127,
        )

    command = build_client_command(
        client_home=resolved_home,
        operation_args=operation_args,
        uv_executable=uv_executable,
    )
    try:
        completed = run_process(command, timeout_sec=timeout_sec, env=build_client_env(client_home=resolved_home))
    except FileNotFoundError as exc:
        return make_result(
            ok=False,
            operation=operation,
            stderr=str(exc),
            exit_code=127,
        )
    except subprocess.TimeoutExpired as exc:
        return make_result(
            ok=False,
            operation=operation,
            stderr=merge_messages(exc.stderr or "", "Amazon CLI client timed out."),
            exit_code=124,
        )

    try:
        payload = parse_payload(completed.stdout)
    except json.JSONDecodeError:
        payload = None

    return normalize_payload(
        payload=payload,
        raw_stdout=completed.stdout,
        operation=operation,
        stderr=merge_messages(completed.stderr),
        exit_code=completed.returncode,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge into the local Amazon CLI client."
    )
    parser.add_argument("--client-home", help="Path to the standalone amazon-intent-cli project.")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument(
        "operation_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed through to amazon-cli. Use `--` before amazon-cli flags.",
    )
    return parser


def build_operation_args(args: argparse.Namespace) -> list[str]:
    operation_args = list(args.operation_args)
    if operation_args and operation_args[0] == "--":
        operation_args = operation_args[1:]
    return operation_args
