import argparse
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from agent_toolbelt_core.common import merge_messages, run_process, windows_local_tools_dir


CLIENT_HOME_ENV = "OUTLOOK_CLASSIC_MAIL_HOME"
CLIENT_FOLDER_NAME = "outlook-classic-mail"
CLIENT_ENTRYPOINT = "outlook-classic-mail-client"
DEFAULT_TIMEOUT_SEC = 180
DEFAULT_QUEUE_TIMEOUT_SEC = 900


def make_result(
    *,
    ok: bool,
    operation: str,
    account: str | None = None,
    store: str | None = None,
    result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    wrapper_diagnostics: dict[str, Any] | None = None,
    stderr: str = "",
    exit_code: int = 0,
) -> dict[str, Any]:
    payload = {
        "ok": ok,
        "operation": operation,
        "account": account,
        "store": store,
        "result": result or {},
        "warnings": warnings or [],
        "stderr": stderr,
        "exit_code": exit_code,
    }
    if wrapper_diagnostics is not None:
        payload["wrapper_diagnostics"] = wrapper_diagnostics
    return payload


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


def client_home_source(*, explicit_home: str | None, resolved_home: Path | None) -> str:
    if resolved_home is None:
        return "unavailable"
    resolved = resolved_home.resolve()
    if explicit_home and Path(explicit_home).expanduser().resolve() == resolved:
        return "explicit"
    env_value = os.getenv(CLIENT_HOME_ENV)
    if env_value and Path(env_value).expanduser().resolve() == resolved:
        return "environment"
    tools_dir = windows_local_tools_dir()
    if tools_dir is not None and (tools_dir / CLIENT_FOLDER_NAME).resolve() == resolved:
        return "local_tools"
    return "resolved"


def build_wrapper_diagnostics(
    *,
    client_home: str | None,
    resolved_home: Path | None,
    queue_timeout_sec: int,
    command_timeout_sec: int,
    failure_kind: str | None = None,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "invocation_id": str(uuid.uuid4()),
        "access_model": "local_outlook_classic_com",
        "cloud_connector_used": False,
        "client_home_source": client_home_source(explicit_home=client_home, resolved_home=resolved_home),
        "client_home_resolved": str(resolved_home) if resolved_home is not None else None,
        "queue_timeout_sec": queue_timeout_sec,
        "command_timeout_sec": command_timeout_sec,
    }
    if failure_kind:
        diagnostics["failure_kind"] = failure_kind
    return diagnostics


def build_client_command(
    *,
    client_home: Path,
    operation_args: list[str],
    uv_executable: str,
    queue_timeout_sec: int = DEFAULT_QUEUE_TIMEOUT_SEC,
) -> list[str]:
    return [
        uv_executable,
        "run",
        "--project",
        str(client_home),
        CLIENT_ENTRYPOINT,
        "--queue-timeout-sec",
        str(queue_timeout_sec),
        *operation_args,
    ]


def normalize_payload(
    *,
    payload: dict[str, Any] | None,
    operation: str,
    stderr: str,
    exit_code: int,
    wrapper_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    if payload is None:
        return make_result(
            ok=exit_code == 0,
            operation=operation,
            stderr=stderr,
            exit_code=exit_code,
            wrapper_diagnostics=wrapper_diagnostics,
        )

    payload.setdefault("operation", operation)
    payload.setdefault("stderr", stderr)
    payload.setdefault("exit_code", exit_code)
    payload.setdefault("warnings", [])
    payload.setdefault("result", {})
    payload.setdefault("account", None)
    payload.setdefault("store", None)
    payload.setdefault("ok", exit_code == 0)
    payload.setdefault("wrapper_diagnostics", wrapper_diagnostics)
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
    queue_timeout_sec: int = DEFAULT_QUEUE_TIMEOUT_SEC,
    client_home: str | None = None,
) -> dict[str, Any]:
    operation = operation_args[0] if operation_args else "unknown"
    resolved_home = resolve_client_home(explicit_home=client_home)
    diagnostics = build_wrapper_diagnostics(
        client_home=client_home,
        resolved_home=resolved_home,
        queue_timeout_sec=queue_timeout_sec,
        command_timeout_sec=timeout_sec,
    )
    if resolved_home is None:
        return make_result(
            ok=False,
            operation=operation,
            stderr=(
                "Outlook Classic mail client not available. "
                f"Set the {CLIENT_HOME_ENV} environment override or provide the client project root "
                "with --client-home. The legacy %LOCALAPPDATA%\\Tools project root remains a "
                "compatibility fallback."
            ),
            exit_code=127,
            wrapper_diagnostics={
                **diagnostics,
                "failure_kind": "client_unavailable",
            },
        )

    uv_executable = resolve_uv_executable()
    if uv_executable is None:
        return make_result(
            ok=False,
            operation=operation,
            stderr="uv is not available on PATH.",
            exit_code=127,
            wrapper_diagnostics={
                **diagnostics,
                "failure_kind": "uv_unavailable",
            },
        )

    command = build_client_command(
        client_home=resolved_home,
        operation_args=operation_args,
        uv_executable=uv_executable,
        queue_timeout_sec=queue_timeout_sec,
    )
    try:
        completed = run_process(command, timeout_sec=timeout_sec + queue_timeout_sec + 15)
    except FileNotFoundError as exc:
        return make_result(
            ok=False,
            operation=operation,
            stderr=str(exc),
            exit_code=127,
            wrapper_diagnostics={
                **diagnostics,
                "failure_kind": "process_start_failed",
            },
        )
    except subprocess.TimeoutExpired as exc:
        return make_result(
            ok=False,
            operation=operation,
            stderr=merge_messages(exc.stderr or "", "Outlook Classic mail client timed out."),
            exit_code=124,
            wrapper_diagnostics={
                **diagnostics,
                "failure_kind": "wrapper_timeout",
            },
        )

    json_decode_failed = False
    try:
        payload = parse_payload(completed.stdout)
    except json.JSONDecodeError:
        payload = None
        json_decode_failed = True

    return normalize_payload(
        payload=payload,
        operation=operation,
        stderr=merge_messages(completed.stderr),
        exit_code=completed.returncode,
        wrapper_diagnostics={
            **diagnostics,
            **({"failure_kind": "invalid_json"} if json_decode_failed else {}),
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge into the local Outlook Classic COM client."
    )
    parser.add_argument("--client-home", help=argparse.SUPPRESS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--queue-timeout-sec", type=int, default=DEFAULT_QUEUE_TIMEOUT_SEC)

    subparsers = parser.add_subparsers(dest="operation", required=True)

    subparsers.add_parser("accounts", help="List configured Outlook accounts and stores.")

    folders = subparsers.add_parser("folders", help="List folders for one Outlook account.")
    folders.add_argument("--account", required=True)

    find_folders = subparsers.add_parser("find-folders", help="Find folders by name or path.")
    find_folders.add_argument("--query", required=True)
    find_folders.add_argument("--account")
    find_folders.add_argument("--all-accounts", action="store_true")
    find_folders.add_argument("--limit", type=int, default=20)

    cache_status = subparsers.add_parser("cache-status", help="Inspect the local Outlook metadata cache.")
    cache_status.add_argument("--query")
    cache_status.add_argument("--cache-path")

    cache_show = subparsers.add_parser("cache-show", help="Show local cache hits for a query.")
    cache_show.add_argument("--query", required=True)
    cache_show.add_argument("--account")
    cache_show.add_argument("--days", type=int)
    cache_show.add_argument("--limit", type=int, default=25)
    cache_show.add_argument("--cache-path")

    cache_refresh = subparsers.add_parser("cache-refresh", help="Refresh recent Outlook metadata into the cache.")
    cache_refresh.add_argument("--account")
    cache_refresh.add_argument("--all-accounts", action="store_true")
    cache_refresh.add_argument("--days", type=int, default=90)
    cache_refresh.add_argument("--force", action="store_true")
    cache_refresh.add_argument("--cache-path")

    cache_clear = subparsers.add_parser("cache-clear", help="Clear local Outlook metadata cache entries.")
    cache_clear.add_argument("--query")
    cache_clear.add_argument("--confirm", action="store_true")
    cache_clear.add_argument("--cache-path")

    sync_mail = subparsers.add_parser("sync-mail", help="Trigger Outlook Send/Receive All Folders.")
    sync_mail.add_argument("--refresh-cache", action="store_true")
    sync_mail.add_argument("--account")
    sync_mail.add_argument("--all-accounts", action="store_true")
    sync_mail.add_argument("--days", type=int, default=90)
    sync_mail.add_argument("--force", action="store_true")
    sync_mail.add_argument("--cache-path")

    subparsers.add_parser("diagnostics-probe", help="Probe Outlook COM availability and diagnostic metadata.")

    diagnostics_log = subparsers.add_parser("diagnostics-log", help="Show recent local Outlook COM diagnostic events.")
    diagnostics_log.add_argument("--limit", type=int, default=20)

    search = subparsers.add_parser("search", help="Search mail in a specific account and folder.")
    search.add_argument("--account")
    search.add_argument("--folder", default="inbox")
    search.add_argument("--query")
    search.add_argument("--all-folders", action="store_true")
    search.add_argument("--all-accounts", action="store_true")
    search.add_argument("--unread", action="store_true")
    search.add_argument("--from", dest="sender")
    search.add_argument("--to", dest="recipient")
    search.add_argument("--days", type=int)
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--folder-limit", type=int, default=10)
    search.add_argument("--per-folder-limit", type=int, default=5)
    search.add_argument("--no-update-hints", action="store_true")
    search.add_argument("--no-cache", action="store_true")
    search.add_argument("--bypass-cache", action="store_true")
    search.add_argument("--broad-scan", action="store_true")
    search.add_argument("--no-update-cache", action="store_true")
    search.add_argument("--cache-path")

    read_thread = subparsers.add_parser("read-thread", help="Read a thread anchored to one message ID.")
    read_thread.add_argument("--account", required=True)
    read_thread.add_argument("--message-id", required=True)

    read_message = subparsers.add_parser("read-message", help="Read one message body and attachment metadata.")
    read_message.add_argument("--account", required=True)
    read_message.add_argument("--message-id", required=True)
    read_message.add_argument("--include-html", action="store_true")

    blocklists = subparsers.add_parser("blocklists", help="Inspect or refresh local DNS blocklist cache.")
    blocklists.add_argument("action", choices=("status", "refresh"))
    blocklists.add_argument("--blocklist-profile", choices=("threat", "debug-all"), default="threat")
    blocklists.add_argument("--blocklist-cache")
    blocklists.add_argument("--force", action="store_true")

    inspect_domains = subparsers.add_parser(
        "inspect-domains",
        help="Inspect domain references on one message without mutating mail.",
    )
    inspect_domains.add_argument("--account", required=True)
    inspect_domains.add_argument("--message-id", required=True)
    inspect_domains.add_argument("--with-rdap", action="store_true")
    inspect_domains.add_argument("--young-days", type=int, default=365)
    inspect_domains.add_argument("--rdap-cache")
    inspect_domains.add_argument("--with-blocklists", action="store_true")
    inspect_domains.add_argument("--blocklist-profile", choices=("threat", "debug-all"), default="threat")
    inspect_domains.add_argument("--blocklist-cache")

    scan_domain_refs = subparsers.add_parser(
        "scan-domain-refs",
        help="Inspect domain references for recent messages in one folder without mutating mail.",
    )
    scan_domain_refs.add_argument("--account", required=True)
    scan_domain_refs.add_argument("--folder", default="inbox")
    scan_domain_refs.add_argument("--days", type=int, default=7)
    scan_domain_refs.add_argument("--limit", type=int, default=20)
    scan_domain_refs.add_argument("--with-rdap", action="store_true")
    scan_domain_refs.add_argument("--young-days", type=int, default=365)
    scan_domain_refs.add_argument("--rdap-cache")
    scan_domain_refs.add_argument("--with-blocklists", action="store_true")
    scan_domain_refs.add_argument("--blocklist-profile", choices=("threat", "debug-all"), default="threat")
    scan_domain_refs.add_argument("--blocklist-cache")

    find_response = subparsers.add_parser("find-response", help="Find sent or draft responses to a message.")
    find_response.add_argument("--account", required=True)
    find_response.add_argument("--message-id", required=True)
    find_response.add_argument("--limit", type=int, default=20)
    find_response.add_argument("--fallback-all-accounts", action="store_true")
    find_response.add_argument("--exclude-drafts", action="store_true")

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
    draft_reply.add_argument("--attach", action="append", default=[])
    draft_reply.add_argument("--send-using-account")
    draft_reply.add_argument("--create-draft", action="store_true")
    draft_reply.add_argument("--confirm", action="store_true")

    draft_forward = subparsers.add_parser("draft-forward", help="Preview or create a forward draft.")
    draft_forward.add_argument("--account", required=True)
    draft_forward.add_argument("--message-id", required=True)
    draft_forward.add_argument("--to", required=True)
    draft_forward.add_argument("--instruction", required=True)
    draft_forward.add_argument("--body")
    draft_forward.add_argument("--attach", action="append", default=[])
    draft_forward.add_argument("--send-using-account")
    draft_forward.add_argument("--create-draft", action="store_true")
    draft_forward.add_argument("--confirm", action="store_true")

    move_message = subparsers.add_parser("move-message", help="Preview or move a message to a folder.")
    move_message.add_argument("--account", required=True)
    move_message.add_argument("--message-id", required=True)
    move_message.add_argument("--target-folder", required=True)
    move_message.add_argument("--confirm", action="store_true")

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
    apply_action.add_argument("--attach", action="append", default=[])

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

    if args.operation == "find-folders":
        parts.extend(["--query", args.query])
        append_optional_arg(parts, "--account", args.account)
        if args.all_accounts:
            parts.append("--all-accounts")
        parts.extend(["--limit", str(args.limit)])
        return parts

    if args.operation == "cache-status":
        append_optional_arg(parts, "--query", args.query)
        append_optional_arg(parts, "--cache-path", args.cache_path)
        return parts

    if args.operation == "cache-show":
        parts.extend(["--query", args.query])
        append_optional_arg(parts, "--account", args.account)
        append_optional_arg(parts, "--days", args.days)
        parts.extend(["--limit", str(args.limit)])
        append_optional_arg(parts, "--cache-path", args.cache_path)
        return parts

    if args.operation == "cache-refresh":
        append_optional_arg(parts, "--account", args.account)
        if args.all_accounts:
            parts.append("--all-accounts")
        parts.extend(["--days", str(args.days)])
        if args.force:
            parts.append("--force")
        append_optional_arg(parts, "--cache-path", args.cache_path)
        return parts

    if args.operation == "cache-clear":
        append_optional_arg(parts, "--query", args.query)
        if args.confirm:
            parts.append("--confirm")
        append_optional_arg(parts, "--cache-path", args.cache_path)
        return parts

    if args.operation == "sync-mail":
        if args.refresh_cache:
            parts.append("--refresh-cache")
        append_optional_arg(parts, "--account", args.account)
        if args.all_accounts:
            parts.append("--all-accounts")
        parts.extend(["--days", str(args.days)])
        if args.force:
            parts.append("--force")
        append_optional_arg(parts, "--cache-path", args.cache_path)
        return parts

    if args.operation == "diagnostics-probe":
        return parts

    if args.operation == "diagnostics-log":
        parts.extend(["--limit", str(args.limit)])
        return parts

    if args.operation == "search":
        if args.account:
            parts.extend(["--account", args.account])
        if not args.all_folders:
            parts.extend(["--folder", args.folder])
        if args.all_folders:
            parts.append("--all-folders")
        append_optional_arg(parts, "--query", args.query)
        if args.all_accounts:
            parts.append("--all-accounts")
        parts.extend(["--limit", str(args.limit)])
        if args.unread:
            parts.append("--unread")
        append_optional_arg(parts, "--from", args.sender)
        append_optional_arg(parts, "--to", args.recipient)
        append_optional_arg(parts, "--days", args.days)
        if args.all_folders:
            parts.extend(["--folder-limit", str(args.folder_limit)])
            parts.extend(["--per-folder-limit", str(args.per_folder_limit)])
        if args.no_update_hints:
            parts.append("--no-update-hints")
        if args.no_cache:
            parts.append("--no-cache")
        if args.bypass_cache:
            parts.append("--bypass-cache")
        if args.broad_scan:
            parts.append("--broad-scan")
        if args.no_update_cache:
            parts.append("--no-update-cache")
        append_optional_arg(parts, "--cache-path", args.cache_path)
        return parts

    if args.operation == "read-thread":
        return [*parts, "--account", args.account, "--message-id", args.message_id]

    if args.operation == "read-message":
        parts.extend(["--account", args.account, "--message-id", args.message_id])
        if args.include_html:
            parts.append("--include-html")
        return parts

    if args.operation == "blocklists":
        parts.append(args.action)
        parts.extend(["--blocklist-profile", args.blocklist_profile])
        append_optional_arg(parts, "--blocklist-cache", args.blocklist_cache)
        if args.force:
            parts.append("--force")
        return parts

    if args.operation == "inspect-domains":
        parts.extend(["--account", args.account, "--message-id", args.message_id])
        if args.with_rdap:
            parts.append("--with-rdap")
        parts.extend(["--young-days", str(args.young_days)])
        append_optional_arg(parts, "--rdap-cache", args.rdap_cache)
        if args.with_blocklists:
            parts.append("--with-blocklists")
        parts.extend(["--blocklist-profile", args.blocklist_profile])
        append_optional_arg(parts, "--blocklist-cache", args.blocklist_cache)
        return parts

    if args.operation == "scan-domain-refs":
        parts.extend(
            [
                "--account",
                args.account,
                "--folder",
                args.folder,
                "--days",
                str(args.days),
                "--limit",
                str(args.limit),
            ]
        )
        if args.with_rdap:
            parts.append("--with-rdap")
        parts.extend(["--young-days", str(args.young_days)])
        append_optional_arg(parts, "--rdap-cache", args.rdap_cache)
        if args.with_blocklists:
            parts.append("--with-blocklists")
        parts.extend(["--blocklist-profile", args.blocklist_profile])
        append_optional_arg(parts, "--blocklist-cache", args.blocklist_cache)
        return parts

    if args.operation == "find-response":
        parts.extend(["--account", args.account, "--message-id", args.message_id, "--limit", str(args.limit)])
        if args.fallback_all_accounts:
            parts.append("--fallback-all-accounts")
        if args.exclude_drafts:
            parts.append("--exclude-drafts")
        return parts

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
        append_optional_arg(parts, "--send-using-account", args.send_using_account)
        append_optional_arg(parts, "--body", args.body)
        for attachment in args.attach or []:
            parts.extend(["--attach", attachment])
        if args.create_draft:
            parts.append("--create-draft")
        if args.confirm:
            parts.append("--confirm")
        return parts

    if args.operation == "move-message":
        parts.extend(
            [
                "--account",
                args.account,
                "--message-id",
                args.message_id,
                "--target-folder",
                args.target_folder,
            ]
        )
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
    for attachment in args.attach or []:
        parts.extend(["--attach", attachment])
    if args.confirm:
        parts.append("--confirm")
    return parts
