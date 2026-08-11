from __future__ import annotations

import contextlib
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterator


STATE_DIR = Path(__file__).resolve().parents[2] / "state"
DEFAULT_QUEUE_PATH = STATE_DIR / "outlook_queue.sqlite"
DEFAULT_QUEUE_TIMEOUT_SEC = 900
DEFAULT_QUEUE_POLL_SEC = 1.0
DEFAULT_QUEUE_LEASE_SEC = 3600
RETRY_DELAYS = (0.1, 0.3, 0.7)


class QueueTimeoutError(RuntimeError):
    def __init__(self, message: str, metadata: dict[str, Any] | None = None):
        super().__init__(message)
        self.metadata = metadata or {}


def pid_is_running(pid: int) -> bool | None:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            still_active = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
            if not handle:
                error = kernel32.GetLastError()
                return False if error == 87 else None
            try:
                exit_code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return None
                return int(exit_code.value) == still_active
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    except OSError:
        return None
    return True


def is_retryable_state_error(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        return any(
            token in text
            for token in (
                "database is locked",
                "database is busy",
                "readonly",
                "unable to open database file",
            )
        )
    if isinstance(exc, OSError):
        errno = getattr(exc, "errno", None)
        winerror = getattr(exc, "winerror", None)
        return errno in {13, 16, 32, 33} or winerror in {5, 32, 33}
    return False


def run_with_state_retries(
    func: Callable[[], Any],
    *,
    sleep_func: Callable[[float], None] = time.sleep,
    retry_delays: tuple[float, ...] = RETRY_DELAYS,
) -> Any:
    attempts = len(retry_delays) + 1
    for index in range(attempts):
        try:
            return func()
        except BaseException as exc:
            if index >= len(retry_delays) or not is_retryable_state_error(exc):
                raise
            sleep_func(retry_delays[index])
    raise RuntimeError("unreachable")


class QueueStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DEFAULT_QUEUE_PATH

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=1.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextlib.contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
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
                CREATE TABLE IF NOT EXISTS queue_tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pid INTEGER NOT NULL,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    lease_expires_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_tickets_status_ticket ON queue_tickets(status, ticket_id)"
            )

    def prune_stale(
        self,
        *,
        now: float | None = None,
        pid_is_running_func: Callable[[int], bool | None] = pid_is_running,
    ) -> dict[str, int]:
        current = time.time() if now is None else now
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT ticket_id, pid, lease_expires_at FROM queue_tickets"
            ).fetchall()
            expired_ids = [int(row["ticket_id"]) for row in rows if float(row["lease_expires_at"]) < current]
            dead_ids = [
                int(row["ticket_id"])
                for row in rows
                if int(row["ticket_id"]) not in expired_ids
                and pid_is_running_func(int(row["pid"])) is False
            ]
            delete_ids = expired_ids + dead_ids
            if delete_ids:
                placeholders = ",".join("?" for _ in delete_ids)
                conn.execute(
                    f"DELETE FROM queue_tickets WHERE ticket_id IN ({placeholders})",
                    delete_ids,
                )
            return {
                "expired": len(expired_ids),
                "dead": len(dead_ids),
            }

    def enqueue(
        self,
        *,
        operation: str,
        pid: int | None = None,
        now: float | None = None,
        lease_sec: int = DEFAULT_QUEUE_LEASE_SEC,
    ) -> dict[str, Any]:
        current = time.time() if now is None else now
        process_id = pid if pid is not None else os.getpid()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO queue_tickets(pid, operation, status, created_at, updated_at, lease_expires_at)
                VALUES(?, ?, 'pending', ?, ?, ?)
                """,
                (process_id, operation, current, current, current + lease_sec),
            )
            ticket_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            row = conn.execute(
                """
                SELECT
                    (
                        SELECT COUNT(*) FROM queue_tickets active
                        WHERE active.ticket_id <= current.ticket_id
                    ) AS position_at_enqueue,
                    (
                        SELECT COUNT(*) FROM queue_tickets active
                    ) AS depth_at_enqueue
                FROM queue_tickets current
                WHERE current.ticket_id = ?
                """,
                (ticket_id,),
            ).fetchone()
        return {
            "ticket_id": ticket_id,
            "position_at_enqueue": int(row["position_at_enqueue"]),
            "depth_at_enqueue": int(row["depth_at_enqueue"]),
        }

    def claim_turn(
        self,
        *,
        ticket_id: int,
        now: float | None = None,
        lease_sec: int = DEFAULT_QUEUE_LEASE_SEC,
    ) -> bool:
        current = time.time() if now is None else now
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE queue_tickets
                SET status = 'running',
                    updated_at = ?,
                    lease_expires_at = ?
                WHERE ticket_id = ?
                  AND ticket_id = (
                      SELECT ticket_id
                      FROM queue_tickets
                      WHERE status IN ('pending', 'running')
                      ORDER BY ticket_id
                      LIMIT 1
                  )
                """,
                (current, current + lease_sec, ticket_id),
            )
            return bool(cursor.rowcount)

    def complete(self, *, ticket_id: int) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM queue_tickets WHERE ticket_id = ?", (ticket_id,))


@contextlib.contextmanager
def acquire_queue_turn(
    operation: str,
    *,
    path: Path | str | None = None,
    timeout_sec: float = DEFAULT_QUEUE_TIMEOUT_SEC,
    poll_interval_sec: float = DEFAULT_QUEUE_POLL_SEC,
    lease_sec: int = DEFAULT_QUEUE_LEASE_SEC,
    pid: int | None = None,
    monotonic_func: Callable[[], float] = time.monotonic,
    wall_time_func: Callable[[], float] = time.time,
    sleep_func: Callable[[float], None] = time.sleep,
    pid_is_running_func: Callable[[int], bool | None] = pid_is_running,
) -> Iterator[dict[str, Any]]:
    store = QueueStore(path)
    run_with_state_retries(store.ensure_schema, sleep_func=sleep_func)
    reclaimed = run_with_state_retries(
        lambda: store.prune_stale(
            now=wall_time_func(),
            pid_is_running_func=pid_is_running_func,
        ),
        sleep_func=sleep_func,
    )
    reclaimed_dead = int(reclaimed["dead"])
    reclaimed_expired = int(reclaimed["expired"])
    ticket = run_with_state_retries(
        lambda: store.enqueue(operation=operation, pid=pid, now=wall_time_func(), lease_sec=lease_sec),
        sleep_func=sleep_func,
    )

    start = monotonic_func()
    try:
        while True:
            claimed = run_with_state_retries(
                lambda: store.claim_turn(ticket_id=ticket["ticket_id"], now=wall_time_func(), lease_sec=lease_sec),
                sleep_func=sleep_func,
            )
            if claimed:
                waited_seconds = round(max(0.0, monotonic_func() - start), 3)
                metadata = {
                    "used": True,
                    "waited_seconds": waited_seconds,
                    "position_at_enqueue": ticket["position_at_enqueue"],
                    "depth_at_enqueue": ticket["depth_at_enqueue"],
                    "timeout_seconds": timeout_sec,
                    "reclaimed_dead_tickets": reclaimed_dead,
                    "reclaimed_expired_tickets": reclaimed_expired,
                }
                try:
                    yield metadata
                finally:
                    with contextlib.suppress(Exception):
                        run_with_state_retries(
                            lambda: store.complete(ticket_id=ticket["ticket_id"]),
                            sleep_func=sleep_func,
                        )
                return

            waited = monotonic_func() - start
            if waited >= timeout_sec:
                metadata = {
                    "used": True,
                    "waited_seconds": round(max(0.0, waited), 3),
                    "position_at_enqueue": ticket["position_at_enqueue"],
                    "depth_at_enqueue": ticket["depth_at_enqueue"],
                    "timeout_seconds": timeout_sec,
                    "reclaimed_dead_tickets": reclaimed_dead,
                    "reclaimed_expired_tickets": reclaimed_expired,
                }
                with contextlib.suppress(Exception):
                    run_with_state_retries(
                        lambda: store.complete(ticket_id=ticket["ticket_id"]),
                        sleep_func=sleep_func,
                    )
                raise QueueTimeoutError(
                    f"Outlook queue wait exceeded {timeout_sec}s for {operation}.",
                    metadata=metadata,
                )

            sleep_func(poll_interval_sec)
            reclaimed = run_with_state_retries(
                lambda: store.prune_stale(
                    now=wall_time_func(),
                    pid_is_running_func=pid_is_running_func,
                ),
                sleep_func=sleep_func,
            )
            reclaimed_dead += int(reclaimed["dead"])
            reclaimed_expired += int(reclaimed["expired"])
    except Exception:
        raise
