from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


FILE_EXTENSION_PATTERN = "py|md|json|yaml|yml|toml|txt|sql|sqlite|ps1|bat|exe|js|ts|tsx|jsx|go|rs|java|c|cpp|h|hpp|sh|html|css"
WINDOWS_FILE_PATH_PATTERN = re.compile(rf"(?:\\\\\?\\)?[A-Za-z]:\\[^\r\n\"']+?\.(?:{FILE_EXTENSION_PATTERN})")
UNIX_FILE_PATH_PATTERN = re.compile(rf"/[^\r\n\"']+?\.(?:{FILE_EXTENSION_PATTERN})")
RELATIVE_FILE_PATH_PATTERN = re.compile(rf"(?<![A-Za-z0-9])(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.(?:{FILE_EXTENSION_PATTERN})")
QUESTION_PATTERN = re.compile(r"[^?]+\?")
BLOCKER_TOKENS = ("permission denied", "failed", "error", "timeout", "traceback", "exception")
RETRY_TOKENS = ("retry", "retrying", "retried")
REPO_PATTERN = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b")
PR_PATTERN = re.compile(r"\bPR\s*`?#?(\d+)`?", re.IGNORECASE)
COMMIT_PATTERN = re.compile(r"\bcommit\s+`?([0-9a-f]{7,40})`?", re.IGNORECASE)
OID_PATTERN = re.compile(r'"oid"\s*:\s*"([0-9a-f]{7,40})"', re.IGNORECASE)
BACKTICK_PATTERN = re.compile(r"`([^`\r\n]{1,160})`")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._-]{2,120}$")
QUALIFIED_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$")
NOISE_TOKENS = (
    "<skills_instructions>",
    "<plugins_instructions>",
    "<environment_context>",
    "`sandbox_mode`",
    "developer message",
)
SHIP_EVENT_KINDS = {"published", "merged", "pushed", "installed"}
GENERIC_PATH_PARENT_FALLBACKS = {"__init__", "readme", "skill", "main", "index", "cli", "app", "plugin"}
ENTITY_STOPWORDS = {
    "pr",
    "commit",
    "published",
    "merged",
    "pushed",
    "installed",
    "enabled",
    "validate",
    "validated",
    "status",
}
CACHE_SCHEMA_VERSION = 2
TEXT_SCAN_LIMIT = 2000
EVIDENCE_SCAN_LIMIT = 200
RAW_TEXT_STORE_LIMIT = 16000
FACET_TABLES: dict[str, tuple[str, str]] = {
    "paths": ("entry_paths", "path"),
    "blockers": ("entry_blockers", "blocker"),
    "retry_signals": ("entry_retry_signals", "retry_signal"),
    "questions": ("entry_questions", "question"),
    "entities": ("entry_entities", "entity"),
    "repos": ("entry_repos", "repo"),
    "pr_numbers": ("entry_pr_numbers", "pr_number"),
    "commit_oids": ("entry_commit_oids", "commit_oid"),
    "qualified_ids": ("entry_qualified_ids", "qualified_id"),
    "event_kinds": ("entry_event_kinds", "event_kind"),
}


def failure(error: str, message: str, *, warnings: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": error, "message": message, "warnings": warnings or []}
    payload.update(extra)
    return payload


def default_codex_home(codex_home: str | Path | None = None) -> Path:
    if codex_home is not None:
        return Path(codex_home).expanduser()
    env_home = os.getenv("CODEX_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ("." + "codex")


def active_thread_id(thread_id: str | None = None) -> str | None:
    if thread_id:
        return thread_id
    return os.getenv("CODEX_THREAD_ID")


def state_db_path(codex_home: Path) -> Path:
    return codex_home / "state_5.sqlite"


def cache_db_path(codex_home: Path) -> Path:
    return codex_home / "cache" / "codex-thread-recall" / "index.sqlite"


def normalize_cwd(value: str | None) -> str | None:
    if not value:
        return value
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


def timestamp_from_epoch(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def elapsed_seconds(start: str | None, end: str | None) -> int | None:
    start_dt = parse_iso_timestamp(start)
    end_dt = parse_iso_timestamp(end)
    if start_dt is None or end_dt is None:
        return None
    return int((end_dt - start_dt).total_seconds())


def thread_metadata_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "cwd": normalize_cwd(row["cwd"]),
        "rollout_path": row["rollout_path"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "created_at_iso": timestamp_from_epoch(row["created_at"]),
        "updated_at_iso": timestamp_from_epoch(row["updated_at"]),
    }


def resolve_thread(
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
) -> tuple[dict[str, Any] | None, list[str], dict[str, Any] | None]:
    warnings: list[str] = []
    selected_thread_id = active_thread_id(thread_id)
    if not selected_thread_id:
        return None, warnings, failure(
            "thread_unavailable",
            "CODEX_THREAD_ID is missing and no --thread-id override was provided.",
        )

    home = default_codex_home(codex_home)
    db_path = state_db_path(home)
    if not db_path.is_file():
        return None, warnings, failure("state_missing", f"Codex state database is missing: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "select id, title, cwd, rollout_path, created_at, updated_at from threads where id = ?",
            (selected_thread_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None, warnings, failure(
            "thread_unavailable",
            f"Thread {selected_thread_id} was not found in {db_path}.",
            thread_id=selected_thread_id,
        )

    thread = thread_metadata_from_row(row)
    rollout_path = Path(thread["rollout_path"])
    if not rollout_path.is_file():
        return None, warnings, failure(
            "rollout_missing",
            f"Rollout path is missing: {rollout_path}",
            thread=thread,
        )
    return thread, warnings, None


def parse_json_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text[0] not in "{[":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def flatten_content(value: Any) -> list[str]:
    parts: list[str] = []
    if value is None:
        return parts
    if isinstance(value, str):
        parsed = parse_json_maybe(value)
        if parsed is not None:
            parts.extend(flatten_content(parsed))
        else:
            parts.append(value)
        return parts
    if isinstance(value, list):
        for item in value:
            parts.extend(flatten_content(item))
        return parts
    if not isinstance(value, dict):
        return parts

    if "text" in value and isinstance(value["text"], str):
        parts.append(value["text"])

    if "summary" in value and isinstance(value["summary"], str):
        parts.append(value["summary"])

    for key in ("content", "output", "message", "stdout", "stderr", "aggregated_output"):
        if key in value:
            parts.extend(flatten_content(value[key]))

    if "arguments" in value:
        parsed = parse_json_maybe(value["arguments"])
        if parsed is not None:
            parts.extend(flatten_content(parsed))
        elif isinstance(value["arguments"], str):
            parts.append(value["arguments"])

    for nested_key, nested_value in value.items():
        if nested_key in {
            "type",
            "role",
            "name",
            "id",
            "call_id",
            "text",
            "summary",
            "content",
            "output",
            "message",
            "stdout",
            "stderr",
            "aggregated_output",
            "arguments",
            "encrypted_content",
        }:
            continue
        if isinstance(nested_value, (dict, list, str)):
            parts.extend(flatten_content(nested_value))
    return parts


def command_from_payload(payload: dict[str, Any]) -> str | None:
    payload_type = payload.get("type")
    if payload_type == "function_call":
        arguments = parse_json_maybe(payload.get("arguments"))
        if isinstance(arguments, dict):
            command = arguments.get("command")
            if isinstance(command, str):
                return command
    if payload_type == "exec_command_end":
        command = payload.get("command")
        if isinstance(command, list):
            return " ".join(str(part) for part in command)
        if isinstance(command, str):
            return command
    return None


def payload_role(payload: dict[str, Any]) -> str | None:
    role = payload.get("role")
    if isinstance(role, str):
        return role
    payload_type = payload.get("type")
    if payload_type in {"user_message", "agent_message"}:
        return "user" if payload_type == "user_message" else "assistant"
    return None


def sentence_candidates(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    pieces = re.split(r"(?<=[.!?])\s+", cleaned)
    return [piece.strip() for piece in pieces if piece.strip()]


def extract_paths(text: str) -> list[str]:
    matches = list(WINDOWS_FILE_PATH_PATTERN.findall(text))
    matches.extend(UNIX_FILE_PATH_PATTERN.findall(text))
    normalized = text.replace("\\", "/")
    for relative in RELATIVE_FILE_PATH_PATTERN.findall(normalized):
        if relative.startswith(("http://", "https://")):
            continue
        matches.append(relative)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in matches:
        cleaned = item.strip("`'\"").rstrip(".,)")
        if cleaned not in seen:
            deduped.append(cleaned)
            seen.add(cleaned)
    return deduped


def extract_questions(text: str) -> list[str]:
    return [match.strip() for match in QUESTION_PATTERN.findall(" ".join(text.split()))]


def extract_blockers(text: str) -> list[str]:
    blockers: list[str] = []
    for piece in sentence_candidates(text):
        lowered = piece.lower()
        if any(token in lowered for token in BLOCKER_TOKENS):
            blockers.append(piece)
    return blockers


def extract_retry_signals(text: str) -> list[str]:
    signals: list[str] = []
    for piece in sentence_candidates(text):
        lowered = piece.lower()
        if any(token in lowered for token in RETRY_TOKENS):
            signals.append(piece)
    return signals


def summarize_text(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def bounded_analysis_text(text: str, *, limit: int = TEXT_SCAN_LIMIT) -> str:
    if len(text) <= limit:
        return text
    head = max(1, limit // 2)
    tail = max(1, limit - head)
    return f"{text[:head]}\n...[truncated]...\n{text[-tail:]}"


def unique_preserving_order(items: list[Any], *, limit: int | None = None) -> list[Any]:
    output: list[Any] = []
    seen: set[Any] = set()
    for item in items:
        cleaned = " ".join(item.split()) if isinstance(item, str) else item
        if not cleaned or cleaned in seen:
            continue
        output.append(cleaned)
        seen.add(cleaned)
        if limit is not None and len(output) >= limit:
            break
    return output


def unique_recent(items: list[Any], *, limit: int | None = None) -> list[Any]:
    output: list[Any] = []
    seen: set[Any] = set()
    for item in reversed(items):
        cleaned = " ".join(item.split()) if isinstance(item, str) else item
        if not cleaned or cleaned in seen:
            continue
        output.append(cleaned)
        seen.add(cleaned)
        if limit is not None and len(output) >= limit:
            break
    return output


def is_human_scale_sentence(sentence: str) -> bool:
    cleaned = " ".join(sentence.split())
    if not cleaned or len(cleaned) > 280:
        return False
    if cleaned.startswith("<") or cleaned.startswith("Exit code:"):
        return False
    if "`sandbox_mode`" in cleaned or "### " in cleaned:
        return False
    return True


def is_hex_oid(token: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{7,40}", token))


def looks_like_email(token: str) -> bool:
    if "@" not in token:
        return False
    local, domain = token.split("@", 1)
    return bool(local) and "." in domain


def normalize_entity_candidate(candidate: str) -> str | None:
    cleaned = candidate.strip("`'\".,)")
    if cleaned.endswith(".cli"):
        cleaned = cleaned[:-4] + "-cli"
    if (
        not cleaned
        or cleaned.isdigit()
        or is_hex_oid(cleaned)
        or "/" in cleaned
        or "\\" in cleaned
        or not IDENTIFIER_PATTERN.fullmatch(cleaned)
        or cleaned.lower() in ENTITY_STOPWORDS
    ):
        return None
    return cleaned


def entity_candidates_from_path(path: str) -> list[str]:
    normalized = path.strip().rstrip("\\/").replace("/", "\\")
    parts = [part for part in normalized.split("\\") if part and part != "?"]
    if not parts:
        return []
    leaf = parts[-1]
    candidate = leaf.rsplit(".", 1)[0] if "." in leaf else leaf
    if candidate.lower() in GENERIC_PATH_PARENT_FALLBACKS and len(parts) >= 2:
        candidate = parts[-2]
    normalized_candidate = normalize_entity_candidate(candidate)
    return [normalized_candidate] if normalized_candidate is not None else []


def extract_qualified_ids(text: str) -> list[str]:
    qualified_ids: list[str] = []
    seen: set[str] = set()
    for token in BACKTICK_PATTERN.findall(text):
        cleaned = token.strip()
        if not QUALIFIED_ID_PATTERN.fullmatch(cleaned) or looks_like_email(cleaned) or cleaned in seen:
            continue
        qualified_ids.append(cleaned)
        seen.add(cleaned)
    return qualified_ids


def extract_entities(text: str) -> list[str]:
    entities: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        cleaned = normalize_entity_candidate(candidate)
        if cleaned is None or cleaned in seen:
            return
        entities.append(cleaned)
        seen.add(cleaned)

    for path in extract_paths(text):
        for candidate in entity_candidates_from_path(path):
            add(candidate)
    for token in BACKTICK_PATTERN.findall(text):
        cleaned = token.strip()
        if QUALIFIED_ID_PATTERN.fullmatch(cleaned) and not looks_like_email(cleaned):
            add(cleaned.split("@", 1)[0])
            continue
        if "/" in cleaned or "\\" in cleaned:
            for candidate in [path_candidate for path in extract_paths(cleaned) for path_candidate in entity_candidates_from_path(path)]:
                add(candidate)
            continue
        add(cleaned)
    return entities


def extract_repos(text: str) -> list[str]:
    repos: list[str] = []
    seen: set[str] = set()
    for repo in REPO_PATTERN.findall(text):
        if repo.startswith("http"):
            continue
        if repo not in seen:
            repos.append(repo)
            seen.add(repo)
    return repos


def extract_pr_numbers(text: str) -> list[int]:
    return unique_preserving_order([int(value) for value in PR_PATTERN.findall(text)])


def extract_commit_oids(text: str) -> list[str]:
    commits = COMMIT_PATTERN.findall(text) + OID_PATTERN.findall(text)
    return unique_preserving_order(commits)


def detect_event_kinds(text: str, *, entry_type: str | None, payload_type: str | None) -> list[str]:
    lowered = text.lower()
    kinds: list[str] = []
    if payload_type == "Plan" or "<proposed_plan>" in lowered or "please implement this plan" in lowered:
        kinds.append("planned")
    if entry_type == "response_item" and payload_type == "function_call":
        kinds.append("implementation_started")
    if "published" in lowered:
        kinds.append("published")
    if "merged" in lowered or '"state":"merged"' in lowered or '"state": "merged"' in lowered:
        kinds.append("merged")
    if "pushed" in lowered:
        kinds.append("pushed")
    if "installed" in lowered or "enabled" in lowered:
        kinds.append("installed")
    if "validate" in lowered or "passed" in lowered:
        kinds.append("validated")
    return unique_preserving_order(kinds)


def classify_search_text(text: str, *, entry_type: str | None, payload_type: str | None, role: str | None) -> tuple[str, bool, str | None]:
    compact = " ".join(text.split())
    lowered = compact.lower()
    if not compact:
        return "", False, None
    if role == "developer":
        return "", True, "developer"
    if lowered.startswith("please implement this plan:") or compact.startswith("<proposed_plan>"):
        return "", True, "plan-boilerplate"
    if any(token in lowered for token in NOISE_TOKENS):
        return "", True, "prompt-noise"
    if entry_type == "compacted":
        return "", True, "compaction-marker"
    if len(compact) > 1400 and not any(token in lowered for token in BLOCKER_TOKENS + RETRY_TOKENS) and not detect_event_kinds(compact, entry_type=entry_type, payload_type=payload_type):
        return "", True, "oversized-output"
    return compact, False, None


def normalize_entry(entry: dict[str, Any], entry_index: int, line_number: int) -> dict[str, Any]:
    payload = entry.get("payload") or {}
    if entry.get("type") == "compacted":
        return {
            "timestamp": entry.get("timestamp"),
            "entry_index": entry_index,
            "rollout_line": line_number,
            "entry_type": entry.get("type"),
            "payload_type": payload.get("type"),
            "role": None,
            "command": None,
            "raw_text": "Context compacted.",
            "search_text": "",
            "excerpt": "Context compacted.",
            "paths": [],
            "blockers": [],
            "retry_signals": [],
            "questions": [],
            "entities": [],
            "repos": [],
            "pr_numbers": [],
            "commit_oids": [],
            "qualified_ids": [],
            "event_kinds": [],
            "is_noise": True,
            "noise_reason": "compaction-marker",
        }

    command = command_from_payload(payload)
    flattened = flatten_content(payload)
    combined_text = " ".join(part for part in flattened if part).strip()
    if command and command not in combined_text:
        combined_text = f"{command}\n{combined_text}".strip()
    analysis_text = bounded_analysis_text(combined_text)

    role = payload_role(payload)
    search_text, is_noise, noise_reason = classify_search_text(
        analysis_text,
        entry_type=entry.get("type"),
        payload_type=payload.get("type"),
        role=role,
    )
    event_kinds = detect_event_kinds(analysis_text, entry_type=entry.get("type"), payload_type=payload.get("type"))
    entities = extract_entities(analysis_text)
    repos = extract_repos(analysis_text)
    pr_numbers = extract_pr_numbers(analysis_text)
    commit_oids = extract_commit_oids(analysis_text)
    qualified_ids = extract_qualified_ids(analysis_text)
    blockers = extract_blockers(analysis_text)
    retry_signals = extract_retry_signals(analysis_text)
    raw_text = combined_text
    if is_noise and len(raw_text) > RAW_TEXT_STORE_LIMIT:
        raw_text = bounded_analysis_text(raw_text, limit=RAW_TEXT_STORE_LIMIT)

    return {
        "timestamp": entry.get("timestamp"),
        "entry_index": entry_index,
        "rollout_line": line_number,
        "entry_type": entry.get("type"),
        "payload_type": payload.get("type"),
        "role": role,
        "command": command,
        "raw_text": raw_text,
        "search_text": search_text,
        "excerpt": summarize_text(search_text or analysis_text) if (search_text or analysis_text) else "",
        "paths": extract_paths(analysis_text),
        "blockers": blockers,
        "retry_signals": retry_signals,
        "questions": extract_questions(analysis_text),
        "entities": entities,
        "repos": repos,
        "pr_numbers": pr_numbers,
        "commit_oids": commit_oids,
        "qualified_ids": qualified_ids,
        "event_kinds": event_kinds,
        "is_noise": is_noise,
        "noise_reason": noise_reason,
    }


def load_rollout_delta(
    rollout_path: Path,
    *,
    start_offset: int = 0,
    start_line: int = 0,
    start_entry: int = 0,
) -> tuple[list[dict[str, Any]], list[str], int, int, int]:
    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    committed_offset = start_offset
    current_line = start_line
    current_entry = start_entry

    with rollout_path.open("rb") as handle:
        handle.seek(start_offset)
        while True:
            line_offset = handle.tell()
            raw_line = handle.readline()
            if not raw_line:
                break
            if not raw_line.endswith(b"\n"):
                handle.seek(line_offset)
                break

            committed_offset = handle.tell()
            current_line += 1
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(f"Skipped malformed JSONL at line {current_line}: {exc.msg}")
                continue

            current_entry += 1
            normalized.append(normalize_entry(entry, current_entry, current_line))
    return normalized, warnings, committed_offset, current_line, current_entry


def connect_cache(codex_home: Path) -> sqlite3.Connection:
    db_path = cache_db_path(codex_home)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma journal_mode = wal")
    conn.execute("pragma synchronous = normal")
    return conn


def drop_cache_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        drop table if exists entries_fts;
        drop table if exists entry_paths;
        drop table if exists entry_blockers;
        drop table if exists entry_retry_signals;
        drop table if exists entry_questions;
        drop table if exists entry_entities;
        drop table if exists entry_repos;
        drop table if exists entry_pr_numbers;
        drop table if exists entry_commit_oids;
        drop table if exists entry_qualified_ids;
        drop table if exists entry_event_kinds;
        drop table if exists entries;
        drop table if exists rollout_indexes;
        """
    )


def ensure_cache_schema(conn: sqlite3.Connection) -> None:
    rollout_exists = conn.execute(
        "select name from sqlite_master where type = 'table' and name = 'rollout_indexes'"
    ).fetchone()
    if rollout_exists is not None:
        rollout_columns = {row["name"] for row in conn.execute("pragma table_info(rollout_indexes)").fetchall()}
        required_rollout_columns = {
            "schema_version",
            "last_indexed_offset",
            "last_indexed_line",
            "last_indexed_entry",
        }
        if not required_rollout_columns.issubset(rollout_columns):
            drop_cache_schema(conn)

    entries_exists = conn.execute(
        "select name from sqlite_master where type = 'table' and name = 'entries'"
    ).fetchone()
    if entries_exists is not None:
        entry_columns = {row["name"] for row in conn.execute("pragma table_info(entries)").fetchall()}
        required_entry_columns = {
            "id",
            "thread_id",
            "entry_index",
            "rollout_line",
            "timestamp",
            "entry_type",
            "payload_type",
            "role",
            "command",
            "raw_text",
            "search_text",
            "excerpt",
            "is_noise",
            "noise_reason",
        }
        if "paths_json" in entry_columns or not required_entry_columns.issubset(entry_columns):
            drop_cache_schema(conn)

    conn.executescript(
        """
        create table if not exists rollout_indexes (
            thread_id text primary key,
            schema_version integer not null,
            rollout_path text not null,
            rollout_size integer not null,
            rollout_mtime_ns integer not null,
            last_indexed_offset integer not null,
            last_indexed_line integer not null,
            last_indexed_entry integer not null,
            built_at text not null,
            entry_count integer not null,
            noise_filtered_count integer not null
        );

        create table if not exists entries (
            id integer primary key,
            thread_id text not null,
            entry_index integer not null,
            rollout_line integer not null,
            timestamp text,
            entry_type text,
            payload_type text,
            role text,
            command text,
            raw_text text,
            search_text text,
            excerpt text,
            is_noise integer not null,
            noise_reason text
        );
        """
    )
    for facet_name, (table_name, column_name) in FACET_TABLES.items():
        column_type = "integer" if facet_name == "pr_numbers" else "text"
        conn.execute(
            f"""
            create table if not exists {table_name} (
                entry_id integer not null references entries(id) on delete cascade,
                {column_name} {column_type} not null
            )
            """
        )

    conn.execute("create index if not exists idx_entries_thread on entries(thread_id, entry_index)")
    conn.execute("create index if not exists idx_entries_timestamp on entries(thread_id, timestamp)")
    conn.execute("create index if not exists idx_entries_role on entries(thread_id, role, entry_index)")
    conn.execute("create index if not exists idx_entries_type on entries(thread_id, entry_type, payload_type, entry_index)")
    for facet_name, (table_name, column_name) in FACET_TABLES.items():
        conn.execute(f"create index if not exists idx_{table_name}_entry on {table_name}(entry_id)")
        conn.execute(f"create index if not exists idx_{table_name}_value on {table_name}({column_name})")
        conn.execute(f"create index if not exists idx_{table_name}_value_entry on {table_name}({column_name}, entry_id)")


def rollout_signature(rollout_path: Path) -> tuple[int, int]:
    stat = rollout_path.stat()
    return stat.st_size, stat.st_mtime_ns


def cache_metadata_row(conn: sqlite3.Connection, thread_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        select schema_version, rollout_path, rollout_size, rollout_mtime_ns,
               last_indexed_offset, last_indexed_line, last_indexed_entry,
               built_at, entry_count, noise_filtered_count
        from rollout_indexes
        where thread_id = ?
        """,
        (thread_id,),
    ).fetchone()


def clear_thread_cache(conn: sqlite3.Connection, thread_id: str) -> None:
    conn.execute("delete from entries where thread_id = ?", (thread_id,))
    conn.execute("delete from rollout_indexes where thread_id = ?", (thread_id,))


def insert_entry_facets(conn: sqlite3.Connection, entry_id: int, entry: dict[str, Any]) -> None:
    for facet_name, (table_name, column_name) in FACET_TABLES.items():
        values = entry[facet_name]
        if not values:
            continue
        conn.executemany(
            f"insert into {table_name} (entry_id, {column_name}) values (?, ?)",
            [(entry_id, value) for value in values],
        )


def insert_entries(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    entries: list[dict[str, Any]],
) -> None:
    for entry in entries:
        cursor = conn.execute(
            """
            insert into entries (
                thread_id, entry_index, rollout_line, timestamp, entry_type, payload_type, role, command,
                raw_text, search_text, excerpt, is_noise, noise_reason
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                entry["entry_index"],
                entry["rollout_line"],
                entry["timestamp"],
                entry["entry_type"],
                entry["payload_type"],
                entry["role"],
                entry["command"],
                entry["raw_text"],
                entry["search_text"],
                entry["excerpt"],
                int(entry["is_noise"]),
                entry["noise_reason"],
            ),
        )
        insert_entry_facets(conn, int(cursor.lastrowid), entry)


def upsert_rollout_index(
    conn: sqlite3.Connection,
    *,
    thread: dict[str, Any],
    rollout_size: int,
    rollout_mtime_ns: int,
    last_indexed_offset: int,
    last_indexed_line: int,
    last_indexed_entry: int,
    entry_count: int,
    noise_filtered_count: int,
) -> None:
    conn.execute(
        """
        insert into rollout_indexes (
            thread_id, schema_version, rollout_path, rollout_size, rollout_mtime_ns,
            last_indexed_offset, last_indexed_line, last_indexed_entry,
            built_at, entry_count, noise_filtered_count
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(thread_id) do update set
            schema_version = excluded.schema_version,
            rollout_path = excluded.rollout_path,
            rollout_size = excluded.rollout_size,
            rollout_mtime_ns = excluded.rollout_mtime_ns,
            last_indexed_offset = excluded.last_indexed_offset,
            last_indexed_line = excluded.last_indexed_line,
            last_indexed_entry = excluded.last_indexed_entry,
            built_at = excluded.built_at,
            entry_count = excluded.entry_count,
            noise_filtered_count = excluded.noise_filtered_count
        """,
        (
            thread["id"],
            CACHE_SCHEMA_VERSION,
            thread["rollout_path"],
            rollout_size,
            rollout_mtime_ns,
            last_indexed_offset,
            last_indexed_line,
            last_indexed_entry,
            datetime.now(tz=UTC).isoformat(),
            entry_count,
            noise_filtered_count,
        ),
    )


def rebuild_index(
    conn: sqlite3.Connection,
    *,
    thread: dict[str, Any],
    entries: list[dict[str, Any]],
    rollout_size: int,
    rollout_mtime_ns: int,
    last_indexed_offset: int,
    last_indexed_line: int,
    last_indexed_entry: int,
) -> None:
    clear_thread_cache(conn, thread["id"])
    insert_entries(conn, thread_id=thread["id"], entries=entries)
    upsert_rollout_index(
        conn,
        thread=thread,
        rollout_size=rollout_size,
        rollout_mtime_ns=rollout_mtime_ns,
        last_indexed_offset=last_indexed_offset,
        last_indexed_line=last_indexed_line,
        last_indexed_entry=last_indexed_entry,
        entry_count=last_indexed_entry,
        noise_filtered_count=sum(1 for entry in entries if entry["is_noise"]),
    )
    conn.commit()


def append_index(
    conn: sqlite3.Connection,
    *,
    thread: dict[str, Any],
    existing: sqlite3.Row,
    new_entries: list[dict[str, Any]],
    rollout_size: int,
    rollout_mtime_ns: int,
    last_indexed_offset: int,
    last_indexed_line: int,
    last_indexed_entry: int,
) -> None:
    insert_entries(conn, thread_id=thread["id"], entries=new_entries)
    upsert_rollout_index(
        conn,
        thread=thread,
        rollout_size=rollout_size,
        rollout_mtime_ns=rollout_mtime_ns,
        last_indexed_offset=last_indexed_offset,
        last_indexed_line=last_indexed_line,
        last_indexed_entry=last_indexed_entry,
        entry_count=int(existing["entry_count"]) + len(new_entries),
        noise_filtered_count=int(existing["noise_filtered_count"]) + sum(1 for entry in new_entries if entry["is_noise"]),
    )
    conn.commit()


def ensure_index(
    conn: sqlite3.Connection,
    *,
    thread: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    rollout_path = Path(thread["rollout_path"])
    rollout_size, rollout_mtime_ns = rollout_signature(rollout_path)
    ensure_cache_schema(conn)
    existing = cache_metadata_row(conn, thread["id"])

    built = False
    stale = False
    appended_entries = 0
    full_rebuild = False

    if existing is None:
        entries, parse_warnings, last_offset, last_line, last_entry = load_rollout_delta(rollout_path)
        warnings.extend(parse_warnings)
        rebuild_index(
            conn,
            thread=thread,
            entries=entries,
            rollout_size=rollout_size,
            rollout_mtime_ns=rollout_mtime_ns,
            last_indexed_offset=last_offset,
            last_indexed_line=last_line,
            last_indexed_entry=last_entry,
        )
        built = True
    else:
        full_rebuild = (
            int(existing["schema_version"]) != CACHE_SCHEMA_VERSION
            or existing["rollout_path"] != str(rollout_path)
            or rollout_size < int(existing["rollout_size"])
            or rollout_size < int(existing["last_indexed_offset"])
            or (rollout_size == int(existing["rollout_size"]) and rollout_mtime_ns != int(existing["rollout_mtime_ns"]))
        )
        if full_rebuild:
            entries, parse_warnings, last_offset, last_line, last_entry = load_rollout_delta(rollout_path)
            warnings.extend(parse_warnings)
            rebuild_index(
                conn,
                thread=thread,
                entries=entries,
                rollout_size=rollout_size,
                rollout_mtime_ns=rollout_mtime_ns,
                last_indexed_offset=last_offset,
                last_indexed_line=last_line,
                last_indexed_entry=last_entry,
            )
            built = True
            stale = True
        elif rollout_size > int(existing["rollout_size"]):
            new_entries, parse_warnings, last_offset, last_line, last_entry = load_rollout_delta(
                rollout_path,
                start_offset=int(existing["last_indexed_offset"]),
                start_line=int(existing["last_indexed_line"]),
                start_entry=int(existing["last_indexed_entry"]),
            )
            warnings.extend(parse_warnings)
            if new_entries:
                append_index(
                    conn,
                    thread=thread,
                    existing=existing,
                    new_entries=new_entries,
                    rollout_size=rollout_size,
                    rollout_mtime_ns=rollout_mtime_ns,
                    last_indexed_offset=last_offset,
                    last_indexed_line=last_line,
                    last_indexed_entry=last_entry,
                )
                built = True
                stale = True
                appended_entries = len(new_entries)

    metadata_row = cache_metadata_row(conn, thread["id"])
    index_meta = {
        "used": True,
        "built": built,
        "stale": stale,
        "entry_count": int(metadata_row["entry_count"]) if metadata_row is not None else 0,
        "noise_filtered_count": int(metadata_row["noise_filtered_count"]) if metadata_row is not None else 0,
        "appended_entries": appended_entries,
    }
    return index_meta, warnings


def load_facets_for_entries(conn: sqlite3.Connection, entry_ids: list[int]) -> dict[int, dict[str, list[Any]]]:
    facets_by_entry: dict[int, dict[str, list[Any]]] = {
        entry_id: {facet_name: [] for facet_name in FACET_TABLES} for entry_id in entry_ids
    }
    if not entry_ids:
        return facets_by_entry

    placeholders = ",".join("?" for _ in entry_ids)
    for facet_name, (table_name, column_name) in FACET_TABLES.items():
        rows = conn.execute(
            f"""
            select entry_id, {column_name} as value
            from {table_name}
            where entry_id in ({placeholders})
            order by entry_id, rowid
            """,
            entry_ids,
        ).fetchall()
        for row in rows:
            facets_by_entry[int(row["entry_id"])][facet_name].append(row["value"])
    return facets_by_entry


def entry_from_row(row: sqlite3.Row, facets: dict[str, list[Any]]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "entry_index": int(row["entry_index"]),
        "rollout_line": int(row["rollout_line"]),
        "timestamp": row["timestamp"],
        "entry_type": row["entry_type"],
        "payload_type": row["payload_type"],
        "role": row["role"],
        "command": row["command"],
        "raw_text": row["raw_text"] or "",
        "search_text": row["search_text"] or "",
        "excerpt": row["excerpt"] or "",
        "is_noise": bool(row["is_noise"]),
        "noise_reason": row["noise_reason"],
        **facets,
    }


def fetch_entry_rows_by_ids(conn: sqlite3.Connection, entry_ids: list[int]) -> list[dict[str, Any]]:
    if not entry_ids:
        return []
    placeholders = ",".join("?" for _ in entry_ids)
    rows = conn.execute(
        f"""
        select id, entry_index, rollout_line, timestamp, entry_type, payload_type, role,
               command, raw_text, search_text, excerpt, is_noise, noise_reason
        from entries
        where id in ({placeholders})
        """,
        entry_ids,
    ).fetchall()
    row_map = {int(row["id"]): row for row in rows}
    facet_map = load_facets_for_entries(conn, entry_ids)
    return [entry_from_row(row_map[entry_id], facet_map[entry_id]) for entry_id in entry_ids if entry_id in row_map]


def matched_facets(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "entities": entry["entities"],
        "repos": entry["repos"],
        "pr_numbers": entry["pr_numbers"],
        "commit_oids": entry["commit_oids"],
        "qualified_ids": entry["qualified_ids"],
        "event_kinds": entry["event_kinds"],
    }


def recent_distinct_values(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    facet_name: str,
    limit: int,
    extra_where: str = "",
    params: tuple[Any, ...] = (),
) -> list[Any]:
    table_name, column_name = FACET_TABLES[facet_name]
    rows = conn.execute(
        f"""
        select f.{column_name} as value, max(e.entry_index) as latest_index
        from {table_name} f
        join entries e on e.id = f.entry_id
        where e.thread_id = ? {extra_where}
        group by f.{column_name}
        order by latest_index desc
        limit ?
        """,
        (thread_id, *params, limit),
    ).fetchall()
    return [row["value"] for row in rows]


def recent_commands(conn: sqlite3.Connection, *, thread_id: str, limit: int) -> list[str]:
    rows = conn.execute(
        """
        select command
        from entries
        where thread_id = ? and command is not null and command != ''
        order by entry_index desc
        limit 250
        """,
        (thread_id,),
    ).fetchall()
    return unique_recent([row["command"] for row in rows], limit=limit)


def recent_text_rows(conn: sqlite3.Connection, *, thread_id: str, limit: int = TEXT_SCAN_LIMIT) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select entry_index, role, search_text, raw_text, entry_type
        from entries
        where thread_id = ? and role in ('assistant', 'user') and search_text != ''
        order by entry_index desc
        limit ?
        """,
        (thread_id, limit),
    ).fetchall()


def aggregate_counts(conn: sqlite3.Connection, *, thread_id: str) -> tuple[dict[str, int], dict[str, int]]:
    entry_counts = {
        row["entry_type"]: int(row["count"])
        for row in conn.execute(
            """
            select entry_type, count(*) as count
            from entries
            where thread_id = ?
            group by entry_type
            """,
            (thread_id,),
        ).fetchall()
    }
    event_counts = {
        row["event_kind"]: int(row["count"])
        for row in conn.execute(
            """
            select ek.event_kind, count(*) as count
            from entry_event_kinds ek
            join entries e on e.id = ek.entry_id
            where e.thread_id = ?
            group by ek.event_kind
            """,
            (thread_id,),
        ).fetchall()
    }
    return entry_counts, event_counts


def evidence_entry_ids(conn: sqlite3.Connection, *, thread_id: str, profile: str, limit: int) -> list[int]:
    if profile == "shipping":
        where_sql = """
            e.entry_type = 'compacted'
            or exists (select 1 from entry_event_kinds ek where ek.entry_id = e.id)
            or exists (select 1 from entry_entities en where en.entry_id = e.id)
            or exists (select 1 from entry_repos rp where rp.entry_id = e.id)
            or exists (select 1 from entry_pr_numbers pn where pn.entry_id = e.id)
            or exists (select 1 from entry_commit_oids co where co.entry_id = e.id)
            or exists (select 1 from entry_qualified_ids qi where qi.entry_id = e.id)
        """
    elif profile == "debug":
        where_sql = """
            e.entry_type = 'compacted'
            or e.command is not null
            or exists (select 1 from entry_blockers bl where bl.entry_id = e.id)
            or exists (select 1 from entry_retry_signals rs where rs.entry_id = e.id)
        """
    else:
        where_sql = "e.entry_type = 'compacted' or (e.search_text != '' and e.is_noise = 0)"

    rows = conn.execute(
        f"""
        select e.id
        from entries e
        where e.thread_id = ? and ({where_sql})
        order by e.entry_index asc
        limit ?
        """,
        (thread_id, limit),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def build_evidence(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    limit: int,
    profile: str,
) -> list[dict[str, Any]]:
    entries = fetch_entry_rows_by_ids(conn, evidence_entry_ids(conn, thread_id=thread_id, profile=profile, limit=limit))
    evidence: list[dict[str, Any]] = []
    for entry in entries:
        evidence.append(
            {
                "entry_index": entry["entry_index"],
                "rollout_line": entry["rollout_line"],
                "timestamp": entry["timestamp"],
                "entry_type": entry["entry_type"],
                "payload_type": entry["payload_type"],
                "role": entry["role"],
                "excerpt": entry["excerpt"] or "Context compacted.",
                "matched_facets": matched_facets(entry),
            }
        )
    return evidence


def build_general_summary(decisions: list[str], blockers: list[str], open_questions: list[str], known_facts: list[str]) -> str:
    parts: list[str] = []
    if decisions:
        parts.append(f"Decisions: {'; '.join(decisions[:2])}")
    if blockers:
        parts.append(f"Blockers: {'; '.join(blockers[:2])}")
    if open_questions:
        parts.append(f"Open questions: {'; '.join(open_questions[:2])}")
    if not parts and known_facts:
        parts.append(f"Known facts: {'; '.join(known_facts[:2])}")
    return " ".join(parts)


def build_shipping_summary(recall: dict[str, Any]) -> str:
    parts: list[str] = []
    if recall["shipped_entities"]:
        parts.append(f"Shipped: {', '.join(recall['shipped_entities'][:3])}")
    if recall["pr_numbers"]:
        parts.append(f"PRs: {', '.join(f'#{value}' for value in recall['pr_numbers'][:4])}")
    if recall["follow_up_fixes"]:
        parts.append(f"Follow-up fixes: {'; '.join(recall['follow_up_fixes'][:2])}")
    if recall["repos_touched"]:
        parts.append(f"Repos: {', '.join(recall['repos_touched'][:2])}")
    return " ".join(parts)


def build_debug_summary(recall: dict[str, Any]) -> str:
    parts: list[str] = []
    if recall["failure_events"]:
        parts.append(f"Failures: {'; '.join(recall['failure_events'][:2])}")
    if recall["retry_signals"]:
        parts.append(f"Retries: {'; '.join(recall['retry_signals'][:2])}")
    if recall["commands"]:
        parts.append(f"Commands: {'; '.join(recall['commands'][:2])}")
    return " ".join(parts)


def collect_general_recall(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    evidence_limit: int,
    profile: str,
) -> dict[str, Any]:
    commands = recent_commands(conn, thread_id=thread_id, limit=25)
    touched_paths = recent_distinct_values(
        conn,
        thread_id=thread_id,
        facet_name="paths",
        limit=25,
        extra_where="and ((e.role in ('assistant', 'user')) or e.entry_type = 'response_item') and e.is_noise = 0",
    )
    blockers = [
        item
        for item in recent_distinct_values(conn, thread_id=thread_id, facet_name="blockers", limit=10)
        if is_human_scale_sentence(str(item))
    ]
    open_questions = [
        item
        for item in recent_distinct_values(
            conn,
            thread_id=thread_id,
            facet_name="questions",
            limit=10,
            extra_where="and e.role in ('assistant', 'user') and e.is_noise = 0",
        )
        if is_human_scale_sentence(str(item))
    ]

    decisions: list[str] = []
    known_facts: list[str] = []
    for row in reversed(recent_text_rows(conn, thread_id=thread_id)):
        if row["role"] == "developer" or not row["search_text"]:
            continue
        for sentence in sentence_candidates(row["search_text"]):
            if not is_human_scale_sentence(sentence):
                continue
            lowered = sentence.lower()
            if lowered.startswith("decision:") or "fail closed" in lowered or "use codex_thread_id" in lowered:
                decisions.append(sentence)
            elif row["role"] in {"assistant", "user"} and "?" not in sentence:
                known_facts.append(sentence)

    decisions = unique_recent(decisions, limit=10)
    known_facts = unique_recent(known_facts, limit=10)
    entry_counts, event_counts = aggregate_counts(conn, thread_id=thread_id)
    evidence = build_evidence(conn, thread_id=thread_id, limit=evidence_limit, profile=profile)

    return {
        "profile": profile,
        "summary": build_general_summary(decisions, blockers, open_questions, known_facts),
        "known_facts": known_facts,
        "decisions": decisions,
        "touched_paths": touched_paths,
        "commands": commands,
        "blockers": blockers,
        "open_questions": open_questions,
        "evidence": evidence,
        "counts": entry_counts,
        "event_counts": event_counts,
    }


def collect_shipping_recall(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    evidence_limit: int,
) -> dict[str, Any]:
    ship_where = "and exists (select 1 from entry_event_kinds ek where ek.entry_id = e.id and ek.event_kind in (?, ?, ?, ?))"
    ship_params: tuple[Any, ...] = tuple(sorted(SHIP_EVENT_KINDS))
    recall = collect_general_recall(conn, thread_id=thread_id, evidence_limit=evidence_limit, profile="shipping")
    shipped_entities = recent_distinct_values(
        conn, thread_id=thread_id, facet_name="entities", limit=15, extra_where=ship_where, params=ship_params
    )
    repos_touched = recent_distinct_values(
        conn, thread_id=thread_id, facet_name="repos", limit=10, extra_where=ship_where, params=ship_params
    )
    pr_numbers = recent_distinct_values(
        conn, thread_id=thread_id, facet_name="pr_numbers", limit=15, extra_where=ship_where, params=ship_params
    )
    commit_oids = recent_distinct_values(
        conn, thread_id=thread_id, facet_name="commit_oids", limit=15, extra_where=ship_where, params=ship_params
    )
    installed_entities = recent_distinct_values(
        conn,
        thread_id=thread_id,
        facet_name="entities",
        limit=15,
        extra_where="and exists (select 1 from entry_event_kinds ek where ek.entry_id = e.id and ek.event_kind = ?)",
        params=("installed",),
    )
    installed_identifiers = recent_distinct_values(
        conn,
        thread_id=thread_id,
        facet_name="qualified_ids",
        limit=15,
        extra_where="and exists (select 1 from entry_event_kinds ek where ek.entry_id = e.id and ek.event_kind = ?)",
        params=("installed",),
    )
    follow_up_rows = conn.execute(
        """
        select raw_text
        from entries e
        where e.thread_id = ?
          and exists (select 1 from entry_event_kinds ek where ek.entry_id = e.id and ek.event_kind = 'merged')
          and (lower(e.raw_text) like '%follow-up%' or lower(e.raw_text) like '%fix%')
        order by e.entry_index desc
        limit 100
        """,
        (thread_id,),
    ).fetchall()
    follow_up_fixes = unique_recent(
        [
            sentence
            for row in follow_up_rows
            for sentence in sentence_candidates(row["raw_text"] or "")
            if is_human_scale_sentence(sentence)
        ],
        limit=10,
    )
    recall.update(
        {
            "shipped_entities": shipped_entities,
            "repos_touched": repos_touched,
            "pr_numbers": pr_numbers,
            "commit_oids": commit_oids,
            "installed_entities": installed_entities,
            "installed_identifiers": installed_identifiers,
            "follow_up_fixes": follow_up_fixes,
        }
    )
    recall["summary"] = build_shipping_summary(recall)
    return recall


def collect_debug_recall(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    evidence_limit: int,
) -> dict[str, Any]:
    recall = collect_general_recall(conn, thread_id=thread_id, evidence_limit=evidence_limit, profile="debug")
    failure_events = [
        item
        for item in recent_distinct_values(conn, thread_id=thread_id, facet_name="blockers", limit=15)
        if is_human_scale_sentence(str(item))
    ]
    retry_signals = [
        item
        for item in recent_distinct_values(conn, thread_id=thread_id, facet_name="retry_signals", limit=15)
        if is_human_scale_sentence(str(item))
    ]
    recall.update({"failure_events": failure_events, "retry_signals": retry_signals})
    recall["summary"] = build_debug_summary(recall)
    return recall


def selected_event_kinds(kind: str) -> set[str]:
    if kind == "all":
        return {"planned", "implementation_started", "published", "merged", "pushed", "installed", "validated"}
    if kind == "shipped":
        return SHIP_EVENT_KINDS
    return {kind}


def build_timeline_event(entry: dict[str, Any], kind: str) -> dict[str, Any]:
    return {
        "timestamp": entry["timestamp"],
        "kind": kind,
        "entry_type": entry["entry_type"],
        "payload_type": entry["payload_type"],
        "role": entry["role"],
        "excerpt": entry["excerpt"],
        "entities": entry["entities"],
        "repos": entry["repos"],
        "pr_numbers": entry["pr_numbers"],
        "commit_oids": entry["commit_oids"],
        "qualified_ids": entry["qualified_ids"],
        "rollout_line": entry["rollout_line"],
    }


def ship_kinds_for_entry(entry: dict[str, Any]) -> list[str]:
    kinds = set(entry["event_kinds"])
    if "published" in kinds:
        selected = ["published"]
        if "installed" in kinds:
            selected.append("installed")
        return selected
    if "pushed" in kinds:
        return ["pushed"]
    if "merged" in kinds:
        return ["merged"]
    if "installed" in kinds:
        return ["installed"]
    return []


def timeline_entry_ids(conn: sqlite3.Connection, *, thread_id: str, kind: str) -> list[int]:
    if kind == "all":
        where_sql = ""
        params: tuple[Any, ...] = ()
    elif kind == "shipped":
        where_sql = "and ek.event_kind in (?, ?, ?, ?)"
        params = tuple(sorted(SHIP_EVENT_KINDS))
    else:
        where_sql = "and ek.event_kind = ?"
        params = (kind,)

    rows = conn.execute(
        f"""
        select distinct e.id, coalesce(e.timestamp, '') as sort_timestamp, e.entry_index
        from entries e
        join entry_event_kinds ek on ek.entry_id = e.id
        where e.thread_id = ?
          {where_sql}
        order by sort_timestamp, e.entry_index
        """,
        (thread_id, *params),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def first_seen_map(conn: sqlite3.Connection, *, thread_id: str, group: str) -> dict[str, str | None]:
    facet_name = "entities" if group == "entity" else "repos"
    table_name, column_name = FACET_TABLES[facet_name]
    rows = conn.execute(
        f"""
        select f.{column_name} as group_key, e.timestamp
        from {table_name} f
        join entries e on e.id = f.entry_id
        where e.thread_id = ?
        order by e.entry_index
        """,
        (thread_id,),
    ).fetchall()
    output: dict[str, str | None] = {}
    for row in rows:
        key = row["group_key"]
        if key not in output:
            output[key] = row["timestamp"]
    return output


def status(thread_id: str | None = None, codex_home: str | Path | None = None) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error
    return {"ok": True, "thread": thread, "warnings": warnings}


def recall(
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
    *,
    evidence_limit: int = 25,
    profile: str = "general",
) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error

    home = default_codex_home(codex_home)
    conn = connect_cache(home)
    try:
        index_meta, index_warnings = ensure_index(conn, thread=thread)
        warnings.extend(index_warnings)

        if profile == "shipping":
            recall_payload = collect_shipping_recall(conn, thread_id=thread["id"], evidence_limit=evidence_limit)
        elif profile == "debug":
            recall_payload = collect_debug_recall(conn, thread_id=thread["id"], evidence_limit=evidence_limit)
        else:
            recall_payload = collect_general_recall(conn, thread_id=thread["id"], evidence_limit=evidence_limit, profile="general")

        return {
            "ok": True,
            "thread": thread,
            "warnings": warnings,
            "index": index_meta,
            "recall": recall_payload,
        }
    finally:
        conn.close()


def grep_rollout(
    pattern: str,
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
    *,
    limit: int = 10,
    role: str | None = None,
    entry_type: str | None = None,
    payload_type: str | None = None,
    after: str | None = None,
    before: str | None = None,
    include_noise: bool = False,
) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error

    home = default_codex_home(codex_home)
    conn = connect_cache(home)
    try:
        index_meta, index_warnings = ensure_index(conn, thread=thread)
        warnings.extend(index_warnings)

        search_column = "raw_text" if include_noise else "search_text"
        where_clauses = ["e.thread_id = ?"]
        params: list[Any] = [thread["id"]]
        if role:
            where_clauses.append("e.role = ?")
            params.append(role)
        if entry_type:
            where_clauses.append("e.entry_type = ?")
            params.append(entry_type)
        if payload_type:
            where_clauses.append("e.payload_type = ?")
            params.append(payload_type)
        if after:
            where_clauses.append("(e.timestamp is null or e.timestamp >= ?)")
            params.append(after)
        if before:
            where_clauses.append("(e.timestamp is null or e.timestamp <= ?)")
            params.append(before)
        where_clauses.append(f"instr(lower(coalesce(e.{search_column}, '')), lower(?)) > 0")
        params.append(pattern)

        rows = conn.execute(
            f"""
            select e.id, e.entry_index, e.rollout_line, e.timestamp, e.entry_type, e.payload_type, e.role,
                   ((select count(*) from entry_entities en where en.entry_id = e.id)
                    + (select count(*) from entry_repos rp where rp.entry_id = e.id)
                    + (select count(*) from entry_pr_numbers pn where pn.entry_id = e.id)
                    + (select count(*) from entry_commit_oids co where co.entry_id = e.id)
                    + (select count(*) from entry_qualified_ids qi where qi.entry_id = e.id)
                    + (select count(*) from entry_event_kinds ek where ek.entry_id = e.id)) as facet_score
            from entries e
            where {' and '.join(where_clauses)}
            order by facet_score desc, coalesce(e.timestamp, ''), e.entry_index
            limit ?
            """,
            (*params, limit),
        ).fetchall()

        entry_ids = [int(row["id"]) for row in rows]
        entries = {entry["id"]: entry for entry in fetch_entry_rows_by_ids(conn, entry_ids)}
        facet_scores = {int(row["id"]): int(row["facet_score"]) for row in rows}
        results = []
        for entry_id in entry_ids:
            entry = entries[entry_id]
            haystack = entry["raw_text"] if include_noise else entry["search_text"]
            results.append(
                {
                    "entry_index": entry["entry_index"],
                    "rollout_line": entry["rollout_line"],
                    "timestamp": entry["timestamp"],
                    "entry_type": entry["entry_type"],
                    "payload_type": entry["payload_type"],
                    "role": entry["role"],
                    "excerpt": summarize_text(haystack),
                    "matched_facets": matched_facets(entry),
                    "_facet_score": facet_scores[entry_id],
                }
            )
        for result in results:
            result.pop("_facet_score", None)

        return {
            "ok": True,
            "thread": thread,
            "pattern": pattern,
            "warnings": warnings,
            "index": index_meta,
            "results": results,
        }
    finally:
        conn.close()


def timeline(
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
    *,
    kind: str = "shipped",
    group: str = "entity",
    limit: int = 10,
) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error

    home = default_codex_home(codex_home)
    conn = connect_cache(home)
    try:
        index_meta, index_warnings = ensure_index(conn, thread=thread)
        warnings.extend(index_warnings)
        selected_kinds = selected_event_kinds(kind)
        entries = fetch_entry_rows_by_ids(conn, timeline_entry_ids(conn, thread_id=thread["id"], kind=kind))

        flat_events: list[dict[str, Any]] = []
        for entry in entries:
            matched_kinds = ship_kinds_for_entry(entry) if kind == "shipped" else entry["event_kinds"]
            for matched_kind in matched_kinds:
                if matched_kind in selected_kinds:
                    flat_events.append(build_timeline_event(entry, matched_kind))

        flat_events.sort(key=lambda item: (item["timestamp"] or "", item["rollout_line"]))
        if group == "none":
            return {
                "ok": True,
                "thread": thread,
                "kind": kind,
                "group": group,
                "warnings": warnings,
                "index": index_meta,
                "timeline": flat_events[:limit],
            }

        grouping: dict[str, dict[str, Any]] = {}
        key_name = "entity" if group == "entity" else "repo"
        seen_map = first_seen_map(conn, thread_id=thread["id"], group=group)
        for event in flat_events:
            keys = event["entities"] if group == "entity" else event["repos"]
            for key in keys:
                bucket = grouping.setdefault(
                    key,
                    {
                        key_name: key,
                        "first_seen_at": seen_map.get(key),
                        "first_ship_at": None,
                        "last_ship_at": None,
                        "elapsed_to_first_ship_seconds": None,
                        "elapsed_to_last_ship_seconds": None,
                        "revisit_count": 0,
                        "ship_events": [],
                        "repos": [],
                        "pr_numbers": [],
                        "commit_oids": [],
                        "qualified_ids": [],
                    },
                )
                bucket["ship_events"].append(event)
                bucket["repos"] = unique_preserving_order(bucket["repos"] + event["repos"])
                bucket["pr_numbers"] = unique_preserving_order(bucket["pr_numbers"] + event["pr_numbers"])
                bucket["commit_oids"] = unique_preserving_order(bucket["commit_oids"] + event["commit_oids"])
                bucket["qualified_ids"] = unique_preserving_order(bucket["qualified_ids"] + event["qualified_ids"])

        for bucket in grouping.values():
            if bucket["ship_events"]:
                bucket["first_ship_at"] = bucket["ship_events"][0]["timestamp"]
                bucket["last_ship_at"] = bucket["ship_events"][-1]["timestamp"]
                bucket["elapsed_to_first_ship_seconds"] = elapsed_seconds(bucket["first_seen_at"], bucket["first_ship_at"])
                bucket["elapsed_to_last_ship_seconds"] = elapsed_seconds(bucket["first_seen_at"], bucket["last_ship_at"])
                distinct_ship_times = unique_preserving_order(
                    [event["timestamp"] for event in bucket["ship_events"] if event["timestamp"]]
                )
                bucket["revisit_count"] = max(0, len(distinct_ship_times) - 1)

        grouped_timeline = sorted(grouping.values(), key=lambda item: item["first_seen_at"] or "")[:limit]
        return {
            "ok": True,
            "thread": thread,
            "kind": kind,
            "group": group,
            "warnings": warnings,
            "index": index_meta,
            "timeline": grouped_timeline,
        }
    finally:
        conn.close()
