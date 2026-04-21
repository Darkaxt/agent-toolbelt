import argparse
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


def package_root() -> Path:
    return Path(__file__).resolve().parent


def bundled_client_home() -> Path:
    return package_root() / "assets" / "amazon-intent-cli"


def runtime_venv_dir() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "agent-toolbelt" / "amazon-cli" / "uv-env"
    cache_home = os.getenv("XDG_CACHE_HOME")
    root = Path(cache_home).expanduser() if cache_home else Path.home() / ".cache"
    return root / "agent-toolbelt" / "amazon-cli" / "uv-env"


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

    bundled_home = bundled_client_home().resolve()
    if (bundled_home / "pyproject.toml").is_file():
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
        "--no-project",
        "--with-editable",
        str(client_home),
        CLIENT_ENTRYPOINT,
        *operation_args,
    ]


def build_client_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT_ENVIRONMENT"] = str(runtime_venv_dir())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
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
                f"Set {CLIENT_HOME_ENV}, restore the bundled client, or install it under "
                f"%LOCALAPPDATA%\\Tools\\{CLIENT_FOLDER_NAME}."
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
        completed = run_process(command, timeout_sec=timeout_sec, env=build_client_env())
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
