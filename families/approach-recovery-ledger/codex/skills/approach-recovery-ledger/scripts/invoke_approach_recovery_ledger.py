"""Shared local approach history. No network, subprocesses, retries or settings edits."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3


SCHEMA_VERSION = 1
APPLICATION_ID = 0x41524C31
MAX_ENTRY_BYTES = 65536
PROGRAMS = {"standard", "daybreak_blue", "daybreak_red", "unknown"}
OUTCOMES = {"interrupted", "technical_failure", "partial", "completed"}
MODE_SOURCES = {"codex_turn_context", "responses_api", "user_report", "unknown"}
TIME_SOURCES = {"event", "thread_record", "thread_report", "unknown"}
SECRET = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{24,}|\bAIza[A-Za-z0-9_-]{30,}")


class LedgerError(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def require(condition, message):
    if not condition:
        raise LedgerError("invalid_entry", message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def choice(value, allowed):
    return isinstance(value, str) and value in allowed


def shape(value, required, optional=(), label="entry"):
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(required) <= value.keys(), f"{label} is missing required fields")
    require(value.keys() <= set(required) | set(optional), f"{label} has unsupported fields")


def texts(value, label, allow_empty=False):
    require(isinstance(value, list) and (allow_empty or bool(value)), f"{label} must be a string list")
    require(all(text(item) for item in value), f"{label} contains an empty/non-string value")
    require(len(value) == len(set(value)), f"{label} contains duplicates")


def timestamp(value, label):
    if value is None:
        return None
    require(isinstance(value, str), f"{label} must be an aware ISO timestamp or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise LedgerError("invalid_entry", f"{label} is not an ISO timestamp") from None
    require(parsed.tzinfo is not None, f"{label} must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def validate_entry(packet):
    shape(packet, {
        "schema_version", "attempt_id", "thread_id", "attempted_at", "attempt_time_source",
        "interrupted_at", "context", "plan", "execution", "outcome", "interruption",
        "satisfied_criteria", "outstanding_criteria", "lesson", "applies_when", "next_decision",
    }, {"previous_attempt_id", "relationship"})
    require(type(packet["schema_version"]) is int and packet["schema_version"] == SCHEMA_VERSION, "Unsupported entry schema_version")
    require(isinstance(packet["attempt_id"], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", packet["attempt_id"]), "attempt_id must be a stable ASCII identifier")
    require(text(packet["thread_id"]), "thread_id is required")
    result = json.loads(json.dumps(packet))
    for name in ("attempted_at", "interrupted_at"):
        result[name] = timestamp(result[name], name)
    require(choice(result["attempt_time_source"], TIME_SOURCES), "Invalid attempt_time_source")
    require((result["attempted_at"] is None) == (result["attempt_time_source"] == "unknown"), "Unknown attempt time must be null with source unknown")
    if result["attempted_at"] and result["interrupted_at"]:
        require(result["attempted_at"] <= result["interrupted_at"], "Interruption predates attempt")
    context = result["context"]
    shape(context, {"client", "model", "cyber_access_program", "program_source", "program_evidence"}, {"raw_cyber_access_program", "desktop_daybreak_preference"}, "context")
    require(text(context["client"]), "context.client is required")
    require(context["model"] is None or text(context["model"]), "model must be a name or null")
    require(choice(context["cyber_access_program"], PROGRAMS), "Invalid cyber_access_program")
    require(choice(context["program_source"], MODE_SOURCES), "Desktop preference/model name cannot establish an effective program")
    if context["cyber_access_program"] != "unknown":
        require(context["program_source"] != "unknown" and text(context["program_evidence"]), "Known program requires a source and evidence reference")
    require(context["program_evidence"] is None or text(context["program_evidence"]), "Invalid program_evidence")
    require(context.get("desktop_daybreak_preference") is None or isinstance(context["desktop_daybreak_preference"], bool), "Desktop preference must be boolean or null")
    require(context.get("raw_cyber_access_program") is None or isinstance(context["raw_cyber_access_program"], (str, bool, int)), "Raw program must be a scalar or null")
    plan = result["plan"]
    shape(plan, {"objective", "scope", "method", "steps", "intended_next_action", "acceptance_criteria"}, label="plan")
    require(all(text(plan[key]) for key in ("objective", "scope", "method", "intended_next_action")), "Plan fields must describe the actual execution plan")
    for name in ("steps", "acceptance_criteria"):
        texts(plan[name], f"plan.{name}")
    for name in ("satisfied_criteria", "outstanding_criteria"):
        texts(result[name], name, allow_empty=True)
    satisfied, outstanding = set(result["satisfied_criteria"]), set(result["outstanding_criteria"])
    require(not satisfied & outstanding and satisfied | outstanding == set(plan["acceptance_criteria"]), "Satisfied/outstanding must partition every original acceptance criterion")
    require(choice(result["outcome"], OUTCOMES), "Invalid attempt outcome")
    require(result["outcome"] != "completed" or not outstanding, "Completed attempt cannot have outstanding criteria")
    require(result["outcome"] != "partial" or bool(outstanding), "Partial attempt must identify outstanding criteria")
    execution = result["execution"]
    shape(execution, {"tool_outcome", "summary", "evidence"}, label="execution")
    require(choice(execution["tool_outcome"], {"completed", "failed", "not_run", "unknown"}), "Invalid tool_outcome")
    require(text(execution["summary"]), "Execution summary is required")
    texts(execution["evidence"], "execution.evidence")
    interruption = result["interruption"]
    if interruption is not None:
        shape(interruption, {"kind", "code", "message", "cause_confidence", "cause"}, label="interruption")
        require(choice(interruption["kind"], {"cyber_policy", "model_refusal", "tool_policy", "transport", "unknown"}), "Invalid interruption kind")
        require(interruption["code"] is None or text(interruption["code"]), "Interruption code must be a string or null")
        require(text(interruption["message"]), "Observed interruption message is required")
        require(choice(interruption["cause_confidence"], {"confirmed", "inferred", "unknown"}), "Invalid cause confidence")
        require(interruption["cause"] is None if interruption["cause_confidence"] == "unknown" else text(interruption["cause"]), "Unknown cause must stay null; other causes require an explanation")
    require(result["outcome"] != "interrupted" or interruption is not None, "Interrupted attempt requires observed interruption details")
    require(text(result["lesson"]) and text(result["applies_when"]), "Lesson and applicability scope are required")
    decision = result["next_decision"]
    shape(decision, {"action", "rationale", "next_step"}, label="next_decision")
    require(choice(decision["action"], {"continue_independent", "alternative", "pause", "resolved"}), "Invalid next decision")
    require(text(decision["rationale"]) and text(decision["next_step"]), "Next decision needs justification and a concrete next step")
    previous, relationship = result.get("previous_attempt_id"), result.get("relationship")
    require((previous is None) == (relationship is None), "Previous ID and relationship must be supplied together")
    if previous is not None:
        require(text(previous) and previous != result["attempt_id"], "Invalid previous attempt reference")
        require(choice(relationship, {"continuation", "alternative", "supersedes"}), "Invalid relationship")
    encoded = json.dumps(result, sort_keys=True, ensure_ascii=True)
    require(len(encoded.encode("utf-8")) <= MAX_ENTRY_BYTES, "Entry exceeds 64 KiB; reference scoped evidence instead of copying transcripts")
    require(not SECRET.search(encoded), "Possible credential/private-key material; remove it and use an evidence reference")
    return result


def default_ledger():
    if os.environ.get("APPROACH_RECOVERY_LEDGER"):
        return Path(os.environ["APPROACH_RECOVERY_LEDGER"]).expanduser()
    return Path("E:/Codex/ledgers/approach-recovery/ledger.sqlite3") if os.name == "nt" else Path.home() / ".local/share/agent-toolbelt/approach-recovery/ledger.sqlite3"


@contextmanager
def store(path, write=False):
    path = Path(path).expanduser().resolve()
    if not write and not path.exists():
        yield None
        return
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path) if write else path.as_uri() + "?mode=ro", uri=not write, timeout=0)
    conn.row_factory = sqlite3.Row
    try:
        if write:
            conn.execute("BEGIN IMMEDIATE")
        app = conn.execute("PRAGMA application_id").fetchone()[0]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if write and app == 0 and version == 0 and not tables:
            conn.execute("CREATE TABLE attempts (id TEXT PRIMARY KEY, attempted_at TEXT, recorded_at TEXT NOT NULL, model TEXT, program TEXT NOT NULL, outcome TEXT NOT NULL, thread_id TEXT NOT NULL, previous_id TEXT, relationship TEXT, content_hash TEXT NOT NULL, search_text TEXT NOT NULL, payload TEXT NOT NULL)")
            conn.execute("CREATE INDEX attempts_recorded ON attempts(recorded_at)")
            conn.execute("CREATE INDEX attempts_previous ON attempts(previous_id)")
            conn.execute(f"PRAGMA application_id={APPLICATION_ID}")
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        elif app != APPLICATION_ID or version != SCHEMA_VERSION:
            raise LedgerError("unsupported_ledger", "File is not a supported dedicated approach ledger")
        yield conn
        if write:
            conn.commit()
    finally:
        conn.close()


def record(path, packet):
    entry = validate_entry(packet)
    now = utc_now()
    require(all(entry[name] is None or entry[name] <= now for name in ("attempted_at", "interrupted_at")), "Attempt/interruption timestamp is in the future")
    encoded = json.dumps(entry, sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    with store(path, write=True) as conn:
        existing = conn.execute("SELECT content_hash, recorded_at FROM attempts WHERE id=?", (entry["attempt_id"],)).fetchone()
        if existing:
            if existing["content_hash"] != digest:
                raise LedgerError("immutable_conflict", "Attempt ID already has different contents; append a linked new attempt")
            return {"attempt_id": entry["attempt_id"], "recorded_at": existing["recorded_at"], "already_recorded": True}
        previous = entry.get("previous_attempt_id")
        if previous:
            old = conn.execute("SELECT payload FROM attempts WHERE id=?", (previous,)).fetchone()
            if old is None:
                raise LedgerError("unknown_previous_attempt", "Previous attempt does not exist in this ledger")
            if entry["relationship"] == "supersedes":
                original = json.loads(old["payload"])["plan"]
                require(entry["outcome"] == "completed", "Only a completed verified attempt can supersede")
                require(all(entry["plan"][key] == original[key] for key in ("objective", "scope")) and set(entry["plan"]["acceptance_criteria"]) == set(original["acceptance_criteria"]), "Supersession must preserve original objective, scope and criteria")
        entry["recorded_at"] = now
        searchable = " ".join([entry["plan"][key] for key in ("objective", "scope", "method")] + [entry["lesson"], entry["applies_when"]]).casefold()
        conn.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            entry["attempt_id"], entry["attempted_at"], now, entry["context"]["model"],
            entry["context"]["cyber_access_program"], entry["outcome"], entry["thread_id"],
            previous, entry.get("relationship"), digest, searchable, json.dumps(entry, ensure_ascii=True),
        ))
        return {"attempt_id": entry["attempt_id"], "recorded_at": now, "already_recorded": False}


def decorated(conn, row, brief=False):
    entry = json.loads(row["payload"])
    entry["superseded_by"] = [r[0] for r in conn.execute("SELECT id FROM attempts WHERE previous_id=? AND relationship='supersedes' ORDER BY recorded_at", (entry["attempt_id"],))]
    if not brief:
        return entry
    return {key: entry.get(key) for key in ("attempt_id", "thread_id", "attempted_at", "attempt_time_source", "interrupted_at", "recorded_at", "context", "outcome", "outstanding_criteria", "lesson", "applies_when", "superseded_by")} | {"objective": entry["plan"]["objective"], "method": entry["plan"]["method"]}


def search(path, *, query="", program=None, model=None, outcome=None, since=None, limit=20):
    require(1 <= limit <= 100, "limit must be between 1 and 100")
    conditions, values = [], []
    for field, value in (("program", program), ("model", model), ("outcome", outcome)):
        if value is not None:
            conditions.append(field + "=?")
            values.append(value)
    for term in query.casefold().split():
        conditions.append("search_text LIKE ? ESCAPE '\\'")
        values.append("%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if since:
        conditions.append("COALESCE(attempted_at,recorded_at)>=?")
        values.append(timestamp(since, "since"))
    with store(path) as conn:
        if conn is None:
            return []
        sql = "SELECT payload FROM attempts" + (" WHERE " + " AND ".join(conditions) if conditions else "")
        rows = conn.execute(sql + " ORDER BY COALESCE(attempted_at,recorded_at) DESC, id LIMIT ?", (*values, limit)).fetchall()
        return [decorated(conn, row, brief=True) for row in rows]


def read_json(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_ENTRY_BYTES + 1)
    require(len(raw) <= MAX_ENTRY_BYTES, "Input exceeds 64 KiB; supply scoped metadata or evidence references")
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        raise LedgerError("invalid_json", "Input is not valid UTF-8 JSON") from None


def normalize_context(packet, source, evidence):
    require(isinstance(packet, dict), "Metadata must be an object")
    data = packet.get("payload", packet) if source == "codex_turn_context" else packet
    require(isinstance(data, dict), "Metadata payload must be an object")
    if source == "codex_turn_context":
        raw = data.get("cyber_access_program")
    else:
        programs = data.get("access_programs")
        raw = programs.get("cyber") if isinstance(programs, dict) else None
    program = raw if isinstance(raw, str) and raw in PROGRAMS else "unknown"
    if source == "responses_api" and "access_programs" in data and data["access_programs"] is None and not data.get("error"):
        program = "standard"
    if source == "responses_api" and data.get("error"):
        program = "unknown"
    return {"client": "codex" if source == "codex_turn_context" else "responses_api", "model": data.get("model") if text(data.get("model")) else None,
            "cyber_access_program": program, "raw_cyber_access_program": raw if isinstance(raw, (str, int, bool, type(None))) else None,
            "program_source": source, "program_evidence": evidence}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=default_ledger())
    commands = parser.add_subparsers(dest="operation", required=True)
    write = commands.add_parser("record")
    write.add_argument("--input", type=Path, required=True)
    query = commands.add_parser("search")
    query.add_argument("--query", default="")
    query.add_argument("--program", choices=sorted(PROGRAMS))
    query.add_argument("--model")
    query.add_argument("--outcome", choices=sorted(OUTCOMES))
    query.add_argument("--since")
    query.add_argument("--limit", type=int, default=20)
    show = commands.add_parser("show")
    show.add_argument("--attempt-id", required=True)
    commands.add_parser("status")
    context = commands.add_parser("context")
    context.add_argument("--input", type=Path, required=True)
    context.add_argument("--source", choices=("codex_turn_context", "responses_api"), required=True)
    args = parser.parse_args(argv)
    result = {"ok": True, "operation": args.operation, "ledger_path": str(args.ledger.expanduser().resolve())}
    try:
        if args.operation == "record":
            result.update(record(args.ledger, read_json(args.input)))
        elif args.operation == "search":
            result["attempts"] = search(args.ledger, query=args.query, program=args.program, model=args.model, outcome=args.outcome, since=args.since, limit=args.limit)
        elif args.operation == "context":
            result["context"] = normalize_context(read_json(args.input), args.source, str(args.input.resolve()))
        else:
            with store(args.ledger) as conn:
                if args.operation == "status":
                    result.update(exists=conn is not None, schema_version=SCHEMA_VERSION, count=conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] if conn else 0)
                else:
                    row = conn.execute("SELECT payload FROM attempts WHERE id=?", (args.attempt_id,)).fetchone() if conn else None
                    if row is None:
                        raise LedgerError("attempt_not_found", "Attempt not found in this shared ledger")
                    result["attempt"] = decorated(conn, row)
    except LedgerError as exc:
        result.update(ok=False, failure_kind=exc.kind, errors=[str(exc)])
    except sqlite3.Error as exc:
        code = getattr(exc, "sqlite_errorcode", 0) or 0
        result.update(ok=False, failure_kind="ledger_busy" if (code & 255) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else "ledger_database_error", errors=[type(exc).__name__], sqlite_error_name=getattr(exc, "sqlite_errorname", None))
    except OSError as exc:
        result.update(ok=False, failure_kind="ledger_io_error", errors=[type(exc).__name__])
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
