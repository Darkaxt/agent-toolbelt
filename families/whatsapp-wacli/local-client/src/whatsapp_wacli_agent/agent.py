import argparse
from datetime import datetime, timezone
import json
import os
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Callable


DEFAULT_TIMEOUT_SEC = 300
DEFAULT_BACKFILL_COUNT = 100
DEFAULT_BACKFILL_REQUESTS = 3
DEFAULT_BACKFILL_WAIT_SEC = 60
DEFAULT_MEDIA_LIMIT = 3
MAX_MEDIA_LIMIT = 10
WACLI_PATH_ENV = "WHATSAPP_WACLI_PATH"
WACLI_STORE_ENV = "WHATSAPP_WACLI_STORE"
JID_RE = re.compile(r"^[^@\s]+@(s\.whatsapp\.net|g\.us|lid)$")
PHONE_JID_SUFFIX = "@s.whatsapp.net"
LID_JID_SUFFIX = "@lid"
MIN_PHONE_FRAGMENT_DIGITS = 6
GENERIC_MEDIA_DISPLAY_RE = re.compile(r"^(sent|shared)\s+(.+)$", re.IGNORECASE)
EDITED_MESSAGE_PREFIX_RE = re.compile(r"^edited message:\s*", re.IGNORECASE)


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
    if wacli_path:
        path_candidate = Path(wacli_path)
    elif os.getenv(WACLI_PATH_ENV):
        path_candidate = Path(os.getenv(WACLI_PATH_ENV, ""))
    else:
        discovered = shutil.which("wacli.exe") or shutil.which("wacli")
        path_candidate = Path(discovered) if discovered else local_tools_dir() / "wacli" / "wacli.exe"

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
            "Write-Host 'Do not close or kill this window from Codex while login/sync may be active.'",
            "Write-Host 'If the store is locked, wait for this process to exit or ask the user before terminating it.'",
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
            "Write-Host 'After this command exits, return to Codex and run auth-status, then sync-once.'",
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


def normalize_lookup_text(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_phone_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def phone_digits_from_jid(jid: Any) -> str:
    jid_text = str(jid or "").strip()
    if not jid_text.endswith(PHONE_JID_SUFFIX):
        return ""
    return normalize_phone_digits(jid_text[: -len(PHONE_JID_SUFFIX)])


def row_phone_digit_values(row: dict[str, Any]) -> list[str]:
    values = [
        normalize_phone_digits(row.get("phone")),
        normalize_phone_digits(row.get("redacted_phone")),
        phone_digits_from_jid(row.get("phone_jid")),
        phone_digits_from_jid(row.get("contact_jid")),
    ]
    jid_digits = phone_digits_from_jid(row.get("jid"))
    if jid_digits:
        values.append(jid_digits)
    seen: set[str] = set()
    digits: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            digits.append(value)
    return digits


def phone_metadata_matches_query(row: dict[str, Any], query: str) -> bool:
    query_digits = normalize_phone_digits(query)
    if len(query_digits) < MIN_PHONE_FRAGMENT_DIGITS:
        return False
    for value in row_phone_digit_values(row):
        if value == query_digits or value.endswith(query_digits):
            return True
    return False


def is_phoneish_query(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and bool(normalize_phone_digits(text)) and not re.search(r"[A-Za-z]", text)


def metadata_matches_query(row: dict[str, Any], query: str) -> bool:
    needle = normalize_lookup_text(query)
    if not needle:
        return False
    if phone_metadata_matches_query(row, query):
        return True
    if is_phoneish_query(query):
        return False
    for key in (
        "name",
        "alias",
        "display_label",
        "push_name",
        "full_name",
        "first_name",
        "business_name",
        "jid",
        "chat_name",
        "sender_name",
    ):
        haystack = normalize_lookup_text(row.get(key))
        if haystack and (haystack == needle or needle in haystack):
            return True
    return False


def dedupe_metadata_matches(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    def source_score(row: dict[str, Any]) -> int:
        source = str(row.get("source") or "")
        if source == "local_chat":
            return 90
        if source == "live_session_contact":
            return 80
        if source == "live_lid_map":
            return 70
        if source == "contact":
            return 60
        if source.endswith("_message_metadata"):
            return 50
        if source.startswith("archived_chat_alias:"):
            return 10
        return 0

    def score(row: dict[str, Any]) -> tuple[int, int, int, int]:
        name_values = [
            normalize_lookup_text(row.get("name")),
            normalize_lookup_text(row.get("display_label")),
            normalize_lookup_text(row.get("push_name")),
        ]
        return (
            1 if phone_metadata_matches_query(row, query) else 0,
            source_score(row),
            1 if normalize_lookup_text(query) in name_values else 0,
            int(row.get("last_message_ts") or 0),
        )

    best_by_jid: dict[str, dict[str, Any]] = {}
    for row in rows:
        jid = str(row.get("jid") or "")
        if not jid:
            continue
        current = best_by_jid.get(jid)
        if current is None or score(row) > score(current):
            best_by_jid[jid] = row
    return list(best_by_jid.values())


def sqlite_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def local_chat_metadata_rows(store_dir: Path, *, source: str) -> list[dict[str, Any]]:
    db_path = store_dir / "wacli.db"
    if not db_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        try:
            chat_columns = sqlite_table_columns(conn, "chats")
            if {"jid", "name"}.issubset(chat_columns):
                select_columns = [
                    "jid",
                    "kind" if "kind" in chat_columns else "null as kind",
                    "name",
                    "last_message_ts" if "last_message_ts" in chat_columns else "null as last_message_ts",
                ]
                for jid, kind, name, last_message_ts in conn.execute(
                    f"select {', '.join(select_columns)} from chats"
                ).fetchall():
                    rows.append(
                        {
                            "jid": jid,
                            "kind": kind or "chat",
                            "name": name or jid,
                            "last_message_ts": last_message_ts,
                            "source": source,
                        }
                    )

            message_columns = sqlite_table_columns(conn, "messages")
            if {"chat_jid", "chat_name"}.issubset(message_columns):
                timestamp_expr = "max(ts)" if "ts" in message_columns else "null"
                sender_expr = "sender_name" if "sender_name" in message_columns else "null as sender_name"
                group_columns = "chat_jid, chat_name, sender_name" if "sender_name" in message_columns else "chat_jid, chat_name"
                query = (
                    f"select chat_jid, chat_name, {sender_expr}, count(*), {timestamp_expr} "
                    f"from messages group by {group_columns}"
                )
                for jid, chat_name, sender_name, message_count, last_message_ts in conn.execute(query).fetchall():
                    rows.append(
                        {
                            "jid": jid,
                            "kind": "message_metadata",
                            "name": chat_name or sender_name or jid,
                            "chat_name": chat_name,
                            "sender_name": sender_name,
                            "message_count": message_count,
                            "last_message_ts": last_message_ts,
                            "source": f"{source}_message_metadata",
                        }
                    )
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    return rows


def local_chat_metadata_matches(
    query: str,
    *,
    config: Config,
    limit: int = 20,
    source: str = "local_chat",
) -> list[dict[str, Any]]:
    matches = [
        row
        for row in local_chat_metadata_rows(config.store_dir, source=source)
        if metadata_matches_query(row, query)
    ]
    matches = dedupe_metadata_matches(matches, query)
    matches.sort(
        key=lambda row: (
            normalize_lookup_text(row.get("name")) != normalize_lookup_text(query),
            -(int(row.get("last_message_ts") or 0)),
            normalize_lookup_text(row.get("name")),
            normalize_lookup_text(row.get("jid")),
        )
    )
    return matches[:limit]


def current_store_has_jid(config: Config, jid: str) -> bool:
    if not jid:
        return False
    if message_count_for_chat(config, jid):
        return True
    db_path = config.store_dir / "wacli.db"
    if not db_path.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        try:
            row = conn.execute("select 1 from chats where jid=? limit 1", (jid,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return bool(row)


def lid_map_rows(config: Config) -> list[dict[str, str]]:
    db_path = config.store_dir / "session.db"
    if not db_path.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        try:
            if "whatsmeow_lid_map" not in {
                row[0] for row in conn.execute("select name from sqlite_master where type='table'").fetchall()
            }:
                return []
            rows = conn.execute("select lid, pn from whatsmeow_lid_map").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    return [
        {"lid": str(lid), "pn": str(pn)}
        for lid, pn in rows
        if lid and pn
    ]


def lid_jid_for_phone_digits(config: Config, phone_digits: str) -> str | None:
    digits = normalize_phone_digits(phone_digits)
    if not digits:
        return None
    for row in lid_map_rows(config):
        if normalize_phone_digits(row["pn"]) == digits:
            return f"{row['lid']}{LID_JID_SUFFIX}"
    return None


def phone_jid_for_lid_jid(config: Config, jid: str) -> str | None:
    jid_text = str(jid or "").strip()
    if not jid_text.endswith(LID_JID_SUFFIX):
        return None
    lid = jid_text[: -len(LID_JID_SUFFIX)]
    for row in lid_map_rows(config):
        if str(row["lid"]) == lid:
            return f"{row['pn']}{PHONE_JID_SUFFIX}"
    return None


def preferred_history_jid_for_phone_jid(config: Config, phone_jid: str) -> str:
    mapped_lid = lid_jid_for_phone_jid(config, phone_jid)
    if mapped_lid and current_store_has_jid(config, mapped_lid):
        return mapped_lid
    return phone_jid


def first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def live_session_metadata_rows(config: Config) -> list[dict[str, Any]]:
    db_path = config.store_dir / "session.db"
    rows: list[dict[str, Any]] = []
    if not db_path.is_file():
        return rows
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        try:
            tables = {
                row[0] for row in conn.execute("select name from sqlite_master where type='table'").fetchall()
            }
            if "whatsmeow_contacts" in tables:
                columns = sqlite_table_columns(conn, "whatsmeow_contacts")
                select_columns = [
                    "their_jid" if "their_jid" in columns else "null as their_jid",
                    "first_name" if "first_name" in columns else "null as first_name",
                    "full_name" if "full_name" in columns else "null as full_name",
                    "push_name" if "push_name" in columns else "null as push_name",
                    "business_name" if "business_name" in columns else "null as business_name",
                    "redacted_phone" if "redacted_phone" in columns else "null as redacted_phone",
                ]
                for their_jid, first_name, full_name, push_name, business_name, redacted_phone in conn.execute(
                    f"select {', '.join(select_columns)} from whatsmeow_contacts"
                ).fetchall():
                    phone_jid = str(their_jid or "").strip() if str(their_jid or "").strip().endswith(PHONE_JID_SUFFIX) else None
                    phone = phone_digits_from_jid(phone_jid) if phone_jid else normalize_phone_digits(redacted_phone)
                    preferred_jid = preferred_history_jid_for_phone_jid(config, phone_jid) if phone_jid else str(their_jid or "").strip()
                    display_label = first_nonempty(push_name, full_name, first_name, business_name, redacted_phone, phone, their_jid)
                    if not preferred_jid:
                        continue
                    rows.append(
                        {
                            "jid": preferred_jid,
                            "kind": "session_contact",
                            "name": display_label or preferred_jid,
                            "display_label": display_label,
                            "push_name": push_name,
                            "full_name": full_name,
                            "first_name": first_name,
                            "business_name": business_name,
                            "redacted_phone": redacted_phone,
                            "phone": phone,
                            "phone_jid": phone_jid,
                            "contact_jid": phone_jid,
                            "source": "live_session_contact",
                        }
                    )
        finally:
            conn.close()
    except sqlite3.Error:
        return rows

    for row in lid_map_rows(config):
        lid_jid = f"{row['lid']}{LID_JID_SUFFIX}"
        phone = normalize_phone_digits(row["pn"])
        phone_jid = f"{phone}{PHONE_JID_SUFFIX}" if phone else None
        preferred_jid = lid_jid if current_store_has_jid(config, lid_jid) else phone_jid
        if not preferred_jid:
            continue
        rows.append(
            {
                "jid": preferred_jid,
                "kind": "lid_map",
                "name": f"+{phone}" if phone else preferred_jid,
                "display_label": f"+{phone}" if phone else preferred_jid,
                "phone": phone,
                "phone_jid": phone_jid,
                "contact_jid": phone_jid,
                "source": "live_lid_map",
            }
        )
    return rows


def live_session_metadata_matches(
    query: str,
    *,
    config: Config,
    limit: int = 20,
) -> list[dict[str, Any]]:
    matches = [
        row
        for row in live_session_metadata_rows(config)
        if metadata_matches_query(row, query)
    ]
    matches = dedupe_metadata_matches(matches, query)
    matches.sort(
        key=lambda row: (
            normalize_lookup_text(row.get("name")) != normalize_lookup_text(query)
            and normalize_lookup_text(row.get("display_label")) != normalize_lookup_text(query),
            0 if phone_metadata_matches_query(row, query) else 1,
            normalize_lookup_text(row.get("source")) != "live_session_contact",
            normalize_lookup_text(row.get("display_label")),
            normalize_lookup_text(row.get("jid")),
        )
    )
    return matches[:limit]


def archived_store_dirs(config: Config) -> list[Path]:
    parent = config.store_dir.parent
    if not parent.is_dir():
        return []
    prefix = f"{config.store_dir.name}-"
    return sorted(
        (path for path in parent.iterdir() if path.is_dir() and path.name.startswith(prefix)),
        key=lambda path: path.name,
        reverse=True,
    )


def archived_chat_metadata_matches(
    query: str,
    *,
    config: Config,
    limit: int = 20,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for store_dir in archived_store_dirs(config):
        source = f"archived_chat_alias:{store_dir.name}"
        for row in local_chat_metadata_rows(store_dir, source=source):
            if not metadata_matches_query(row, query):
                continue
            jid = str(row.get("jid") or "")
            if not current_store_has_jid(config, jid):
                continue
            enriched = dict(row)
            enriched["alias_store"] = str(store_dir)
            matches.append(enriched)
    matches = dedupe_metadata_matches(matches, query)
    matches.sort(
        key=lambda row: (
            normalize_lookup_text(row.get("name")) != normalize_lookup_text(query),
            -(int(row.get("last_message_ts") or 0)),
            normalize_lookup_text(row.get("name")),
            normalize_lookup_text(row.get("jid")),
        )
    )
    return matches[:limit]


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
    contact_jid = str(resolved.get("contact_jid") or resolved.get("phone_jid") or "").strip()
    if not contact_jid and jid.endswith(PHONE_JID_SUFFIX):
        contact_jid = jid
    if not contact_jid and jid.endswith(LID_JID_SUFFIX):
        contact_jid = phone_jid_for_lid_jid(config, jid) or ""
    mapped_lid = lid_jid_for_phone_jid(config, jid) if use_lid_mapping else None
    resolved_jid = str(resolved.get("resolved_jid") or mapped_lid or jid)
    resolution_source = "pn_lid_map" if mapped_lid and not source.startswith("live_") else source

    resolved["requested_chat"] = requested_chat
    resolved["contact_jid"] = contact_jid or None
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
        "phone": chat_info.get("phone"),
        "phone_jid": chat_info.get("phone_jid"),
        "display_label": chat_info.get("display_label"),
    }


def unique_jids(*values: Any) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for value in values:
        jid = str(value or "").strip()
        if jid and jid not in seen:
            seen.add(jid)
            candidates.append(jid)
    return candidates


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


def iso_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return str(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def message_time_bounds_for_chat(config: Config, jid: str) -> dict[str, Any]:
    bounds: dict[str, Any] = {
        "jid": jid,
        "message_count": None,
        "timestamp_available": None,
        "oldest_message_ts": None,
        "latest_message_ts": None,
        "oldest_message_at": None,
        "latest_message_at": None,
    }
    db_path = config.store_dir / "wacli.db"
    if not db_path.is_file():
        return bounds
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        try:
            columns = {row[1] for row in conn.execute("pragma table_info(messages)").fetchall()}
            if "ts" not in columns:
                row = conn.execute(
                    "select count(*) from messages where chat_jid=?",
                    (jid,),
                ).fetchone()
                bounds["message_count"] = int(row[0] or 0) if row else None
                bounds["timestamp_available"] = False
                return bounds
            row = conn.execute(
                "select count(*), min(ts), max(ts) from messages where chat_jid=?",
                (jid,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return bounds
    if not row:
        return bounds
    bounds["message_count"] = int(row[0] or 0)
    bounds["timestamp_available"] = True
    bounds["oldest_message_ts"] = row[1]
    bounds["latest_message_ts"] = row[2]
    bounds["oldest_message_at"] = iso_timestamp(row[1])
    bounds["latest_message_at"] = iso_timestamp(row[2])
    return bounds


def chat_last_message_ts_for_jid(config: Config, jid: str) -> int | None:
    db_path = config.store_dir / "wacli.db"
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        try:
            row = conn.execute(
                "select last_message_ts from chats where jid=? limit 1",
                (jid,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row or row[0] is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def message_store_freshness(
    *,
    resolution: dict[str, Any],
    config: Config,
    used_jid: str | None,
    attempted_jids: list[str] | None = None,
) -> dict[str, Any]:
    candidate_jids = unique_jids(
        *(attempted_jids or []),
        used_jid,
        resolution.get("chat_jid"),
        resolution.get("resolved_jid"),
        resolution.get("contact_jid"),
    )
    bounds_by_jid = {
        jid: message_time_bounds_for_chat(config, jid)
        for jid in candidate_jids
    }
    chat_last_by_jid = {
        jid: chat_last_message_ts_for_jid(config, jid)
        for jid in candidate_jids
    }
    known_chat_timestamps = [
        ts
        for ts in chat_last_by_jid.values()
        if ts is not None
    ]
    message_timestamps = [
        int(bounds["latest_message_ts"])
        for bounds in bounds_by_jid.values()
        if bounds.get("latest_message_ts") is not None
    ]
    chat_last_ts = max(known_chat_timestamps) if known_chat_timestamps else None
    latest_readable_ts = max(message_timestamps) if message_timestamps else None
    timestamps_available = any(bounds.get("timestamp_available") for bounds in bounds_by_jid.values())
    stale = (
        timestamps_available
        and chat_last_ts is not None
        and (latest_readable_ts is None or latest_readable_ts < chat_last_ts)
    )
    gap_seconds = chat_last_ts - latest_readable_ts if stale and latest_readable_ts is not None else None
    recovery = None
    if stale:
        recovery = {
            "recommended_action": "recreate_session",
            "message": (
                "The local wacli store has newer chat metadata than readable message rows. "
                "Normal sync/backfill did not recover message bodies; recreate or relink the "
                "wacli session into a fresh store before treating this chat as current."
            ),
        }
    return {
        "stale": stale,
        "warning": "message_store_lag" if stale else None,
        "used_jid": used_jid,
        "chat_last_message_ts": chat_last_ts,
        "chat_last_message_at": iso_timestamp(chat_last_ts),
        "latest_readable_message_ts": latest_readable_ts,
        "latest_readable_message_at": iso_timestamp(latest_readable_ts),
        "gap_seconds": gap_seconds,
        "recovery": recovery,
        "jid_bounds": bounds_by_jid,
        "chat_last_message_by_jid": {
            jid: {
                "last_message_ts": ts,
                "last_message_at": iso_timestamp(ts),
            }
            for jid, ts in chat_last_by_jid.items()
        },
    }


def apply_message_store_freshness(response: dict[str, Any], freshness: dict[str, Any]) -> dict[str, Any]:
    response["result"]["message_store_freshness"] = freshness
    if freshness.get("stale"):
        response["ok"] = False
        response["exit_code"] = response.get("exit_code") or 2
        warnings = response.get("warnings", [])
        if "message_store_lag" not in warnings:
            response["warnings"] = [*warnings, "message_store_lag"]
        recovery_message = freshness.get("recovery", {}).get("message")
        stale_message = (
            recovery_message
            or "chat metadata is newer than the local readable message store; recreate or relink the wacli session"
        )
        response["stderr"] = "\n".join(part for part in (response.get("stderr", ""), stale_message) if part)
    return response


def message_items_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    return payload_items(
        response.get("result", {}).get("payload"),
        ("messages", "data", "items", "results"),
    )


def containers_with_messages(payload: Any) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list):
            containers.append(payload)
        for value in payload.values():
            containers.extend(containers_with_messages(value))
    elif isinstance(payload, list):
        for item in payload:
            containers.extend(containers_with_messages(item))
    return containers


def message_value(message: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in message and message[key] not in (None, ""):
            return message[key]
    return None


def display_name_for_resolution(resolution: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not resolution:
        return None, None
    for key in ("display_label", "name", "requested_chat"):
        value = str(resolution.get(key) or "").strip()
        if value and not is_jid(value):
            return value, "resolution"
    return None, None


def local_display_name_for_jid(config: Config, jid: str) -> tuple[str | None, str | None]:
    for row in live_session_metadata_rows(config):
        if row.get("jid") == jid or row.get("phone_jid") == jid or row.get("contact_jid") == jid:
            value = first_nonempty(row.get("display_label"), row.get("name"))
            if value and not is_jid(value):
                return value, str(row.get("source") or "live_session_contact")
    for row in local_chat_metadata_rows(config.store_dir, source="local_metadata"):
        if row.get("jid") == jid:
            value = first_nonempty(row.get("name"), row.get("chat_name"), row.get("sender_name"))
            if value and not is_jid(value):
                return value, "local_metadata"
    return None, None


def message_chat_display_name(
    message: dict[str, Any],
    *,
    config: Config,
    resolution: dict[str, Any] | None,
) -> tuple[str, str]:
    value, source = display_name_for_resolution(resolution)
    if value:
        return value, source or "resolution"
    jid = str(message_value(message, "ChatJID", "chat_jid") or "")
    value, source = local_display_name_for_jid(config, jid)
    if value:
        return value, source or "local_metadata"
    raw = str(message_value(message, "ChatName", "chat_name", "ChatJID", "chat_jid") or "")
    return raw, "raw"


def metadata_value(metadata: dict[str, Any] | None, *keys: str) -> Any:
    if not metadata:
        return None
    for key in keys:
        if key in metadata and metadata[key] not in (None, ""):
            return metadata[key]
    return None


def compact_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if value not in (None, "", [], {})
    }


def basename_from_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        if "\\" in text or re.match(r"^[A-Za-z]:", text):
            return PureWindowsPath(text).name
        return Path(text).name
    except (OSError, ValueError):
        return text.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]


def derive_filename(*values: Any) -> str:
    for value in values:
        name = basename_from_path(value)
        if name and name not in {".", "/"}:
            return name
    return ""


def message_media_type(message: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    return str(message_value(message, "MediaType", "media_type") or metadata_value(metadata, "media_type") or "").strip()


def message_media_caption(message: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    return str(
        message_value(message, "Caption", "MediaCaption", "media_caption")
        or metadata_value(metadata, "media_caption")
        or ""
    ).strip()


def message_filename(message: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    explicit = str(
        message_value(message, "Filename", "FileName", "filename")
        or metadata_value(metadata, "filename")
        or ""
    ).strip()
    if explicit:
        return explicit
    return derive_filename(message_local_path(message, metadata))


def message_mime_type(message: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    return str(
        message_value(message, "MimeType", "MIMEType", "mime_type")
        or metadata_value(metadata, "mime_type")
        or ""
    ).strip()


def message_file_length(message: dict[str, Any], metadata: dict[str, Any] | None = None) -> Any:
    return message_value(message, "FileLength", "file_length") or metadata_value(metadata, "file_length")


def message_local_path(message: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    return str(message_value(message, "LocalPath", "local_path") or metadata_value(metadata, "local_path") or "").strip()


def message_downloaded_at(message: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    return str(message_value(message, "DownloadedAt", "downloaded_at") or metadata_value(metadata, "downloaded_at") or "").strip()


def local_message_media_metadata(config: Config, message: dict[str, Any]) -> dict[str, Any]:
    db_path = config.store_dir / "wacli.db"
    msg_id = str(message_value(message, "MsgID", "msg_id", "ID", "id") or "").strip()
    chat_jid = str(message_value(message, "ChatJID", "chat_jid") or "").strip()
    if not db_path.is_file() or not msg_id or not chat_jid:
        return {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        try:
            columns = sqlite_table_columns(conn, "messages")
            if not {"chat_jid", "msg_id"}.issubset(columns):
                return {}
            safe_columns = [
                column
                for column in (
                    "media_type",
                    "media_caption",
                    "filename",
                    "mime_type",
                    "file_length",
                    "local_path",
                    "downloaded_at",
                )
                if column in columns
            ]
            if not safe_columns:
                return {}
            row = conn.execute(
                f"select {', '.join(safe_columns)} from messages where chat_jid=? and msg_id=? limit 1",
                (chat_jid, msg_id),
            ).fetchone()
            if row is None:
                return {}
            return {
                column: value
                for column, value in zip(safe_columns, row)
                if value not in (None, "")
            }
        finally:
            conn.close()
    except sqlite3.Error:
        return {}


def presentation_text_for_message(message: dict[str, Any], metadata: dict[str, Any] | None = None) -> tuple[str, str, bool]:
    raw_text = str(message_value(message, "Text", "text") or "").strip()
    display_text = str(message_value(message, "DisplayText", "display_text", "Snippet", "snippet") or "").strip()
    caption = message_media_caption(message, metadata)
    media_type = message_media_type(message, metadata)
    is_edited = bool(EDITED_MESSAGE_PREFIX_RE.match(display_text))

    if caption and media_type and (not raw_text or GENERIC_MEDIA_DISPLAY_RE.match(raw_text)):
        return caption, "media_caption", is_edited
    if raw_text:
        return raw_text, "text", is_edited
    if caption:
        return caption, "media_caption", is_edited
    if display_text:
        source = "media_placeholder" if media_type and GENERIC_MEDIA_DISPLAY_RE.match(display_text) else "display_text"
        return display_text, source, is_edited
    if media_type:
        return f"Sent {media_type}", "media_placeholder", is_edited
    return "", "empty", is_edited


def presentation_for_message(
    message: dict[str, Any],
    *,
    config: Config,
    resolution: dict[str, Any] | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chat_display_name, chat_display_name_source = message_chat_display_name(
        message,
        config=config,
        resolution=resolution,
    )
    text, text_source, is_edited = presentation_text_for_message(message, metadata)
    media_type = message_media_type(message, metadata)
    media_caption = message_media_caption(message, metadata)
    filename = message_filename(message, metadata)
    mime_type = message_mime_type(message, metadata)
    file_length = message_file_length(message, metadata)
    local_path = message_local_path(message, metadata)
    downloaded_at = message_downloaded_at(message, metadata)
    media_label = ""
    if media_type:
        media_label = media_caption or str(message_value(message, "DisplayText", "display_text") or "").strip() or f"Sent {media_type}"

    presentation = {
        "chat_display_name": chat_display_name,
        "chat_display_name_source": chat_display_name_source,
        "text": text,
        "text_source": text_source,
        "is_edited": is_edited,
    }
    if media_type:
        presentation["media_type"] = media_type
    if media_caption:
        presentation["media_caption"] = media_caption
    if filename:
        presentation["filename"] = filename
    if mime_type:
        presentation["mime_type"] = mime_type
    if file_length not in (None, ""):
        presentation["file_length"] = file_length
    if local_path:
        presentation["local_path"] = local_path
    if downloaded_at:
        presentation["downloaded_at"] = downloaded_at
    if media_label:
        presentation["media_label"] = media_label
    return presentation


def enrich_message_presentations(
    response: dict[str, Any],
    *,
    config: Config,
    resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for container in containers_with_messages(response.get("result", {}).get("payload")):
        for message in container.get("messages") or []:
            if isinstance(message, dict):
                metadata = local_message_media_metadata(config, message)
                message["presentation"] = presentation_for_message(
                    message,
                    config=config,
                    resolution=resolution,
                    metadata=metadata,
                )
    return response


def validate_media_limit(media_limit: int) -> int:
    if media_limit < 0:
        raise ValueError("--media-limit must be >= 0")
    if media_limit > MAX_MEDIA_LIMIT:
        raise ValueError(f"--media-limit must be <= {MAX_MEDIA_LIMIT}")
    return media_limit


def has_downloadable_media(message: dict[str, Any], metadata: dict[str, Any] | None = None) -> bool:
    return bool(message_media_type(message, metadata)) and bool(message_value(message, "MsgID", "msg_id", "ID", "id"))


def output_path_from_media_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("path", "output", "file", "local_path", "LocalPath"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        for value in payload.values():
            nested = output_path_from_media_payload(value)
            if nested:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = output_path_from_media_payload(item)
            if nested:
                return nested
    return None


def download_media_for_message(
    message: dict[str, Any],
    *,
    chat_jid: str,
    runner: Callable[..., ProcessResult],
    config: Config,
    timeout_sec: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    msg_id = str(message_value(message, "MsgID", "msg_id", "ID", "id") or "")
    existing_path = message_local_path(message, metadata)
    media_result = {
        "download_attempted": False,
        "downloaded": False,
        "available": bool(existing_path),
        "artifact_path": existing_path,
        "artifact_source": "existing_local_path" if existing_path else "missing",
        "error": None,
    }
    if not msg_id:
        media_result["error"] = "missing_message_id"
        media_result["available"] = bool(existing_path)
        return media_result
    if not chat_jid:
        media_result["error"] = "missing_chat_jid"
        media_result["available"] = bool(existing_path)
        return media_result

    completed = invoke_wacli(
        "media-download",
        ["media", "download", "--id", msg_id, "--chat", chat_jid],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=False,
    )
    media_result["download_attempted"] = True
    if completed["ok"]:
        payload = completed.get("result", {}).get("payload")
        downloaded_path = output_path_from_media_payload(payload)
        artifact_path = downloaded_path or media_result["artifact_path"]
        media_result["downloaded"] = bool(downloaded_path)
        media_result["available"] = bool(artifact_path)
        media_result["artifact_path"] = artifact_path
        media_result["artifact_source"] = "downloaded" if downloaded_path else media_result["artifact_source"]
        media_result["payload"] = payload
    else:
        error_text = completed.get("stderr") or completed.get("result", {}).get("payload", {}).get("error") or "media_download_failed"
        media_result["exit_code"] = completed.get("exit_code")
        if existing_path:
            media_result["download_attempt_error"] = error_text
            media_result["available"] = True
            media_result["artifact_source"] = "existing_local_path"
        else:
            media_result["error"] = error_text
            media_result["available"] = False
    return media_result


def enrich_media_artifacts(
    response: dict[str, Any],
    *,
    include_media: bool,
    media_limit: int,
    chat_jid: str | None,
    runner: Callable[..., ProcessResult],
    config: Config,
    timeout_sec: int,
) -> dict[str, Any]:
    if not include_media:
        return response
    media_limit = validate_media_limit(media_limit)
    if media_limit == 0:
        return response
    downloaded = 0
    errors = 0
    for message in message_items_from_response(response):
        if downloaded >= media_limit:
            break
        if not isinstance(message, dict):
            continue
        metadata = local_message_media_metadata(config, message)
        if not has_downloadable_media(message, metadata):
            continue
        message_chat_jid = str(message_value(message, "ChatJID", "chat_jid") or chat_jid or "")
        media = download_media_for_message(
            message,
            chat_jid=message_chat_jid,
            runner=runner,
            config=config,
            timeout_sec=timeout_sec,
            metadata=metadata,
        )
        downloaded += 1
        if media.get("error") and not media.get("available"):
            errors += 1
        presentation = message.setdefault("presentation", {})
        artifact_path = media.get("artifact_path") or message_local_path(message, metadata)
        filename = (
            presentation.get("filename")
            or message_filename(message, metadata)
            or derive_filename(artifact_path)
        )
        local_path = presentation.get("local_path") or message_local_path(message, metadata)
        if filename:
            presentation["filename"] = filename
        if local_path:
            presentation["local_path"] = local_path
        media_presentation = {
            "artifact_path": media.get("artifact_path") or "",
            "available": bool(media.get("available")),
            "artifact_source": media.get("artifact_source") or "missing",
            "downloaded": bool(media.get("downloaded")),
            "download_attempted": bool(media.get("download_attempted")),
            "mime_type": presentation.get("mime_type") or message_mime_type(message, metadata),
            "file_length": presentation.get("file_length") or message_file_length(message, metadata),
            "filename": filename,
            "local_path": local_path,
            "downloaded_at": presentation.get("downloaded_at") or message_downloaded_at(message, metadata),
        }
        if media.get("download_attempt_error"):
            media_presentation["download_attempt_error"] = media.get("download_attempt_error")
        if media.get("error"):
            media_presentation["download_error"] = media.get("error")
        presentation["media"] = compact_dict(media_presentation)
    response["result"]["media"] = {
        "include_media": True,
        "media_limit": media_limit,
        "media_attempted": downloaded,
        "media_errors": errors,
    }
    if errors:
        response["warnings"] = [*response.get("warnings", []), "media_download_partial_failure"]
    return response


def normalized_context_message(message: dict[str, Any]) -> dict[str, Any]:
    presentation = message.get("presentation") if isinstance(message.get("presentation"), dict) else {}
    media = presentation.get("media") if isinstance(presentation.get("media"), dict) else {}
    normalized: dict[str, Any] = compact_dict({
        "message_id": str(message_value(message, "MsgID", "msg_id", "ID", "id") or ""),
        "timestamp": message_value(message, "Timestamp", "timestamp", "ts"),
        "from_me": message_value(message, "FromMe", "from_me"),
        "sender_jid": str(message_value(message, "SenderJID", "sender_jid") or ""),
        "sender_name": str(message_value(message, "SenderName", "sender_name") or ""),
        "chat_jid": str(message_value(message, "ChatJID", "chat_jid") or ""),
        "chat_display_name": presentation.get("chat_display_name") or "",
        "text": presentation.get("text") or "",
        "text_source": presentation.get("text_source") or "",
        "is_edited": bool(presentation.get("is_edited")),
    })
    for key in ("media_type", "media_caption", "media_label", "filename", "mime_type", "file_length", "local_path", "downloaded_at"):
        value = presentation.get(key)
        if value not in (None, ""):
            normalized[key] = value
    if media:
        normalized["media"] = compact_dict({
            key: value
            for key, value in media.items()
            if key in {
                "artifact_path",
                "available",
                "artifact_source",
                "downloaded",
                "download_attempted",
                "download_attempt_error",
                "download_error",
                "mime_type",
                "file_length",
                "filename",
                "local_path",
                "downloaded_at",
            }
        })
    return normalized


def media_artifacts_from_context_messages(context_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for message in context_messages:
        media = message.get("media") if isinstance(message.get("media"), dict) else {}
        artifact_path = str(media.get("artifact_path") or message.get("local_path") or "")
        if not artifact_path:
            continue
        available = bool(media.get("available", True))
        artifact_source = (
            str(media.get("artifact_source") or "")
            or ("downloaded" if media.get("downloaded") else "existing_local_path")
        )
        artifacts.append(
            compact_dict({
                "message_id": message.get("message_id") or "",
                "artifact_path": artifact_path,
                "available": available,
                "artifact_source": artifact_source,
                "downloaded": bool(media.get("downloaded")),
                "download_attempt_error": media.get("download_attempt_error"),
                "download_error": media.get("download_error"),
                "media_type": message.get("media_type") or "",
                "mime_type": media.get("mime_type") or message.get("mime_type") or "",
                "file_length": media.get("file_length") or message.get("file_length"),
                "filename": media.get("filename") or message.get("filename") or "",
            })
        )
    return artifacts


def truncate_for_prompt(value: Any, limit: int = 280) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def build_context_summary(
    context_messages: list[dict[str, Any]],
    media_artifacts: list[dict[str, Any]],
    *,
    max_messages: int = 8,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    for message in context_messages[:max_messages]:
        media = message.get("media") if isinstance(message.get("media"), dict) else {}
        messages.append(
            compact_dict(
                {
                    "message_id": message.get("message_id"),
                    "timestamp": message.get("timestamp"),
                    "from_me": message.get("from_me"),
                    "chat_display_name": message.get("chat_display_name"),
                    "text": truncate_for_prompt(message.get("text")),
                    "text_source": message.get("text_source"),
                    "is_edited": message.get("is_edited") if message.get("is_edited") else None,
                    "media_type": message.get("media_type"),
                    "media_label": message.get("media_label"),
                    "media_available": media.get("available"),
                    "artifact_source": media.get("artifact_source"),
                    "artifact_path": media.get("artifact_path"),
                }
            )
        )
    return {
        "message_count": len(context_messages),
        "media_artifact_count": len(media_artifacts),
        "messages": messages,
        "truncated": len(context_messages) > len(messages),
    }


def build_draft_model_prompt(
    *,
    instruction: str,
    resolution: dict[str, Any] | None,
    context_messages: list[dict[str, Any]],
    media_artifacts: list[dict[str, Any]],
    context_summary: dict[str, Any] | None = None,
) -> str:
    chat_label = ""
    if resolution:
        chat_label = str(resolution.get("display_label") or resolution.get("requested_chat") or resolution.get("used_jid") or "")
    context_summary = context_summary or build_context_summary(context_messages, media_artifacts)
    lines = [
        "Draft a WhatsApp reply using only the normalized context below.",
        "Do not send the reply. Return only the proposed reply text.",
        f"User instruction: {instruction}",
    ]
    if chat_label:
        lines.append(f"Chat: {chat_label}")
    lines.append(f"Context messages ({context_summary.get('message_count', len(context_messages))} total):")
    for index, message in enumerate(context_summary.get("messages") or [], 1):
        sender = "Me" if message.get("from_me") is True else (message.get("sender_name") or message.get("chat_display_name") or "Them")
        timestamp = message.get("timestamp") or "unknown-time"
        text = message.get("text") or ""
        suffix = " [edited]" if message.get("is_edited") else ""
        if message.get("media_type"):
            media_label = message.get("media_label") or message.get("media_type")
            suffix = f"{suffix} [media: {media_label}]"
        lines.append(f"{index}. [{timestamp}] {sender}: {text}{suffix}")
    if media_artifacts:
        lines.append("Local media artifacts:")
        for artifact in media_artifacts:
            availability = "available" if artifact.get("available") else "unavailable"
            source = artifact.get("artifact_source") or "unknown"
            lines.append(
                f"- message {artifact.get('message_id')}: {artifact.get('artifact_path')} ({availability}, {source})"
            )
    return "\n".join(lines)


def build_draft_packet(
    *,
    instruction: str,
    latest_result: dict[str, Any],
) -> dict[str, Any]:
    resolution = latest_result.get("result", {}).get("resolution")
    context_messages = [
        normalized_context_message(message)
        for message in message_items_from_response(latest_result)
        if isinstance(message, dict)
    ]
    media_artifacts = media_artifacts_from_context_messages(context_messages)
    context_summary = build_context_summary(context_messages, media_artifacts)
    return {
        "draft_status": "needs_model_generation",
        "instruction": instruction,
        "resolution": resolution,
        "context_message_count": len(context_messages),
        "media_artifact_count": len(media_artifacts),
        "context_summary": context_summary,
        "context_messages": context_messages,
        "media_artifacts": media_artifacts,
        "model_prompt": build_draft_model_prompt(
            instruction=instruction,
            resolution=resolution,
            context_messages=context_messages,
            media_artifacts=media_artifacts,
            context_summary=context_summary,
        ),
        "mutation_performed": False,
    }


def nested_key_container(payload: Any, key: str) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if key in payload:
            return payload
        for value in payload.values():
            found = nested_key_container(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = nested_key_container(item, key)
            if found is not None:
                return found
    return None


def response_has_null_messages(response: dict[str, Any]) -> bool:
    container = nested_key_container(response.get("result", {}).get("payload"), "messages")
    return container is not None and container.get("messages") is None


def normalize_null_messages(response: dict[str, Any]) -> bool:
    container = nested_key_container(response.get("result", {}).get("payload"), "messages")
    if container is None or container.get("messages") is not None:
        return False
    container["messages"] = []
    return True


def history_jid_candidates(
    *,
    resolution: dict[str, Any],
    config: Config,
) -> tuple[list[str], dict[str, int | None]]:
    candidates = unique_jids(
        resolution.get("chat_jid"),
        resolution.get("resolved_jid"),
        resolution.get("contact_jid"),
    )
    counts = {jid: message_count_for_chat(config, jid) for jid in candidates}
    if len(candidates) <= 1:
        return candidates, counts

    seeded = [jid for jid in candidates if (counts.get(jid) or 0) > 0]
    seeded.sort(key=lambda jid: (-(counts.get(jid) or 0), candidates.index(jid)))
    unseeded = [jid for jid in candidates if jid not in seeded]
    return seeded + unseeded, counts


def enrich_history_resolution(
    *,
    resolution: dict[str, Any],
    config: Config,
    used_jid: str | None = None,
    attempted_jids: list[str] | None = None,
) -> dict[str, Any]:
    candidates, counts = history_jid_candidates(resolution=resolution, config=config)
    enriched = dict(resolution)
    enriched["history_jids"] = candidates
    enriched["history_jid_message_counts"] = counts
    if used_jid:
        enriched["used_jid"] = used_jid
    if attempted_jids:
        enriched["attempted_jids"] = attempted_jids
    return enriched


def invoke_history_read(
    *,
    operation: str,
    jids: list[str],
    command_builder: Callable[[str], list[str]],
    runner: Callable[..., ProcessResult],
    config: Config,
    timeout_sec: int,
) -> tuple[dict[str, Any], str | None, list[str]]:
    attempted: list[str] = []
    last_response: dict[str, Any] | None = None

    for jid in jids:
        response = invoke_wacli(
            operation,
            command_builder(jid),
            runner=runner,
            config=config,
            timeout_sec=timeout_sec,
            read_only_env=True,
        )
        attempted.append(jid)
        last_response = response
        if not response["ok"]:
            return response, jid, attempted
        if response_has_null_messages(response) and len(attempted) < len(jids):
            continue
        if normalize_null_messages(response):
            response["warnings"] = [*response.get("warnings", []), "messages_null_normalized"]
        if len(attempted) > 1:
            response["warnings"] = [*response.get("warnings", []), "jid_fallback_used"]
        return response, jid, attempted

    return last_response or make_result(ok=False, operation=operation, exit_code=1), None, attempted


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

    local_matches = local_chat_metadata_matches(query, config=config, limit=limit)
    if len(local_matches) == 1:
        chat = add_resolution_metadata(requested_chat=query, chat_info=local_matches[0], config=config)
        response["result"] = {"chat": chat, "matches": local_matches}
        return response

    exact_local_matches = [
        match
        for match in local_matches
        if normalize_lookup_text(match.get("name")) == normalize_lookup_text(query)
        or normalize_lookup_text(match.get("chat_name")) == normalize_lookup_text(query)
        or normalize_lookup_text(match.get("sender_name")) == normalize_lookup_text(query)
        or normalize_lookup_text(match.get("jid")) == normalize_lookup_text(query)
    ]
    if len(exact_local_matches) == 1:
        chat = add_resolution_metadata(requested_chat=query, chat_info=exact_local_matches[0], config=config)
        response["result"] = {"chat": chat, "matches": local_matches}
        return response
    if local_matches:
        return make_result(
            ok=False,
            operation="find-chat",
            result={"matches": local_matches},
            warnings=["ambiguous_chat"],
            exit_code=2,
        )

    live_session_matches = live_session_metadata_matches(query, config=config, limit=limit)
    if len(live_session_matches) == 1:
        chat = add_resolution_metadata(requested_chat=query, chat_info=live_session_matches[0], config=config)
        response["result"] = {"chat": chat, "matches": live_session_matches}
        return response

    exact_live_session_matches = [
        match
        for match in live_session_matches
        if normalize_lookup_text(match.get("name")) == normalize_lookup_text(query)
        or normalize_lookup_text(match.get("display_label")) == normalize_lookup_text(query)
        or normalize_lookup_text(match.get("push_name")) == normalize_lookup_text(query)
        or phone_metadata_matches_query(match, query)
    ]
    if len(exact_live_session_matches) == 1:
        chat = add_resolution_metadata(requested_chat=query, chat_info=exact_live_session_matches[0], config=config)
        response["result"] = {"chat": chat, "matches": live_session_matches}
        return response
    if live_session_matches:
        return make_result(
            ok=False,
            operation="find-chat",
            result={"matches": live_session_matches},
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

    archived_matches = archived_chat_metadata_matches(query, config=config, limit=limit)
    if len(archived_matches) == 1:
        contacts_response["operation"] = "find-chat"
        chat = add_resolution_metadata(requested_chat=query, chat_info=archived_matches[0], config=config)
        contacts_response["result"] = {"chat": chat, "matches": archived_matches}
        contacts_response["warnings"] = [*contacts_response.get("warnings", []), "resolved_from_archived_store_alias"]
        return contacts_response

    exact_archived_matches = [
        match
        for match in archived_matches
        if normalize_lookup_text(match.get("name")) == normalize_lookup_text(query)
        or normalize_lookup_text(match.get("chat_name")) == normalize_lookup_text(query)
        or normalize_lookup_text(match.get("sender_name")) == normalize_lookup_text(query)
    ]
    if len(exact_archived_matches) == 1:
        contacts_response["operation"] = "find-chat"
        chat = add_resolution_metadata(requested_chat=query, chat_info=exact_archived_matches[0], config=config)
        contacts_response["result"] = {"chat": chat, "matches": archived_matches}
        contacts_response["warnings"] = [*contacts_response.get("warnings", []), "resolved_from_archived_store_alias"]
        return contacts_response
    if archived_matches:
        return make_result(
            ok=False,
            operation="find-chat",
            result={"matches": archived_matches},
            warnings=["ambiguous_chat"],
            exit_code=2,
        )

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
    include_media: bool = False,
    media_limit: int = DEFAULT_MEDIA_LIMIT,
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
    candidate_jids, _ = history_jid_candidates(resolution=resolution, config=config)
    response, jid, attempted_jids = invoke_history_read(
        operation="latest",
        jids=candidate_jids,
        command_builder=lambda candidate_jid: ["messages", "list", "--chat", candidate_jid, "--limit", str(limit)],
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
    )
    if not response["ok"]:
        return response
    response["result"]["resolution"] = enrich_history_resolution(
        resolution=resolution,
        config=config,
        used_jid=jid,
        attempted_jids=attempted_jids,
    )
    response = enrich_message_presentations(response, config=config, resolution=response["result"]["resolution"])
    freshness = message_store_freshness(
        resolution=resolution,
        config=config,
        used_jid=jid,
        attempted_jids=attempted_jids,
    )

    messages_returned = len(message_items_from_response(response))
    if not auto_backfill:
        response["result"]["backfill"] = {"backfill_attempted": False}
        response = enrich_media_artifacts(
            response,
            include_media=include_media,
            media_limit=media_limit,
            chat_jid=jid,
            runner=runner,
            config=config,
            timeout_sec=timeout_sec,
        )
        return apply_message_store_freshness(response, freshness)
    if messages_returned >= limit:
        response["result"]["backfill"] = {
            "backfill_attempted": False,
            "reason": "requested_limit_satisfied",
            "messages_returned": messages_returned,
        }
        response = enrich_media_artifacts(
            response,
            include_media=include_media,
            media_limit=media_limit,
            chat_jid=jid,
            runner=runner,
            config=config,
            timeout_sec=timeout_sec,
        )
        return apply_message_store_freshness(response, freshness)

    backfill_result = backfill(
        chat,
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
        response = enrich_media_artifacts(
            response,
            include_media=include_media,
            media_limit=media_limit,
            chat_jid=jid,
            runner=runner,
            config=config,
            timeout_sec=timeout_sec,
        )
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
        refreshed["result"]["resolution"] = enrich_history_resolution(
            resolution=resolution,
            config=config,
            used_jid=jid,
            attempted_jids=attempted_jids,
        )
        refreshed = enrich_message_presentations(refreshed, config=config, resolution=refreshed["result"]["resolution"])
        refreshed = enrich_media_artifacts(
            refreshed,
            include_media=include_media,
            media_limit=media_limit,
            chat_jid=jid,
            runner=runner,
            config=config,
            timeout_sec=timeout_sec,
        )
        refreshed["result"]["backfill"] = backfill_result["result"]
        refreshed["result"]["backfill"]["trigger"] = "messages_returned_below_limit"
        refreshed["result"]["backfill"]["initial_messages_returned"] = messages_returned
        refreshed_freshness = message_store_freshness(
            resolution=resolution,
            config=config,
            used_jid=jid,
            attempted_jids=attempted_jids,
        )
        return apply_message_store_freshness(refreshed, refreshed_freshness)

    response["warnings"] = [*response.get("warnings", []), "refresh_after_backfill_failed"]
    response["result"]["backfill"] = backfill_result["result"]
    response["stderr"] = refreshed.get("stderr", "")
    response = enrich_media_artifacts(
        response,
        include_media=include_media,
        media_limit=media_limit,
        chat_jid=jid,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
    )
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
    candidate_jids, counts = history_jid_candidates(resolution=resolution, config=config)
    attempted_jids: list[str] = []
    last_result: dict[str, Any] | None = None

    for jid in candidate_jids:
        attempted_jids.append(jid)
        before_count = counts.get(jid)
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
        result = make_result(
            ok=response["ok"],
            operation="backfill",
            result={
                "chat": enrich_history_resolution(
                    resolution=resolution,
                    config=config,
                    used_jid=jid,
                    attempted_jids=attempted_jids,
                ),
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
        if len(attempted_jids) > 1 and result["ok"]:
            result["warnings"] = [*result.get("warnings", []), "jid_fallback_used"]
        if result["ok"]:
            return result
        last_result = result
        if not is_backfill_seed_missing(result) or len(attempted_jids) >= len(candidate_jids):
            return result

    return last_result or make_result(ok=False, operation="backfill", exit_code=1)


def search_messages(
    query: str,
    *,
    chat: str | None = None,
    limit: int = 50,
    include_media: bool = False,
    media_limit: int = DEFAULT_MEDIA_LIMIT,
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
        resolved_config = config or resolve_config()
        candidate_jids, _ = history_jid_candidates(resolution=resolution, config=resolved_config)
        response, jid, attempted_jids = invoke_history_read(
            operation="search",
            jids=candidate_jids,
            command_builder=lambda candidate_jid: [*args, "--chat", candidate_jid],
            runner=runner,
            config=resolved_config,
            timeout_sec=timeout_sec,
        )
        if response["ok"]:
            response["result"]["resolution"] = enrich_history_resolution(
                resolution=resolution,
                config=resolved_config,
                used_jid=jid,
                attempted_jids=attempted_jids,
            )
            response = enrich_message_presentations(response, config=resolved_config, resolution=response["result"]["resolution"])
            response = enrich_media_artifacts(
                response,
                include_media=include_media,
                media_limit=media_limit,
                chat_jid=jid,
                runner=runner,
                config=resolved_config,
                timeout_sec=timeout_sec,
            )
        return response
    response = invoke_wacli(
        "search",
        args,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
        read_only_env=True,
    )
    if response["ok"]:
        resolved_config = config or resolve_config()
        response = enrich_message_presentations(response, config=resolved_config)
        response = enrich_media_artifacts(
            response,
            include_media=include_media,
            media_limit=media_limit,
            chat_jid=None,
            runner=runner,
            config=resolved_config,
            timeout_sec=timeout_sec,
        )
    return response


def context(
    message_id: str,
    *,
    before: int = 5,
    after: int = 5,
    include_media: bool = False,
    media_limit: int = DEFAULT_MEDIA_LIMIT,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    response = invoke_wacli(
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
    if response["ok"]:
        resolved_config = config or resolve_config()
        response = enrich_message_presentations(response, config=resolved_config)
        response = enrich_media_artifacts(
            response,
            include_media=include_media,
            media_limit=media_limit,
            chat_jid=None,
            runner=runner,
            config=resolved_config,
            timeout_sec=timeout_sec,
        )
    return response


def draft_reply(
    chat: str,
    instruction: str,
    *,
    limit: int = 20,
    include_media: bool = False,
    media_limit: int = DEFAULT_MEDIA_LIMIT,
    runner: Callable[..., ProcessResult] = default_runner,
    config: Config | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    latest_result = latest(
        chat,
        limit=limit,
        include_media=include_media,
        media_limit=media_limit,
        runner=runner,
        config=config,
        timeout_sec=timeout_sec,
    )
    if not latest_result["ok"]:
        return latest_result
    draft_packet = build_draft_packet(
        instruction=instruction,
        latest_result=latest_result,
    )
    return make_result(
        ok=True,
        operation="draft-reply",
        result={
            "instruction": instruction,
            "context": latest_result["result"].get("payload"),
            "draft_status": draft_packet["draft_status"],
            "draft_packet": draft_packet,
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
                "note": (
                    "QR login launched in a separate Windows PowerShell console. "
                    "Do not terminate that process from Codex; it may own the wacli store lock while login or sync is active."
                ),
                "login_process_safety": {
                    "do_not_terminate_from_agent": True,
                    "lock_behavior": "The QR/login process may hold the local store lock after authentication.",
                    "safe_next_step": "Poll auth-status/status and run sync-once only after the popup process exits or releases the lock.",
                    "requires_user_approval_before_kill": True,
                },
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
    latest_parser.add_argument("--include-media", action="store_true")
    latest_parser.add_argument("--media-limit", type=int, default=DEFAULT_MEDIA_LIMIT)

    backfill_parser = subparsers.add_parser("backfill")
    backfill_parser.add_argument("--chat", required=True)
    backfill_parser.add_argument("--count", type=int, default=DEFAULT_BACKFILL_COUNT)
    backfill_parser.add_argument("--requests", type=int, default=DEFAULT_BACKFILL_REQUESTS)
    backfill_parser.add_argument("--wait-sec", type=int, default=DEFAULT_BACKFILL_WAIT_SEC)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--chat")
    search_parser.add_argument("--limit", type=int, default=50)
    search_parser.add_argument("--include-media", action="store_true")
    search_parser.add_argument("--media-limit", type=int, default=DEFAULT_MEDIA_LIMIT)

    context_parser = subparsers.add_parser("context")
    context_parser.add_argument("--message-id", required=True)
    context_parser.add_argument("--before", type=int, default=5)
    context_parser.add_argument("--after", type=int, default=5)
    context_parser.add_argument("--include-media", action="store_true")
    context_parser.add_argument("--media-limit", type=int, default=DEFAULT_MEDIA_LIMIT)

    draft = subparsers.add_parser("draft-reply")
    draft.add_argument("--chat", required=True)
    draft.add_argument("--instruction", required=True)
    draft.add_argument("--limit", type=int, default=20)
    draft.add_argument("--include-media", action="store_true")
    draft.add_argument("--media-limit", type=int, default=DEFAULT_MEDIA_LIMIT)

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
            include_media=args.include_media,
            media_limit=args.media_limit,
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
        return search_messages(
            args.query,
            chat=args.chat,
            limit=args.limit,
            include_media=args.include_media,
            media_limit=args.media_limit,
            **common,
        )
    if args.operation == "context":
        return context(
            args.message_id,
            before=args.before,
            after=args.after,
            include_media=args.include_media,
            media_limit=args.media_limit,
            **common,
        )
    if args.operation == "draft-reply":
        return draft_reply(
            args.chat,
            args.instruction,
            limit=args.limit,
            include_media=args.include_media,
            media_limit=args.media_limit,
            **common,
        )
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
