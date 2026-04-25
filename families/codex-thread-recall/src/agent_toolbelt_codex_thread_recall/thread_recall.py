from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


FILE_EXTENSION_PATTERN = "py|md|json|yaml|yml|toml|txt|sql|sqlite|ps1|bat|exe|js|ts|tsx|jsx|go|rs|java|c|cpp|h|hpp|sh|html|css"
WINDOWS_FILE_PATH_PATTERN = re.compile(rf"(?:\\\\\?\\)?[A-Za-z]:\\[^\r\n\"']+?\.(?:{FILE_EXTENSION_PATTERN})")
UNIX_FILE_PATH_PATTERN = re.compile(rf"/[^\r\n\"']+?\.(?:{FILE_EXTENSION_PATTERN})")
RELATIVE_FILE_PATH_PATTERN = re.compile(rf"(?<![A-Za-z0-9])(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.(?:{FILE_EXTENSION_PATTERN})")
QUESTION_PATTERN = re.compile(r"[^?]+\?")
BLOCKER_TOKENS = ("permission denied", "failed", "error", "timeout", "traceback", "exception")
RETRY_TOKENS = ("retry", "retrying", "retried")
DECISION_TOKENS = ("decision:", "fail closed", "do not", "prefer", "use ", "keep ", "will ")
GOAL_TOKENS = ("implement", "ship", "fix", "add", "update", "review", "check", "publish", "merge", "install", "refine", "plan", "build")
REPO_PATTERN = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b")
PR_PATTERN = re.compile(r"\bPR\s*`?#?(\d+)`?", re.IGNORECASE)
COMMIT_PATTERN = re.compile(r"\bcommit\s+`?([0-9a-f]{7,40})`?", re.IGNORECASE)
OID_PATTERN = re.compile(r'"oid"\s*:\s*"([0-9a-f]{7,40})"', re.IGNORECASE)
BACKTICK_PATTERN = re.compile(r"`([^`\r\n]{1,160})`")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._-]{2,120}$")
QUALIFIED_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$")
INSTRUCTION_WRAPPER_TOKENS = (
    "<skills_instructions>",
    "<plugins_instructions>",
    "<apps_instructions>",
    "<environment_context>",
    "<permissions instructions>",
    "<app-context>",
    "<collaboration_mode>",
)
SHIP_EVENT_KINDS = {"published", "merged", "pushed", "installed"}
GENERIC_PATH_PARENT_FALLBACKS = {"__init__", "readme", "skill", "main", "index", "cli", "app", "plugin"}
ENTITY_STOPWORDS = {
    "pr",
    "commit",
    "entry",
    "line",
    "marketplace",
    "marketplaces",
    "path",
    "paths",
    "plugin",
    "plugins",
    "published",
    "merged",
    "pushed",
    "installed",
    "enabled",
    "quick_validate",
    "readme",
    "rollout",
    "skill",
    "skills",
    "stderr",
    "stdout",
    "test",
    "tests",
    "traceback",
    "validate",
    "validated",
    "status",
}
GENERIC_RUNTIME_ENTITY_TOKENS = {
    "__main__",
    "apply_patch",
    "bash",
    "cmd",
    "curl",
    "git",
    "gh",
    "grep",
    "node",
    "npm",
    "npx",
    "pip",
    "pip3",
    "powershell",
    "pwsh",
    "py",
    "pathlib",
    "python",
    "python3",
    "rg",
    "sed",
    "sh",
    "sqlite3",
    "tempfile",
    "threading",
    "unittest",
    "uv",
    "uvx",
    "wget",
    "zsh",
}
GENERIC_PATH_SEGMENTS = {
    ".venv",
    "bin",
    "build",
    "debug",
    "dist",
    "lib",
    "release",
    "releases",
    "scripts",
    "site-packages",
    "src",
    "tests",
    "tools",
}
HELPER_PATH_PREFIXES = ("invoke_", "install_", "run_", "test_", "validate_", "debug_", "bootstrap_", "setup_")
HELPER_PATH_SUFFIXES = ("_wrapper", "_bootstrap", "_launcher", "_runtime", "_script", "_validate", "_helper", "_check")
HELPER_PATH_NAMES = {"bootstrap", "installer", "launcher", "runtime", "wrapper"}
ENTITY_SOURCE_BASE_WEIGHTS = {
    "qualified_id_prefix": 60,
    "path_parent_fallback": 45,
    "backtick_identifier": 40,
    "path_leaf": 25,
}
ENTITY_SOURCE_STRENGTH = {
    "path_leaf": 1,
    "backtick_identifier": 2,
    "path_parent_fallback": 3,
    "qualified_id_prefix": 4,
}
CONTENT_CLASSES = {"work", "meta", "command_output", "transcript_dump", "compaction"}
CACHE_SCHEMA_VERSION = 6
TEXT_SCAN_LIMIT = 2000
EVIDENCE_SCAN_LIMIT = 200
RAW_TEXT_STORE_LIMIT = 16000
INDEX_LOCK_POLL_SECONDS = 0.1
INDEX_LOCK_WAIT_SECONDS = 5.0
INDEX_LOCK_STALE_SECONDS = 300.0
EPISODE_GAP_SECONDS = 1800
EPISODE_DOMINANT_LIMIT = 5
FACET_TABLES: dict[str, tuple[str, str]] = {
    "paths": ("entry_paths", "path"),
    "blockers": ("entry_blockers", "blocker"),
    "retry_signals": ("entry_retry_signals", "retry_signal"),
    "questions": ("entry_questions", "question"),
    "goals": ("entry_goals", "goal"),
    "decisions": ("entry_decisions", "decision"),
    "facts": ("entry_facts", "fact"),
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


class IndexBusyError(RuntimeError):
    def __init__(self, message: str, *, lock_state: dict[str, Any]) -> None:
        super().__init__(message)
        self.lock_state = lock_state


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


def cache_root(codex_home: Path) -> Path:
    return cache_db_path(codex_home).parent


def thread_lock_path(codex_home: Path, thread_id: str) -> Path:
    digest = sha256(thread_id.encode("utf-8")).hexdigest()[:16]
    return cache_root(codex_home) / f"thread-{digest}.lock.json"


def runtime_context_from_env() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": os.getenv("CODEX_THREAD_RECALL_RUNTIME_MODE", "direct"),
        "python": os.getenv("CODEX_THREAD_RECALL_RUNTIME_PYTHON", sys.executable),
    }
    release_root = os.getenv("CODEX_THREAD_RECALL_RUNTIME_RELEASE_ROOT")
    repo_root = os.getenv("CODEX_THREAD_RECALL_RUNTIME_REPO_ROOT")
    if release_root:
        payload["release_root"] = release_root
    if repo_root:
        payload["repo_root"] = repo_root
    return payload


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


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_lock_metadata(lock_path: Path) -> dict[str, Any] | None:
    if not lock_path.is_file():
        return None
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def classify_lock_state(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {"state": "unlocked"}

    pid = metadata.get("pid")
    try:
        started_ts = parse_iso_timestamp(metadata.get("started_at"))
    except TypeError:
        started_ts = None
    age_seconds = None
    if started_ts is not None:
        age_seconds = max(0.0, (datetime.now(tz=UTC) - started_ts).total_seconds())
    pid_alive = isinstance(pid, int) and pid_is_running(pid)
    state = "locked"
    if age_seconds is not None and age_seconds > INDEX_LOCK_STALE_SECONDS:
        state = "stale"
    elif isinstance(pid, int) and not pid_alive:
        state = "stale"
    return {
        "state": state,
        "thread_id": metadata.get("thread_id"),
        "rollout_path": metadata.get("rollout_path"),
        "pid": pid,
        "started_at": metadata.get("started_at"),
        "age_seconds": age_seconds,
    }


class ThreadIndexLock:
    def __init__(self, *, codex_home: Path, thread: dict[str, Any]) -> None:
        self.path = thread_lock_path(codex_home, thread["id"])
        self.metadata = {
            "thread_id": thread["id"],
            "rollout_path": thread["rollout_path"],
            "pid": os.getpid(),
            "started_at": datetime.now(tz=UTC).isoformat(),
        }
        self.state = "acquired"
        self._acquired = False

    def acquire(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        started_wait = time.monotonic()
        waited = False
        reclaimed = False
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(self.metadata, handle, indent=2)
                    handle.write("\n")
                self._acquired = True
                if reclaimed:
                    self.state = "reclaimed-stale"
                elif waited:
                    self.state = "waited"
                return {"state": self.state, **self.metadata}
            except FileExistsError:
                existing = classify_lock_state(read_lock_metadata(self.path))
                if existing["state"] == "stale":
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        continue
                    reclaimed = True
                    continue
                if time.monotonic() - started_wait >= INDEX_LOCK_WAIT_SECONDS:
                    raise IndexBusyError(
                        "The thread recall index is currently being built by another live process.",
                        lock_state={**existing, "state": "busy"},
                    )
                waited = True
                time.sleep(INDEX_LOCK_POLL_SECONDS)

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            current = read_lock_metadata(self.path)
            if current is None or current.get("pid") == self.metadata["pid"]:
                self.path.unlink(missing_ok=True)
        finally:
            self._acquired = False

    def __enter__(self) -> dict[str, Any]:
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release()
        return False


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
    if "### " in cleaned:
        return False
    return True


def is_hex_oid(token: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{7,40}", token))


def looks_like_email(token: str) -> bool:
    if "@" not in token:
        return False
    local, domain = token.split("@", 1)
    return bool(local) and "." in domain


def is_generic_runtime_entity(token: str) -> bool:
    lowered = token.strip().lower()
    if lowered.endswith(".exe"):
        lowered = lowered[:-4]
    return lowered in GENERIC_RUNTIME_ENTITY_TOKENS


def looks_like_helper_path_basename(token: str) -> bool:
    lowered = token.strip().lower()
    return (
        lowered in HELPER_PATH_NAMES
        or any(lowered.startswith(prefix) for prefix in HELPER_PATH_PREFIXES)
        or any(lowered.endswith(suffix) for suffix in HELPER_PATH_SUFFIXES)
    )


def looks_like_env_var_token(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", token))


def looks_like_bare_filename(token: str) -> bool:
    return bool(re.fullmatch(rf"[A-Za-z0-9_.-]+\.(?:{FILE_EXTENSION_PATTERN})", token))


def build_entity_mention(entity: str, *, source_kind: str, source_text: str) -> dict[str, Any] | None:
    normalized = normalize_entity_candidate(entity)
    if normalized is None:
        return None
    return {
        "entity": normalized,
        "source_kind": source_kind,
        "source_text": source_text,
        "base_weight": ENTITY_SOURCE_BASE_WEIGHTS[source_kind],
    }


def normalize_entity_candidate(candidate: str) -> str | None:
    cleaned = candidate.strip("`'\".,)")
    if cleaned.endswith(".cli"):
        cleaned = cleaned[:-4] + "-cli"
    if (
        not cleaned
        or cleaned.isdigit()
        or is_hex_oid(cleaned)
        or looks_like_env_var_token(cleaned)
        or looks_like_bare_filename(cleaned)
        or "/" in cleaned
        or "\\" in cleaned
        or not IDENTIFIER_PATTERN.fullmatch(cleaned)
        or cleaned.lower() in ENTITY_STOPWORDS
        or is_generic_runtime_entity(cleaned)
    ):
        return None
    return cleaned


def nearest_meaningful_parent_candidate(parts: list[str]) -> str | None:
    for part in reversed(parts[:-1]):
        cleaned = part.strip()
        if not cleaned or cleaned == "?" or cleaned.lower() in GENERIC_PATH_SEGMENTS:
            continue
        normalized_candidate = normalize_entity_candidate(cleaned)
        if normalized_candidate is not None:
            return normalized_candidate
    return None


def entity_mentions_from_path(path: str) -> list[dict[str, Any]]:
    normalized = path.strip().rstrip("\\/").replace("/", "\\")
    parts = [part for part in normalized.split("\\") if part and part != "?"]
    if not parts:
        return []
    leaf = parts[-1]
    candidate = leaf.rsplit(".", 1)[0] if "." in leaf else leaf
    if is_generic_runtime_entity(candidate):
        return []
    if candidate.lower() in GENERIC_PATH_PARENT_FALLBACKS or looks_like_helper_path_basename(candidate):
        fallback = nearest_meaningful_parent_candidate(parts)
        if fallback is None:
            return []
        mention = build_entity_mention(fallback, source_kind="path_parent_fallback", source_text=path)
        return [mention] if mention is not None else []
    mention = build_entity_mention(candidate, source_kind="path_leaf", source_text=path)
    return [mention] if mention is not None else []


def entity_candidates_from_path(path: str) -> list[str]:
    return [mention["entity"] for mention in entity_mentions_from_path(path)]


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


def heading_candidates(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        heading = stripped.lstrip("#").strip()
        if heading:
            headings.append(heading)
    return headings


def extract_goals(text: str, *, role: str | None) -> list[str]:
    goals: list[str] = []
    for heading in heading_candidates(text):
        if is_human_scale_sentence(heading):
            goals.append(heading)
    for sentence in sentence_candidates(text):
        if not is_human_scale_sentence(sentence):
            continue
        lowered = sentence.lower()
        if role == "user":
            if lowered.startswith("please ") or any(f" {token}" in f" {lowered} " for token in GOAL_TOKENS):
                goals.append(sentence)
        elif role == "assistant":
            if lowered.startswith(("i'm ", "i am ", "i will ", "i'll ", "next ")):
                goals.append(sentence)
    return unique_preserving_order(goals, limit=8)


def extract_decisions(text: str, *, role: str | None) -> list[str]:
    if role not in {"assistant", "user"}:
        return []
    decisions: list[str] = []
    for sentence in sentence_candidates(text):
        if not is_human_scale_sentence(sentence):
            continue
        lowered = sentence.lower()
        if lowered.startswith("decision:") or any(token in lowered for token in DECISION_TOKENS):
            decisions.append(sentence)
    return unique_preserving_order(decisions, limit=8)


def extract_facts(
    text: str,
    *,
    role: str | None,
    blockers: list[str],
    retry_signals: list[str],
    questions: list[str],
    goals: list[str],
    decisions: list[str],
) -> list[str]:
    if role not in {"assistant", "user"}:
        return []
    excluded = {" ".join(item.split()) for item in [*blockers, *retry_signals, *questions, *goals, *decisions] if item}
    facts: list[str] = []
    for sentence in sentence_candidates(text):
        cleaned = " ".join(sentence.split())
        if not is_human_scale_sentence(cleaned) or cleaned in excluded or "?" in cleaned:
            continue
        facts.append(cleaned)
    return unique_preserving_order(facts, limit=10)


def looks_like_instruction_envelope(text: str, *, role: str | None) -> tuple[bool, str | None]:
    lowered = text.lower()
    if role == "developer":
        return True, "developer"
    if lowered.startswith("please implement this plan:") or "<proposed_plan>" in lowered:
        return True, "plan-boilerplate"
    if any(token in lowered for token in INSTRUCTION_WRAPPER_TOKENS):
        return True, "instruction-envelope"
    return False, None


def looks_like_transcript_dump(text: str) -> bool:
    score = 0
    line_wrapped_envelopes = len(re.findall(r'(?m)^\d+:\{', text))
    if line_wrapped_envelopes >= 2:
        score += 2
    if re.search(r'(?m)^\d+:\{"timestamp":', text) and '"payload"' in text and text.count('"type"') >= 2:
        score += 2
    if text.count('{"timestamp"') >= 2:
        score += 1
    if text.count('"payload"') >= 2 and text.count('"type"') >= 3:
        score += 1
    if len(re.findall(r"(?m)^LINE \d+ ENTRY ", text)) >= 2:
        score += 1
    if len(text) < 120 and score < 2:
        return False
    return score >= 2


def classify_content(
    text: str,
    *,
    entry_type: str | None,
    payload_type: str | None,
    role: str | None,
) -> tuple[str, bool, str | None]:
    compact = " ".join(text.split())
    if entry_type == "compacted":
        return "compaction", True, "compaction-marker"
    if not compact:
        return "work", False, None
    is_meta, meta_reason = looks_like_instruction_envelope(compact, role=role)
    if is_meta:
        return "meta", True, meta_reason
    if looks_like_transcript_dump(text):
        return "transcript_dump", True, "transcript-dump"
    if payload_type in {"function_call_output", "exec_command_end"}:
        if len(compact) > 1400 and not any(token in compact.lower() for token in BLOCKER_TOKENS + RETRY_TOKENS):
            return "command_output", True, "oversized-output"
        return "command_output", False, None
    if len(compact) > 1400 and not any(token in compact.lower() for token in BLOCKER_TOKENS + RETRY_TOKENS):
        return "work", True, "oversized-output"
    return "work", False, None


def extract_entities(text: str) -> list[str]:
    return unique_preserving_order([mention["entity"] for mention in extract_entity_mentions(text)])


def extract_entity_mentions(text: str) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(mention: dict[str, Any] | None) -> None:
        if mention is None:
            return
        key = (mention["entity"], mention["source_kind"], mention["source_text"])
        if key in seen:
            return
        mentions.append(mention)
        seen.add(key)

    for path in extract_paths(text):
        for mention in entity_mentions_from_path(path):
            add(mention)
    for token in BACKTICK_PATTERN.findall(text):
        cleaned = token.strip()
        if QUALIFIED_ID_PATTERN.fullmatch(cleaned) and not looks_like_email(cleaned):
            add(build_entity_mention(cleaned.split("@", 1)[0], source_kind="qualified_id_prefix", source_text=cleaned))
            continue
        if "/" in cleaned or "\\" in cleaned:
            for path in extract_paths(cleaned):
                for mention in entity_mentions_from_path(path):
                    add(mention)
            continue
        add(build_entity_mention(cleaned, source_kind="backtick_identifier", source_text=cleaned))
    return mentions


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


def has_ship_anchor(
    *,
    paths: list[str],
    entities: list[str],
    repos: list[str],
    pr_numbers: list[int],
    commit_oids: list[str],
    qualified_ids: list[str],
) -> bool:
    return bool(paths or entities or repos or pr_numbers or commit_oids or qualified_ids)


def detect_event_kinds(
    text: str,
    *,
    entry_type: str | None,
    payload_type: str | None,
    role: str | None,
    content_class: str,
    paths: list[str],
    entities: list[str],
    repos: list[str],
    pr_numbers: list[int],
    commit_oids: list[str],
    qualified_ids: list[str],
) -> list[str]:
    lowered = text.lower()
    kinds: list[str] = []
    if payload_type == "Plan" or "<proposed_plan>" in lowered or "please implement this plan" in lowered:
        kinds.append("planned")
    if entry_type == "response_item" and payload_type == "function_call":
        kinds.append("implementation_started")
    ship_anchor = has_ship_anchor(
        paths=paths,
        entities=entities,
        repos=repos,
        pr_numbers=pr_numbers,
        commit_oids=commit_oids,
        qualified_ids=qualified_ids,
    )
    ship_eligible = role != "user" and content_class in {"work", "meta"} and ship_anchor
    if ship_eligible and "published" in lowered:
        kinds.append("published")
    if ship_eligible and ("merged" in lowered or '"state":"merged"' in lowered or '"state": "merged"' in lowered):
        kinds.append("merged")
    if ship_eligible and "pushed" in lowered:
        kinds.append("pushed")
    if ship_eligible and ("installed" in lowered or "enabled" in lowered):
        kinds.append("installed")
    if role != "user" and content_class in {"work", "meta"} and ("validate" in lowered or "passed" in lowered):
        kinds.append("validated")
    return unique_preserving_order(kinds)


def classify_search_text(
    text: str,
    *,
    content_class: str,
    is_noise: bool,
) -> str:
    compact = " ".join(text.split())
    lowered = compact.lower()
    if not compact:
        return ""
    if content_class in {"meta", "transcript_dump", "compaction"}:
        return ""
    if is_noise and not any(token in lowered for token in BLOCKER_TOKENS + RETRY_TOKENS):
        return ""
    return compact


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
            "content_class": "compaction",
            "command": None,
            "raw_text": "Context compacted.",
            "search_text": "",
            "excerpt": "Context compacted.",
            "paths": [],
            "blockers": [],
            "retry_signals": [],
            "questions": [],
            "goals": [],
            "decisions": [],
            "facts": [],
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
    content_class, is_noise, noise_reason = classify_content(
        analysis_text,
        entry_type=entry.get("type"),
        payload_type=payload.get("type"),
        role=role,
    )
    paths = extract_paths(analysis_text)
    entity_mentions = extract_entity_mentions(analysis_text)
    entities = unique_preserving_order([mention["entity"] for mention in entity_mentions])
    repos = extract_repos(analysis_text)
    pr_numbers = extract_pr_numbers(analysis_text)
    commit_oids = extract_commit_oids(analysis_text)
    qualified_ids = extract_qualified_ids(analysis_text)
    blockers = extract_blockers(analysis_text)
    retry_signals = extract_retry_signals(analysis_text)
    goals = extract_goals(analysis_text, role=role)
    decisions = extract_decisions(analysis_text, role=role) if content_class == "work" else []
    questions = extract_questions(analysis_text)
    facts = extract_facts(
        analysis_text,
        role=role,
        blockers=blockers,
        retry_signals=retry_signals,
        questions=questions,
        goals=goals,
        decisions=decisions,
    ) if content_class == "work" else []
    if content_class == "transcript_dump":
        entity_mentions = []
        paths = []
        entities = []
        repos = []
        pr_numbers = []
        commit_oids = []
        qualified_ids = []
        blockers = []
        retry_signals = []
        goals = []
        decisions = []
        questions = []
        facts = []
    event_kinds = detect_event_kinds(
        analysis_text,
        entry_type=entry.get("type"),
        payload_type=payload.get("type"),
        role=role,
        content_class=content_class,
        paths=paths,
        entities=entities,
        repos=repos,
        pr_numbers=pr_numbers,
        commit_oids=commit_oids,
        qualified_ids=qualified_ids,
    )
    search_text = classify_search_text(
        analysis_text,
        content_class=content_class,
        is_noise=is_noise,
    )
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
        "content_class": content_class,
        "command": command,
        "raw_text": raw_text,
        "search_text": search_text,
        "excerpt": summarize_text(search_text or analysis_text) if (search_text or analysis_text) else "",
        "paths": paths,
        "blockers": blockers,
        "retry_signals": retry_signals,
        "questions": questions,
        "goals": goals,
        "decisions": decisions,
        "facts": facts,
        "entity_mentions": entity_mentions,
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
        drop table if exists entry_episode_links;
        drop table if exists episodes;
        drop table if exists entry_paths;
        drop table if exists entry_blockers;
        drop table if exists entry_retry_signals;
        drop table if exists entry_questions;
        drop table if exists entry_goals;
        drop table if exists entry_decisions;
        drop table if exists entry_facts;
        drop table if exists entry_entity_mentions;
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
            "last_rebuild_reason",
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
            "content_class",
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
            noise_filtered_count integer not null,
            last_rebuild_reason text
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
            noise_reason text,
            content_class text not null
        );

        create table if not exists episodes (
            id integer primary key,
            thread_id text not null,
            episode_index integer not null,
            started_entry_index integer not null,
            ended_entry_index integer not null,
            started_at text,
            ended_at text,
            entry_count integer not null,
            work_entry_count integer not null,
            boundary_reason text
        );

        create table if not exists entry_episode_links (
            entry_id integer primary key references entries(id) on delete cascade,
            episode_id integer not null references episodes(id) on delete cascade
        );

        create table if not exists entry_entity_mentions (
            entry_id integer not null references entries(id) on delete cascade,
            entity text not null,
            source_kind text not null,
            source_text text not null,
            base_weight integer not null,
            is_work_eligible integer not null,
            is_ship_eligible integer not null
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
    conn.execute("create index if not exists idx_entries_class on entries(thread_id, content_class, entry_index)")
    conn.execute("create index if not exists idx_episodes_thread on episodes(thread_id, episode_index)")
    conn.execute("create index if not exists idx_episode_links_episode on entry_episode_links(episode_id)")
    conn.execute("create index if not exists idx_entry_entity_mentions_entry on entry_entity_mentions(entry_id)")
    conn.execute("create index if not exists idx_entry_entity_mentions_entity on entry_entity_mentions(entity)")
    conn.execute("create index if not exists idx_entry_entity_mentions_entity_entry on entry_entity_mentions(entity, entry_id)")
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
               built_at, entry_count, noise_filtered_count, last_rebuild_reason
        from rollout_indexes
        where thread_id = ?
        """,
        (thread_id,),
    ).fetchone()


def clear_thread_cache(conn: sqlite3.Connection, thread_id: str) -> None:
    conn.execute(
        "delete from entry_episode_links where episode_id in (select id from episodes where thread_id = ?)",
        (thread_id,),
    )
    conn.execute("delete from episodes where thread_id = ?", (thread_id,))
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


def insert_entry_entity_mentions(conn: sqlite3.Connection, entry_id: int, entry: dict[str, Any]) -> None:
    mentions = entry.get("entity_mentions", [])
    if not mentions:
        return
    is_work_eligible = int(entry["content_class"] == "work" and entry["is_noise"] is False and entry["role"] in {"assistant", "user"})
    is_ship_eligible = int(
        is_work_eligible == 1 and any(kind in SHIP_EVENT_KINDS for kind in entry["event_kinds"])
    )
    conn.executemany(
        """
        insert into entry_entity_mentions (
            entry_id, entity, source_kind, source_text, base_weight, is_work_eligible, is_ship_eligible
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                entry_id,
                mention["entity"],
                mention["source_kind"],
                mention["source_text"],
                int(mention["base_weight"]),
                is_work_eligible,
                is_ship_eligible,
            )
            for mention in mentions
        ],
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
                thread_id, entry_index, rollout_line, timestamp, entry_type, payload_type, role, content_class,
                command, raw_text, search_text, excerpt, is_noise, noise_reason
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                entry["entry_index"],
                entry["rollout_line"],
                entry["timestamp"],
                entry["entry_type"],
                entry["payload_type"],
                entry["role"],
                entry["content_class"],
                entry["command"],
                entry["raw_text"],
                entry["search_text"],
                entry["excerpt"],
                int(entry["is_noise"]),
                entry["noise_reason"],
            ),
        )
        insert_entry_facets(conn, int(cursor.lastrowid), entry)
        insert_entry_entity_mentions(conn, int(cursor.lastrowid), entry)


def all_entries_for_thread(conn: sqlite3.Connection, thread_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select id, entry_index, rollout_line, timestamp, entry_type, payload_type, role, content_class,
               command, raw_text, search_text, excerpt, is_noise, noise_reason
        from entries
        where thread_id = ?
        order by entry_index
        """,
        (thread_id,),
    ).fetchall()
    entry_ids = [int(row["id"]) for row in rows]
    facet_map = load_facets_for_entries(conn, entry_ids)
    output: list[dict[str, Any]] = []
    for row in rows:
        entry_id = int(row["id"])
        item = entry_from_row(row, facet_map[entry_id])
        output.append(item)
    return output


def entry_scope_anchors(entry: dict[str, Any]) -> list[str]:
    return [*entry["entities"], *entry["repos"], *[str(value) for value in entry["qualified_ids"]]]


def entry_is_anchor_source(entry: dict[str, Any]) -> bool:
    return entry["content_class"] == "work" and entry["is_noise"] is False and entry["role"] in {"assistant", "user"}


def entry_is_episode_candidate(entry: dict[str, Any]) -> bool:
    if entry["content_class"] == "transcript_dump":
        return False
    if entry["content_class"] == "meta" and entry["role"] != "user":
        return False
    return True


def entry_is_episode_work(entry: dict[str, Any]) -> bool:
    return entry["content_class"] in {"work", "command_output"} and entry["is_noise"] is False


def episode_dominant_anchors(entries: list[dict[str, Any]]) -> set[str]:
    counter: Counter[str] = Counter()
    for entry in entries:
        if not entry_is_anchor_source(entry):
            continue
        counter.update(entry_scope_anchors(entry))
    return {value for value, _count in counter.most_common(EPISODE_DOMINANT_LIMIT)}


def should_start_new_episode(
    current_entries: list[dict[str, Any]],
    entry: dict[str, Any],
) -> str | None:
    if not current_entries:
        return None
    current_work_entries = [item for item in current_entries if entry_is_episode_work(item)]
    previous_relevant = next((item for item in reversed(current_entries) if entry_is_episode_candidate(item)), None)
    if previous_relevant is not None:
        gap = elapsed_seconds(previous_relevant["timestamp"], entry["timestamp"])
        if gap is not None and gap > EPISODE_GAP_SECONDS and len(current_work_entries) >= 2:
            return "time-gap"
    if entry["role"] == "user":
        if any(
            item["content_class"] in {"work", "command_output"}
            and kind in SHIP_EVENT_KINDS
            for item in current_entries
            for kind in item["event_kinds"]
        ):
            return "post-ship-user-request"
        current_dominant = episode_dominant_anchors(current_entries)
        next_anchors = set(entry_scope_anchors(entry))
        if current_dominant and next_anchors and current_dominant.isdisjoint(next_anchors) and len(current_work_entries) >= 2:
            return "dominant-anchor-shift"
    elif entry_scope_anchors(entry):
        current_dominant = episode_dominant_anchors(current_entries)
        next_anchors = set(entry_scope_anchors(entry))
        if current_dominant and next_anchors and current_dominant.isdisjoint(next_anchors) and len(current_work_entries) >= 5:
            return "dominant-anchor-shift"
    return None


def rebuild_thread_episodes(conn: sqlite3.Connection, *, thread_id: str) -> None:
    entries = all_entries_for_thread(conn, thread_id)
    conn.execute(
        "delete from entry_episode_links where episode_id in (select id from episodes where thread_id = ?)",
        (thread_id,),
    )
    conn.execute("delete from episodes where thread_id = ?", (thread_id,))
    if not entries:
        return

    episodes: list[dict[str, Any]] = []
    current_entries: list[dict[str, Any]] = []
    current_reason = "thread-start"

    def flush_episode() -> None:
        nonlocal current_entries, current_reason
        if not current_entries:
            return
        episode_index = len(episodes) + 1
        episodes.append(
            {
                "episode_index": episode_index,
                "started_entry_index": current_entries[0]["entry_index"],
                "ended_entry_index": current_entries[-1]["entry_index"],
                "started_at": current_entries[0]["timestamp"],
                "ended_at": current_entries[-1]["timestamp"],
                "entry_count": len(current_entries),
                "work_entry_count": sum(1 for item in current_entries if entry_is_episode_work(item)),
                "boundary_reason": current_reason,
                "entry_ids": [item["id"] for item in current_entries],
            }
        )
        current_entries = []
        current_reason = "thread-start"

    for entry in entries:
        if not current_entries:
            current_entries = [entry]
            continue
        boundary_reason = should_start_new_episode(current_entries, entry)
        if boundary_reason is not None:
            flush_episode()
            current_reason = boundary_reason
        current_entries.append(entry)
    flush_episode()

    for episode in episodes:
        cursor = conn.execute(
            """
            insert into episodes (
                thread_id, episode_index, started_entry_index, ended_entry_index,
                started_at, ended_at, entry_count, work_entry_count, boundary_reason
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                episode["episode_index"],
                episode["started_entry_index"],
                episode["ended_entry_index"],
                episode["started_at"],
                episode["ended_at"],
                episode["entry_count"],
                episode["work_entry_count"],
                episode["boundary_reason"],
            ),
        )
        episode_id = int(cursor.lastrowid)
        conn.executemany(
            "insert into entry_episode_links (entry_id, episode_id) values (?, ?)",
            [(entry_id, episode_id) for entry_id in episode["entry_ids"]],
        )

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
    last_rebuild_reason: str | None,
    built_at: str | None = None,
) -> None:
    conn.execute(
        """
        insert into rollout_indexes (
            thread_id, schema_version, rollout_path, rollout_size, rollout_mtime_ns,
            last_indexed_offset, last_indexed_line, last_indexed_entry,
            built_at, entry_count, noise_filtered_count, last_rebuild_reason
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            noise_filtered_count = excluded.noise_filtered_count,
            last_rebuild_reason = excluded.last_rebuild_reason
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
            built_at or datetime.now(tz=UTC).isoformat(),
            entry_count,
            noise_filtered_count,
            last_rebuild_reason,
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
    rebuild_reason: str,
) -> None:
    clear_thread_cache(conn, thread["id"])
    insert_entries(conn, thread_id=thread["id"], entries=entries)
    rebuild_thread_episodes(conn, thread_id=thread["id"])
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
        last_rebuild_reason=rebuild_reason,
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
    rebuild_reason: str,
) -> None:
    insert_entries(conn, thread_id=thread["id"], entries=new_entries)
    rebuild_thread_episodes(conn, thread_id=thread["id"])
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
        last_rebuild_reason=rebuild_reason,
    )
    conn.commit()


def thread_entry_stats(conn: sqlite3.Connection, thread_id: str) -> sqlite3.Row:
    return conn.execute(
        """
        select count(*) as entry_rows,
               coalesce(max(entry_index), 0) as max_entry_index,
               coalesce(max(rollout_line), 0) as max_rollout_line
        from entries
        where thread_id = ?
        """,
        (thread_id,),
    ).fetchone()


def cache_rebuild_reason(
    *,
    existing: sqlite3.Row | None,
    thread_stats: sqlite3.Row,
    rollout_path: Path,
    rollout_size: int,
    rollout_mtime_ns: int,
) -> tuple[str | None, bool]:
    entry_rows = int(thread_stats["entry_rows"])
    if existing is None:
        return ("initial-build" if entry_rows == 0 else "orphaned-thread-cache"), False

    if int(existing["schema_version"]) != CACHE_SCHEMA_VERSION:
        return "schema-version-mismatch", True
    if existing["rollout_path"] != str(rollout_path):
        return "rollout-path-changed", True
    if rollout_size < int(existing["rollout_size"]) or rollout_size < int(existing["last_indexed_offset"]):
        return "rollout-truncated", True
    if entry_rows != int(existing["entry_count"]):
        return "entry-count-mismatch", True
    if entry_rows and int(thread_stats["max_entry_index"]) != int(existing["last_indexed_entry"]):
        return "entry-index-mismatch", True
    if int(thread_stats["max_rollout_line"]) and int(thread_stats["max_rollout_line"]) < int(existing["last_indexed_line"]):
        return "rollout-line-mismatch", True
    if rollout_size > int(existing["rollout_size"]):
        return "append-rollout-growth", False
    if rollout_size == int(existing["rollout_size"]) and rollout_mtime_ns != int(existing["rollout_mtime_ns"]):
        return "metadata-drift", False
    return None, False


def refresh_rollout_metadata(
    conn: sqlite3.Connection,
    *,
    thread: dict[str, Any],
    existing: sqlite3.Row,
    rollout_size: int,
    rollout_mtime_ns: int,
) -> None:
    upsert_rollout_index(
        conn,
        thread=thread,
        rollout_size=rollout_size,
        rollout_mtime_ns=rollout_mtime_ns,
        last_indexed_offset=int(existing["last_indexed_offset"]),
        last_indexed_line=int(existing["last_indexed_line"]),
        last_indexed_entry=int(existing["last_indexed_entry"]),
        entry_count=int(existing["entry_count"]),
        noise_filtered_count=int(existing["noise_filtered_count"]),
        last_rebuild_reason=existing["last_rebuild_reason"],
        built_at=existing["built_at"],
    )
    conn.commit()


def index_meta_payload(
    codex_home: Path,
    metadata_row: sqlite3.Row | None,
    *,
    built: bool,
    stale: bool,
    appended_entries: int,
    lock_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "used": True,
        "built": built,
        "stale": stale,
        "entry_count": int(metadata_row["entry_count"]) if metadata_row is not None else 0,
        "noise_filtered_count": int(metadata_row["noise_filtered_count"]) if metadata_row is not None else 0,
        "appended_entries": appended_entries,
        "schema_version": int(metadata_row["schema_version"]) if metadata_row is not None else CACHE_SCHEMA_VERSION,
        "cache_path": str(cache_db_path(codex_home)),
        "last_indexed_line": int(metadata_row["last_indexed_line"]) if metadata_row is not None else 0,
        "last_indexed_offset": int(metadata_row["last_indexed_offset"]) if metadata_row is not None else 0,
        "built_at": metadata_row["built_at"] if metadata_row is not None else None,
        "last_rebuild_reason": metadata_row["last_rebuild_reason"] if metadata_row is not None else None,
        "lock_state": lock_state,
    }


def ensure_index(
    conn: sqlite3.Connection,
    *,
    thread: dict[str, Any],
    codex_home: Path,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    rollout_path = Path(thread["rollout_path"])
    rollout_size, rollout_mtime_ns = rollout_signature(rollout_path)
    ensure_cache_schema(conn)
    existing = cache_metadata_row(conn, thread["id"])
    thread_stats = thread_entry_stats(conn, thread["id"])

    built = False
    stale = False
    appended_entries = 0
    lock_state = classify_lock_state(read_lock_metadata(thread_lock_path(codex_home, thread["id"])))

    rebuild_reason, force_rebuild = cache_rebuild_reason(
        existing=existing,
        thread_stats=thread_stats,
        rollout_path=rollout_path,
        rollout_size=rollout_size,
        rollout_mtime_ns=rollout_mtime_ns,
    )

    def _reload_state() -> tuple[sqlite3.Row | None, sqlite3.Row]:
        ensure_cache_schema(conn)
        refreshed_existing = cache_metadata_row(conn, thread["id"])
        refreshed_stats = thread_entry_stats(conn, thread["id"])
        return refreshed_existing, refreshed_stats

    if rebuild_reason == "metadata-drift" and existing is not None:
        refresh_rollout_metadata(
            conn,
            thread=thread,
            existing=existing,
            rollout_size=rollout_size,
            rollout_mtime_ns=rollout_mtime_ns,
        )
    elif rebuild_reason is not None:
        with ThreadIndexLock(codex_home=codex_home, thread=thread) as active_lock_state:
            lock_state = active_lock_state
            existing, thread_stats = _reload_state()
            rebuild_reason, force_rebuild = cache_rebuild_reason(
                existing=existing,
                thread_stats=thread_stats,
                rollout_path=rollout_path,
                rollout_size=rollout_size,
                rollout_mtime_ns=rollout_mtime_ns,
            )
            if rebuild_reason == "metadata-drift" and existing is not None:
                refresh_rollout_metadata(
                    conn,
                    thread=thread,
                    existing=existing,
                    rollout_size=rollout_size,
                    rollout_mtime_ns=rollout_mtime_ns,
                )
            elif rebuild_reason is not None:
                if existing is None or force_rebuild or rebuild_reason != "append-rollout-growth":
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
                        rebuild_reason=rebuild_reason,
                    )
                    built = True
                    stale = rebuild_reason != "initial-build"
                elif existing is not None:
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
                            rebuild_reason=rebuild_reason,
                        )
                        built = True
                        stale = True
                        appended_entries = len(new_entries)

    metadata_row = cache_metadata_row(conn, thread["id"])
    return index_meta_payload(
        codex_home,
        metadata_row,
        built=built,
        stale=stale,
        appended_entries=appended_entries,
        lock_state=lock_state,
    ), warnings


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
        "content_class": row["content_class"],
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
        select id, entry_index, rollout_line, timestamp, entry_type, payload_type, role, content_class,
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
        "content_class": entry["content_class"],
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
    scope_info: dict[str, Any] | None = None,
    extra_where: str = "",
    params: tuple[Any, ...] = (),
) -> list[Any]:
    table_name, column_name = FACET_TABLES[facet_name]
    scoped_sql, scoped_params = scope_clause(scope_info or {"applied": "thread"}, alias="e")
    rows = conn.execute(
        f"""
        select f.{column_name} as value, max(e.entry_index) as latest_index
        from {table_name} f
        join entries e on e.id = f.entry_id
        where e.thread_id = ? {scoped_sql} {extra_where}
        group by f.{column_name}
        order by latest_index desc
        limit ?
        """,
        (thread_id, *scoped_params, *params, limit),
    ).fetchall()
    return [row["value"] for row in rows]


def recent_commands(conn: sqlite3.Connection, *, thread_id: str, limit: int, scope_info: dict[str, Any]) -> list[str]:
    scoped_sql, scoped_params = scope_clause(scope_info, alias="entries")
    rows = conn.execute(
        """
        select command
        from entries
        where thread_id = ? {scoped_sql} and command is not null and command != ''
        order by entry_index desc
        limit 250
        """.format(scoped_sql=scoped_sql),
        (thread_id, *scoped_params),
    ).fetchall()
    return unique_recent([row["command"] for row in rows], limit=limit)


def aggregate_counts(conn: sqlite3.Connection, *, thread_id: str, scope_info: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    scoped_sql, scoped_params = scope_clause(scope_info, alias="entries")
    entry_counts = {
        row["entry_type"]: int(row["count"])
        for row in conn.execute(
            """
            select entry_type, count(*) as count
            from entries
            where thread_id = ? {scoped_sql}
            group by entry_type
            """.format(scoped_sql=scoped_sql),
            (thread_id, *scoped_params),
        ).fetchall()
    }
    scoped_event_sql, scoped_event_params = scope_clause(scope_info, alias="e")
    event_counts = {
        row["event_kind"]: int(row["count"])
        for row in conn.execute(
            """
            select ek.event_kind, count(*) as count
            from entry_event_kinds ek
            join entries e on e.id = ek.entry_id
            where e.thread_id = ? {scoped_sql}
            group by ek.event_kind
            """.format(scoped_sql=scoped_event_sql),
            (thread_id, *scoped_event_params),
        ).fetchall()
    }
    return entry_counts, event_counts


def ranked_entity_score(item: dict[str, Any]) -> int:
    score = int(item["base_weight_sum"])
    if item["has_user_goal"]:
        score += 80
    if item["has_assistant_semantic"]:
        score += 35
    if item["has_ship_event"]:
        score += 25
    if item["has_user_work"] and item["has_assistant_work"]:
        score += 30
    score += max(0, min(int(item["work_entry_count"]), 6) - 1) * 5
    return score


def collaborative_entity_signal(item: dict[str, Any]) -> bool:
    return bool(item["has_user_goal"] or (item["has_user_work"] and item["has_assistant_work"]))


def ranked_entity_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -int(item["score"]),
        -int(item["strongest_source_rank"]),
        -int(item["has_user_work"]),
        -len(item["entity"]),
        item["entity"],
    )


def ranked_entity_rows(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    scope_info: dict[str, Any],
    include_meta: bool = False,
    kind_filter: set[str] | None = None,
    prefer_collaborative: bool = False,
) -> list[dict[str, Any]]:
    scoped_sql, scoped_params = scope_clause(scope_info, alias="e")
    eligibility_sql = "m.is_work_eligible = 1"
    if include_meta:
        eligibility_sql = f"({eligibility_sql} or e.content_class = 'meta')"
    selected_kind_sql = "0 as has_selected_kind,"
    if kind_filter:
        kind_literals = ", ".join(f"'{value}'" for value in sorted(kind_filter))
        selected_kind_sql = f"""
            max(case when exists (
                select 1 from entry_event_kinds ek
                where ek.entry_id = e.id and ek.event_kind in ({kind_literals})
            ) then 1 else 0 end) as has_selected_kind,
        """
    rows = conn.execute(
        f"""
        select
            m.entity,
            sum(m.base_weight) as base_weight_sum,
            max(
                case m.source_kind
                    when 'qualified_id_prefix' then 4
                    when 'path_parent_fallback' then 3
                    when 'backtick_identifier' then 2
                    when 'path_leaf' then 1
                    else 0
                end
            ) as strongest_source_rank,
            max(case when e.role = 'user' and exists (select 1 from entry_goals g where g.entry_id = e.id) then 1 else 0 end) as has_user_goal,
            max(case when e.role = 'assistant' and (exists (select 1 from entry_decisions d where d.entry_id = e.id) or exists (select 1 from entry_facts f where f.entry_id = e.id)) then 1 else 0 end) as has_assistant_semantic,
            max(case when m.is_ship_eligible = 1 then 1 else 0 end) as has_ship_event,
            max(case when e.role = 'user' and m.is_work_eligible = 1 then 1 else 0 end) as has_user_work,
            max(case when e.role = 'assistant' and m.is_work_eligible = 1 then 1 else 0 end) as has_assistant_work,
            count(distinct case when m.is_work_eligible = 1 then e.id end) as work_entry_count,
            count(distinct e.id) as eligible_entry_count,
            {selected_kind_sql}
            min(case when m.is_work_eligible = 1 then e.timestamp end) as first_work_timestamp,
            min(e.timestamp) as first_eligible_timestamp
        from entry_entity_mentions m
        join entries e on e.id = m.entry_id
        where e.thread_id = ?
          {scoped_sql}
          and {eligibility_sql}
        group by m.entity
        """,
        (thread_id, *scoped_params),
    ).fetchall()
    ranked_rows: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "entity": row["entity"],
            "base_weight_sum": int(row["base_weight_sum"] or 0),
            "strongest_source_rank": int(row["strongest_source_rank"] or 0),
            "has_user_goal": bool(row["has_user_goal"]),
            "has_assistant_semantic": bool(row["has_assistant_semantic"]),
            "has_ship_event": bool(row["has_ship_event"]),
            "has_user_work": bool(row["has_user_work"]),
            "has_assistant_work": bool(row["has_assistant_work"]),
            "work_entry_count": int(row["work_entry_count"] or 0),
            "eligible_entry_count": int(row["eligible_entry_count"] or 0),
            "has_selected_kind": bool(row["has_selected_kind"]),
            "first_seen_at": row["first_work_timestamp"] or row["first_eligible_timestamp"],
        }
        if kind_filter is not None:
            item["has_ship_event"] = item["has_selected_kind"]
        item["score"] = ranked_entity_score(item)
        ranked_rows.append(item)
    if kind_filter is not None:
        ranked_rows = [item for item in ranked_rows if item["has_selected_kind"]]
    if prefer_collaborative and any(collaborative_entity_signal(item) for item in ranked_rows):
        ranked_rows = [item for item in ranked_rows if collaborative_entity_signal(item)]
    ranked_rows.sort(key=ranked_entity_sort_key)
    return ranked_rows


def ranked_entity_names(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    scope_info: dict[str, Any],
    limit: int,
    include_meta: bool = False,
    kind_filter: set[str] | None = None,
    prefer_collaborative: bool = False,
) -> list[str]:
    rows = ranked_entity_rows(
        conn,
        thread_id=thread_id,
        scope_info=scope_info,
        include_meta=include_meta,
        kind_filter=kind_filter,
        prefer_collaborative=prefer_collaborative,
    )
    return [row["entity"] for row in rows[:limit]]


def entry_primary_ranked_entities(
    conn: sqlite3.Connection,
    *,
    entry_ids: list[int],
    ranked_entities: list[dict[str, Any]],
) -> dict[int, str]:
    if not entry_ids or not ranked_entities:
        return {}
    ranked_lookup = {item["entity"]: item for item in ranked_entities}
    placeholders = ",".join("?" for _ in entry_ids)
    entity_placeholders = ",".join("?" for _ in ranked_lookup)
    rows = conn.execute(
        f"""
        select
            m.entry_id,
            m.entity,
            max(
                case m.source_kind
                    when 'qualified_id_prefix' then 4
                    when 'path_parent_fallback' then 3
                    when 'backtick_identifier' then 2
                    when 'path_leaf' then 1
                    else 0
                end
            ) as entry_source_rank
        from entry_entity_mentions m
        where m.entry_id in ({placeholders})
          and m.entity in ({entity_placeholders})
        group by m.entry_id, m.entity
        """,
        (*entry_ids, *ranked_lookup.keys()),
    ).fetchall()
    candidates_by_entry: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        item = ranked_lookup[row["entity"]]
        candidates_by_entry[int(row["entry_id"])].append(
            (
                -int(item["score"]),
                -int(row["entry_source_rank"] or 0),
                -int(item["has_user_work"]),
                -len(item["entity"]),
                item["entity"],
            )
        )
    output: dict[int, str] = {}
    for entry_id, candidates in candidates_by_entry.items():
        best = sorted(candidates)[0]
        output[entry_id] = best[-1]
    return output


def episode_public_id(episode_index: int) -> str:
    return f"episode-{episode_index}"


def dominant_episode_values(conn: sqlite3.Connection, *, episode_id: int, facet_name: str, limit: int = 5) -> list[Any]:
    table_name, column_name = FACET_TABLES[facet_name]
    scopes = (
        "and e.content_class = 'work' and e.is_noise = 0 and e.role in ('assistant', 'user')",
        "and e.content_class = 'work' and e.is_noise = 0",
    )
    for extra_where in scopes:
        rows = conn.execute(
            f"""
            select f.{column_name} as value, count(*) as value_count, max(e.entry_index) as latest_index
            from {table_name} f
            join entries e on e.id = f.entry_id
            join entry_episode_links eel on eel.entry_id = e.id
            where eel.episode_id = ?
              {extra_where}
            group by f.{column_name}
            order by value_count desc, latest_index desc
            limit ?
            """,
            (episode_id, limit),
        ).fetchall()
        if rows:
            return [row["value"] for row in rows]
    return []


def scope_info_for_episode_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "requested": "episode",
        "applied": "episode",
        "reason": "episode-payload",
        "episode_row": row,
    }


def episode_payload(conn: sqlite3.Connection, row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    episode_id = int(row["id"])
    episode_scope = scope_info_for_episode_row(row)
    return {
        "id": episode_public_id(int(row["episode_index"])),
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "entry_count": int(row["entry_count"]),
        "dominant_entities": ranked_entity_names(
            conn,
            thread_id=row["thread_id"],
            scope_info=episode_scope,
            limit=5,
            prefer_collaborative=True,
        ),
        "dominant_repos": dominant_episode_values(conn, episode_id=episode_id, facet_name="repos", limit=5),
        "boundary_reason": row["boundary_reason"],
        "started_entry_index": int(row["started_entry_index"]),
        "ended_entry_index": int(row["ended_entry_index"]),
    }


def current_episode_row(conn: sqlite3.Connection, *, thread_id: str) -> sqlite3.Row | None:
    row = conn.execute(
        """
        select id, thread_id, episode_index, started_entry_index, ended_entry_index, started_at, ended_at,
               entry_count, work_entry_count, boundary_reason
        from episodes
        where thread_id = ?
        order by case
            when exists (
                select 1
                from entry_episode_links eel
                join entries e on e.id = eel.entry_id
                where eel.episode_id = episodes.id
                  and e.content_class = 'work'
                  and e.is_noise = 0
                  and e.role in ('assistant', 'user')
                  and (
                    exists (select 1 from entry_goals g where g.entry_id = e.id)
                    or exists (select 1 from entry_decisions d where d.entry_id = e.id)
                    or exists (select 1 from entry_facts f where f.entry_id = e.id)
                    or exists (select 1 from entry_blockers b where b.entry_id = e.id)
                    or exists (select 1 from entry_questions q where q.entry_id = e.id)
                  )
            ) then 0
            when exists (
                select 1
                from entry_episode_links eel
                join entries e on e.id = eel.entry_id
                where eel.episode_id = episodes.id
                  and e.content_class = 'work'
                  and e.is_noise = 0
                  and e.role in ('assistant', 'user')
            ) then 1
            when work_entry_count > 0 then 2
            else 3
        end, episode_index desc
        limit 1
        """,
        (thread_id,),
    ).fetchone()
    return row


def episode_count(conn: sqlite3.Connection, *, thread_id: str) -> int:
    row = conn.execute("select count(*) as total from episodes where thread_id = ?", (thread_id,)).fetchone()
    return int(row["total"]) if row is not None else 0


def resolve_episode_row(conn: sqlite3.Connection, *, thread_id: str, episode_id: str) -> sqlite3.Row | None:
    match = re.fullmatch(r"episode-(\d+)", episode_id)
    if match is None:
        return None
    return conn.execute(
        """
        select id, thread_id, episode_index, started_entry_index, ended_entry_index, started_at, ended_at,
               entry_count, work_entry_count, boundary_reason
        from episodes
        where thread_id = ? and episode_index = ?
        """,
        (thread_id, int(match.group(1))),
    ).fetchone()


def resolve_scope(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    requested_scope: str,
    episode_id: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    total = episode_count(conn, thread_id=thread_id)
    current_row = current_episode_row(conn, thread_id=thread_id)
    current_payload = episode_payload(conn, current_row)

    if requested_scope == "thread":
        return {
            "requested": requested_scope,
            "applied": "thread",
            "reason": "explicit-thread-scope",
            "episode_row": None,
            "episodes_total": total,
            "current_episode": current_payload,
        }, current_payload, None

    if requested_scope == "episode":
        if not episode_id:
            return None, None, failure("episode_unavailable", "Episode scope requires --episode-id.")
        row = resolve_episode_row(conn, thread_id=thread_id, episode_id=episode_id)
        if row is None:
            return None, None, failure("episode_unavailable", f"Could not resolve episode id: {episode_id}")
        resolved_payload = episode_payload(conn, row)
        return {
            "requested": requested_scope,
            "applied": "episode",
            "reason": "explicit-episode-scope",
            "episode_row": row,
            "episodes_total": total,
            "current_episode": current_payload,
        }, resolved_payload, None

    if total <= 1 or current_row is None:
        return {
            "requested": requested_scope,
            "applied": "thread",
            "reason": "single-episode-thread",
            "episode_row": current_row,
            "episodes_total": total,
            "current_episode": current_payload,
        }, current_payload, None

    return {
        "requested": requested_scope,
        "applied": "episode",
        "reason": "current-active-episode",
        "episode_row": current_row,
        "episodes_total": total,
        "current_episode": current_payload,
    }, current_payload, None


def scope_clause(scope_info: dict[str, Any], *, alias: str = "e") -> tuple[str, tuple[Any, ...]]:
    episode_row = scope_info.get("episode_row")
    if scope_info.get("applied") != "episode" or episode_row is None:
        return "", ()
    return (
        f" and {alias}.entry_index between ? and ?",
        (int(episode_row["started_entry_index"]), int(episode_row["ended_entry_index"])),
    )


def scope_payload(scope_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "requested": scope_info["requested"],
        "applied": scope_info["applied"],
        "reason": scope_info["reason"],
    }


def evidence_entry_ids(conn: sqlite3.Connection, *, thread_id: str, profile: str, limit: int, scope_info: dict[str, Any]) -> list[int]:
    if profile == "shipping":
        where_sql = """
            e.entry_type = 'compacted'
            or (e.content_class in ('work', 'command_output') and exists (select 1 from entry_event_kinds ek where ek.entry_id = e.id))
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
        where_sql = "e.entry_type = 'compacted' or (e.content_class = 'work' and e.search_text != '' and e.is_noise = 0)"

    scoped_sql, scoped_params = scope_clause(scope_info, alias="e")

    rows = conn.execute(
        f"""
        select e.id
        from entries e
        where e.thread_id = ? and ({where_sql}) {scoped_sql}
        order by e.entry_index asc
        limit ?
        """,
        (thread_id, *scoped_params, limit),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def build_evidence(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    limit: int,
    profile: str,
    scope_info: dict[str, Any],
) -> list[dict[str, Any]]:
    entries = fetch_entry_rows_by_ids(
        conn,
        evidence_entry_ids(conn, thread_id=thread_id, profile=profile, limit=limit, scope_info=scope_info),
    )
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


def build_general_summary(
    current_goal: str | None,
    decisions: list[str],
    blockers: list[str],
    open_questions: list[str],
    known_facts: list[str],
) -> str:
    parts: list[str] = []
    if current_goal:
        parts.append(f"Goal: {current_goal}")
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
    scope_info: dict[str, Any],
) -> dict[str, Any]:
    commands = recent_commands(conn, thread_id=thread_id, limit=25, scope_info=scope_info)
    touched_paths = recent_distinct_values(
        conn,
        thread_id=thread_id,
        facet_name="paths",
        limit=25,
        scope_info=scope_info,
        extra_where="and ((e.role in ('assistant', 'user')) or e.entry_type = 'response_item') and e.content_class in ('work', 'command_output') and e.is_noise = 0",
    )
    blockers = [
        item
        for item in recent_distinct_values(conn, thread_id=thread_id, facet_name="blockers", limit=10, scope_info=scope_info)
        if is_human_scale_sentence(str(item))
    ]
    open_questions = [
        item
        for item in recent_distinct_values(
            conn,
            thread_id=thread_id,
            facet_name="questions",
            limit=10,
            scope_info=scope_info,
            extra_where="and e.role in ('assistant', 'user') and e.content_class = 'work' and e.is_noise = 0",
        )
        if is_human_scale_sentence(str(item))
    ]
    goals = [
        item
        for item in recent_distinct_values(
            conn,
            thread_id=thread_id,
            facet_name="goals",
            limit=10,
            scope_info=scope_info,
            extra_where="and e.role in ('assistant', 'user') and e.content_class = 'work'",
        )
        if is_human_scale_sentence(str(item))
    ]
    decisions = [
        item
        for item in recent_distinct_values(
            conn,
            thread_id=thread_id,
            facet_name="decisions",
            limit=10,
            scope_info=scope_info,
            extra_where="and e.content_class = 'work'",
        )
        if is_human_scale_sentence(str(item))
    ]
    known_facts = [
        item
        for item in recent_distinct_values(
            conn,
            thread_id=thread_id,
            facet_name="facts",
            limit=10,
            scope_info=scope_info,
            extra_where="and e.content_class = 'work'",
        )
        if is_human_scale_sentence(str(item))
    ]
    entry_counts, event_counts = aggregate_counts(conn, thread_id=thread_id, scope_info=scope_info)
    evidence = build_evidence(conn, thread_id=thread_id, limit=evidence_limit, profile=profile, scope_info=scope_info)
    current_goal = goals[0] if goals else None

    return {
        "profile": profile,
        "summary": build_general_summary(current_goal, decisions, blockers, open_questions, known_facts),
        "current_goal": current_goal,
        "goals": goals,
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
    scope_info: dict[str, Any],
) -> dict[str, Any]:
    ship_where = "and e.content_class in ('work', 'command_output') and exists (select 1 from entry_event_kinds ek where ek.entry_id = e.id and ek.event_kind in (?, ?, ?, ?))"
    ship_params: tuple[Any, ...] = tuple(sorted(SHIP_EVENT_KINDS))
    recall = collect_general_recall(
        conn,
        thread_id=thread_id,
        evidence_limit=evidence_limit,
        profile="shipping",
        scope_info=scope_info,
    )
    shipped_entities = ranked_entity_names(
        conn,
        thread_id=thread_id,
        scope_info=scope_info,
        limit=15,
        kind_filter=SHIP_EVENT_KINDS,
        prefer_collaborative=True,
    )
    repos_touched = recent_distinct_values(
        conn, thread_id=thread_id, facet_name="repos", limit=10, scope_info=scope_info, extra_where=ship_where, params=ship_params
    )
    pr_numbers = recent_distinct_values(
        conn, thread_id=thread_id, facet_name="pr_numbers", limit=15, scope_info=scope_info, extra_where=ship_where, params=ship_params
    )
    commit_oids = recent_distinct_values(
        conn, thread_id=thread_id, facet_name="commit_oids", limit=15, scope_info=scope_info, extra_where=ship_where, params=ship_params
    )
    installed_entities = ranked_entity_names(
        conn,
        thread_id=thread_id,
        scope_info=scope_info,
        limit=15,
        kind_filter={"installed"},
        prefer_collaborative=True,
    )
    installed_identifiers = recent_distinct_values(
        conn,
        thread_id=thread_id,
        facet_name="qualified_ids",
        limit=15,
        scope_info=scope_info,
        extra_where="and e.content_class in ('work', 'command_output') and exists (select 1 from entry_event_kinds ek where ek.entry_id = e.id and ek.event_kind = ?)",
        params=("installed",),
    )
    scoped_sql, scoped_params = scope_clause(scope_info, alias="e")
    follow_up_rows = conn.execute(
        """
        select ff.fact
        from entry_facts ff
        join entries e on e.id = ff.entry_id
        where e.thread_id = ? {scoped_sql}
          and exists (select 1 from entry_event_kinds ek where ek.entry_id = e.id and ek.event_kind = 'merged')
          and (lower(ff.fact) like '%follow-up%' or lower(ff.fact) like '%fix%')
        order by e.entry_index desc
        limit 100
        """.format(scoped_sql=scoped_sql),
        (thread_id, *scoped_params),
    ).fetchall()
    follow_up_fixes = unique_recent(
        [
            row["fact"]
            for row in follow_up_rows
            if is_human_scale_sentence(str(row["fact"]))
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
    scope_info: dict[str, Any],
) -> dict[str, Any]:
    recall = collect_general_recall(
        conn,
        thread_id=thread_id,
        evidence_limit=evidence_limit,
        profile="debug",
        scope_info=scope_info,
    )
    failure_events = [
        item
        for item in recent_distinct_values(conn, thread_id=thread_id, facet_name="blockers", limit=15, scope_info=scope_info)
        if is_human_scale_sentence(str(item))
    ]
    retry_signals = [
        item
        for item in recent_distinct_values(conn, thread_id=thread_id, facet_name="retry_signals", limit=15, scope_info=scope_info)
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
        "_entry_id": entry["id"],
        "timestamp": entry["timestamp"],
        "kind": kind,
        "entry_type": entry["entry_type"],
        "payload_type": entry["payload_type"],
        "role": entry["role"],
        "content_class": entry["content_class"],
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


def timeline_entry_ids(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    kind: str,
    scope_info: dict[str, Any],
    include_meta: bool,
) -> list[int]:
    if kind == "all":
        where_sql = ""
        params: tuple[Any, ...] = ()
    elif kind == "shipped":
        where_sql = "and ek.event_kind in (?, ?, ?, ?)"
        params = tuple(sorted(SHIP_EVENT_KINDS))
    else:
        where_sql = "and ek.event_kind = ?"
        params = (kind,)
    scoped_sql, scoped_params = scope_clause(scope_info, alias="e")
    class_sql = "" if include_meta else "and e.content_class in ('work', 'command_output')"

    rows = conn.execute(
        f"""
        select distinct e.id, coalesce(e.timestamp, '') as sort_timestamp, e.entry_index
        from entries e
        join entry_event_kinds ek on ek.entry_id = e.id
        where e.thread_id = ?
          {scoped_sql}
          {class_sql}
          {where_sql}
        order by sort_timestamp, e.entry_index
        """,
        (thread_id, *scoped_params, *params),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def first_seen_map(conn: sqlite3.Connection, *, thread_id: str, group: str, scope_info: dict[str, Any]) -> dict[str, str | None]:
    if group == "entity":
        rows = ranked_entity_rows(
            conn,
            thread_id=thread_id,
            scope_info=scope_info,
        )
        return {row["entity"]: row["first_seen_at"] for row in rows}
    facet_name = "entities" if group == "entity" else "repos"
    table_name, column_name = FACET_TABLES[facet_name]
    scoped_sql, scoped_params = scope_clause(scope_info, alias="e")
    rows = conn.execute(
        f"""
        select f.{column_name} as group_key, e.timestamp
        from {table_name} f
        join entries e on e.id = f.entry_id
        where e.thread_id = ?
          {scoped_sql}
          and e.content_class in ('work', 'command_output')
        order by e.entry_index
        """,
        (thread_id, *scoped_params),
    ).fetchall()
    output: dict[str, str | None] = {}
    for row in rows:
        key = row["group_key"]
        if key not in output:
            output[key] = row["timestamp"]
    return output


def index_busy_failure(thread: dict[str, Any], warnings: list[str], error: IndexBusyError) -> dict[str, Any]:
    return failure(
        "index_busy",
        str(error),
        warnings=warnings,
        thread=thread,
        cache={"lock_state": error.lock_state, "path": str(cache_db_path(default_codex_home()))},
    )


def status(thread_id: str | None = None, codex_home: str | Path | None = None) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error
    home = default_codex_home(codex_home)
    conn = connect_cache(home)
    try:
        index_meta, index_warnings = ensure_index(conn, thread=thread, codex_home=home)
        warnings.extend(index_warnings)
        current_episode = episode_payload(conn, current_episode_row(conn, thread_id=thread["id"]))
        return {
            "ok": True,
            "thread": thread,
            "warnings": warnings,
            "runtime": runtime_context_from_env(),
            "cache": {
                "path": index_meta["cache_path"],
                "schema_version": index_meta["schema_version"],
                "entry_count": index_meta["entry_count"],
                "noise_filtered_count": index_meta["noise_filtered_count"],
                "last_indexed_line": index_meta["last_indexed_line"],
                "last_indexed_offset": index_meta["last_indexed_offset"],
                "built_at": index_meta["built_at"],
                "last_rebuild_reason": index_meta["last_rebuild_reason"],
                "lock_state": index_meta["lock_state"],
            },
            "episodes": {
                "total": episode_count(conn, thread_id=thread["id"]),
                "current": current_episode,
                "last_boundary_reason": current_episode["boundary_reason"] if current_episode is not None else None,
            },
        }
    except IndexBusyError as exc:
        return failure(
            "index_busy",
            str(exc),
            warnings=warnings,
            thread=thread,
            runtime=runtime_context_from_env(),
            cache={
                "path": str(cache_db_path(home)),
                "lock_state": exc.lock_state,
            },
        )
    finally:
        conn.close()


def recall(
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
    *,
    evidence_limit: int = 25,
    profile: str = "general",
    scope: str = "current",
    episode_id: str | None = None,
) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error

    home = default_codex_home(codex_home)
    conn = connect_cache(home)
    try:
        index_meta, index_warnings = ensure_index(conn, thread=thread, codex_home=home)
        warnings.extend(index_warnings)
        scope_info, episode_payload_data, scope_error = resolve_scope(
            conn,
            thread_id=thread["id"],
            requested_scope=scope,
            episode_id=episode_id,
        )
        if scope_error is not None:
            scope_error["thread"] = thread
            return scope_error

        if profile == "shipping":
            recall_payload = collect_shipping_recall(
                conn,
                thread_id=thread["id"],
                evidence_limit=evidence_limit,
                scope_info=scope_info,
            )
        elif profile == "debug":
            recall_payload = collect_debug_recall(
                conn,
                thread_id=thread["id"],
                evidence_limit=evidence_limit,
                scope_info=scope_info,
            )
        else:
            recall_payload = collect_general_recall(
                conn,
                thread_id=thread["id"],
                evidence_limit=evidence_limit,
                profile="general",
                scope_info=scope_info,
            )

        return {
            "ok": True,
            "thread": thread,
            "warnings": warnings,
            "index": index_meta,
            "scope": scope_payload(scope_info),
            "episode": episode_payload_data,
            "recall": recall_payload,
        }
    except IndexBusyError as exc:
        return failure(
            "index_busy",
            str(exc),
            warnings=warnings,
            thread=thread,
            cache={"path": str(cache_db_path(home)), "lock_state": exc.lock_state},
        )
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
    scope: str = "thread",
    episode_id: str | None = None,
) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error

    home = default_codex_home(codex_home)
    conn = connect_cache(home)
    try:
        index_meta, index_warnings = ensure_index(conn, thread=thread, codex_home=home)
        warnings.extend(index_warnings)
        scope_info, episode_payload_data, scope_error = resolve_scope(
            conn,
            thread_id=thread["id"],
            requested_scope=scope,
            episode_id=episode_id,
        )
        if scope_error is not None:
            scope_error["thread"] = thread
            return scope_error

        search_column = "raw_text" if include_noise else "search_text"
        where_clauses = ["e.thread_id = ?"]
        params: list[Any] = [thread["id"]]
        scoped_sql, scoped_params = scope_clause(scope_info, alias="e")
        if scoped_sql:
            where_clauses.append(scoped_sql.strip().removeprefix("and ").strip())
            params.extend(scoped_params)
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
            "scope": scope_payload(scope_info),
            "episode": episode_payload_data,
            "results": results,
        }
    except IndexBusyError as exc:
        return failure(
            "index_busy",
            str(exc),
            warnings=warnings,
            thread=thread,
            cache={"path": str(cache_db_path(home)), "lock_state": exc.lock_state},
        )
    finally:
        conn.close()


def timeline(
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
    *,
    kind: str = "shipped",
    group: str = "entity",
    limit: int = 10,
    scope: str = "current",
    episode_id: str | None = None,
    include_meta: bool = False,
) -> dict[str, Any]:
    thread, warnings, error = resolve_thread(thread_id=thread_id, codex_home=codex_home)
    if error is not None:
        return error

    home = default_codex_home(codex_home)
    conn = connect_cache(home)
    try:
        index_meta, index_warnings = ensure_index(conn, thread=thread, codex_home=home)
        warnings.extend(index_warnings)
        scope_info, episode_payload_data, scope_error = resolve_scope(
            conn,
            thread_id=thread["id"],
            requested_scope=scope,
            episode_id=episode_id,
        )
        if scope_error is not None:
            scope_error["thread"] = thread
            return scope_error
        selected_kinds = selected_event_kinds(kind)
        entries = fetch_entry_rows_by_ids(
            conn,
            timeline_entry_ids(
                conn,
                thread_id=thread["id"],
                kind=kind,
                scope_info=scope_info,
                include_meta=include_meta,
            ),
        )

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
                "scope": scope_payload(scope_info),
                "episode": episode_payload_data,
                "timeline": [{key: value for key, value in event.items() if key != "_entry_id"} for event in flat_events[:limit]],
            }

        grouping: dict[str, dict[str, Any]] = {}
        key_name = "entity" if group == "entity" else "repo"
        ranked_rows = ranked_entity_rows(
            conn,
            thread_id=thread["id"],
            scope_info=scope_info,
            include_meta=include_meta,
            prefer_collaborative=not include_meta,
        ) if group == "entity" else []
        primary_entity_map = entry_primary_ranked_entities(
            conn,
            entry_ids=[entry["id"] for entry in entries],
            ranked_entities=ranked_rows,
        ) if group == "entity" else {}
        seen_map = (
            {row["entity"]: row["first_seen_at"] for row in ranked_rows}
            if group == "entity"
            else first_seen_map(conn, thread_id=thread["id"], group=group, scope_info=scope_info)
        )
        for event in flat_events:
            if group == "entity":
                primary_entity = primary_entity_map.get(int(event["_entry_id"]))
                keys = [primary_entity] if primary_entity else []
            else:
                keys = event["repos"]
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
                bucket["ship_events"].append({key_name: value for key_name, value in event.items() if key_name != "_entry_id"})
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
            "scope": scope_payload(scope_info),
            "episode": episode_payload_data,
            "timeline": grouped_timeline,
        }
    except IndexBusyError as exc:
        return failure(
            "index_busy",
            str(exc),
            warnings=warnings,
            thread=thread,
            cache={"path": str(cache_db_path(home)), "lock_state": exc.lock_state},
        )
    finally:
        conn.close()
