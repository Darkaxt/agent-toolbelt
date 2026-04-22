from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME_ENV = "OBSERVABLE_REPUTATION_HOME"


def default_state_dir() -> Path:
    env_home = os.getenv(HOME_ENV)
    if env_home:
        return Path(env_home).expanduser().resolve() / "state"
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "agent-toolbelt" / "observable-reputation" / "state"
    return Path.home() / ".local" / "state" / "agent-toolbelt" / "observable-reputation"


DEFAULT_CACHE_PATH = default_state_dir() / "reputation_cache.sqlite"


class ReputationCache:
    def __init__(self, path: Path | None = None, *, ttl_seconds: int = 86400):
        self.path = path or DEFAULT_CACHE_PATH
        self.ttl_seconds = ttl_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reputation_cache (
                        cache_key TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        fetched_at TEXT NOT NULL
                    )
                    """
                )

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payload, fetched_at FROM reputation_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        fetched_at = datetime.fromisoformat(row[1])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - fetched_at).total_seconds() > self.ttl_seconds:
            return None
        return json.loads(row[0])

    def set(self, cache_key: str, payload: dict[str, Any]) -> None:
        fetched_at = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO reputation_cache(cache_key, payload, fetched_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        payload = excluded.payload,
                        fetched_at = excluded.fetched_at
                    """,
                    (cache_key, json.dumps(payload, sort_keys=True), fetched_at),
                )
