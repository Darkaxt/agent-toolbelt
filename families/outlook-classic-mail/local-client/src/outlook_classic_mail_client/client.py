import argparse
import contextlib
import html
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from . import blocklists, domain_inspector, mail_cache, queueing


OL_FOLDER_DELETED_ITEMS = 3
OL_FOLDER_SENT_MAIL = 5
OL_FOLDER_INBOX = 6
OL_FOLDER_DRAFTS = 16
OL_MAIL_ITEM = 0

DEFAULT_FOLDER_IDS = {
    "trash": OL_FOLDER_DELETED_ITEMS,
    "deleted": OL_FOLDER_DELETED_ITEMS,
    "sent": OL_FOLDER_SENT_MAIL,
    "inbox": OL_FOLDER_INBOX,
    "drafts": OL_FOLDER_DRAFTS,
}
MUTATING_ACTIONS = {"create-draft", "send", "move", "delete", "category", "mark-read"}
DEFAULT_FOLDER_HINTS_PATH = Path(__file__).resolve().parents[2] / "folder_hints.json"
DEFAULT_COM_LOCK_PATH = Path(__file__).resolve().parents[2] / "state" / "outlook_com.lock"
DEFAULT_DIAGNOSTICS_LOG_PATH = Path(__file__).resolve().parents[2] / "state" / "diagnostics" / "outlook_com_events.jsonl"
DIAGNOSTICS_LOG_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_QUEUE_TIMEOUT_SEC = queueing.DEFAULT_QUEUE_TIMEOUT_SEC


class OutlookBusyError(RuntimeError):
    pass


class OutlookComUnavailableError(RuntimeError):
    def __init__(self, message: str, *, failure_kind: str, diagnostics: dict[str, Any]):
        super().__init__(message)
        self.failure_kind = failure_kind
        self.diagnostics = diagnostics


QueueTimeoutError = queueing.QueueTimeoutError


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
    queue: dict[str, Any] | None = None,
    client_diagnostics: dict[str, Any] | None = None,
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
        "queue": queue,
    }
    if client_diagnostics is not None:
        payload["client_diagnostics"] = client_diagnostics
    return payload


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def process_session_id() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        session_id = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session_id))
        return int(session_id.value) if ok else None
    except Exception:
        return None


def active_console_session_id() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        value = ctypes.windll.kernel32.WTSGetActiveConsoleSessionId()
        return None if value == 0xFFFFFFFF else int(value)
    except Exception:
        return None


def input_desktop_accessible() -> bool | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        user32 = ctypes.windll.user32
        desktop = user32.OpenInputDesktop(0, False, 0x0100)
        if not desktop:
            return False
        user32.CloseDesktop(desktop)
        return True
    except Exception:
        return None


def outlook_process_running() -> bool | None:
    if sys.platform != "win32":
        return None
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq OUTLOOK.EXE", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    output = (completed.stdout or "") + (completed.stderr or "")
    if "INFO:" in output:
        return False
    return "OUTLOOK.EXE" in output.upper()


def build_client_diagnostics(operation: str) -> dict[str, Any]:
    return {
        "invocation_id": str(uuid.uuid4()),
        "created_at": utc_timestamp(),
        "operation": operation,
        "pid": os.getpid(),
        "python_executable": sys.executable,
        "cwd": str(Path.cwd()),
        "username": os.getenv("USERNAME") or os.getenv("USER"),
        "computer_name": os.getenv("COMPUTERNAME"),
        "session_name": os.getenv("SESSIONNAME"),
        "process_session_id": process_session_id(),
        "active_console_session_id": active_console_session_id(),
        "input_desktop_accessible": input_desktop_accessible(),
        "outlook_process_running": outlook_process_running(),
        "started_monotonic": time.monotonic(),
        "elapsed_ms": None,
        "failure_kind": None,
        "exception": None,
        "com_stages": {
            "pywin32_import": "not_started",
            "co_initialize": "not_started",
            "dispatch_outlook_application": "not_started",
            "session_access": "not_started",
        },
    }


def mark_com_stage(diagnostics: dict[str, Any] | None, stage: str, status: str) -> None:
    if diagnostics is not None:
        diagnostics.setdefault("com_stages", {})[stage] = status


def redact_diagnostic_text(value: str, *, limit: int = 320) -> str:
    redacted = value
    redacted = re.sub(r"\bmsg[-_][A-Za-z0-9_.:-]+\b", "<redacted-message-id>", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\b(entry[-_]?id|message[-_]?id|query|subject)=\S+", r"\1=<redacted>", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<redacted-email>", redacted)
    return redacted[:limit]


def exception_diagnostics(exc: BaseException) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": type(exc).__name__,
        "message": redact_diagnostic_text(str(exc)),
    }
    hresult = getattr(exc, "hresult", None)
    if hresult is not None:
        payload["hresult"] = hresult
    if getattr(exc, "args", None):
        for value in exc.args:
            if isinstance(value, int):
                payload.setdefault("hresult", value)
                break
    excepinfo = getattr(exc, "excepinfo", None)
    if excepinfo is not None:
        payload["excepinfo"] = redact_diagnostic_text(str(excepinfo))
    return payload


def finish_client_diagnostics(
    diagnostics: dict[str, Any],
    *,
    failure_kind: str | None = None,
    exception: BaseException | None = None,
) -> dict[str, Any]:
    if failure_kind is not None:
        diagnostics["failure_kind"] = failure_kind
    if exception is not None:
        diagnostics["exception"] = exception_diagnostics(exception)
    started = diagnostics.get("started_monotonic")
    if isinstance(started, (int, float)):
        diagnostics["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    diagnostics.pop("started_monotonic", None)
    return diagnostics


def rotate_diagnostics_log(path: Path) -> None:
    if not path.exists() or path.stat().st_size <= DIAGNOSTICS_LOG_MAX_BYTES:
        return
    previous = path.with_suffix(path.suffix + ".1")
    with contextlib.suppress(FileNotFoundError):
        previous.unlink()
    path.replace(previous)


def write_diagnostics_event(
    diagnostics: dict[str, Any],
    *,
    log_path: Path | None = None,
    include_success: bool = False,
) -> None:
    if not include_success and not diagnostics.get("failure_kind"):
        return
    path = log_path or DEFAULT_DIAGNOSTICS_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate_diagnostics_log(path)
    event = json.loads(json.dumps(diagnostics, default=str))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def read_diagnostics_events(*, limit: int, log_path: Path | None = None) -> list[dict[str, Any]]:
    path = log_path or DEFAULT_DIAGNOSTICS_LOG_PATH
    if limit <= 0 or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for candidate in (path.with_suffix(path.suffix + ".1"), path):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows[-limit:][::-1]


def connect_outlook(diagnostics: dict[str, Any] | None = None):
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        mark_com_stage(diagnostics, "pywin32_import", "failed")
        failure_kind = "pywin32_unavailable"
        if diagnostics is not None:
            finish_client_diagnostics(diagnostics, failure_kind=failure_kind, exception=exc)
        raise OutlookComUnavailableError(
            "pywin32 is required for Outlook Classic COM access.",
            failure_kind=failure_kind,
            diagnostics=diagnostics or {},
        ) from exc

    mark_com_stage(diagnostics, "pywin32_import", "ok")
    try:
        pythoncom.CoInitialize()
    except Exception as exc:
        mark_com_stage(diagnostics, "co_initialize", "failed")
        failure_kind = "co_initialize_failed"
        if diagnostics is not None:
            finish_client_diagnostics(diagnostics, failure_kind=failure_kind, exception=exc)
        raise OutlookComUnavailableError(
            "Outlook COM initialization failed.",
            failure_kind=failure_kind,
            diagnostics=diagnostics or {},
        ) from exc

    mark_com_stage(diagnostics, "co_initialize", "ok")
    try:
        application = win32com.client.Dispatch("Outlook.Application")
    except Exception as exc:
        mark_com_stage(diagnostics, "dispatch_outlook_application", "failed")
        failure_kind = "outlook_dispatch_failed"
        if diagnostics is not None:
            finish_client_diagnostics(diagnostics, failure_kind=failure_kind, exception=exc)
        raise OutlookComUnavailableError(
            "Outlook.Application COM dispatch failed.",
            failure_kind=failure_kind,
            diagnostics=diagnostics or {},
        ) from exc

    mark_com_stage(diagnostics, "dispatch_outlook_application", "ok")
    try:
        session = application.Session
    except Exception as exc:
        mark_com_stage(diagnostics, "session_access", "failed")
        failure_kind = "outlook_session_unavailable"
        if diagnostics is not None:
            finish_client_diagnostics(diagnostics, failure_kind=failure_kind, exception=exc)
        raise OutlookComUnavailableError(
            "Outlook session access failed.",
            failure_kind=failure_kind,
            diagnostics=diagnostics or {},
        ) from exc

    mark_com_stage(diagnostics, "session_access", "ok")
    return application, session


@contextlib.contextmanager
def outlook_com_lock(path: Path | None = None):
    lock_path = path or DEFAULT_COM_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = lock_path.open("a+b")
    except OSError as exc:
        raise OutlookBusyError("Outlook COM is busy with another mail operation.") from exc
    try:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            locked = "msvcrt"
        except ImportError:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = "fcntl"
        except OSError as exc:
            raise OutlookBusyError("Outlook COM is busy with another mail operation.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if locked == "msvcrt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def safe_get(obj: Any, attribute: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attribute)
    except Exception:
        return default


def iterate_collection(collection: Any, limit: int | None = None) -> Iterable[Any]:
    if isinstance(collection, list):
        yield from collection[:limit]
        return

    count = safe_get(collection, "Count", 0) or 0
    count = int(count)
    if limit is not None:
        count = min(count, limit)

    for index in range(1, count + 1):
        try:
            item = collection.Item(index)
        except AttributeError:
            item = collection[index - 1]
        yield item


def iter_folder_tree(folder: Any) -> Iterable[Any]:
    yield folder
    for child in iterate_collection(safe_get(folder, "Folders", [])):
        yield from iter_folder_tree(child)


def format_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def body_excerpt(item: Any, limit: int = 280) -> str:
    body = safe_get(item, "Body", "") or ""
    normalized = " ".join(str(body).split())
    return normalized[:limit]


def normalize_topic(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    while normalized.startswith(("re:", "fw:", "fwd:")):
        normalized = normalized.split(":", 1)[1].strip()
    return normalized


def folder_summary(folder: Any) -> dict[str, Any]:
    return {
        "name": safe_get(folder, "Name", ""),
        "path": safe_get(folder, "FolderPath", ""),
    }


def folder_summary_with_selector(
    *,
    account_info: dict[str, Any],
    folder: Any,
    folder_selector: str,
    source: str = "discovery",
) -> dict[str, Any]:
    return {
        **folder_summary(folder),
        "folder_selector": folder_selector,
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "source": source,
    }


def message_summary(item: Any) -> dict[str, Any]:
    return {
        "entry_id": safe_get(item, "EntryID", ""),
        "subject": safe_get(item, "Subject", ""),
        "sender_name": safe_get(item, "SenderName", ""),
        "sender_email": safe_get(item, "SenderEmailAddress", ""),
        "to": safe_get(item, "To", ""),
        "received_time": format_datetime(safe_get(item, "ReceivedTime")),
        "unread": bool(safe_get(item, "UnRead", False)),
        "body_excerpt": body_excerpt(item),
        "conversation_id": safe_get(item, "ConversationID", ""),
        "conversation_topic": safe_get(item, "ConversationTopic", ""),
        "folder_path": safe_get(safe_get(item, "Parent"), "FolderPath", ""),
    }


def attachment_summary(attachment: Any) -> dict[str, Any]:
    return {
        "file_name": safe_get(attachment, "FileName", "") or "",
        "display_name": safe_get(attachment, "DisplayName", "") or "",
        "size": safe_get(attachment, "Size", None),
        "type": safe_get(attachment, "Type", None),
        "position": safe_get(attachment, "Position", None),
    }


def safe_attachment_filename(value: str, fallback: str) -> str:
    name = Path(value or fallback).name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name or fallback


def unique_output_path(output_dir: Path, filename: str) -> Path:
    candidate = output_dir / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        alternate = output_dir / f"{stem}-{index}{suffix}"
        if not alternate.exists():
            return alternate
        index += 1


def message_detail(item: Any, *, include_html: bool = False) -> dict[str, Any]:
    attachments = safe_get(item, "Attachments")
    attachment_count = int(safe_get(attachments, "Count", 0) or 0)
    body = str(safe_get(item, "Body", "") or "")
    detail = {
        **message_summary(item),
        "body": body,
        "body_length": len(body),
        "attachment_count": attachment_count,
        "has_attachments": attachment_count > 0,
        "attachments": [attachment_summary(attachment) for attachment in iterate_collection(attachments, attachment_count)],
    }
    if include_html:
        html_body = str(safe_get(item, "HTMLBody", "") or "")
        detail["html_body"] = html_body
        detail["html_body_length"] = len(html_body)
    return detail


def message_datetime(item: Any) -> datetime | None:
    for attribute in ("ReceivedTime", "SentOn", "CreationTime", "LastModificationTime"):
        value = safe_get(item, attribute)
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
    return None


def cache_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None, microsecond=0).isoformat()
    return ""


def message_cache_record(
    *,
    account_info: dict[str, Any],
    folder: Any,
    folder_selector: str,
    item: Any,
) -> dict[str, Any]:
    attachments = safe_get(item, "Attachments")
    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "store_id": account_info["store_id"],
        "folder_selector": folder_selector,
        "folder_path": safe_get(folder, "FolderPath", ""),
        "entry_id": safe_get(item, "EntryID", ""),
        "internet_message_id": safe_get(item, "InternetMessageID", ""),
        "conversation_id": safe_get(item, "ConversationID", ""),
        "conversation_topic": safe_get(item, "ConversationTopic", ""),
        "subject": safe_get(item, "Subject", ""),
        "sender_name": safe_get(item, "SenderName", ""),
        "sender_email": safe_get(item, "SenderEmailAddress", ""),
        "to_text": safe_get(item, "To", ""),
        "cc_text": safe_get(item, "CC", ""),
        "received_time": cache_datetime(safe_get(item, "ReceivedTime")),
        "sent_time": cache_datetime(safe_get(item, "SentOn")),
        "last_modified_time": cache_datetime(safe_get(item, "LastModificationTime")),
        "message_date": cache_datetime(message_datetime(item)),
        "unread": bool(safe_get(item, "UnRead", False)),
        "categories": safe_get(item, "Categories", ""),
        "has_attachments": bool(safe_get(attachments, "Count", 0)),
    }


def collect_accounts(session: Any) -> list[dict[str, Any]]:
    accounts: list[dict[str, Any]] = []
    for account in iterate_collection(safe_get(session, "Accounts", [])):
        store = safe_get(account, "DeliveryStore")
        accounts.append(
            {
                "display_name": safe_get(account, "DisplayName", ""),
                "smtp_address": safe_get(account, "SmtpAddress", ""),
                "delivery_store": safe_get(store, "DisplayName", ""),
                "store_id": safe_get(store, "StoreID", ""),
            }
        )
    return accounts


def iter_account_infos(
    session: Any,
    *,
    account_selector: str | None,
    all_accounts: bool,
) -> list[dict[str, Any]]:
    if all_accounts or not account_selector:
        return [
            resolve_account(session, account["smtp_address"])
            for account in collect_accounts(session)
        ]
    return [resolve_account(session, account_selector)]


def resolve_account(session: Any, selector: str | None) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for account in iterate_collection(safe_get(session, "Accounts", [])):
        store = safe_get(account, "DeliveryStore")
        candidates.append(
            {
                "account": account,
                "store": store,
                "display_name": safe_get(account, "DisplayName", ""),
                "smtp_address": safe_get(account, "SmtpAddress", ""),
                "delivery_store": safe_get(store, "DisplayName", ""),
                "store_id": safe_get(store, "StoreID", ""),
            }
        )

    if not candidates:
        raise ValueError("No Outlook accounts are configured in the current profile.")

    if not selector:
        if len(candidates) == 1:
            return candidates[0]
        raise ValueError("An account selector is required because multiple Outlook accounts are configured.")

    selector_lower = selector.strip().lower()
    for key in ("smtp_address", "delivery_store", "display_name"):
        matches = [
            candidate
            for candidate in candidates
            if str(candidate.get(key, "")).strip().lower() == selector_lower
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Account selector is ambiguous for {selector!r}.")

    raise ValueError(f"No Outlook account matched {selector!r}.")


def resolve_folder(account_info: dict[str, Any], folder_selector: str | None) -> Any:
    store = account_info["store"]
    selector = (folder_selector or "inbox").strip()
    key = selector.lower()

    if key in DEFAULT_FOLDER_IDS:
        return store.GetDefaultFolder(DEFAULT_FOLDER_IDS[key])

    if not key.startswith("custom:"):
        raise ValueError(f"Unsupported folder selector: {folder_selector}")

    root = store.GetRootFolder()
    path_text = selector.split(":", 1)[1]
    segments = [segment for segment in path_text.replace("\\", "/").split("/") if segment]
    current = root
    for segment in segments:
        next_folder = None
        for child in iterate_collection(safe_get(current, "Folders", [])):
            if str(safe_get(child, "Name", "")).strip().lower() == segment.lower():
                next_folder = child
                break
        if next_folder is None:
            raise ValueError(f"Custom folder path segment not found: {segment}")
        current = next_folder
    return current


def iter_folder_tree_with_selectors(root: Any) -> Iterable[tuple[Any, str]]:
    for child in iterate_collection(safe_get(root, "Folders", [])):
        child_name = str(safe_get(child, "Name", ""))
        child_selector = f"custom:{child_name}"
        yield child, child_selector
        for descendant, selector in iter_child_folder_selectors(child, child_selector):
            yield descendant, selector


def iter_child_folder_selectors(folder: Any, parent_selector: str) -> Iterable[tuple[Any, str]]:
    for child in iterate_collection(safe_get(folder, "Folders", [])):
        child_name = str(safe_get(child, "Name", ""))
        child_selector = f"{parent_selector}/{child_name}"
        yield child, child_selector
        yield from iter_child_folder_selectors(child, child_selector)


def collection_sort_by_received_time(collection: Any) -> None:
    try:
        collection.Sort("[ReceivedTime]", True)
    except Exception:
        return


def iter_recent_messages(folder: Any, scan_limit: int) -> Iterable[Any]:
    items = safe_get(folder, "Items", [])
    collection_sort_by_received_time(items)
    for item in iterate_collection(items, scan_limit):
        if safe_get(item, "EntryID", None):
            yield item


def matches_filters(
    item: Any,
    *,
    query: str | None,
    unread: bool,
    sender: str | None,
    recipient: str | None,
    cutoff: datetime | None,
) -> bool:
    if unread and not bool(safe_get(item, "UnRead", False)):
        return False

    received_time = safe_get(item, "ReceivedTime")
    if cutoff and isinstance(received_time, datetime) and is_before_cutoff(received_time, cutoff):
        return False

    if sender:
        sender_lower = sender.lower()
        haystacks = (
            str(safe_get(item, "SenderName", "")).lower(),
            str(safe_get(item, "SenderEmailAddress", "")).lower(),
        )
        if not any(sender_lower in haystack for haystack in haystacks):
            return False

    if recipient:
        if recipient.lower() not in str(safe_get(item, "To", "")).lower():
            return False

    if query:
        query_lower = query.lower()
        searchable = " ".join(
            [
                str(safe_get(item, "Subject", "")),
                str(safe_get(item, "SenderName", "")),
                str(safe_get(item, "SenderEmailAddress", "")),
                str(safe_get(item, "To", "")),
                body_excerpt(item, limit=500),
            ]
        ).lower()
        if query_lower not in searchable:
            return False

    return True


def is_before_cutoff(received_time: datetime, cutoff: datetime) -> bool:
    if received_time.tzinfo is not None and cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=received_time.tzinfo)
    elif received_time.tzinfo is None and cutoff.tzinfo is not None:
        received_time = received_time.replace(tzinfo=cutoff.tzinfo)
    return received_time < cutoff


def resolve_message(session: Any, account_info: dict[str, Any], message_id: str) -> Any:
    if not message_id:
        raise ValueError("A message ID is required for this operation.")
    try:
        return session.GetItemFromID(message_id, account_info["store_id"])
    except Exception:
        try:
            return session.GetItemFromID(message_id)
        except Exception as exc:
            raise ValueError(f"Unable to resolve Outlook message ID {message_id!r}.") from exc


def operation_uses_queue(operation: str) -> bool:
    return operation not in {"blocklists", "cache-status", "cache-show", "cache-clear", "diagnostics-log"}


def outlook_operation_queue(
    operation: str,
    *,
    queue_timeout_sec: int = DEFAULT_QUEUE_TIMEOUT_SEC,
):
    return queueing.acquire_queue_turn(operation, timeout_sec=queue_timeout_sec)


def warning_text(prefix: str, exc: BaseException) -> str:
    return f"{prefix}: {exc}"


def append_warning(warnings: list[str], prefix: str, exc: BaseException) -> None:
    warnings.append(warning_text(prefix, exc))


def try_local_state_write(
    func,
    *,
    warnings: list[str],
    warning_prefix: str,
) -> None:
    try:
        queueing.run_with_state_retries(func)
    except BaseException as exc:
        if queueing.is_retryable_state_error(exc):
            append_warning(warnings, warning_prefix, exc)
            return
        raise


def search_messages(
    session: Any,
    *,
    account_selector: str,
    folder_selector: str,
    query: str | None,
    unread: bool,
    sender: str | None,
    recipient: str | None,
    days: int | None,
    limit: int,
    cache: mail_cache.MailCache | None = None,
    update_cache: bool = False,
) -> dict[str, Any]:
    account_info = resolve_account(session, account_selector)
    folder = resolve_folder(account_info, folder_selector)
    cutoff = datetime.now() - timedelta(days=days) if days else None
    scan_limit = max(limit * 25, 200)

    messages: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in iter_recent_messages(folder, scan_limit):
        if not matches_filters(
            item,
            query=query,
            unread=unread,
            sender=sender,
            recipient=recipient,
            cutoff=cutoff,
        ):
            continue
        if cache is not None and update_cache:
            record = message_cache_record(
                account_info=account_info,
                folder=folder,
                folder_selector=folder_selector,
                item=item,
            )
            try_local_state_write(
                lambda record=record: cache.upsert_message(record),
                warnings=warnings,
                warning_prefix="mail cache write skipped",
            )
        messages.append(message_summary(item))
        if len(messages) >= limit:
            break

    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "folder": folder_summary(folder),
        "messages": messages,
        "warnings": warnings,
    }


def inspect_domains(
    session: Any,
    *,
    account_selector: str,
    message_id: str,
    with_rdap: bool,
    young_days: int,
    rdap_cache: str | None = None,
    with_blocklists: bool = False,
    blocklist_profile: str = "threat",
    blocklist_cache: str | None = None,
) -> dict[str, Any]:
    account_info = resolve_account(session, account_selector)
    item = resolve_message(session, account_info, message_id)
    cache_path = Path(rdap_cache) if rdap_cache else None
    blocklist_cache_path = Path(blocklist_cache) if blocklist_cache else None
    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "message": message_summary(item),
        **domain_inspector.inspect_item_domains(
            item,
            with_rdap=with_rdap,
            cache_path=cache_path,
            young_days=young_days,
            with_blocklists=with_blocklists,
            blocklist_profile=blocklist_profile,
            blocklist_cache_path=blocklist_cache_path,
        ),
    }


def scan_domain_refs(
    session: Any,
    *,
    account_selector: str,
    folder_selector: str,
    days: int | None,
    limit: int,
    with_rdap: bool,
    young_days: int,
    rdap_cache: str | None = None,
    with_blocklists: bool = False,
    blocklist_profile: str = "threat",
    blocklist_cache: str | None = None,
) -> dict[str, Any]:
    account_info = resolve_account(session, account_selector)
    folder = resolve_folder(account_info, folder_selector)
    cutoff = datetime.now() - timedelta(days=days) if days else None
    scan_limit = max(limit * 25, 200)
    cache_path = Path(rdap_cache) if rdap_cache else None
    blocklist_cache_path = Path(blocklist_cache) if blocklist_cache else None
    messages: list[dict[str, Any]] = []

    for item in iter_recent_messages(folder, scan_limit):
        received_time = safe_get(item, "ReceivedTime")
        if cutoff and isinstance(received_time, datetime) and is_before_cutoff(received_time, cutoff):
            continue
        messages.append(
            {
                "message": message_summary(item),
                **domain_inspector.inspect_item_domains(
                    item,
                    with_rdap=with_rdap,
                    cache_path=cache_path,
                    young_days=young_days,
                    with_blocklists=with_blocklists,
                    blocklist_profile=blocklist_profile,
                    blocklist_cache_path=blocklist_cache_path,
                ),
            }
        )
        if len(messages) >= limit:
            break

    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "folder": folder_summary(folder),
        "messages": messages,
    }


def manage_blocklists(
    *,
    action: str,
    profile: str,
    blocklist_cache: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    cache_path = Path(blocklist_cache) if blocklist_cache else None
    cache = blocklists.BlocklistCache(cache_path)
    if action == "refresh":
        return {
            "profile": profile,
            "refresh": cache.refresh(profile=profile, force=force),
            "sources": cache.status(profile=profile),
        }
    if action == "status":
        return {"profile": profile, "sources": cache.status(profile=profile)}
    raise ValueError(f"Unsupported blocklist action: {action}")


def normalize_hint_key(query: str) -> str:
    return query.strip().lower()


def load_folder_hints(path: Path | None = None) -> dict[str, list[str]]:
    hint_path = path or DEFAULT_FOLDER_HINTS_PATH
    if not hint_path.is_file():
        return {}
    try:
        payload = json.loads(hint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        selectors = [selector for selector in value if isinstance(selector, str)]
        if selectors:
            normalized[normalize_hint_key(key)] = sorted(dict.fromkeys(selectors))
    return normalized


def save_folder_hints(hints: dict[str, list[str]], path: Path | None = None) -> None:
    hint_path = path or DEFAULT_FOLDER_HINTS_PATH
    hint_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        key: sorted(dict.fromkeys(value))
        for key, value in sorted(hints.items())
        if value
    }
    hint_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")


def remember_folder_hints(
    *,
    query: str,
    matches: list[dict[str, Any]],
    path: Path | None = None,
) -> None:
    if not matches:
        return
    hints = load_folder_hints(path)
    key = normalize_hint_key(query)
    existing = list(hints.get(key, []))
    for match in matches:
        selector = match.get("folder_selector")
        if isinstance(selector, str):
            existing.append(selector)
    hints[key] = sorted(dict.fromkeys(existing))
    save_folder_hints(hints, path)


def folder_matches_query(folder: Any, folder_selector: str, query: str) -> bool:
    query_lower = query.lower()
    haystack = " ".join(
        [
            str(safe_get(folder, "Name", "")),
            str(safe_get(folder, "FolderPath", "")),
            folder_selector,
        ]
    ).lower()
    return query_lower in haystack


def find_folders(
    session: Any,
    *,
    query: str,
    account_selector: str | None,
    all_accounts: bool,
    limit: int,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    limited = False
    for account_info in iter_account_infos(
        session,
        account_selector=account_selector,
        all_accounts=all_accounts,
    ):
        root = account_info["store"].GetRootFolder()
        for folder, folder_selector in iter_folder_tree_with_selectors(root):
            if not folder_matches_query(folder, folder_selector, query):
                continue
            if len(matches) >= limit:
                limited = True
                break
            matches.append(
                folder_summary_with_selector(
                    account_info=account_info,
                    folder=folder,
                    folder_selector=folder_selector,
                    source="discovery",
                )
            )
        if limited:
            break

    return {
        "query": query,
        "matches": matches,
        "scope": {
            "strategy": "folder-discovery",
            "limit": limit,
            "limited": limited,
            "all_accounts": all_accounts or not account_selector,
        },
    }


def dedupe_folder_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (str(entry.get("account", "")), str(entry.get("folder_selector", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def hint_folder_entries(
    session: Any,
    *,
    query: str,
    account_infos: list[dict[str, Any]],
    folder_hints: dict[str, list[str]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for selector in folder_hints.get(normalize_hint_key(query), []):
        for account_info in account_infos:
            try:
                folder = resolve_folder(account_info, selector)
            except Exception:
                continue
            entries.append(
                folder_summary_with_selector(
                    account_info=account_info,
                    folder=folder,
                    folder_selector=selector,
                    source="hint",
                )
            )
    return dedupe_folder_entries(entries)


def fallback_folder_entries(
    account_infos: list[dict[str, Any]],
    *,
    folder_limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    entries: list[dict[str, Any]] = []
    limited = False
    for account_info in account_infos:
        root = account_info["store"].GetRootFolder()
        for folder, folder_selector in iter_folder_tree_with_selectors(root):
            if len(entries) >= folder_limit:
                limited = True
                return entries, limited
            entries.append(
                folder_summary_with_selector(
                    account_info=account_info,
                    folder=folder,
                    folder_selector=folder_selector,
                    source="bounded-fallback",
                )
            )
    return entries, limited


def cache_candidate_folder_entries(
    cache_rows: list[dict[str, Any]],
    *,
    folder_limit: int,
) -> list[dict[str, Any]]:
    cache = mail_cache.MailCache()
    return cache.candidate_folders(cache_rows, limit=folder_limit)


def cache_folder_entries(account_info: dict[str, Any]) -> list[tuple[Any, str]]:
    entries: list[tuple[Any, str]] = []
    seen_paths: set[str] = set()

    for selector in ("inbox", "sent", "drafts", "trash"):
        try:
            folder = resolve_folder(account_info, selector)
        except Exception:
            continue
        path = str(safe_get(folder, "FolderPath", ""))
        if path in seen_paths:
            continue
        seen_paths.add(path)
        entries.append((folder, selector))

    root = account_info["store"].GetRootFolder()
    for folder, selector in iter_folder_tree_with_selectors(root):
        path = str(safe_get(folder, "FolderPath", ""))
        if path in seen_paths:
            continue
        seen_paths.add(path)
        entries.append((folder, selector))

    return entries


def cache_status(*, cache_path: str | None = None, query: str | None = None) -> dict[str, Any]:
    return mail_cache.MailCache(cache_path).status(query=query)


def cache_show(
    *,
    cache_path: str | None = None,
    query: str,
    account_selector: str | None = None,
    days: int | None = None,
    limit: int,
) -> dict[str, Any]:
    cache = mail_cache.MailCache(cache_path)
    rows = cache.search(
        query=query,
        sender=None,
        recipient=None,
        unread=False,
        days=days,
        account=account_selector,
        limit=limit,
    )
    return {
        "cache": cache.status(),
        "query": query,
        "messages": rows,
        "candidate_folders": cache.candidate_folders(rows, limit=10),
    }


def cache_clear(*, cache_path: str | None = None, query: str | None = None, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Clearing the Outlook metadata cache requires --confirm.")
    return mail_cache.MailCache(cache_path).clear(query=query)


def cache_refresh(
    session: Any,
    *,
    account_selector: str | None,
    all_accounts: bool,
    days: int,
    force: bool,
    cache_path: str | None = None,
) -> dict[str, Any]:
    cache = mail_cache.MailCache(cache_path)
    cache.ensure_schema()
    cutoff = datetime.now() - timedelta(days=days)
    overlap = timedelta(hours=24)
    refreshed_at = mail_cache.utc_now_iso()
    accounts = iter_account_infos(
        session,
        account_selector=account_selector,
        all_accounts=all_accounts,
    )
    folders: list[dict[str, Any]] = []
    messages_cached = 0
    warnings: list[str] = []

    for account_info in accounts:
        for folder, folder_selector in cache_folder_entries(account_info):
            high_watermark_text = None if force else cache.folder_high_watermark(account_info["store_id"], folder_selector)
            high_watermark = mail_cache.parse_iso(high_watermark_text)
            refresh_cutoff = cutoff
            if high_watermark is not None:
                refresh_cutoff = max(cutoff, high_watermark - overlap)

            folder_cached = 0
            folder_scanned = 0
            newest_seen: datetime | None = high_watermark
            try:
                for item in iter_recent_messages(folder, 20000):
                    folder_scanned += 1
                    message_time = message_datetime(item)
                    if message_time is not None and is_before_cutoff(message_time, refresh_cutoff):
                        break
                    cache.upsert_message(
                        message_cache_record(
                            account_info=account_info,
                            folder=folder,
                            folder_selector=folder_selector,
                            item=item,
                        )
                    )
                    folder_cached += 1
                    messages_cached += 1
                    if message_time is not None and (newest_seen is None or newest_seen < message_time):
                        newest_seen = message_time
            except Exception as exc:
                warnings.append(
                    f"Unable to refresh folder {safe_get(folder, 'FolderPath', folder_selector)!r}: {exc}"
                )

            cache.update_folder_state(
                {
                    "store_id": account_info["store_id"],
                    "account": account_info["smtp_address"],
                    "store": account_info["delivery_store"],
                    "folder_selector": folder_selector,
                    "folder_path": safe_get(folder, "FolderPath", ""),
                    "high_watermark": cache_datetime(newest_seen),
                    "refreshed_at": refreshed_at,
                    "message_count": folder_cached,
                }
            )
            folders.append(
                {
                    "account": account_info["smtp_address"],
                    "store": account_info["delivery_store"],
                    "folder_selector": folder_selector,
                    "folder_path": safe_get(folder, "FolderPath", ""),
                    "scanned": folder_scanned,
                    "cached": folder_cached,
                    "high_watermark": cache_datetime(newest_seen),
                    "incremental_from": cache_datetime(refresh_cutoff),
                }
            )

    pruned = cache.prune(days=days)
    return {
        "cache": cache.status(),
        "days": days,
        "force": force,
        "folders_scanned": len(folders),
        "messages_cached": messages_cached,
        "messages_pruned": pruned,
        "folders": folders,
        "warnings": warnings,
    }


def sync_mail(
    application: Any,
    session: Any,
    *,
    refresh_cache: bool,
    account_selector: str | None,
    all_accounts: bool,
    days: int,
    force: bool,
    cache_path: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    attempted: list[dict[str, Any]] = []
    warnings: list[str] = []

    sync_objects = safe_get(session, "SyncObjects")
    if sync_objects:
        for sync_object in iterate_collection(sync_objects):
            name = str(safe_get(sync_object, "Name", "") or "SyncObject")
            try:
                sync_object.Start()
                attempted.append({"name": name, "method": "SyncObjects.Start", "status": "started"})
            except Exception as exc:
                warnings.append(f"Sync object {name!r} failed: {exc}")

    if not attempted:
        send_receive = safe_get(session, "SendAndReceive") or safe_get(application, "SendAndReceive")
        if callable(send_receive):
            try:
                send_receive(False)
            except TypeError:
                send_receive()
            attempted.append({"name": "SendAndReceive", "method": "Session.SendAndReceive", "status": "started"})
        else:
            warnings.append("No Outlook SyncObjects or SendAndReceive API was available.")

    payload: dict[str, Any] = {
        "attempted": attempted,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "status": "started" if attempted else "unavailable",
        "warnings": warnings,
    }
    if refresh_cache:
        payload["cache_refresh"] = cache_refresh(
            session,
            account_selector=account_selector,
            all_accounts=all_accounts,
            days=days,
            force=force,
            cache_path=cache_path,
        )
    return payload


def search_all_folders(
    session: Any,
    *,
    account_selector: str | None,
    all_accounts: bool,
    query: str,
    unread: bool,
    sender: str | None,
    recipient: str | None,
    days: int | None,
    folder_limit: int,
    per_folder_limit: int,
    folder_hints: dict[str, list[str]] | None = None,
    update_hints: bool = True,
    use_cache: bool = False,
    update_cache: bool = False,
    broad_scan: bool = False,
    cache_path: str | None = None,
) -> dict[str, Any]:
    account_infos = iter_account_infos(
        session,
        account_selector=account_selector,
        all_accounts=all_accounts,
    )
    cache = mail_cache.MailCache(cache_path) if use_cache or update_cache else None
    cache_rows: list[dict[str, Any]] = []
    cache_entries: list[dict[str, Any]] = []
    cache_warnings: list[str] = []
    fallback_reason: str | None = None
    if use_cache and query:
        try:
            cache_rows = cache.search(
                query=query,
                sender=sender,
                recipient=recipient,
                unread=unread,
                days=days,
                account=None if all_accounts else account_selector,
                limit=max(folder_limit * per_folder_limit * 5, 50),
            ) if cache is not None else []
            cache_entries = cache.candidate_folders(cache_rows, limit=folder_limit) if cache is not None else []
        except Exception as exc:
            cache_warnings.append(f"mail cache unavailable: {exc}")

    if cache_entries and not broad_scan:
        messages: list[dict[str, Any]] = []
        searched_folders: list[dict[str, Any]] = []
        for entry in cache_entries[:folder_limit]:
            try:
                search_result = search_messages(
                    session,
                    account_selector=entry["account"],
                    folder_selector=entry["folder_selector"],
                    query=query,
                    unread=unread,
                    sender=sender,
                    recipient=recipient,
                    days=days,
                    limit=per_folder_limit,
                    cache=cache,
                    update_cache=update_cache,
                )
            except Exception as exc:
                cache_warnings.append(
                    f"cached folder {entry.get('folder_selector', '')!r} could not be searched: {exc}"
                )
                continue
            folder = search_result["folder"]
            searched_folders.append(
                {
                    "name": folder.get("name", ""),
                    "path": folder.get("path", entry.get("folder_path", "")),
                    "folder_selector": entry["folder_selector"],
                    "account": search_result["account"],
                    "store": search_result["store"],
                    "source": "mail-cache",
                    "hit_count": entry.get("hit_count", 0),
                    "latest_message_date": entry.get("latest_message_date", ""),
                }
            )
            messages.extend(search_result["messages"])
            cache_warnings.extend(search_result.get("warnings", []))
        if messages:
            messages = sorted(messages, key=lambda item: item.get("received_time") or "", reverse=True)
            return {
                "query": query,
                "messages": messages,
                "matched_folders": searched_folders,
                "searched_folders": searched_folders,
                "backend": "mail-cache+live-com",
                "cache_hit": True,
                "cache_refreshed": bool(update_cache),
                "fallback_reason": None,
                "warnings": cache_warnings,
                "scope": {
                    "strategy": "mail-cache",
                    "folder_limit": folder_limit,
                    "per_folder_limit": per_folder_limit,
                    "limited": len(cache_entries) > folder_limit,
                    "all_accounts": all_accounts or not account_selector,
                },
            }
        fallback_reason = "cache_candidates_no_live_hits"
    elif use_cache:
        fallback_reason = "cache_miss"

    hints = folder_hints if folder_hints is not None else load_folder_hints()
    hint_entries = hint_folder_entries(
        session,
        query=query,
        account_infos=account_infos,
        folder_hints=hints,
    )
    discovery = find_folders(
        session,
        query=query,
        account_selector=account_selector,
        all_accounts=all_accounts,
        limit=folder_limit,
    )
    discovery_entries = discovery["matches"]
    if update_hints and discovery_entries:
        try_local_state_write(
            lambda: remember_folder_hints(query=query, matches=discovery_entries),
            warnings=cache_warnings,
            warning_prefix="folder hint write skipped",
        )

    search_entries = dedupe_folder_entries([*hint_entries, *discovery_entries])
    strategy = "matched-folders"
    limited = bool(discovery["scope"]["limited"])
    if not search_entries:
        search_entries, limited = fallback_folder_entries(
            account_infos,
            folder_limit=folder_limit,
        )
        strategy = "bounded-all-folders"

    messages: list[dict[str, Any]] = []
    searched_folders: list[dict[str, Any]] = []
    for entry in search_entries[:folder_limit]:
        searched_folders.append(entry)
        search_result = search_messages(
            session,
            account_selector=entry["account"],
            folder_selector=entry["folder_selector"],
            query=query,
            unread=unread,
            sender=sender,
            recipient=recipient,
            days=days,
            limit=per_folder_limit,
            cache=cache,
            update_cache=update_cache,
        )
        messages.extend(search_result["messages"])
        cache_warnings.extend(search_result.get("warnings", []))

    messages = sorted(messages, key=lambda item: item.get("received_time") or "", reverse=True)
    return {
        "query": query,
        "messages": messages,
        "matched_folders": discovery_entries,
        "searched_folders": searched_folders,
        "backend": "live-com",
        "cache_hit": bool(cache_entries),
        "cache_refreshed": bool(cache is not None and update_cache and messages),
        "fallback_reason": fallback_reason,
        "warnings": cache_warnings,
        "scope": {
            "strategy": strategy,
            "folder_limit": folder_limit,
            "per_folder_limit": per_folder_limit,
            "limited": limited or len(search_entries) > folder_limit,
            "all_accounts": all_accounts or not account_selector,
        },
    }


def same_thread(item: Any, *, conversation_id: str, conversation_topic: str) -> bool:
    if conversation_id and str(safe_get(item, "ConversationID", "")) == conversation_id:
        return True
    item_topic = normalize_topic(str(safe_get(item, "ConversationTopic", "") or safe_get(item, "Subject", "")))
    return bool(conversation_topic) and item_topic == conversation_topic


def default_thread_folders(account_info: dict[str, Any], anchor_item: Any) -> list[Any]:
    folders: list[Any] = []
    seen: set[str] = set()
    for selector in ("inbox", "sent", "drafts", "trash"):
        try:
            folder = resolve_folder(account_info, selector)
        except Exception:
            continue
        path = str(safe_get(folder, "FolderPath", ""))
        if path not in seen:
            folders.append(folder)
            seen.add(path)

    parent = safe_get(anchor_item, "Parent")
    if parent is not None:
        path = str(safe_get(parent, "FolderPath", ""))
        if path not in seen:
            folders.append(parent)
    return folders


def read_thread(session: Any, *, account_selector: str, message_id: str) -> dict[str, Any]:
    account_info = resolve_account(session, account_selector)
    anchor = resolve_message(session, account_info, message_id)
    conversation_id = str(safe_get(anchor, "ConversationID", ""))
    conversation_topic = normalize_topic(
        str(safe_get(anchor, "ConversationTopic", "") or safe_get(anchor, "Subject", ""))
    )

    thread_map: dict[str, dict[str, Any]] = {}
    for folder in default_thread_folders(account_info, anchor):
        for item in iter_recent_messages(folder, 250):
            if same_thread(item, conversation_id=conversation_id, conversation_topic=conversation_topic):
                thread_map[str(safe_get(item, "EntryID", ""))] = message_summary(item)

    anchor_summary = message_summary(anchor)
    thread_map.setdefault(anchor_summary["entry_id"], anchor_summary)
    messages = sorted(thread_map.values(), key=lambda item: item.get("received_time") or "")

    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "anchor": anchor_summary,
        "messages": messages,
    }


def read_message(
    session: Any,
    *,
    account_selector: str,
    message_id: str,
    include_html: bool = False,
) -> dict[str, Any]:
    account_info = resolve_account(session, account_selector)
    item = resolve_message(session, account_info, message_id)
    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "message": message_detail(item, include_html=include_html),
    }


def save_attachments(
    session: Any,
    *,
    account_selector: str,
    message_id: str,
    output_dir: str,
) -> dict[str, Any]:
    account_info = resolve_account(session, account_selector)
    item = resolve_message(session, account_info, message_id)
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise ValueError(f"Attachment output path is not a directory: {output_dir}")

    attachments = safe_get(item, "Attachments")
    attachment_count = int(safe_get(attachments, "Count", 0) or 0)
    saved_items: list[dict[str, Any]] = []
    for index, attachment in enumerate(iterate_collection(attachments, attachment_count), start=1):
        filename = safe_attachment_filename(
            str(safe_get(attachment, "FileName", "") or safe_get(attachment, "DisplayName", "")),
            f"attachment-{index}",
        )
        target = unique_output_path(destination, filename)
        save_as_file = safe_get(attachment, "SaveAsFile")
        if not callable(save_as_file):
            raise ValueError(f"Attachment cannot be saved through Outlook: {filename}")
        save_as_file(str(target))
        saved_items.append(
            {
                **attachment_summary(attachment),
                "filename": filename,
                "path": str(target),
                "saved": True,
                "warnings": [],
            }
        )

    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "message": message_summary(item),
        "attachment_export": {
            "output_dir": str(destination),
            "saved_count": len(saved_items),
            "items": saved_items,
            "warnings": [],
        },
    }


def extract_recipient_emails(item: Any) -> set[str]:
    text = " ".join(
        [
            str(safe_get(item, "To", "")),
            str(safe_get(item, "CC", "")),
        ]
    )
    return {match.lower() for match in re.findall(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}", text)}


def response_search_accounts(
    session: Any,
    *,
    anchor_account_info: dict[str, Any],
    anchor_item: Any,
    fallback_all_accounts: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_accounts = iter_account_infos(session, account_selector=None, all_accounts=True)
    recipient_emails = extract_recipient_emails(anchor_item)
    recipient_accounts = [
        account
        for account in all_accounts
        if str(account.get("smtp_address", "")).lower() in recipient_emails
    ]

    if not recipient_accounts:
        recipient_accounts = [anchor_account_info]

    recipient_keys = {str(account.get("smtp_address", "")).lower() for account in recipient_accounts}
    fallback_accounts = (
        [
            account
            for account in all_accounts
            if str(account.get("smtp_address", "")).lower() not in recipient_keys
        ]
        if fallback_all_accounts
        else []
    )
    return recipient_accounts, fallback_accounts


def response_match(
    item: Any,
    *,
    anchor_item: Any,
    conversation_id: str,
    conversation_topic: str,
    anchor_time: Any,
) -> tuple[str, float] | None:
    item_id = str(safe_get(item, "EntryID", ""))
    if item_id and item_id == str(safe_get(anchor_item, "EntryID", "")):
        return None

    received_time = safe_get(item, "ReceivedTime")
    if isinstance(anchor_time, datetime) and isinstance(received_time, datetime):
        if is_before_cutoff(received_time, anchor_time):
            return None

    if conversation_id and str(safe_get(item, "ConversationID", "")) == conversation_id:
        return "conversation_id", 1.0

    item_topic = normalize_topic(str(safe_get(item, "ConversationTopic", "") or safe_get(item, "Subject", "")))
    if conversation_topic and item_topic == conversation_topic:
        return "conversation_topic", 0.75

    return None


def search_response_folders(
    *,
    account_infos: list[dict[str, Any]],
    scope: str,
    include_drafts: bool,
) -> list[dict[str, Any]]:
    selectors = ["sent", *([] if not include_drafts else ["drafts"])]
    entries: list[dict[str, Any]] = []
    for account_info in account_infos:
        for selector in selectors:
            try:
                folder = resolve_folder(account_info, selector)
            except Exception:
                continue
            entries.append(
                {
                    **folder_summary_with_selector(
                        account_info=account_info,
                        folder=folder,
                        folder_selector=selector,
                        source=scope,
                    ),
                    "_folder": folder,
                    "scope": scope,
                }
            )
    return entries


def find_response(
    session: Any,
    *,
    account_selector: str,
    message_id: str,
    limit: int,
    fallback_all_accounts: bool,
    include_drafts: bool,
) -> dict[str, Any]:
    anchor_account_info = resolve_account(session, account_selector)
    anchor_item = resolve_message(session, anchor_account_info, message_id)
    conversation_id = str(safe_get(anchor_item, "ConversationID", ""))
    conversation_topic = normalize_topic(
        str(safe_get(anchor_item, "ConversationTopic", "") or safe_get(anchor_item, "Subject", ""))
    )
    anchor_time = safe_get(anchor_item, "ReceivedTime")

    recipient_accounts, fallback_accounts = response_search_accounts(
        session,
        anchor_account_info=anchor_account_info,
        anchor_item=anchor_item,
        fallback_all_accounts=fallback_all_accounts,
    )
    search_entries = [
        *search_response_folders(
            account_infos=recipient_accounts,
            scope="recipient-account",
            include_drafts=include_drafts,
        ),
        *search_response_folders(
            account_infos=fallback_accounts,
            scope="fallback-account",
            include_drafts=include_drafts,
        ),
    ]

    response_map: dict[str, dict[str, Any]] = {}
    searched_folders: list[dict[str, Any]] = []
    for entry in search_entries:
        folder = entry["_folder"]
        public_entry = {key: value for key, value in entry.items() if key != "_folder"}
        searched_folders.append(public_entry)
        for item in iter_recent_messages(folder, max(limit * 25, 200)):
            match = response_match(
                item,
                anchor_item=anchor_item,
                conversation_id=conversation_id,
                conversation_topic=conversation_topic,
                anchor_time=anchor_time,
            )
            if match is None:
                continue
            match_reason, confidence = match
            summary = message_summary(item)
            response_map[summary["entry_id"]] = {
                **summary,
                "match_reason": match_reason,
                "scope": entry["scope"],
                "confidence": confidence,
            }

    messages = sorted(response_map.values(), key=lambda item: item.get("received_time") or "", reverse=True)[:limit]
    return {
        "account": anchor_account_info["smtp_address"],
        "store": anchor_account_info["delivery_store"],
        "anchor": message_summary(anchor_item),
        "recipient_accounts": [account["smtp_address"] for account in recipient_accounts],
        "searched_folders": searched_folders,
        "messages": messages,
        "scope": {
            "strategy": "recipient-account-first",
            "limit": limit,
            "fallback_all_accounts": fallback_all_accounts,
            "include_drafts": include_drafts,
            "anchor_account": anchor_account_info["smtp_address"],
        },
    }


def classify_message(summary: dict[str, Any]) -> tuple[str, str]:
    text = " ".join([summary["subject"], summary["body_excerpt"]]).lower()
    if any(token in text for token in ("urgent", "asap", "today", "deadline", "blocked", "approval")):
        return "Urgent", "Unread or time-sensitive request with strong urgency language."
    if summary["unread"] and any(token in text for token in ("please", "can you", "could you", "confirm", "review", "?")):
        return "Needs reply soon", "Looks like a direct ask that still needs a response."
    if not summary["unread"] and summary["subject"].lower().startswith("re:"):
        return "Waiting", "Looks like an ongoing thread where the latest visible item is not a fresh unread ask."
    return "FYI", "Looks informational rather than time-sensitive."


def triage_messages(
    session: Any,
    *,
    account_selector: str | None,
    all_accounts: bool,
    days: int,
    limit: int,
) -> dict[str, Any]:
    account_selectors = (
        [account["smtp_address"] for account in collect_accounts(session)]
        if all_accounts or not account_selector
        else [account_selector]
    )

    buckets = {"Urgent": [], "Needs reply soon": [], "Waiting": [], "FYI": []}
    coverage: list[dict[str, Any]] = []
    for selector in account_selectors:
        search_result = search_messages(
            session,
            account_selector=selector,
            folder_selector="inbox",
            query=None,
            unread=False,
            sender=None,
            recipient=None,
            days=days,
            limit=limit,
        )
        coverage.append(
            {
                "account": search_result["account"],
                "store": search_result["store"],
                "folder": search_result["folder"]["path"],
                "message_count": len(search_result["messages"]),
            }
        )
        for summary in search_result["messages"]:
            bucket, why = classify_message(summary)
            buckets[bucket].append({**summary, "why": why})

    return {
        "buckets": buckets,
        "coverage": coverage,
    }


def compose_draft_body(
    *,
    instruction: str,
    message: Any,
    body: str | None,
    mode: str,
) -> str:
    del instruction, message, mode
    if body is not None and body.strip():
        return body
    return ""


def require_final_draft_body(*, body: str | None, mode: str) -> None:
    if body is not None and body.strip():
        return
    raise ValueError(
        f"Creating a {mode} draft requires --body with the final draft text. "
        "--instruction is guidance/context only and is never used as the draft body."
    )


def draft_body_state(*, suggested_body: str, created: bool) -> dict[str, Any]:
    if suggested_body:
        return {
            "draft_status": "created" if created else "ready_to_create",
            "draft_body_source": "body",
            "warnings": [],
        }
    return {
        "draft_status": "needs_body",
        "draft_body_source": "missing",
        "warnings": ["draft_body_missing"],
    }


def prepare_draft_attachments(attachments: Iterable[str] | None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for raw_path in attachments or []:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise ValueError(f"Attachment path does not exist: {raw_path}")
        if not path.is_file():
            raise ValueError(f"Attachment path is not a file: {raw_path}")
        resolved = path.resolve()
        items.append(
            {
                "filename": resolved.name,
                "path": str(resolved),
                "attached": False,
                "warnings": [],
            }
        )
    return {
        "count": len(items),
        "items": items,
        "warnings": [],
    }


def attach_draft_files(draft: Any, draft_attachments: dict[str, Any]) -> None:
    if not draft_attachments.get("items"):
        return
    attachments = safe_get(draft, "Attachments")
    add_attachment = safe_get(attachments, "Add")
    if not callable(add_attachment):
        raise ValueError("Draft item does not expose Attachments.Add.")
    for item in draft_attachments["items"]:
        add_attachment(item["path"])
        item["attached"] = True


def apply_recipient_fields(
    draft: Any,
    *,
    to: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    requested = {"to": to, "cc": cc, "bcc": bcc}
    warnings: list[str] = []
    for attribute, value in (("To", to), ("CC", cc), ("BCC", bcc)):
        if value is None:
            continue
        try:
            setattr(draft, attribute, value)
        except Exception:
            add_unique_warning(warnings, f"{attribute.lower()}_unset")
    return {
        "requested": {key: value for key, value in requested.items() if value is not None},
        "actual": {
            "to": str(safe_get(draft, "To", "") or ""),
            "cc": str(safe_get(draft, "CC", "") or ""),
            "bcc": str(safe_get(draft, "BCC", "") or ""),
        },
        "warnings": warnings,
    }


def draft_recipients_summary(
    draft: Any,
    *,
    reply_mode: str | None = None,
    requested: dict[str, str | None] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        **({"reply_mode": reply_mode} if reply_mode is not None else {}),
        "requested": {key: value for key, value in (requested or {}).items() if value is not None},
        "actual": {
            "to": str(safe_get(draft, "To", "") or ""),
            "cc": str(safe_get(draft, "CC", "") or ""),
            "bcc": str(safe_get(draft, "BCC", "") or ""),
        },
        "warnings": list(warnings or []),
    }


def validate_operation_args(args: argparse.Namespace) -> None:
    operation = getattr(args, "operation", "")
    if operation not in {"draft-reply", "draft-forward"} or not getattr(args, "create_draft", False):
        return
    mode = "reply" if operation == "draft-reply" else "forward"
    if not getattr(args, "confirm", False):
        raise ValueError(f"Creating a {mode} draft requires --confirm.")
    require_final_draft_body(body=getattr(args, "body", None), mode=mode)


def text_to_html_fragment(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [html.escape(line.strip()) for line in block.split("\n") if line.strip()]
        if lines:
            paragraphs.append(f"<p>{'<br>'.join(lines)}</p>")
    return "".join(paragraphs)


def prepend_html_body(*, existing_html: str, draft_text: str) -> str:
    draft_html = text_to_html_fragment(draft_text)
    if not draft_html:
        return existing_html

    body_match = re.search(r"<body\b[^>]*>", existing_html, flags=re.IGNORECASE)
    if body_match:
        return f"{existing_html[:body_match.end()]}{draft_html}{existing_html[body_match.end():]}"
    return f"{draft_html}{existing_html}"


def prepend_draft_body(item: Any, suggested_body: str) -> str:
    existing_html = safe_get(item, "HTMLBody", "")
    if isinstance(existing_html, str) and existing_html.strip():
        item.HTMLBody = prepend_html_body(existing_html=existing_html, draft_text=suggested_body)
        return "html"

    item.Body = f"{suggested_body}\r\n\r\n{safe_get(item, 'Body', '')}"
    return "plain"


def html_body_content(html_body: str) -> str:
    body_match = re.search(r"<body\b[^>]*>(?P<body>.*)</body>", html_body, flags=re.IGNORECASE | re.DOTALL)
    if body_match:
        return body_match.group("body")
    return html_body


def text_from_html(html_body: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", html_body)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def normalize_body_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def source_thread_text(message: Any) -> str:
    body = str(safe_get(message, "Body", "") or "")
    html_body = safe_get(message, "HTMLBody", "")
    html_text = text_from_html(html_body) if isinstance(html_body, str) and html_body.strip() else ""
    return normalize_body_text("\n".join(part for part in (body, html_text) if part))


def candidate_thread_snippets(source_text: str) -> list[str]:
    if not source_text:
        return []
    snippets: list[str] = []
    if len(source_text) <= 120:
        snippets.append(source_text)
    else:
        snippets.append(source_text[:120])
        midpoint = max(0, (len(source_text) // 2) - 60)
        snippets.append(source_text[midpoint : midpoint + 120])
        snippets.append(source_text[-120:])
    return [snippet.strip() for snippet in snippets if len(snippet.strip()) >= 20]


def draft_contains_thread_content(item: Any, source_message: Any) -> bool:
    source_text = source_thread_text(source_message)
    snippets = candidate_thread_snippets(source_text)
    if not snippets:
        return False
    existing_html = safe_get(item, "HTMLBody", "")
    existing_body = safe_get(item, "Body", "")
    existing_parts = []
    if isinstance(existing_html, str) and existing_html.strip():
        existing_parts.append(text_from_html(existing_html))
    if existing_body:
        existing_parts.append(str(existing_body))
    existing_text = normalize_body_text("\n".join(existing_parts))
    return any(snippet in existing_text for snippet in snippets)


def append_html_body(existing_html: str, html_fragment: str) -> str:
    if not existing_html.strip():
        return f"<html><body>{html_fragment}</body></html>"
    body_close = re.search(r"</body\s*>", existing_html, flags=re.IGNORECASE)
    if body_close:
        return f"{existing_html[:body_close.start()]}{html_fragment}{existing_html[body_close.start():]}"
    return f"{existing_html}{html_fragment}"


def message_thread_html(message: Any) -> str:
    html_body = safe_get(message, "HTMLBody", "")
    if isinstance(html_body, str) and html_body.strip():
        body_content = html_body_content(html_body)
    else:
        body_content = text_to_html_fragment(str(safe_get(message, "Body", "") or ""))
    if not body_content.strip():
        return ""

    headers = [
        ("From", safe_get(message, "SenderName", "") or safe_get(message, "SenderEmailAddress", "")),
        ("Sent", safe_get(message, "ReceivedTime", "")),
        ("To", safe_get(message, "To", "")),
        ("Subject", safe_get(message, "Subject", "")),
    ]
    header_html = "".join(
        f"<div><strong>{html.escape(label)}:</strong> {html.escape(str(value))}</div>"
        for label, value in headers
        if value
    )
    return (
        '<div class="agent-toolbelt-quoted-thread">'
        f"{header_html}"
        '<div class="agent-toolbelt-quoted-body">'
        f"{body_content}"
        "</div>"
        "</div>"
    )


def message_thread_plain(message: Any) -> str:
    body = str(safe_get(message, "Body", "") or "").strip()
    if not body:
        return ""
    headers = [
        ("From", safe_get(message, "SenderName", "") or safe_get(message, "SenderEmailAddress", "")),
        ("Sent", safe_get(message, "ReceivedTime", "")),
        ("To", safe_get(message, "To", "")),
        ("Subject", safe_get(message, "Subject", "")),
    ]
    header_text = "\r\n".join(f"{label}: {value}" for label, value in headers if value)
    return "\r\n".join(part for part in (header_text, "", body) if part)


def ensure_thread_content(item: Any, source_message: Any, mode: str) -> dict[str, Any]:
    warnings: list[str] = []
    existing_html = safe_get(item, "HTMLBody", "")
    existing_body = safe_get(item, "Body", "")
    if draft_contains_thread_content(item, source_message):
        return {
            "thread_content_included": True,
            "thread_content_source": f"native_{mode}",
            "warnings": warnings,
        }

    quote_html = message_thread_html(source_message)
    quote_plain = message_thread_plain(source_message)
    if quote_html:
        item.HTMLBody = append_html_body(str(existing_html or ""), quote_html)
        if quote_plain:
            existing_plain = str(existing_body or "").strip()
            item.Body = f"{existing_plain}\r\n\r\n{quote_plain}".strip()
        add_unique_warning(warnings, "thread_quote_fallback_used")
        return {
            "thread_content_included": True,
            "thread_content_source": "manual_quote_fallback",
            "warnings": warnings,
        }
    if quote_plain:
        existing_plain = str(existing_body or "").strip()
        item.Body = f"{existing_plain}\r\n\r\n{quote_plain}".strip()
        add_unique_warning(warnings, "thread_quote_fallback_used")
        return {
            "thread_content_included": True,
            "thread_content_source": "manual_quote_fallback",
            "warnings": warnings,
        }

    add_unique_warning(warnings, "thread_content_missing")
    return {
        "thread_content_included": False,
        "thread_content_source": "missing",
        "warnings": warnings,
    }


def account_store_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_store_id = str(left.get("store_id") or "").strip().lower()
    right_store_id = str(right.get("store_id") or "").strip().lower()
    if left_store_id and right_store_id:
        return left_store_id == right_store_id
    return str(left.get("delivery_store") or "").strip().lower() == str(right.get("delivery_store") or "").strip().lower()


def add_unique_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def send_using_account_smtp(item: Any) -> str:
    account = safe_get(item, "SendUsingAccount")
    if account is None:
        return ""
    return str(safe_get(account, "SmtpAddress", "") or "")


def set_send_using_account(item: Any, account_info: dict[str, Any], warnings: list[str]) -> str:
    expected = str(account_info.get("smtp_address") or "").strip().lower()
    try:
        item.SendUsingAccount = account_info["account"]
    except Exception:
        add_unique_warning(warnings, "send_using_account_unset")
    actual = send_using_account_smtp(item)
    if expected and not actual:
        add_unique_warning(warnings, "send_using_account_unset")
    elif expected and actual.strip().lower() != expected:
        add_unique_warning(warnings, "send_using_account_mismatch")
    return actual


def copy_draft_fields(source: Any, target: Any) -> None:
    for attribute in ("To", "CC", "BCC", "Subject"):
        value = safe_get(source, attribute, "")
        if value:
            try:
                setattr(target, attribute, value)
            except Exception:
                pass
    html_body = safe_get(source, "HTMLBody", "")
    body = safe_get(source, "Body", "")
    if isinstance(html_body, str) and html_body.strip():
        target.HTMLBody = html_body
    elif body:
        target.Body = body


def create_mail_item_in_folder(folder: Any) -> Any:
    items = safe_get(folder, "Items")
    add_item = safe_get(items, "Add")
    if not callable(add_item):
        raise ValueError("Target Drafts folder does not expose Items.Add.")
    return add_item("IPM.Note")


def draft_placement_summary(
    *,
    strategy: str,
    target_account_info: dict[str, Any],
    target_folder: Any | None,
    draft: Any | None,
    warnings: list[str],
) -> dict[str, Any]:
    target_folder_summary = folder_summary(target_folder) if target_folder is not None else None
    actual_folder = safe_get(draft, "Parent") if draft is not None else None
    actual_folder_summary = folder_summary(actual_folder) if actual_folder is not None else None
    target_path = str((target_folder_summary or {}).get("path") or "")
    actual_path = str((actual_folder_summary or {}).get("path") or "")
    placement_verified = bool(target_path and actual_path and target_path == actual_path)
    if draft is not None and target_path and actual_path and not placement_verified:
        add_unique_warning(warnings, "draft_folder_mismatch")
    elif draft is not None and target_path and not actual_path:
        add_unique_warning(warnings, "draft_folder_unverified")

    return {
        "strategy": strategy,
        "target_store": target_account_info.get("delivery_store"),
        "target_account": target_account_info.get("smtp_address"),
        "target_drafts_folder": target_folder_summary,
        "actual_folder": actual_folder_summary,
        "actual_send_using_account": send_using_account_smtp(draft) if draft is not None else "",
        "placement_verified": placement_verified,
        "warnings": warnings,
    }


def save_target_store_draft(
    *,
    template: Any,
    target_account_info: dict[str, Any],
    suggested_body: str,
    source_message: Any | None = None,
    mode: str | None = None,
    initial_warnings: list[str] | None = None,
    draft_attachments: dict[str, Any] | None = None,
) -> tuple[Any, str, dict[str, Any], dict[str, Any]]:
    warnings: list[str] = list(initial_warnings or [])
    draft_content = {
        "thread_content_included": False,
        "thread_content_source": "missing",
        "warnings": [],
    }
    if source_message is not None and mode is not None:
        draft_content = ensure_thread_content(template, source_message, mode)
    body_format = prepend_draft_body(template, suggested_body)
    draft_content["body_format"] = body_format
    target_folder = target_account_info["store"].GetDefaultFolder(OL_FOLDER_DRAFTS)
    draft = create_mail_item_in_folder(target_folder)
    copy_draft_fields(template, draft)
    set_send_using_account(draft, target_account_info, warnings)
    attach_draft_files(draft, draft_attachments or {})
    draft.Save()
    placement = draft_placement_summary(
        strategy="target_store_drafts",
        target_account_info=target_account_info,
        target_folder=target_folder,
        draft=draft,
        warnings=warnings,
    )
    return draft, body_format, placement, draft_content


def create_target_store_draft(
    account_info: dict[str, Any],
    *,
    subject: str | None,
    to: str | None,
    body: str | None,
    cc: str | None = None,
    bcc: str | None = None,
    draft_attachments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    target_folder = account_info["store"].GetDefaultFolder(OL_FOLDER_DRAFTS)
    draft = create_mail_item_in_folder(target_folder)
    draft_recipients = apply_recipient_fields(draft, to=to, cc=cc, bcc=bcc)
    if subject:
        draft.Subject = subject
    if body:
        draft.Body = body
    set_send_using_account(draft, account_info, warnings)
    attach_draft_files(draft, draft_attachments or {})
    draft.Save()
    placement = draft_placement_summary(
        strategy="target_store_drafts",
        target_account_info=account_info,
        target_folder=target_folder,
        draft=draft,
        warnings=warnings,
    )
    return {
        "created": True,
        "draft_entry_id": safe_get(draft, "EntryID", None),
        "subject": safe_get(draft, "Subject", ""),
        "to": safe_get(draft, "To", ""),
        "draft_recipients": draft_recipients,
        "send_using_account": account_info.get("smtp_address"),
        "draft_placement": placement,
        "draft_content": {
            "thread_content_included": False,
            "thread_content_source": "missing",
            "body_format": "plain" if body else "empty",
            "warnings": [],
        },
        "draft_attachments": draft_attachments or prepare_draft_attachments([]),
    }


def resolve_send_using_account(
    session: Any,
    *,
    anchor_account_info: dict[str, Any],
    send_using_account_selector: str | None,
) -> dict[str, Any]:
    if not send_using_account_selector:
        return anchor_account_info
    return resolve_account(session, send_using_account_selector)


def draft_reply(
    session: Any,
    *,
    account_selector: str,
    send_using_account_selector: str | None = None,
    message_id: str,
    instruction: str,
    body: str | None,
    create_draft: bool,
    confirm: bool,
    attachments: Iterable[str] | None = None,
    reply_mode: str = "sender",
    to: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    if create_draft and not confirm:
        raise ValueError("Creating a reply draft requires --confirm.")
    if create_draft:
        require_final_draft_body(body=body, mode="reply")
    draft_attachments = prepare_draft_attachments(attachments)

    account_info = resolve_account(session, account_selector)
    message = resolve_message(session, account_info, message_id)
    if reply_mode == "all":
        reply_all = safe_get(message, "ReplyAll")
        if not callable(reply_all):
            raise ValueError("Message does not expose ReplyAll.")
        reply = reply_all()
    elif reply_mode == "sender":
        reply = message.Reply()
    else:
        raise ValueError("Reply mode must be sender or all.")
    recipient_summary = apply_recipient_fields(reply, to=to, cc=cc, bcc=bcc)
    suggested_body = compose_draft_body(
        instruction=instruction,
        message=message,
        body=body,
        mode="reply",
    )

    created = False
    draft_entry_id = None
    body_format = "preview"
    draft_placement: dict[str, Any] = {"strategy": "preview"}
    draft_content: dict[str, Any] = {
        "thread_content_included": False,
        "thread_content_source": "missing",
        "body_format": "preview",
        "warnings": [],
    }
    send_account_info = resolve_send_using_account(
        session,
        anchor_account_info=account_info,
        send_using_account_selector=send_using_account_selector,
    )
    if create_draft:
        if send_using_account_selector and not account_store_matches(account_info, send_account_info):
            reply, body_format, draft_placement, draft_content = save_target_store_draft(
                template=reply,
                target_account_info=send_account_info,
                suggested_body=suggested_body,
                source_message=message,
                mode="reply",
                draft_attachments=draft_attachments,
            )
        else:
            warnings: list[str] = []
            actual_sender = set_send_using_account(reply, send_account_info, warnings)
            if not actual_sender or warnings:
                fallback_warnings = ["native_send_using_account_unverified"]
                reply, body_format, draft_placement, draft_content = save_target_store_draft(
                    template=reply,
                    target_account_info=send_account_info,
                    suggested_body=suggested_body,
                    source_message=message,
                    mode="reply",
                    initial_warnings=fallback_warnings,
                    draft_attachments=draft_attachments,
                )
            else:
                draft_content = ensure_thread_content(reply, message, "reply")
                body_format = prepend_draft_body(reply, suggested_body)
                draft_content["body_format"] = body_format
                attach_draft_files(reply, draft_attachments)
                reply.Save()
                target_folder = account_info["store"].GetDefaultFolder(OL_FOLDER_DRAFTS)
                draft_placement = draft_placement_summary(
                    strategy="native_reply",
                    target_account_info=send_account_info,
                    target_folder=target_folder,
                    draft=reply,
                    warnings=warnings,
                )
        created = True
        draft_entry_id = safe_get(reply, "EntryID", None)
    body_state = draft_body_state(suggested_body=suggested_body, created=created)

    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "message": message_summary(message),
        "to": safe_get(reply, "To", ""),
        "subject": safe_get(reply, "Subject", ""),
        "suggested_body": suggested_body,
        "instruction": instruction,
        "draft_status": body_state["draft_status"],
        "draft_body_source": body_state["draft_body_source"],
        "warnings": body_state["warnings"],
        "send_using_account": send_account_info["smtp_address"],
        "body_format": body_format,
        "created": created,
        "draft_entry_id": draft_entry_id,
        "draft_placement": draft_placement,
        "draft_content": draft_content,
        "draft_attachments": draft_attachments,
        "draft_recipients": draft_recipients_summary(
            reply,
            reply_mode=reply_mode,
            requested=recipient_summary["requested"],
            warnings=recipient_summary["warnings"],
        ),
    }


def draft_forward(
    session: Any,
    *,
    account_selector: str,
    send_using_account_selector: str | None = None,
    message_id: str,
    to: str,
    instruction: str,
    body: str | None,
    create_draft: bool,
    confirm: bool,
    attachments: Iterable[str] | None = None,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    if create_draft and not confirm:
        raise ValueError("Creating a forward draft requires --confirm.")
    if create_draft:
        require_final_draft_body(body=body, mode="forward")
    draft_attachments = prepare_draft_attachments(attachments)

    account_info = resolve_account(session, account_selector)
    message = resolve_message(session, account_info, message_id)
    forward = message.Forward()
    recipient_summary = apply_recipient_fields(forward, to=to, cc=cc, bcc=bcc)
    suggested_body = compose_draft_body(
        instruction=instruction,
        message=message,
        body=body,
        mode="forward",
    )

    created = False
    draft_entry_id = None
    body_format = "preview"
    draft_placement: dict[str, Any] = {"strategy": "preview"}
    draft_content: dict[str, Any] = {
        "thread_content_included": False,
        "thread_content_source": "missing",
        "body_format": "preview",
        "warnings": [],
    }
    send_account_info = resolve_send_using_account(
        session,
        anchor_account_info=account_info,
        send_using_account_selector=send_using_account_selector,
    )
    if create_draft:
        if send_using_account_selector and not account_store_matches(account_info, send_account_info):
            forward, body_format, draft_placement, draft_content = save_target_store_draft(
                template=forward,
                target_account_info=send_account_info,
                suggested_body=suggested_body,
                source_message=message,
                mode="forward",
                draft_attachments=draft_attachments,
            )
        else:
            warnings: list[str] = []
            actual_sender = set_send_using_account(forward, send_account_info, warnings)
            if not actual_sender or warnings:
                fallback_warnings = ["native_send_using_account_unverified"]
                forward, body_format, draft_placement, draft_content = save_target_store_draft(
                    template=forward,
                    target_account_info=send_account_info,
                    suggested_body=suggested_body,
                    source_message=message,
                    mode="forward",
                    initial_warnings=fallback_warnings,
                    draft_attachments=draft_attachments,
                )
            else:
                draft_content = ensure_thread_content(forward, message, "forward")
                body_format = prepend_draft_body(forward, suggested_body)
                draft_content["body_format"] = body_format
                attach_draft_files(forward, draft_attachments)
                forward.Save()
                target_folder = account_info["store"].GetDefaultFolder(OL_FOLDER_DRAFTS)
                draft_placement = draft_placement_summary(
                    strategy="native_forward",
                    target_account_info=send_account_info,
                    target_folder=target_folder,
                    draft=forward,
                    warnings=warnings,
                )
        created = True
        draft_entry_id = safe_get(forward, "EntryID", None)
    body_state = draft_body_state(suggested_body=suggested_body, created=created)

    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "message": message_summary(message),
        "to": safe_get(forward, "To", ""),
        "subject": safe_get(forward, "Subject", ""),
        "suggested_body": suggested_body,
        "instruction": instruction,
        "draft_status": body_state["draft_status"],
        "draft_body_source": body_state["draft_body_source"],
        "warnings": body_state["warnings"],
        "send_using_account": send_account_info["smtp_address"],
        "body_format": body_format,
        "created": created,
        "draft_entry_id": draft_entry_id,
        "draft_placement": draft_placement,
        "draft_content": draft_content,
        "draft_attachments": draft_attachments,
        "draft_recipients": draft_recipients_summary(
            forward,
            requested=recipient_summary["requested"],
            warnings=recipient_summary["warnings"],
        ),
    }


def move_message(
    session: Any,
    *,
    account_selector: str,
    message_id: str,
    target_folder: str,
    confirm: bool,
) -> dict[str, Any]:
    if not target_folder:
        raise ValueError("Move-message requires --target-folder.")

    account_info = resolve_account(session, account_selector)
    item = resolve_message(session, account_info, message_id)
    source_folder = safe_get(item, "Parent")
    target = resolve_folder(account_info, target_folder)

    if not confirm:
        return {
            "account": account_info["smtp_address"],
            "store": account_info["delivery_store"],
            "message": message_summary(item),
            "source_folder": folder_summary(source_folder),
            "target_folder": folder_summary(target),
            "target_folder_selector": target_folder,
            "would_move": True,
            "moved": False,
        }

    moved = item.Move(target)
    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "message": message_summary(moved),
        "source_folder": folder_summary(source_folder),
        "target_folder": folder_summary(target),
        "target_folder_selector": target_folder,
        "would_move": False,
        "moved": True,
    }


def create_generic_draft(
    application: Any,
    account_info: dict[str, Any],
    *,
    subject: str | None,
    to: str | None,
    body: str | None,
    cc: str | None = None,
    bcc: str | None = None,
    attachments: Iterable[str] | None = None,
) -> dict[str, Any]:
    return create_target_store_draft(
        account_info,
        subject=subject,
        to=to,
        body=body,
        cc=cc,
        bcc=bcc,
        draft_attachments=prepare_draft_attachments(attachments),
    )


def folder_paths_match(left: Any, right: Any) -> bool:
    left_path = str(safe_get(left, "FolderPath", "") or "").strip().lower()
    right_path = str(safe_get(right, "FolderPath", "") or "").strip().lower()
    return bool(left_path and right_path and left_path == right_path)


def set_draft_body(item: Any, body: str) -> str:
    item.Body = body
    item.HTMLBody = f"<html><body>{text_to_html_fragment(body)}</body></html>"
    return "html_and_plain"


def edit_draft(
    session: Any,
    *,
    account_selector: str,
    message_id: str,
    body: str | None = None,
    subject: str | None = None,
    to: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
    attachments: Iterable[str] | None = None,
    confirm: bool,
) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Editing a draft requires --confirm.")
    if not any(value is not None for value in (body, subject, to, cc, bcc)) and not list(attachments or []):
        raise ValueError("Editing a draft requires at least one field to update.")
    if body is not None and not body.strip():
        raise ValueError("Editing a draft body requires --body with non-empty final draft text.")
    draft_attachments = prepare_draft_attachments(attachments)

    account_info = resolve_account(session, account_selector)
    item = resolve_message(session, account_info, message_id)
    drafts_folder = account_info["store"].GetDefaultFolder(OL_FOLDER_DRAFTS)
    parent_folder = safe_get(item, "Parent")
    if not folder_paths_match(parent_folder, drafts_folder):
        raise ValueError("Message is not in the selected account's Drafts folder; refusing to edit it as a draft.")

    body_format = None
    if body is not None:
        body_format = set_draft_body(item, body)
    if subject is not None:
        item.Subject = subject
    recipient_summary = apply_recipient_fields(item, to=to, cc=cc, bcc=bcc)
    attach_draft_files(item, draft_attachments)
    item.Save()
    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "message": message_summary(item),
        "updated": True,
        "draft_edit": {
            "body_source": "body" if body is not None else "unchanged",
            "body_format": body_format or "unchanged",
            "draft_folder": folder_summary(parent_folder),
            "target_drafts_folder": folder_summary(drafts_folder),
            "draft_folder_verified": True,
            "warnings": [],
        },
        "draft_recipients": draft_recipients_summary(
            item,
            requested=recipient_summary["requested"],
            warnings=recipient_summary["warnings"],
        ),
        "draft_attachments": draft_attachments,
    }


def apply_action(
    session: Any,
    *,
    account_selector: str,
    message_id: str | None,
    action: str,
    confirm: bool,
    application: Any | None = None,
    target_folder: str | None = None,
    category: str | None = None,
    read_state: str | None = None,
    subject: str | None = None,
    to: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
    body: str | None = None,
    attachments: Iterable[str] | None = None,
) -> dict[str, Any]:
    if action in MUTATING_ACTIONS and not confirm:
        raise ValueError(f"Action {action} requires --confirm.")

    account_info = resolve_account(session, account_selector)
    if action == "create-draft":
        return {
            "account": account_info["smtp_address"],
            "store": account_info["delivery_store"],
            **create_generic_draft(
                application,
                account_info,
                subject=subject,
                to=to,
                cc=cc,
                bcc=bcc,
                body=body,
                attachments=attachments,
            ),
        }

    item = resolve_message(session, account_info, message_id or "")
    if action == "send":
        try:
            item.SendUsingAccount = account_info["account"]
        except Exception:
            pass
        item.Send()
        return {"account": account_info["smtp_address"], "store": account_info["delivery_store"], "sent": True}

    if action == "move":
        if not target_folder:
            raise ValueError("Move requires --target-folder.")
        folder = resolve_folder(account_info, target_folder)
        moved = item.Move(folder)
        return {
            "account": account_info["smtp_address"],
            "store": account_info["delivery_store"],
            "message": message_summary(moved),
            "target_folder": folder_summary(folder),
        }

    if action == "delete":
        item.Delete()
        return {"account": account_info["smtp_address"], "store": account_info["delivery_store"], "deleted": True}

    if action == "category":
        if not category:
            raise ValueError("Category changes require --category.")
        existing = str(safe_get(item, "Categories", "")).strip()
        updated = [value for value in (existing, category) if value]
        item.Categories = ", ".join(dict.fromkeys(updated))
        item.Save()
        return {
            "account": account_info["smtp_address"],
            "store": account_info["delivery_store"],
            "categories": item.Categories,
        }

    if action == "mark-read":
        desired_state = read_state or "read"
        item.UnRead = desired_state == "unread"
        item.Save()
        return {
            "account": account_info["smtp_address"],
            "store": account_info["delivery_store"],
            "unread": bool(item.UnRead),
        }

    raise ValueError(f"Unsupported action: {action}")


def list_folders(session: Any, *, account_selector: str) -> dict[str, Any]:
    account_info = resolve_account(session, account_selector)
    folders = [folder_summary(folder) for folder in iter_folder_tree(account_info["store"].GetRootFolder())]
    return {
        "account": account_info["smtp_address"],
        "store": account_info["delivery_store"],
        "folders": folders,
    }


def dispatch_operation(args: argparse.Namespace, *, application: Any, session: Any) -> dict[str, Any]:
    if args.operation == "blocklists":
        payload = manage_blocklists(
            action=args.action,
            profile=args.blocklist_profile,
            blocklist_cache=args.blocklist_cache,
            force=args.force,
        )
        return make_result(
            ok=True,
            operation="blocklists",
            result=payload,
        )

    if args.operation == "cache-status":
        payload = cache_status(cache_path=args.cache_path, query=args.query)
        return make_result(
            ok=True,
            operation="cache-status",
            result=payload,
        )

    if args.operation == "cache-show":
        payload = cache_show(
            cache_path=args.cache_path,
            query=args.query,
            account_selector=args.account,
            days=args.days,
            limit=args.limit,
        )
        return make_result(
            ok=True,
            operation="cache-show",
            result=payload,
        )

    if args.operation == "cache-clear":
        payload = cache_clear(cache_path=args.cache_path, query=args.query, confirm=args.confirm)
        return make_result(
            ok=True,
            operation="cache-clear",
            result=payload,
        )

    if args.operation == "cache-refresh":
        payload = cache_refresh(
            session,
            account_selector=args.account,
            all_accounts=args.all_accounts,
            days=args.days,
            force=args.force,
            cache_path=args.cache_path,
        )
        return make_result(
            ok=True,
            operation="cache-refresh",
            result=payload,
            warnings=payload.get("warnings", []),
        )

    if args.operation == "sync-mail":
        payload = sync_mail(
            application,
            session,
            refresh_cache=args.refresh_cache,
            account_selector=args.account,
            all_accounts=args.all_accounts,
            days=args.days,
            force=args.force,
            cache_path=args.cache_path,
        )
        return make_result(
            ok=bool(payload.get("attempted")),
            operation="sync-mail",
            result=payload,
            warnings=payload.get("warnings", []),
            exit_code=0 if payload.get("attempted") else 1,
        )

    if args.operation == "accounts":
        return make_result(
            ok=True,
            operation="accounts",
            result={"accounts": collect_accounts(session)},
        )

    if args.operation == "folders":
        payload = list_folders(session, account_selector=args.account)
        return make_result(
            ok=True,
            operation="folders",
            account=payload["account"],
            store=payload["store"],
            result={"folders": payload["folders"]},
        )

    if args.operation == "find-folders":
        payload = find_folders(
            session,
            query=args.query,
            account_selector=args.account,
            all_accounts=args.all_accounts,
            limit=args.limit,
        )
        return make_result(
            ok=True,
            operation="find-folders",
            result=payload,
        )

    if args.operation == "search":
        if args.all_folders:
            if not args.query:
                raise ValueError("All-folder search requires --query.")
            payload = search_all_folders(
                session,
                account_selector=args.account,
                all_accounts=args.all_accounts,
                query=args.query,
                unread=args.unread,
                sender=args.sender,
                recipient=args.recipient,
                days=args.days,
                folder_limit=args.folder_limit,
                per_folder_limit=args.per_folder_limit,
                update_hints=not args.no_update_hints,
                use_cache=not (args.no_cache or args.bypass_cache),
                update_cache=not args.no_update_cache,
                broad_scan=args.broad_scan,
                cache_path=args.cache_path,
            )
            return make_result(
                ok=True,
                operation="search",
                result=payload,
                warnings=payload.get("warnings", []),
            )
        if not args.account:
            raise ValueError("Search requires --account unless --all-folders is used with --all-accounts.")
        payload = search_messages(
            session,
            account_selector=args.account,
            folder_selector=args.folder,
            query=args.query,
            unread=args.unread,
            sender=args.sender,
            recipient=args.recipient,
            days=args.days,
            limit=args.limit,
            cache=None if args.no_update_cache else mail_cache.MailCache(args.cache_path),
            update_cache=not args.no_update_cache,
        )
        return make_result(
            ok=True,
            operation="search",
            account=payload["account"],
            store=payload["store"],
            result={"folder": payload["folder"], "messages": payload["messages"]},
            warnings=payload.get("warnings", []),
        )

    if args.operation == "read-thread":
        payload = read_thread(
            session,
            account_selector=args.account,
            message_id=args.message_id,
        )
        return make_result(
            ok=True,
            operation="read-thread",
            account=payload["account"],
            store=payload["store"],
            result={"anchor": payload["anchor"], "messages": payload["messages"]},
        )

    if args.operation == "read-message":
        payload = read_message(
            session,
            account_selector=args.account,
            message_id=args.message_id,
            include_html=args.include_html,
        )
        return make_result(
            ok=True,
            operation="read-message",
            account=payload["account"],
            store=payload["store"],
            result={"message": payload["message"]},
        )

    if args.operation == "save-attachments":
        payload = save_attachments(
            session,
            account_selector=args.account,
            message_id=args.message_id,
            output_dir=args.output_dir,
        )
        return make_result(
            ok=True,
            operation="save-attachments",
            account=payload["account"],
            store=payload["store"],
            result=payload,
        )

    if args.operation == "inspect-domains":
        payload = inspect_domains(
            session,
            account_selector=args.account,
            message_id=args.message_id,
            with_rdap=args.with_rdap,
            young_days=args.young_days,
            rdap_cache=args.rdap_cache,
            with_blocklists=args.with_blocklists,
            blocklist_profile=args.blocklist_profile,
            blocklist_cache=args.blocklist_cache,
        )
        return make_result(
            ok=True,
            operation="inspect-domains",
            account=payload["account"],
            store=payload["store"],
            result=payload,
        )

    if args.operation == "scan-domain-refs":
        payload = scan_domain_refs(
            session,
            account_selector=args.account,
            folder_selector=args.folder,
            days=args.days,
            limit=args.limit,
            with_rdap=args.with_rdap,
            young_days=args.young_days,
            rdap_cache=args.rdap_cache,
            with_blocklists=args.with_blocklists,
            blocklist_profile=args.blocklist_profile,
            blocklist_cache=args.blocklist_cache,
        )
        return make_result(
            ok=True,
            operation="scan-domain-refs",
            account=payload["account"],
            store=payload["store"],
            result=payload,
        )

    if args.operation == "find-response":
        payload = find_response(
            session,
            account_selector=args.account,
            message_id=args.message_id,
            limit=args.limit,
            fallback_all_accounts=args.fallback_all_accounts,
            include_drafts=not args.exclude_drafts,
        )
        return make_result(
            ok=True,
            operation="find-response",
            account=payload["account"],
            store=payload["store"],
            result={
                "anchor": payload["anchor"],
                "recipient_accounts": payload["recipient_accounts"],
                "searched_folders": payload["searched_folders"],
                "messages": payload["messages"],
                "scope": payload["scope"],
            },
        )

    if args.operation == "triage":
        payload = triage_messages(
            session,
            account_selector=args.account,
            all_accounts=args.all_accounts,
            days=args.days,
            limit=args.limit,
        )
        return make_result(
            ok=True,
            operation="triage",
            result=payload,
        )

    if args.operation == "draft-reply":
        payload = draft_reply(
            session,
            account_selector=args.account,
            send_using_account_selector=args.send_using_account,
            message_id=args.message_id,
            instruction=args.instruction,
            body=args.body,
            create_draft=args.create_draft,
            confirm=args.confirm,
            attachments=args.attach,
            reply_mode=args.reply_mode,
            to=args.to,
            cc=args.cc,
            bcc=args.bcc,
        )
        return make_result(
            ok=True,
            operation="draft-reply",
            account=payload["account"],
            store=payload["store"],
            result=payload,
        )

    if args.operation == "draft-forward":
        payload = draft_forward(
            session,
            account_selector=args.account,
            send_using_account_selector=args.send_using_account,
            message_id=args.message_id,
            to=args.to,
            cc=args.cc,
            bcc=args.bcc,
            instruction=args.instruction,
            body=args.body,
            create_draft=args.create_draft,
            confirm=args.confirm,
            attachments=args.attach,
        )
        return make_result(
            ok=True,
            operation="draft-forward",
            account=payload["account"],
            store=payload["store"],
            result=payload,
        )

    if args.operation == "move-message":
        payload = move_message(
            session,
            account_selector=args.account,
            message_id=args.message_id,
            target_folder=args.target_folder,
            confirm=args.confirm,
        )
        return make_result(
            ok=True,
            operation="move-message",
            account=payload["account"],
            store=payload["store"],
            result=payload,
        )

    if args.operation == "edit-draft":
        payload = edit_draft(
            session,
            account_selector=args.account,
            message_id=args.message_id,
            body=args.body,
            subject=args.subject,
            to=args.to,
            cc=args.cc,
            bcc=args.bcc,
            attachments=args.attach,
            confirm=args.confirm,
        )
        return make_result(
            ok=True,
            operation="edit-draft",
            account=payload["account"],
            store=payload["store"],
            result=payload,
        )

    payload = apply_action(
        session,
        account_selector=args.account,
        message_id=args.message_id,
        action=args.action,
        confirm=args.confirm,
        application=application,
        target_folder=args.target_folder,
        category=args.category,
        read_state=args.read_state,
        subject=args.subject,
        to=args.to,
        cc=args.cc,
        bcc=args.bcc,
        body=args.body,
        attachments=args.attach,
    )
    return make_result(
        ok=True,
        operation="apply-action",
        account=payload.get("account"),
        store=payload.get("store"),
        result=payload,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone Outlook Classic COM client for local mailbox workflows."
    )
    parser.add_argument(
        "--queue-timeout-sec",
        type=int,
        default=DEFAULT_QUEUE_TIMEOUT_SEC,
        help="Maximum time to wait in the local Outlook FIFO queue before failing.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    subparsers.add_parser("accounts", help="List configured Outlook accounts.")

    blocklists_parser = subparsers.add_parser("blocklists", help="Inspect or refresh local DNS blocklist cache.")
    blocklists_parser.add_argument("action", choices=("status", "refresh"))
    blocklists_parser.add_argument("--blocklist-profile", choices=("threat", "debug-all"), default="threat")
    blocklists_parser.add_argument("--blocklist-cache")
    blocklists_parser.add_argument("--force", action="store_true")

    cache_status_parser = subparsers.add_parser("cache-status", help="Inspect the local Outlook metadata cache.")
    cache_status_parser.add_argument("--query")
    cache_status_parser.add_argument("--cache-path")

    cache_show_parser = subparsers.add_parser("cache-show", help="Show cache hits for a contact or subject query.")
    cache_show_parser.add_argument("--query", required=True)
    cache_show_parser.add_argument("--account")
    cache_show_parser.add_argument("--days", type=int)
    cache_show_parser.add_argument("--limit", type=int, default=25)
    cache_show_parser.add_argument("--cache-path")

    cache_refresh_parser = subparsers.add_parser(
        "cache-refresh",
        help="Refresh recent Outlook metadata into the local cache.",
    )
    cache_refresh_parser.add_argument("--account")
    cache_refresh_parser.add_argument("--all-accounts", action="store_true")
    cache_refresh_parser.add_argument("--days", type=int, default=90)
    cache_refresh_parser.add_argument("--force", action="store_true")
    cache_refresh_parser.add_argument("--cache-path")

    cache_clear_parser = subparsers.add_parser("cache-clear", help="Clear local Outlook metadata cache entries.")
    cache_clear_parser.add_argument("--query")
    cache_clear_parser.add_argument("--confirm", action="store_true")
    cache_clear_parser.add_argument("--cache-path")

    sync_mail_parser = subparsers.add_parser("sync-mail", help="Trigger Outlook Send/Receive All Folders.")
    sync_mail_parser.add_argument("--refresh-cache", action="store_true")
    sync_mail_parser.add_argument("--account")
    sync_mail_parser.add_argument("--all-accounts", action="store_true")
    sync_mail_parser.add_argument("--days", type=int, default=90)
    sync_mail_parser.add_argument("--force", action="store_true")
    sync_mail_parser.add_argument("--cache-path")

    subparsers.add_parser("diagnostics-probe", help="Probe Outlook COM availability and write diagnostic metadata.")

    diagnostics_log = subparsers.add_parser("diagnostics-log", help="Show recent local Outlook COM diagnostic events.")
    diagnostics_log.add_argument("--limit", type=int, default=20)

    folders = subparsers.add_parser("folders", help="List folders for an Outlook account.")
    folders.add_argument("--account", required=True)

    find_folders_parser = subparsers.add_parser("find-folders", help="Find folders by name or path.")
    find_folders_parser.add_argument("--query", required=True)
    find_folders_parser.add_argument("--account")
    find_folders_parser.add_argument("--all-accounts", action="store_true")
    find_folders_parser.add_argument("--limit", type=int, default=20)

    search = subparsers.add_parser("search", help="Search mail in one Outlook account and folder.")
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

    read_thread = subparsers.add_parser("read-thread", help="Read a thread anchored by one message ID.")
    read_thread.add_argument("--account", required=True)
    read_thread.add_argument("--message-id", required=True)

    read_message_parser = subparsers.add_parser("read-message", help="Read one message body and attachment metadata.")
    read_message_parser.add_argument("--account", required=True)
    read_message_parser.add_argument("--message-id", required=True)
    read_message_parser.add_argument("--include-html", action="store_true")

    save_attachments_parser = subparsers.add_parser(
        "save-attachments",
        help="Save all attachments from one message to a local directory.",
    )
    save_attachments_parser.add_argument("--account", required=True)
    save_attachments_parser.add_argument("--message-id", required=True)
    save_attachments_parser.add_argument("--output-dir", required=True)

    inspect_domains_parser = subparsers.add_parser(
        "inspect-domains",
        help="Inspect domain references on one message without mutating mail.",
    )
    inspect_domains_parser.add_argument("--account", required=True)
    inspect_domains_parser.add_argument("--message-id", required=True)
    inspect_domains_parser.add_argument("--with-rdap", action="store_true")
    inspect_domains_parser.add_argument("--young-days", type=int, default=365)
    inspect_domains_parser.add_argument("--rdap-cache")
    inspect_domains_parser.add_argument("--with-blocklists", action="store_true")
    inspect_domains_parser.add_argument("--blocklist-profile", choices=("threat", "debug-all"), default="threat")
    inspect_domains_parser.add_argument("--blocklist-cache")

    scan_domain_refs_parser = subparsers.add_parser(
        "scan-domain-refs",
        help="Inspect domain references for recent messages in one folder without mutating mail.",
    )
    scan_domain_refs_parser.add_argument("--account", required=True)
    scan_domain_refs_parser.add_argument("--folder", default="inbox")
    scan_domain_refs_parser.add_argument("--days", type=int, default=7)
    scan_domain_refs_parser.add_argument("--limit", type=int, default=20)
    scan_domain_refs_parser.add_argument("--with-rdap", action="store_true")
    scan_domain_refs_parser.add_argument("--young-days", type=int, default=365)
    scan_domain_refs_parser.add_argument("--rdap-cache")
    scan_domain_refs_parser.add_argument("--with-blocklists", action="store_true")
    scan_domain_refs_parser.add_argument("--blocklist-profile", choices=("threat", "debug-all"), default="threat")
    scan_domain_refs_parser.add_argument("--blocklist-cache")

    find_response_parser = subparsers.add_parser("find-response", help="Find sent or draft responses to a message.")
    find_response_parser.add_argument("--account", required=True)
    find_response_parser.add_argument("--message-id", required=True)
    find_response_parser.add_argument("--limit", type=int, default=20)
    find_response_parser.add_argument("--fallback-all-accounts", action="store_true")
    find_response_parser.add_argument("--exclude-drafts", action="store_true")

    triage = subparsers.add_parser("triage", help="Triage one inbox or all configured inboxes.")
    triage.add_argument("--account")
    triage.add_argument("--all-accounts", action="store_true")
    triage.add_argument("--days", type=int, default=7)
    triage.add_argument("--limit", type=int, default=20)

    draft_reply_parser = subparsers.add_parser("draft-reply", help="Preview or create a reply draft.")
    draft_reply_parser.add_argument("--account", required=True)
    draft_reply_parser.add_argument("--message-id", required=True)
    draft_reply_parser.add_argument("--instruction", required=True)
    draft_reply_parser.add_argument("--body")
    draft_reply_parser.add_argument("--reply-mode", choices=("sender", "all"), default="sender")
    draft_reply_parser.add_argument("--to")
    draft_reply_parser.add_argument("--cc")
    draft_reply_parser.add_argument("--bcc")
    draft_reply_parser.add_argument("--attach", action="append", default=[])
    draft_reply_parser.add_argument("--send-using-account")
    draft_reply_parser.add_argument("--create-draft", action="store_true")
    draft_reply_parser.add_argument("--confirm", action="store_true")

    draft_forward_parser = subparsers.add_parser("draft-forward", help="Preview or create a forward draft.")
    draft_forward_parser.add_argument("--account", required=True)
    draft_forward_parser.add_argument("--message-id", required=True)
    draft_forward_parser.add_argument("--to", required=True)
    draft_forward_parser.add_argument("--cc")
    draft_forward_parser.add_argument("--bcc")
    draft_forward_parser.add_argument("--instruction", required=True)
    draft_forward_parser.add_argument("--body")
    draft_forward_parser.add_argument("--attach", action="append", default=[])
    draft_forward_parser.add_argument("--send-using-account")
    draft_forward_parser.add_argument("--create-draft", action="store_true")
    draft_forward_parser.add_argument("--confirm", action="store_true")

    move_message_parser = subparsers.add_parser("move-message", help="Preview or move a message to a folder.")
    move_message_parser.add_argument("--account", required=True)
    move_message_parser.add_argument("--message-id", required=True)
    move_message_parser.add_argument("--target-folder", required=True)
    move_message_parser.add_argument("--confirm", action="store_true")

    edit_draft_parser = subparsers.add_parser("edit-draft", help="Replace the body of an existing draft.")
    edit_draft_parser.add_argument("--account", required=True)
    edit_draft_parser.add_argument("--message-id", required=True)
    edit_draft_parser.add_argument("--body")
    edit_draft_parser.add_argument("--subject")
    edit_draft_parser.add_argument("--to")
    edit_draft_parser.add_argument("--cc")
    edit_draft_parser.add_argument("--bcc")
    edit_draft_parser.add_argument("--attach", action="append", default=[])
    edit_draft_parser.add_argument("--confirm", action="store_true")

    apply_action = subparsers.add_parser("apply-action", help="Apply an explicit mailbox action.")
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
    apply_action.add_argument("--cc")
    apply_action.add_argument("--bcc")
    apply_action.add_argument("--body")
    apply_action.add_argument("--attach", action="append", default=[])

    return parser
