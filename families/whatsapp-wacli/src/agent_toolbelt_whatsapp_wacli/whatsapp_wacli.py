import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_toolbelt_core.common import merge_messages, run_process, windows_local_tools_dir


CLIENT_HOME_ENV = "WHATSAPP_WACLI_AGENT_HOME"
CLIENT_FOLDER_NAME = "whatsapp-wacli-agent"
CLIENT_ENTRYPOINT = "whatsapp-wacli-agent"
DEFAULT_TIMEOUT_SEC = 300
DEFAULT_BACKFILL_COUNT = 100
DEFAULT_BACKFILL_REQUESTS = 3
DEFAULT_BACKFILL_WAIT_SEC = 60
DEFAULT_MEDIA_LIMIT = 3


@dataclass(frozen=True)
class ProcessLike:
    returncode: int
    stdout: str
    stderr: str


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
        "backend": "whatsapp-wacli-agent",
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

    payload.setdefault("operation", operation)
    payload.setdefault("backend", "whatsapp-wacli-agent")
    payload.setdefault("stderr", stderr)
    payload.setdefault("exit_code", exit_code)
    payload.setdefault("warnings", [])
    payload.setdefault("result", {})
    payload.setdefault("ok", exit_code == 0)
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
            warnings=["client_missing"],
            stderr=(
                "WhatsApp wacli agent client not available. "
                f"Set the {CLIENT_HOME_ENV} environment override or provide the client project root "
                "with --client-home. The legacy %LOCALAPPDATA%\\Tools project root remains a "
                "compatibility fallback."
            ),
            exit_code=127,
        )

    uv_executable = resolve_uv_executable()
    if uv_executable is None:
        return make_result(
            ok=False,
            operation=operation,
            warnings=["uv_missing"],
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
        return make_result(
            ok=False,
            operation=operation,
            warnings=["client_launch_failed"],
            stderr=str(exc),
            exit_code=127,
        )
    except subprocess.TimeoutExpired as exc:
        return make_result(
            ok=False,
            operation=operation,
            warnings=["timeout"],
            stderr=merge_messages(exc.stderr or "", "WhatsApp wacli agent client timed out."),
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
        description="Bridge into the local WhatsApp wacli agent client."
    )
    parser.add_argument("--client-home", help=argparse.SUPPRESS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    subparsers.add_parser("status")
    subparsers.add_parser("auth-status")
    auth_login = subparsers.add_parser("auth-login")
    auth_login.add_argument("--popup", action="store_true")
    subparsers.add_parser("sync-once")

    find_chat = subparsers.add_parser("find-chat")
    find_chat.add_argument("--query", required=True)
    find_chat.add_argument("--limit", type=int, default=20)

    latest = subparsers.add_parser("latest")
    latest.add_argument("--chat", required=True)
    latest.add_argument("--limit", type=int, default=20)
    latest.add_argument("--no-backfill", action="store_true")
    latest.add_argument("--backfill-count", type=int, default=DEFAULT_BACKFILL_COUNT)
    latest.add_argument("--backfill-requests", type=int, default=DEFAULT_BACKFILL_REQUESTS)
    latest.add_argument("--backfill-wait-sec", type=int, default=DEFAULT_BACKFILL_WAIT_SEC)
    latest.add_argument("--include-media", action="store_true")
    latest.add_argument("--media-limit", type=int, default=DEFAULT_MEDIA_LIMIT)

    backfill = subparsers.add_parser("backfill")
    backfill.add_argument("--chat", required=True)
    backfill.add_argument("--count", type=int, default=DEFAULT_BACKFILL_COUNT)
    backfill.add_argument("--requests", type=int, default=DEFAULT_BACKFILL_REQUESTS)
    backfill.add_argument("--wait-sec", type=int, default=DEFAULT_BACKFILL_WAIT_SEC)

    search = subparsers.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--chat")
    search.add_argument("--limit", type=int, default=50)
    search.add_argument("--include-media", action="store_true")
    search.add_argument("--media-limit", type=int, default=DEFAULT_MEDIA_LIMIT)

    context = subparsers.add_parser("context")
    context.add_argument("--message-id", required=True)
    context.add_argument("--before", type=int, default=5)
    context.add_argument("--after", type=int, default=5)
    context.add_argument("--include-media", action="store_true")
    context.add_argument("--media-limit", type=int, default=DEFAULT_MEDIA_LIMIT)

    draft_reply = subparsers.add_parser("draft-reply")
    draft_reply.add_argument("--chat", required=True)
    draft_reply.add_argument("--instruction", required=True)
    draft_reply.add_argument("--limit", type=int, default=20)
    draft_reply.add_argument("--include-media", action="store_true")
    draft_reply.add_argument("--media-limit", type=int, default=DEFAULT_MEDIA_LIMIT)

    send_text = subparsers.add_parser("send-text")
    send_text.add_argument("--chat", required=True)
    send_text.add_argument("--message", required=True)
    send_text.add_argument("--confirm", action="store_true")

    react = subparsers.add_parser("react")
    react.add_argument("--chat", required=True)
    react.add_argument("--message-id", required=True)
    react.add_argument("--reaction", required=True)
    react.add_argument("--confirm", action="store_true")

    presence = subparsers.add_parser("presence")
    presence.add_argument("--chat", required=True)
    presence.add_argument("--state", choices=("typing", "paused"), required=True)
    presence.add_argument("--confirm", action="store_true")

    return parser


def build_operation_args(args: argparse.Namespace) -> list[str]:
    parts = [args.operation]
    if args.operation in {"status", "auth-status", "sync-once"}:
        return parts
    if args.operation == "auth-login":
        if args.popup:
            parts.append("--popup")
        return parts
    if args.operation == "find-chat":
        return [*parts, "--query", args.query, "--limit", str(args.limit)]
    if args.operation == "latest":
        parts.extend(["--chat", args.chat, "--limit", str(args.limit)])
        if args.no_backfill:
            parts.append("--no-backfill")
        parts.extend(["--backfill-count", str(args.backfill_count)])
        parts.extend(["--backfill-requests", str(args.backfill_requests)])
        parts.extend(["--backfill-wait-sec", str(args.backfill_wait_sec)])
        if args.include_media:
            parts.append("--include-media")
        parts.extend(["--media-limit", str(args.media_limit)])
        return parts
    if args.operation == "backfill":
        return [
            *parts,
            "--chat",
            args.chat,
            "--count",
            str(args.count),
            "--requests",
            str(args.requests),
            "--wait-sec",
            str(args.wait_sec),
        ]
    if args.operation == "search":
        parts.extend(["--query", args.query, "--limit", str(args.limit)])
        if args.chat:
            parts.extend(["--chat", args.chat])
        if args.include_media:
            parts.append("--include-media")
        parts.extend(["--media-limit", str(args.media_limit)])
        return parts
    if args.operation == "context":
        parts.extend(["--message-id", args.message_id])
        parts.extend(["--before", str(args.before), "--after", str(args.after)])
        if args.include_media:
            parts.append("--include-media")
        parts.extend(["--media-limit", str(args.media_limit)])
        return parts
    if args.operation == "draft-reply":
        parts.extend(["--chat", args.chat, "--instruction", args.instruction])
        parts.extend(["--limit", str(args.limit)])
        if args.include_media:
            parts.append("--include-media")
        parts.extend(["--media-limit", str(args.media_limit)])
        return parts
    if args.operation == "send-text":
        parts.extend(["--chat", args.chat, "--message", args.message])
        if args.confirm:
            parts.append("--confirm")
        return parts
    if args.operation == "react":
        parts.extend(["--chat", args.chat, "--message-id", args.message_id, "--reaction", args.reaction])
        if args.confirm:
            parts.append("--confirm")
        return parts
    if args.operation == "presence":
        parts.extend(["--chat", args.chat, "--state", args.state])
        if args.confirm:
            parts.append("--confirm")
        return parts
    return parts
