from __future__ import annotations

import contextlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


STATE_DIR = Path(__file__).resolve().parents[2] / "state"
DEFAULT_CACHE_PATH = STATE_DIR / "mail_cache.sqlite"
SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def normalize_query(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def clean_text(value: Any) -> str:
    text = str(value or "")
    return text.encode("utf-8", "replace").decode("utf-8")


def sql_like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def fts_query(value: str) -> str:
    tokens = [token.replace('"', '""') for token in normalize_query(value).split() if token]
    return " AND ".join(f'"{token}"' for token in tokens)


class MailCache:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DEFAULT_CACHE_PATH

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextlib.contextmanager
    def connection(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    account TEXT NOT NULL,
                    store TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    folder_selector TEXT NOT NULL,
                    folder_path TEXT NOT NULL,
                    entry_id TEXT NOT NULL,
                    internet_message_id TEXT,
                    conversation_id TEXT,
                    conversation_topic TEXT,
                    subject TEXT,
                    sender_name TEXT,
                    sender_email TEXT,
                    to_text TEXT,
                    cc_text TEXT,
                    received_time TEXT,
                    sent_time TEXT,
                    last_modified_time TEXT,
                    message_date TEXT,
                    unread INTEGER NOT NULL DEFAULT 0,
                    categories TEXT,
                    has_attachments INTEGER NOT NULL DEFAULT 0,
                    cached_at TEXT NOT NULL,
                    UNIQUE(store_id, entry_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(message_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_folder ON messages(store_id, folder_selector)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_email, sender_name)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS folder_state (
                    store_id TEXT NOT NULL,
                    account TEXT NOT NULL,
                    store TEXT NOT NULL,
                    folder_selector TEXT NOT NULL,
                    folder_path TEXT NOT NULL,
                    high_watermark TEXT,
                    refreshed_at TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(store_id, folder_selector)
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    subject,
                    conversation_topic,
                    sender_name,
                    sender_email,
                    to_text,
                    cc_text
                )
                """
            )
            conn.execute(
                """
                INSERT INTO cache_meta(key, value)
                VALUES('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(SCHEMA_VERSION),),
            )

    def upsert_message(self, record: dict[str, Any]) -> None:
        self.ensure_schema()
        values = {
            "account": clean_text(record.get("account")),
            "store": clean_text(record.get("store")),
            "store_id": clean_text(record.get("store_id")),
            "folder_selector": clean_text(record.get("folder_selector")),
            "folder_path": clean_text(record.get("folder_path")),
            "entry_id": clean_text(record.get("entry_id")),
            "internet_message_id": clean_text(record.get("internet_message_id")),
            "conversation_id": clean_text(record.get("conversation_id")),
            "conversation_topic": clean_text(record.get("conversation_topic")),
            "subject": clean_text(record.get("subject")),
            "sender_name": clean_text(record.get("sender_name")),
            "sender_email": clean_text(record.get("sender_email")),
            "to_text": clean_text(record.get("to_text")),
            "cc_text": clean_text(record.get("cc_text")),
            "received_time": clean_text(record.get("received_time")),
            "sent_time": clean_text(record.get("sent_time")),
            "last_modified_time": clean_text(record.get("last_modified_time")),
            "message_date": clean_text(record.get("message_date")),
            "unread": 1 if record.get("unread") else 0,
            "categories": clean_text(record.get("categories")),
            "has_attachments": 1 if record.get("has_attachments") else 0,
            "cached_at": clean_text(record.get("cached_at") or utc_now_iso()),
        }
        if not values["store_id"] or not values["entry_id"]:
            return

        columns = list(values)
        placeholders = ", ".join(f":{name}" for name in columns)
        update_columns = [name for name in columns if name not in {"store_id", "entry_id"}]
        updates = ", ".join(f"{name}=excluded.{name}" for name in update_columns)
        with self.connection() as conn:
            cur = conn.execute(
                f"""
                INSERT INTO messages({", ".join(columns)})
                VALUES({placeholders})
                ON CONFLICT(store_id, entry_id) DO UPDATE SET {updates}
                RETURNING id
                """,
                values,
            )
            row_id = int(cur.fetchone()["id"])
            conn.execute("DELETE FROM messages_fts WHERE rowid = ?", (row_id,))
            conn.execute(
                """
                INSERT INTO messages_fts(
                    rowid, subject, conversation_topic, sender_name, sender_email, to_text, cc_text
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    values["subject"],
                    values["conversation_topic"],
                    values["sender_name"],
                    values["sender_email"],
                    values["to_text"],
                    values["cc_text"],
                ),
            )

    def update_folder_state(self, record: dict[str, Any]) -> None:
        self.ensure_schema()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO folder_state(
                    store_id, account, store, folder_selector, folder_path, high_watermark, refreshed_at, message_count
                )
                VALUES(:store_id, :account, :store, :folder_selector, :folder_path, :high_watermark, :refreshed_at, :message_count)
                ON CONFLICT(store_id, folder_selector) DO UPDATE SET
                    account=excluded.account,
                    store=excluded.store,
                    folder_path=excluded.folder_path,
                    high_watermark=excluded.high_watermark,
                    refreshed_at=excluded.refreshed_at,
                    message_count=excluded.message_count
                """,
                {
                    "store_id": record.get("store_id") or "",
                    "account": record.get("account") or "",
                    "store": record.get("store") or "",
                    "folder_selector": record.get("folder_selector") or "",
                    "folder_path": record.get("folder_path") or "",
                    "high_watermark": record.get("high_watermark") or "",
                    "refreshed_at": record.get("refreshed_at") or utc_now_iso(),
                    "message_count": int(record.get("message_count") or 0),
                },
            )

    def folder_high_watermark(self, store_id: str, folder_selector: str) -> str | None:
        self.ensure_schema()
        with self.connection() as conn:
            row = conn.execute(
                "SELECT high_watermark FROM folder_state WHERE store_id = ? AND folder_selector = ?",
                (store_id, folder_selector),
            ).fetchone()
        return str(row["high_watermark"]) if row and row["high_watermark"] else None

    def prune(self, *, days: int) -> int:
        self.ensure_schema()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.connection() as conn:
            rows = conn.execute("SELECT id FROM messages WHERE message_date < ?", (cutoff,)).fetchall()
            ids = [int(row["id"]) for row in rows]
            for row_id in ids:
                conn.execute("DELETE FROM messages_fts WHERE rowid = ?", (row_id,))
            conn.execute("DELETE FROM messages WHERE message_date < ?", (cutoff,))
        return len(ids)

    def search(
        self,
        *,
        query: str | None,
        sender: str | None,
        recipient: str | None,
        unread: bool,
        days: int | None,
        account: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        where: list[str] = []
        params: list[Any] = []
        joins = ""
        normalized_query = normalize_query(query)
        if normalized_query:
            match = fts_query(normalized_query)
            if match:
                joins = "JOIN messages_fts ON messages_fts.rowid = messages.id"
                where.append("messages_fts MATCH ?")
                params.append(match)
        if sender:
            where.append("(lower(sender_name) LIKE ? ESCAPE '\\' OR lower(sender_email) LIKE ? ESCAPE '\\')")
            value = sql_like(sender.lower())
            params.extend([value, value])
        if recipient:
            where.append("(lower(to_text) LIKE ? ESCAPE '\\' OR lower(cc_text) LIKE ? ESCAPE '\\')")
            value = sql_like(recipient.lower())
            params.extend([value, value])
        if unread:
            where.append("unread = 1")
        if account:
            where.append("(lower(account) = ? OR lower(store) = ?)")
            params.extend([account.lower(), account.lower()])
        if days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            where.append("message_date >= ?")
            params.append(cutoff)
        sql = f"SELECT messages.* FROM messages {joins}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY message_date DESC LIMIT ?"
        params.append(limit)
        try:
            with self.connection() as conn:
                return [dict(row) for row in conn.execute(sql, params).fetchall()]
        except sqlite3.OperationalError:
            if not normalized_query:
                raise
            return self._search_like(
                query=query,
                sender=sender,
                recipient=recipient,
                unread=unread,
                days=days,
                account=account,
                limit=limit,
            )

    def _search_like(
        self,
        *,
        query: str | None,
        sender: str | None,
        recipient: str | None,
        unread: bool,
        days: int | None,
        account: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if query:
            value = sql_like(query.lower())
            where.append(
                "(lower(subject) LIKE ? ESCAPE '\\' OR lower(conversation_topic) LIKE ? ESCAPE '\\' "
                "OR lower(sender_name) LIKE ? ESCAPE '\\' OR lower(sender_email) LIKE ? ESCAPE '\\' "
                "OR lower(to_text) LIKE ? ESCAPE '\\' OR lower(cc_text) LIKE ? ESCAPE '\\')"
            )
            params.extend([value] * 6)
        if sender:
            value = sql_like(sender.lower())
            where.append("(lower(sender_name) LIKE ? ESCAPE '\\' OR lower(sender_email) LIKE ? ESCAPE '\\')")
            params.extend([value, value])
        if recipient:
            value = sql_like(recipient.lower())
            where.append("(lower(to_text) LIKE ? ESCAPE '\\' OR lower(cc_text) LIKE ? ESCAPE '\\')")
            params.extend([value, value])
        if unread:
            where.append("unread = 1")
        if account:
            where.append("(lower(account) = ? OR lower(store) = ?)")
            params.extend([account.lower(), account.lower()])
        if days:
            cutoff = (datetime.utcnow() - timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"
            where.append("message_date >= ?")
            params.append(cutoff)
        sql = "SELECT * FROM messages"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY message_date DESC LIMIT ?"
        params.append(limit)
        with self.connection() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def candidate_folders(self, rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            key = (str(row.get("store_id") or ""), str(row.get("folder_selector") or ""))
            entry = grouped.setdefault(
                key,
                {
                    "account": row.get("account") or "",
                    "store": row.get("store") or "",
                    "store_id": row.get("store_id") or "",
                    "folder_selector": row.get("folder_selector") or "",
                    "folder_path": row.get("folder_path") or "",
                    "source": "mail-cache",
                    "hit_count": 0,
                    "latest_message_date": "",
                },
            )
            entry["hit_count"] += 1
            if str(row.get("message_date") or "") > str(entry.get("latest_message_date") or ""):
                entry["latest_message_date"] = row.get("message_date") or ""
        return sorted(
            grouped.values(),
            key=lambda item: (int(item["hit_count"]), str(item["latest_message_date"])),
            reverse=True,
        )[:limit]

    def status(self, *, query: str | None = None) -> dict[str, Any]:
        self.ensure_schema()
        with self.connection() as conn:
            message_count = int(conn.execute("SELECT COUNT(*) AS count FROM messages").fetchone()["count"])
            folder_count = int(conn.execute("SELECT COUNT(*) AS count FROM folder_state").fetchone()["count"])
            date_row = conn.execute(
                "SELECT MIN(message_date) AS oldest, MAX(message_date) AS latest, MAX(cached_at) AS cached_at FROM messages"
            ).fetchone()
            result: dict[str, Any] = {
                "path": str(self.path),
                "message_count": message_count,
                "folder_count": folder_count,
                "oldest_message_date": date_row["oldest"] if date_row else "",
                "latest_message_date": date_row["latest"] if date_row else "",
                "last_cached_at": date_row["cached_at"] if date_row else "",
            }
            if query:
                matches = self.search(
                    query=query,
                    sender=None,
                    recipient=None,
                    unread=False,
                    days=None,
                    account=None,
                    limit=25,
                )
                result["query"] = query
                result["query_match_count"] = len(matches)
                result["candidate_folders"] = self.candidate_folders(matches, limit=10)
            return result

    def clear(self, *, query: str | None = None) -> dict[str, Any]:
        self.ensure_schema()
        if query:
            rows = self.search(
                query=query,
                sender=None,
                recipient=None,
                unread=False,
                days=None,
                account=None,
                limit=100000,
            )
            ids = [int(row["id"]) for row in rows]
            with self.connection() as conn:
                for row_id in ids:
                    conn.execute("DELETE FROM messages_fts WHERE rowid = ?", (row_id,))
                    conn.execute("DELETE FROM messages WHERE id = ?", (row_id,))
            return {"cleared_messages": len(ids), "query": query}
        with self.connection() as conn:
            message_count = int(conn.execute("SELECT COUNT(*) AS count FROM messages").fetchone()["count"])
            conn.execute("DELETE FROM messages_fts")
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM folder_state")
        return {"cleared_messages": message_count, "query": None}
