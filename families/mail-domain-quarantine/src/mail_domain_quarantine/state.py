from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME_ENV = "MAIL_DOMAIN_QUARANTINE_HOME"


def default_home_dir() -> Path:
    env_home = os.getenv(HOME_ENV)
    if env_home:
        return Path(env_home).expanduser().resolve()
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "agent-toolbelt" / "mail-domain-quarantine"
    return Path.home() / ".local" / "state" / "agent-toolbelt" / "mail-domain-quarantine"


HOME_DIR = default_home_dir()
STATE_DIR = HOME_DIR / "state"
REPORT_DIR = HOME_DIR / "reports"
DOMAIN_CACHE_PATH = STATE_DIR / "domain_cache.sqlite"
BLOCKLIST_CACHE_PATH = STATE_DIR / "blocklist_cache.sqlite"

DEFAULT_BLOCKLIST_SUPPRESSIONS = {
    "exacttarget.com": "shared mail/marketing infrastructure",
    "exct.net": "shared mail/marketing infrastructure",
    "salesforce.com": "shared mail/marketing infrastructure",
    "returnpath.net": "shared mail/marketing infrastructure",
    "awstrack.me": "shared mail/marketing infrastructure",
}


def ensure_state() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(STATE_DIR / "trust.sqlite")) as conn:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS domain_trust (
                    domain TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS blocklist_suppression (
                    domain TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            updated_at = datetime.now(timezone.utc).isoformat()
            conn.executemany(
                """
                INSERT OR IGNORE INTO blocklist_suppression(domain, reason, updated_at)
                VALUES (?, ?, ?)
                """,
                [
                    (domain, reason, updated_at)
                    for domain, reason in sorted(DEFAULT_BLOCKLIST_SUPPRESSIONS.items())
                ],
            )
    with closing(sqlite3.connect(STATE_DIR / "quarantine_ledger.sqlite")) as conn:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quarantine_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account TEXT NOT NULL,
                    message_entry_id TEXT NOT NULL,
                    internet_message_id TEXT,
                    original_folder TEXT,
                    quarantine_folder TEXT NOT NULL,
                    sender TEXT,
                    subject TEXT,
                    domains_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    moved_at TEXT NOT NULL
                )
                """
            )


def load_trusted_domains() -> set[str]:
    ensure_state()
    with closing(sqlite3.connect(STATE_DIR / "trust.sqlite")) as conn:
        rows = conn.execute(
            "SELECT domain FROM domain_trust WHERE decision IN ('trusted', 'ignored')"
        ).fetchall()
    return {str(row[0]).lower() for row in rows}


def load_blocklist_suppressions() -> dict[str, str]:
    ensure_state()
    with closing(sqlite3.connect(STATE_DIR / "trust.sqlite")) as conn:
        rows = conn.execute(
            "SELECT domain, reason FROM blocklist_suppression"
        ).fetchall()
    return {str(row[0]).strip(".").lower(): str(row[1]) for row in rows if row[0]}


def write_ledger_entry(
    *,
    account: str,
    message: dict[str, Any],
    quarantine_folder: str,
    domains: list[str],
    reason: str,
) -> None:
    ensure_state()
    moved_at = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(STATE_DIR / "quarantine_ledger.sqlite")) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO quarantine_ledger(
                    account,
                    message_entry_id,
                    internet_message_id,
                    original_folder,
                    quarantine_folder,
                    sender,
                    subject,
                    domains_json,
                    reason,
                    moved_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account,
                    message.get("entry_id", ""),
                    message.get("internet_message_id"),
                    message.get("folder_path"),
                    quarantine_folder,
                    message.get("sender_email"),
                    message.get("subject"),
                    json.dumps(domains, sort_keys=True),
                    reason,
                    moved_at,
                ),
            )
