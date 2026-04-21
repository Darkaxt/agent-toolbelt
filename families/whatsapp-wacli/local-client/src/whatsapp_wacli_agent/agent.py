import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_TIMEOUT_SEC = 300
DEFAULT_BACKFILL_COUNT = 100
DEFAULT_BACKFILL_REQUESTS = 3
DEFAULT_BACKFILL_WAIT_SEC = 60
WACLI_PATH_ENV = "WHATSAPP_WACLI_PATH"
WACLI_STORE_ENV = "WHATSAPP_WACLI_STORE"
JID_RE = re.compile(r"^[^@\s]+@(s\.whatsapp\.net|g\.us|lid)$")
PHONE_JID_SUFFIX = "@s.whatsapp.net"
LID_JID_SUFFIX = "@lid"


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Config:
    wacli_path: Path
    store_dir: Path


Runner = Callable[[list[str]], ProcessResult]
Launcher = Callable[[list[str]], int]


def local_tools_dir() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "Tools"
    return Path.home() / "AppData" / "Local" / "Tools"


def resolve_config(
    *,
    wacli_path: str | None = None,
    store_dir: str | None = None,
) -> Config:
    path_candidate = (
        Path(wacli_path)
        if wacli_path
        else Path(os.getenv(WACLI_PATH_ENV, ""))
        if os.getenv(WACLI_PATH_ENV)
        else local_tools_dir() / "wacli" / "wacli.exe"
    )
    if not path_candidate.exists():
        discovered = shutil.which("wacli.exe") or shutil.which("wacli")
        if discovered:
            path_candidate = Path(discovered)

    store_candidate = (
        Path(store_dir)
        if store_dir
        else Path(os.getenv(WACLI_STORE_ENV, ""))
        if os.getenv(WACLI_STORE_ENV)
        else local_tools_dir() / "wacli" / "store"
    )
    return Config(
        wacli_path=path_candidate.expanduser().resolve(),
        store_dir=store_candidate.expanduser().resolve(),
    )


def make_result(
    *,
    ok: bool,
    operation: str,
    result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    stderr: str = "",
    exit_code: int = 0,
    backend: str = "wacli",
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


def build_wacli_command(config: Config, args: list[str]) -> list[str]:
    return [
        str(config.wacli_path),
        "--store",
        str(config.store_dir),
        "--json",
        *args,
    ]


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_auth_popup_command(config: Config) -> list[str]:
    script = "\n".join(
        [
            "$Host.UI.RawUI.WindowTitle = 'WhatsApp wacli QR login'",
            "Write-Host 'WhatsApp QR login for local wacli store'",
            "Write-Host 'Scan the QR in WhatsApp: Settings > Linked devices > Link a device.'",
            "Write-Host ''",
            (
                "& "
                + powershell_quote(str(config.wacli_path))
                + " --store "
                + powershell_quote(str(config.store_dir))
                + " auth --idle-exit 30s"
            ),
            "Write-Host ''",
            "Write-Host ('wacli auth exited with code ' + $LASTEXITCODE)",
            "Write-Host 'After scanning, return to Codex and run auth-status. You can close this window.'",
        ]
    )
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-NoExit",
        "-Command",
        script,
    ]


def default_runner(
    command: list[str],
    *,
    timeout_sec: int,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout_sec,
        env=merged_env,
    )
    return ProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def default_launcher(command: list[str]) -> int:
    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    process = subprocess.Popen(command, creationflags=creation_flags)
    return process.pid


def normalize_process_result(
    *,
    operation: str,
    backend: str,
    completed: ProcessResult,
) -> dict[str, Any]:
    payload: Any = None
    warnings: list[str] = []
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    raw = stdout.strip() or stderr.strip()
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            warnings.append("malformed_json")
    return make_result(
        ok=completed.returncode == 0 and "malformed_json" not in warnings,
        operation=operation,
        backend=backend,
        result={"payload": payload} if payload is not None else {},
        warnings=warnings,
        stderr=completed.stderr.strip(),
        exit_code=completed.returncode,
    )


def invoke_wacli(
    operation: str,
    args: list[str],
    *,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    read_only_env: bool = True,
) -> dict[str, Any]:
    config = config or resolve_config()
    if not config.wacli_path.exists():
        return make_result(
            ok=False,
            operation=operation,
            warnings=["wacli_missing"],
            stderr=f"wacli not found at {config.wacli_path}",
            exit_code=127,
        )
    config.store_dir.mkdir(parents=True, exist_ok=True)
    env = {"WACLI_READONLY": "1"} if read_only_env else {}
    try:
        completed = runner(
            build_wacli_command(config, args),
            timeout_sec=timeout_sec,
            env=env,
        )
    except FileNotFoundError as exc:
        return make_result(
            ok=False,
            operation=operation,
            warnings=["wacli_missing"],
            stderr=str(exc),
            exit_code=127,
        )
    except subprocess.TimeoutExpired as exc:
        return make_result(
            ok=False,
            operation=operation,
            warnings=["timeout"],
            stderr=str(exc),
            exit_code=124,
        )
    return normalize_process_result(operation=operation, backend="wacli", completed=completed)


def payload_items(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = payload_items(value, keys)
            if nested:
                return nested
    value = payload.get("payload")
    if value is not None:
        return payload_items(value, keys)
    return []


def normalize_chat(chat: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(chat)
    field_map = {
        "JID": "jid",
        "Name": "name",
        "Kind": "kind",
        "LastMessageTS": "last_message_ts",
    }
    for source, target in field_map.items():
        if source in chat and target not in normalized:
            normalized[target] = chat[source]
    return normalized


def normalize_contact(contact: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(contact)
    field_map = {
        "JID": "jid",
        "Phone": "phone",
        "Name": "name",
        "Alias": "alias",
        "Tags": "tags",
        "UpdatedAt": "updated_at",
    }
    for source, target in field_map.items():
        if source in contact and target not in normalized:
            normalized[target] = contact[source]
    if "name" not in normalized:
        for candidate in ("alias", "push_name", "full_name", "business_name", "first_name", "phone", "jid"):
            value = normalized.get(candidate)
            if value:
                normalized["name"] = value
                break
    normalized["kind"] = "contact"
    normalized["source"] = "contact"
    return normalized


def lid_jid_for_phone_jid(config: Config, jid: str) -> str | None:
    jid = jid.strip()
    if not jid.endswith(PHONE_JID_SUFFIX):
        return None
    phone = jid[: -len(PHONE_JID_SUFFIX)]
    if not phone:
        return None

    db_path = config.store_dir / "session.db"
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        try:
            row = conn.execute(
                "select lid from whatsmeow_lid_map where pn=? limit 1",
                (phone,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    return f"{row[0]}{LID_JID_SUFFIX}"


def add_resolution_metadata(
    *,
    requested_chat: str,
    chat_info: dict[str, Any],
    config: Config,
    use_lid_mapping: bool = True,
) -> dict[str, Any]:
    resolved = dict(chat_info)
    jid = str(resolved.get("jid", "")).strip()
    source = str(resolved.get("source") or "chat")
    contact_jid = jid if jid.endswith(PHONE_JID_SUFFIX) else None
    mapped_lid = lid_jid_for_phone_jid(config, jid) if use_lid_mapping else None
    resolved_jid = mapped_lid or jid
    resolution_source = "pn_lid_map" if mapped_lid else source

    resolved["requested_chat"] = requested_chat
    resolved["contact_jid"] = contact_jid
    resolved["resolved_jid"] = resolved_jid
    resolved["resolution_source"] = resolution_source
    return resolved


def resolution_summary(chat_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "requested_chat": chat_info.get("requested_chat"),
        "chat_jid": chat_info.get("jid"),
        "contact_jid": chat_info.get("contact_jid"),
        "resolved_jid": chat_info.get("resolved_jid") or chat_info.get("jid"),
        "resolution_source": chat_info.get("resolution_source") or chat_info.get("source") or "chat",
    }


def search_contacts(
    query: str,
    *,
    limit: int = 20,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    response = invoke_wacli(
        "contacts-search",
        ["contacts", "search", query, "--limit", str(limit)],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=True,
    )
    if not response["ok"]:
        return response
    contacts = [
        normalize_contact(contact)
        for contact in payload_items(response["result"].get("payload"), ("data", "contacts", "items", "results"))
    ]
    response["result"] = {"contacts": contacts}
    return response


def message_count_for_chat(config: Config, jid: str) -> int | None:
    db_path = config.store_dir / "wacli.db"
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        try:
            row = conn.execute(
                "select count(*) from messages where chat_jid=?",
                (jid,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return int(row[0]) if row else None


def message_items_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    return payload_items(
        response.get("result", {}).get("payload"),
        ("messages", "data", "items", "results"),
    )


def is_jid(value: str) -> bool:
    return bool(JID_RE.match(value.strip()))


def find_chat(
    query: str,
    *,
    limit: int = 20,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    config = config or resolve_config()
    response = invoke_wacli(
        "find-chat",
        ["chats", "list", "--query", query, "--limit", str(limit)],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=True,
    )
    if not response["ok"]:
        return response

    chats = [
        normalize_chat(chat)
        for chat in payload_items(response["result"].get("payload"), ("data", "chats", "items", "results"))
    ]
    if len(chats) == 1:
        chat = add_resolution_metadata(requested_chat=query, chat_info=chats[0], config=config)
        response["result"] = {"chat": chat, "matches": chats}
        return response

    exact = [
        chat
        for chat in chats
        if str(chat.get("name", "")).strip().lower() == query.strip().lower()
    ]
    if len(exact) == 1:
        chat = add_resolution_metadata(requested_chat=query, chat_info=exact[0], config=config)
        response["result"] = {"chat": chat, "matches": chats}
        return response
    if chats:
        return make_result(
            ok=False,
            operation="find-chat",
            result={"matches": chats},
            warnings=["ambiguous_chat"],
            exit_code=2,
        )

    contacts_response = search_contacts(
        query,
        limit=limit,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
    )
    if not contacts_response["ok"]:
        return contacts_response
    contacts = contacts_response["result"]["contacts"]
    if len(contacts) == 1:
        contacts_response["operation"] = "find-chat"
        chat = add_resolution_metadata(requested_chat=query, chat_info=contacts[0], config=config)
        contacts_response["result"] = {"chat": chat, "matches": contacts}
        return contacts_response

    exact_contacts = [
        contact
        for contact in contacts
        if str(contact.get("name", "")).strip().lower() == query.strip().lower()
        or str(contact.get("alias", "")).strip().lower() == query.strip().lower()
        or str(contact.get("phone", "")).strip().lower() == query.strip().lower()
    ]
    if len(exact_contacts) == 1:
        contacts_response["operation"] = "find-chat"
        chat = add_resolution_metadata(requested_chat=query, chat_info=exact_contacts[0], config=config)
        contacts_response["result"] = {"chat": chat, "matches": contacts}
        return contacts_response

    return make_result(
        ok=False,
        operation="find-chat",
        result={"matches": chats or contacts},
        warnings=["chat_not_found" if not chats and not contacts else "ambiguous_chat"],
        exit_code=2,
    )


def resolve_chat_details(
    chat: str,
    *,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    use_lid_mapping: bool = True,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    config = config or resolve_config()
    if is_jid(chat):
        chat_info = add_resolution_metadata(
            requested_chat=chat,
            chat_info={"jid": chat, "source": "direct_jid"},
            config=config,
            use_lid_mapping=use_lid_mapping,
        )
        return resolution_summary(chat_info), None

    resolved = find_chat(
        chat,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
    )
    if not resolved["ok"]:
        return None, resolved
    chat_info = resolved["result"]["chat"]
    if not use_lid_mapping:
        chat_info = add_resolution_metadata(
            requested_chat=chat,
            chat_info=chat_info,
            config=config,
            use_lid_mapping=False,
        )
    return resolution_summary(chat_info), None


def resolve_chat(
    chat: str,
    *,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    use_lid_mapping: bool = True,
) -> tuple[str | None, dict[str, Any] | None]:
    details, error = resolve_chat_details(
        chat,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        use_lid_mapping=use_lid_mapping,
    )
    if error:
        return None, error
    return str(details.get("resolved_jid", "")) if details else None, None


def is_backfill_seed_missing(backfill_result: dict[str, Any]) -> bool:
    payload = backfill_result.get("result", {}).get("payload")
    error = ""
    if isinstance(payload, dict):
        error = str(payload.get("error") or payload.get("message") or "")
    combined = f"{error}\n{backfill_result.get('stderr', '')}".lower()
    return "no messages for" in combined and "local db" in combined


def latest(
    chat: str,
    *,
    limit: int = 20,
    auto_backfill: bool = True,
    backfill_count: int = DEFAULT_BACKFILL_COUNT,
    backfill_requests: int = DEFAULT_BACKFILL_REQUESTS,
    backfill_wait_sec: int = DEFAULT_BACKFILL_WAIT_SEC,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    config = config or resolve_config()
    resolution, resolution_error = resolve_chat_details(
        chat,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
    )
    if resolution_error:
        return resolution_error
    jid = str(resolution.get("resolved_jid") or chat)
    response = invoke_wacli(
        "latest",
        ["messages", "list", "--chat", jid, "--limit", str(limit)],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=True,
    )
    if not response["ok"]:
        return response
    response["result"]["resolution"] = resolution

    messages_returned = len(message_items_from_response(response))
    if not auto_backfill:
        response["result"]["backfill"] = {"backfill_attempted": False}
        return response
    if messages_returned >= limit:
        response["result"]["backfill"] = {
            "backfill_attempted": False,
            "reason": "requested_limit_satisfied",
            "messages_returned": messages_returned,
        }
        return response

    backfill_result = backfill(
        jid,
        count=backfill_count,
        requests=backfill_requests,
        wait_sec=backfill_wait_sec,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
    )
    if not backfill_result["ok"]:
        response["result"]["backfill"] = backfill_result["result"]
        warning = "backfill_seed_missing" if messages_returned == 0 and is_backfill_seed_missing(backfill_result) else "backfill_failed"
        response["warnings"] = [*response.get("warnings", []), warning]
        response["stderr"] = backfill_result.get("stderr", "")
        if warning == "backfill_seed_missing":
            response["ok"] = False
            response["exit_code"] = backfill_result.get("exit_code", 2) or 2
        return response

    refreshed = invoke_wacli(
        "latest",
        ["messages", "list", "--chat", jid, "--limit", str(limit)],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=True,
    )
    if refreshed["ok"]:
        refreshed["result"]["resolution"] = resolution
        refreshed["result"]["backfill"] = backfill_result["result"]
        refreshed["result"]["backfill"]["trigger"] = "messages_returned_below_limit"
        refreshed["result"]["backfill"]["initial_messages_returned"] = messages_returned
        return refreshed

    response["warnings"] = [*response.get("warnings", []), "refresh_after_backfill_failed"]
    response["result"]["backfill"] = backfill_result["result"]
    response["stderr"] = refreshed.get("stderr", "")
    return response


def backfill(
    chat: str,
    *,
    count: int = DEFAULT_BACKFILL_COUNT,
    requests: int = DEFAULT_BACKFILL_REQUESTS,
    wait_sec: int = DEFAULT_BACKFILL_WAIT_SEC,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    config = config or resolve_config()
    resolution, resolution_error = resolve_chat_details(
        chat,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
    )
    if resolution_error:
        return resolution_error
    jid = str(resolution.get("resolved_jid") or chat)

    before_count = message_count_for_chat(config, jid)
    response = invoke_wacli(
        "backfill",
        [
            "history",
            "backfill",
            "--chat",
            jid,
            "--count",
            str(count),
            "--requests",
            str(requests),
            "--wait",
            f"{wait_sec}s",
        ],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=False,
    )
    after_count = message_count_for_chat(config, jid)
    messages_added = (
        after_count - before_count
        if before_count is not None and after_count is not None
        else None
    )
    return make_result(
        ok=response["ok"],
        operation="backfill",
        result={
            "chat": resolution,
            "before_count": before_count,
            "after_count": after_count,
            "messages_added": messages_added,
            "backfill_attempted": True,
            "payload": response.get("result", {}).get("payload"),
        },
        warnings=response.get("warnings", []),
        stderr=response.get("stderr", ""),
        exit_code=response.get("exit_code", 0),
    )


def search_messages(
    query: str,
    *,
    chat: str | None = None,
    limit: int = 50,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    args = ["messages", "search", query, "--limit", str(limit)]
    resolution = None
    if chat:
        resolution, resolution_error = resolve_chat_details(
            chat,
            runner=runner,
            config=config,
            timeout_sec=timeout_sec,
        )
        if resolution_error:
            return resolution_error
        args.extend(["--chat", str(resolution.get("resolved_jid") or chat)])
    response = invoke_wacli(
        "search",
        args,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=True,
    )
    if resolution and response["ok"]:
        response["result"]["resolution"] = resolution
    return response


def context(
    message_id: str,
    *,
    before: int = 5,
    after: int = 5,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    return invoke_wacli(
        "context",
        [
            "messages",
            "context",
            "--id",
            message_id,
            "--before",
            str(before),
            "--after",
            str(after),
        ],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=True,
    )


def draft_reply(
    chat: str,
    instruction: str,
    *,
    limit: int = 20,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    latest_result = latest(
        chat,
        limit=limit,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
    )
    if not latest_result["ok"]:
        return latest_result
    return make_result(
        ok=True,
        operation="draft-reply",
        result={
            "instruction": instruction,
            "context": latest_result["result"].get("payload"),
            "mutation_performed": False,
        },
    )


def confirmation_required(operation: str) -> dict[str, Any]:
    return make_result(
        ok=False,
        operation=operation,
        warnings=["confirmation_required"],
        stderr=f"{operation} is WhatsApp-visible and requires --confirm.",
        exit_code=2,
    )


def send_text(
    chat: str,
    message: str,
    *,
    confirm: bool,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    if not confirm:
        return confirmation_required("send-text")
    jid, resolution_error = resolve_chat(
        chat,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        use_lid_mapping=False,
    )
    if resolution_error:
        return resolution_error
    return invoke_wacli(
        "send-text",
        ["send", "text", "--to", jid or chat, "--message", message],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=False,
    )


def react(
    chat: str,
    message_id: str,
    reaction: str,
    *,
    confirm: bool,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    if not confirm:
        return confirmation_required("react")
    jid, resolution_error = resolve_chat(
        chat,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        use_lid_mapping=False,
    )
    if resolution_error:
        return resolution_error
    return invoke_wacli(
        "react",
        ["send", "react", "--to", jid or chat, "--id", message_id, "--reaction", reaction],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=False,
    )


def presence(
    chat: str,
    state: str,
    *,
    confirm: bool,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    if not confirm:
        return confirmation_required("presence")
    jid, resolution_error = resolve_chat(
        chat,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        use_lid_mapping=False,
    )
    if resolution_error:
        return resolution_error
    return invoke_wacli(
        "presence",
        ["presence", state, "--to", jid or chat],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=False,
    )


def status(**kwargs: Any) -> dict[str, Any]:
    return invoke_wacli("status", ["doctor"], **kwargs, read_only_env=True)


def auth_status(**kwargs: Any) -> dict[str, Any]:
    return invoke_wacli("auth-status", ["auth", "status"], **kwargs, read_only_env=True)


def auth_login(
    *,
    popup: bool = False,
    launcher: Launcher = default_launcher,
    **kwargs: Any,
) -> dict[str, Any]:
    if popup:
        config = kwargs.get("config") or resolve_config()
        if not config.wacli_path.exists():
            return make_result(
                ok=False,
                operation="auth-login",
                warnings=["wacli_missing"],
                stderr=f"wacli not found at {config.wacli_path}",
                exit_code=127,
            )
        config.store_dir.mkdir(parents=True, exist_ok=True)
        try:
            pid = launcher(build_auth_popup_command(config))
        except FileNotFoundError as exc:
            return make_result(
                ok=False,
                operation="auth-login",
                backend="wacli-popup",
                warnings=["powershell_missing"],
                stderr=str(exc),
                exit_code=127,
            )
        return make_result(
            ok=True,
            operation="auth-login",
            backend="wacli-popup",
            result={
                "pid": pid,
                "store_dir": str(config.store_dir),
                "note": "QR login launched in a separate Windows PowerShell console.",
            },
        )
    return invoke_wacli(
        "auth-login",
        ["auth", "--idle-exit", "30s"],
        **kwargs,
        read_only_env=False,
    )


def sync_once(**kwargs: Any) -> dict[str, Any]:
    return invoke_wacli(
        "sync-once",
        ["sync", "--once", "--idle-exit", "20s", "--max-reconnect", "1m"],
        **kwargs,
        read_only_env=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Curated agent adapter for wacli.")
    parser.add_argument("--wacli-path")
    parser.add_argument("--store-dir")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    subparsers.add_parser("status")
    subparsers.add_parser("auth-status")
    auth_login_parser = subparsers.add_parser("auth-login")
    auth_login_parser.add_argument(
        "--popup",
        action="store_true",
        help="Launch QR auth in a separate Windows console so the QR is not clipped.",
    )
    subparsers.add_parser("sync-once")

    find = subparsers.add_parser("find-chat")
    find.add_argument("--query", required=True)
    find.add_argument("--limit", type=int, default=20)

    latest_parser = subparsers.add_parser("latest")
    latest_parser.add_argument("--chat", required=True)
    latest_parser.add_argument("--limit", type=int, default=20)
    latest_parser.add_argument("--no-backfill", action="store_true")
    latest_parser.add_argument("--backfill-count", type=int, default=DEFAULT_BACKFILL_COUNT)
    latest_parser.add_argument("--backfill-requests", type=int, default=DEFAULT_BACKFILL_REQUESTS)
    latest_parser.add_argument("--backfill-wait-sec", type=int, default=DEFAULT_BACKFILL_WAIT_SEC)

    backfill_parser = subparsers.add_parser("backfill")
    backfill_parser.add_argument("--chat", required=True)
    backfill_parser.add_argument("--count", type=int, default=DEFAULT_BACKFILL_COUNT)
    backfill_parser.add_argument("--requests", type=int, default=DEFAULT_BACKFILL_REQUESTS)
    backfill_parser.add_argument("--wait-sec", type=int, default=DEFAULT_BACKFILL_WAIT_SEC)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--chat")
    search_parser.add_argument("--limit", type=int, default=50)

    context_parser = subparsers.add_parser("context")
    context_parser.add_argument("--message-id", required=True)
    context_parser.add_argument("--before", type=int, default=5)
    context_parser.add_argument("--after", type=int, default=5)

    draft = subparsers.add_parser("draft-reply")
    draft.add_argument("--chat", required=True)
    draft.add_argument("--instruction", required=True)
    draft.add_argument("--limit", type=int, default=20)

    send = subparsers.add_parser("send-text")
    send.add_argument("--chat", required=True)
    send.add_argument("--message", required=True)
    send.add_argument("--confirm", action="store_true")

    react_parser = subparsers.add_parser("react")
    react_parser.add_argument("--chat", required=True)
    react_parser.add_argument("--message-id", required=True)
    react_parser.add_argument("--reaction", required=True)
    react_parser.add_argument("--confirm", action="store_true")

    presence_parser = subparsers.add_parser("presence")
    presence_parser.add_argument("--chat", required=True)
    presence_parser.add_argument("--state", choices=("typing", "paused"), required=True)
    presence_parser.add_argument("--confirm", action="store_true")

    return parser


def run_cli(args: argparse.Namespace) -> dict[str, Any]:
    config = resolve_config(wacli_path=args.wacli_path, store_dir=args.store_dir)
    common = {"config": config, "timeout_sec": args.timeout_sec}
    if args.operation == "status":
        return status(**common)
    if args.operation == "auth-status":
        return auth_status(**common)
    if args.operation == "auth-login":
        return auth_login(popup=args.popup, **common)
    if args.operation == "sync-once":
        return sync_once(**common)
    if args.operation == "find-chat":
        return find_chat(args.query, limit=args.limit, **common)
    if args.operation == "latest":
        return latest(
            args.chat,
            limit=args.limit,
            auto_backfill=not args.no_backfill,
            backfill_count=args.backfill_count,
            backfill_requests=args.backfill_requests,
            backfill_wait_sec=args.backfill_wait_sec,
            **common,
        )
    if args.operation == "backfill":
        return backfill(
            args.chat,
            count=args.count,
            requests=args.requests,
            wait_sec=args.wait_sec,
            **common,
        )
    if args.operation == "search":
        return search_messages(args.query, chat=args.chat, limit=args.limit, **common)
    if args.operation == "context":
        return context(args.message_id, before=args.before, after=args.after, **common)
    if args.operation == "draft-reply":
        return draft_reply(args.chat, args.instruction, limit=args.limit, **common)
    if args.operation == "send-text":
        return send_text(args.chat, args.message, confirm=args.confirm, **common)
    if args.operation == "react":
        return react(args.chat, args.message_id, args.reaction, confirm=args.confirm, **common)
    if args.operation == "presence":
        return presence(args.chat, args.state, confirm=args.confirm, **common)
    return make_result(
        ok=False,
        operation=args.operation,
        warnings=["unsupported_operation"],
        exit_code=2,
    )
