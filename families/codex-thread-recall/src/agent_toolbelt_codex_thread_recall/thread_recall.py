from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


WINDOWS_FILE_PATH_PATTERN = re.compile(
    r"(?:\\\\\?\\)?[A-Za-z]:\\[^\r\n\"']+?\.(?:py|md|json|yaml|yml|toml|txt|sql|sqlite|ps1|bat|exe)"
)
RELATIVE_FAMILY_PATH_PATTERN = re.compile(
    r"families/[A-Za-z0-9._/-]+?\.(?:py|md|json|yaml|yml|toml|txt|sql|sqlite|ps1|bat|exe)"
)
QUESTION_PATTERN = re.compile(r"[^?]+\?")
BLOCKER_TOKENS = ("permission denied", "failed", "error", "timeout", "traceback", "exception")


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


def resolve_thread(thread_id: str | None = None, codex_home: str | Path | None = None) -> tuple[dict[str, Any] | None, list[str], dict[str, Any] | None]:
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

    for key in ("content", "output"):
        if key in value:
            parts.extend(flatten_content(value[key]))

    if "arguments" in value:
        parsed = parse_json_maybe(value["arguments"])
        if parsed is not None:
            parts.extend(flatten_content(parsed))
        elif isinstance(value["arguments"], str):
            parts.append(value["arguments"])

    for nested_key, nested_value in value.items():
        if nested_key in {"text", "summary", "content", "output", "arguments", "encrypted_content"}:
            continue
        if isinstance(nested_value, (dict, list)):
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
        for key in ("command", "cmdline"):
            command = payload.get(key)
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
    for relative in RELATIVE_FAMILY_PATH_PATTERN.findall(text.replace("\\", "/")):
        matches.append(relative.replace("/", "\\"))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in matches:
        cleaned = item.strip().rstrip(".,)")
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


def summarize_text(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def normalize_entry(entry: dict[str, Any], entry_index: int) -> dict[str, Any]:
    payload = entry.get("payload") or {}
    command = command_from_payload(payload)
    flattened = flatten_content(payload)
    combined_text = " ".join(part for part in flattened if part).strip()
    if command and command not in combined_text:
        combined_text = f"{command}\n{combined_text}".strip()
    if entry.get("type") == "compacted" and not combined_text:
        combined_text = "Context compacted."
    return {
        "timestamp": entry.get("timestamp"),
        "entry_index": entry_index,
        "rollout_line": entry_index,
        "entry_type": entry.get("type"),
        "payload_type": payload.get("type"),
        "role": payload_role(payload),
        "command": command,
        "text": combined_text,
        "excerpt": summarize_text(combined_text) if combined_text else "",
        "paths": extract_paths(combined_text),
        "blockers": extract_blockers(combined_text),
        "questions": extract_questions(combined_text),
    }


def load_rollout(rollout_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    with rollout_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(f"Skipped malformed JSONL at line {line_number}: {exc.msg}")
                continue
            normalized.append(normalize_entry(entry, len(normalized) + 1))
    return normalized, warnings


def unique_preserving_order(items: list[str], *, limit: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = " ".join(item.split())
        if not cleaned or cleaned in seen:
            continue
        output.append(cleaned)
        seen.add(cleaned)
        if limit is not None and len(output) >= limit:
            break
    return output


def unique_recent(items: list[str], *, limit: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in reversed(items):
        cleaned = " ".join(item.split())
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


def build_evidence(entries: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for entry in entries:
        if entry["excerpt"] or entry["entry_type"] == "compacted":
            selected.append(
                {
                    "entry_index": entry["entry_index"],
                    "rollout_line": entry["rollout_line"],
                    "timestamp": entry["timestamp"],
                    "entry_type": entry["entry_type"],
                    "payload_type": entry["payload_type"],
                    "role": entry["role"],
                    "excerpt": entry["excerpt"] or "Context compacted.",
                }
            )
        if len(selected) >= limit:
            break
    return selected


def build_summary(decisions: list[str], blockers: list[str], open_questions: list[str], known_facts: list[str]) -> str:
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
) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error

    entries, parse_warnings = load_rollout(Path(thread["rollout_path"]))
    warnings.extend(parse_warnings)

    commands = unique_recent([entry["command"] for entry in entries if entry["command"]], limit=25)
    touched_paths = unique_recent(
        [
            path
            for entry in entries
            if entry["role"] in {"assistant", "user"} or entry["entry_type"] == "response_item"
            for path in entry["paths"]
        ],
        limit=25,
    )
    blockers = unique_recent(
        [
            item
            for entry in entries
            for item in entry["blockers"]
            if is_human_scale_sentence(item)
        ],
        limit=10,
    )
    open_questions = unique_recent(
        [
            item
            for entry in entries
            if entry["role"] in {"assistant", "user"}
            for item in entry["questions"]
            if is_human_scale_sentence(item)
        ],
        limit=10,
    )

    decisions: list[str] = []
    known_facts: list[str] = []
    for entry in entries:
        if entry["role"] == "developer":
            continue
        if not entry["text"]:
            continue
        for sentence in sentence_candidates(entry["text"]):
            if not is_human_scale_sentence(sentence):
                continue
            lowered = sentence.lower()
            if lowered.startswith("decision:") or "fail closed" in lowered or "use codex_thread_id" in lowered:
                decisions.append(sentence)
            elif entry["role"] in {"assistant", "user"} and "?" not in sentence:
                known_facts.append(sentence)

    decisions = unique_recent(decisions, limit=10)
    known_facts = unique_recent(known_facts, limit=10)
    evidence = build_evidence(entries, limit=evidence_limit)

    return {
        "ok": True,
        "thread": thread,
        "warnings": warnings,
        "recall": {
            "summary": build_summary(decisions, blockers, open_questions, known_facts),
            "known_facts": known_facts,
            "decisions": decisions,
            "touched_paths": touched_paths,
            "commands": commands,
            "blockers": blockers,
            "open_questions": open_questions,
            "evidence": evidence,
            "counts": dict(Counter(entry["entry_type"] for entry in entries)),
        },
    }


def grep_rollout(
    pattern: str,
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error

    entries, parse_warnings = load_rollout(Path(thread["rollout_path"]))
    warnings.extend(parse_warnings)
    lowered_pattern = pattern.lower()
    matches = [
        {
            "entry_index": entry["entry_index"],
            "rollout_line": entry["rollout_line"],
            "timestamp": entry["timestamp"],
            "entry_type": entry["entry_type"],
            "payload_type": entry["payload_type"],
            "role": entry["role"],
            "excerpt": entry["excerpt"],
        }
        for entry in entries
        if lowered_pattern in entry["text"].lower()
    ][:limit]

    return {
        "ok": True,
        "thread": thread,
        "pattern": pattern,
        "results": matches,
        "warnings": warnings,
    }
