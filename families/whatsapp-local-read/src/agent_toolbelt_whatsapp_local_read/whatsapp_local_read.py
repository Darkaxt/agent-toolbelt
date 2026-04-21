import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agent_toolbelt_core.common import merge_messages, run_process, windows_local_tools_dir


CLIENT_HOME_ENV = "WHATSAPP_LOCAL_READ_HOME"
CLIENT_FOLDER_NAME = "whatsapp-local-read"
CLIENT_ENTRYPOINT = "whatsapp-local-read-client"
DEFAULT_TIMEOUT_SEC = 120


def make_result(
    *,
    ok: bool,
    operation: str,
    backend: str = "unknown",
    result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    stderr: str = "",
    exit_code: int = 0,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "operation": operation,
        "backend": backend,
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


def parse_payload(stdout: str) -> dict[str, Any] | None:
    stripped = stdout.strip()
    if not stripped:
        return None
    return json.loads(stripped)


def normalize_payload(
    *,
    payload: dict[str, Any] | None,
    operation: str,
    stderr: str,
    exit_code: int,
) -> dict[str, Any]:
    if payload is None:
        return make_result(
            ok=exit_code == 0,
            operation=operation,
            stderr=stderr,
            exit_code=exit_code,
        )

    payload.setdefault("ok", exit_code == 0)
    payload.setdefault("operation", operation)
    payload.setdefault("backend", "unknown")
    payload.setdefault("result", {})
    payload.setdefault("warnings", [])
    payload.setdefault("stderr", stderr)
    payload.setdefault("exit_code", exit_code)
    return payload


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
                "WhatsApp local read client not available. "
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
        completed = run_process(command, timeout_sec=timeout_sec)
    except FileNotFoundError as exc:
        return make_result(ok=False, operation=operation, stderr=str(exc), exit_code=127)
    except subprocess.TimeoutExpired as exc:
        return make_result(
            ok=False,
            operation=operation,
            stderr=merge_messages(exc.stderr or "", "WhatsApp local read client timed out."),
            exit_code=124,
        )

    try:
        payload = parse_payload(completed.stdout)
    except json.JSONDecodeError:
        payload = None

    return normalize_payload(
        payload=payload,
        operation=operation,
        stderr=merge_messages(completed.stderr),
        exit_code=completed.returncode,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge into the local read-only WhatsApp Desktop inspection client."
    )
    parser.add_argument("--client-home", help=argparse.SUPPRESS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)

    subparsers = parser.add_subparsers(dest="operation", required=True)

    subparsers.add_parser("status", help="Report installed package, storage, process, and backend status.")
    subparsers.add_parser("probe-db", help="Probe local stores with safe magic-byte/schema checks.")
    subparsers.add_parser("current-chat", help="Capture text from the currently visible WhatsApp chat.")

    db_read = subparsers.add_parser("db-read", help="Read from a proven plain local store when supported.")
    db_read.add_argument("--store")

    summarize = subparsers.add_parser("summarize", help="Summarize captured visible/current chat content.")
    summarize.add_argument("--source", choices=("current-chat",), default="current-chat")

    suggest = subparsers.add_parser("suggest-response", help="Suggest response text from visible/current chat.")
    suggest.add_argument("--instruction", required=True)
    suggest.add_argument("--source", choices=("current-chat",), default="current-chat")

    return parser


def build_operation_args(args: argparse.Namespace) -> list[str]:
    parts = [args.operation]

    if args.operation in {"status", "probe-db", "current-chat"}:
        return parts

    if args.operation == "db-read":
        if args.store:
            parts.extend(["--store", args.store])
        return parts

    if args.operation == "summarize":
        return [*parts, "--source", args.source]

    if args.operation == "suggest-response":
        return [*parts, "--instruction", args.instruction, "--source", args.source]

    return parts
