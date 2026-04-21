import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agent_toolbelt_core.common import merge_messages, run_process, windows_local_tools_dir


CLIENT_HOME_ENV = "OUTLOOK_CLASSIC_MAIL_HOME"
CLIENT_FOLDER_NAME = "outlook-classic-mail"
CLIENT_ENTRYPOINT = "outlook-classic-mail-client"
DEFAULT_TIMEOUT_SEC = 180


def make_result(
    *,
    ok: bool,
    operation: str,
    account: str | None = None,
    store: str | None = None,
    result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    stderr: str = "",
    exit_code: int = 0,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "operation": operation,
        "account": account,
        "store": store,
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
    payload.setdefault("stderr", stderr)
    payload.setdefault("exit_code", exit_code)
    payload.setdefault("warnings", [])
    payload.setdefault("result", {})
    payload.setdefault("account", None)
    payload.setdefault("store", None)
    payload.setdefault("ok", exit_code == 0)
    return payload


def parse_payload(stdout: str) -> dict[str, Any] | None:
    stripped = stdout.strip()
    if not stripped:
        return None
    return json.loads(stripped)


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
                "Outlook Classic mail client not available. "
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
            stderr=merge_messages(exc.stderr or "", "Outlook Classic mail client timed out."),
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
        description="Bridge into the local Outlook Classic COM client."
    )
    parser.add_argument("--client-home", help=argparse.SUPPRESS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)

    subparsers = parser.add_subparsers(dest="operation", required=True)

    subparsers.add_parser("accounts", help="List configured Outlook accounts and stores.")

    folders = subparsers.add_parser("folders", help="List folders for one Outlook account.")
    folders.add_argument("--account", required=True)

    search = subparsers.add_parser("search", help="Search mail in a specific account and folder.")
    search.add_argument("--account", required=True)
    search.add_argument("--folder", default="inbox")
    search.add_argument("--query")
    search.add_argument("--unread", action="store_true")
    search.add_argument("--from", dest="sender")
    search.add_argument("--to", dest="recipient")
    search.add_argument("--days", type=int)
    search.add_argument("--limit", type=int, default=20)

    read_thread = subparsers.add_parser("read-thread", help="Read a thread anchored to one message ID.")
    read_thread.add_argument("--account", required=True)
    read_thread.add_argument("--message-id", required=True)

    triage = subparsers.add_parser("triage", help="Triage inbox mail.")
    triage.add_argument("--account")
    triage.add_argument("--all-accounts", action="store_true")
    triage.add_argument("--days", type=int, default=7)
    triage.add_argument("--limit", type=int, default=20)

    draft_reply = subparsers.add_parser("draft-reply", help="Preview or create a reply draft.")
    draft_reply.add_argument("--account", required=True)
    draft_reply.add_argument("--message-id", required=True)
    draft_reply.add_argument("--instruction", required=True)
    draft_reply.add_argument("--body")
    draft_reply.add_argument("--create-draft", action="store_true")
    draft_reply.add_argument("--confirm", action="store_true")

    draft_forward = subparsers.add_parser("draft-forward", help="Preview or create a forward draft.")
    draft_forward.add_argument("--account", required=True)
    draft_forward.add_argument("--message-id", required=True)
    draft_forward.add_argument("--to", required=True)
    draft_forward.add_argument("--instruction", required=True)
    draft_forward.add_argument("--body")
    draft_forward.add_argument("--create-draft", action="store_true")
    draft_forward.add_argument("--confirm", action="store_true")

    apply_action = subparsers.add_parser("apply-action", help="Apply an explicit mailbox mutation.")
    apply_action.add_argument("--account", required=True)
    apply_action.add_argument("--message-id")
    apply_action.add_argument(
        "--action",
        required=True,
        choices=("create-draft", "send", "move", "delete", "category", "mark-read"),
    )
    apply_action.add_argument("--confirm", action="store_true")
    apply_action.add_argument("--target-folder")
    apply_action.add_argument("--category")
    apply_action.add_argument("--read-state", choices=("read", "unread"))
    apply_action.add_argument("--subject")
    apply_action.add_argument("--to")
    apply_action.add_argument("--body")

    return parser


def append_optional_arg(parts: list[str], flag: str, value: Any) -> None:
    if value not in (None, False):
        parts.extend([flag, str(value)])


def build_operation_args(args: argparse.Namespace) -> list[str]:
    parts = [args.operation]

    if args.operation == "accounts":
        return parts

    if args.operation == "folders":
        return [*parts, "--account", args.account]

    if args.operation == "search":
        parts.extend(["--account", args.account, "--folder", args.folder, "--limit", str(args.limit)])
        append_optional_arg(parts, "--query", args.query)
        if args.unread:
            parts.append("--unread")
        append_optional_arg(parts, "--from", args.sender)
        append_optional_arg(parts, "--to", args.recipient)
        append_optional_arg(parts, "--days", args.days)
        return parts

    if args.operation == "read-thread":
        return [*parts, "--account", args.account, "--message-id", args.message_id]

    if args.operation == "triage":
        if args.account:
            parts.extend(["--account", args.account])
        if args.all_accounts:
            parts.append("--all-accounts")
        append_optional_arg(parts, "--days", args.days)
        append_optional_arg(parts, "--limit", args.limit)
        return parts

    if args.operation in {"draft-reply", "draft-forward"}:
        parts.extend(["--account", args.account, "--message-id", args.message_id, "--instruction", args.instruction])
        if args.operation == "draft-forward":
            parts.extend(["--to", args.to])
        append_optional_arg(parts, "--body", args.body)
        if args.create_draft:
            parts.append("--create-draft")
        if args.confirm:
            parts.append("--confirm")
        return parts

    parts.extend(["--account", args.account, "--action", args.action])
    append_optional_arg(parts, "--message-id", args.message_id)
    append_optional_arg(parts, "--target-folder", args.target_folder)
    append_optional_arg(parts, "--category", args.category)
    append_optional_arg(parts, "--read-state", args.read_state)
    append_optional_arg(parts, "--subject", args.subject)
    append_optional_arg(parts, "--to", args.to)
    append_optional_arg(parts, "--body", args.body)
    if args.confirm:
        parts.append("--confirm")
    return parts
