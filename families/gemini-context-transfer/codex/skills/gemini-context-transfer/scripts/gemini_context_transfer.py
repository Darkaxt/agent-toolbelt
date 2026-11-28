"""Gemini (Antigravity CLI "agy") conversation takeover into Claude Code.

inspect, catalog, handoff, acceptance, verified 7-Zip archive, restore and an
exact retirement of one conversation's own files. Read-only toward live agy
state except `retire`, which deletes only the archived per-conversation members
(brain/<id>, conversations/<id>.db, annotations/<id>.pbtxt). Shared indexes
(cache/*, conversation_summaries.db, history.jsonl, ...) are reported as
residuals and never edited.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable
from uuid import UUID

VERSION = "0.1.0"
PREFIX = "agent_toolbelt_gemini_context_transfer"
DEFAULT_ARCHIVE_ROOT = Path(r"G:\Archives\Gemini\ContextTransfers")
DEFAULT_GEMINI_HOME = Path.home() / ".gemini" / "antigravity-cli"
DEFAULT_CLAUDE_HOME = Path.home() / ".claude"
LIVE_PROCESS_RE = re.compile(r"agy|antigravity|language_server", re.IGNORECASE)
REFRAME_HOOK_RE = re.compile(r"Reframe[\\/].*hooks[\\/]([^\\/]+)$", re.IGNORECASE)
SHARED_FILES = ("cache/conversation_metadata.json", "cache/last_conversations.json",
                "conversation_summaries.db", "history.jsonl", "jetski_state.pbtxt")
TRANSCRIPT = ".system_generated/logs/transcript.jsonl"
REQUIRED_SECTIONS = (
    "Current Objective",
    "Authoritative Specifications And Plans",
    "Completed Work With Evidence",
    "Active Stage And Exact Next Actions",
    "Unresolved Blockers And Required Deferrals",
    "Durable Decisions And User Constraints",
    "Failed Approaches Not To Repeat",
    "Repositories Branches And Artifacts",
    "Gemini Subagent And Task Map",
    "Uncertainties Requiring Verification",
    "Archive And Recall References",
)
MILESTONES = ("decision", "blocker", "failed", "error", "tests passed", "verified", "commit ",
              "merged", "pushed", "released", "next action", "plan")
COMPRESSION = ["-t7z", "-mx=9", "-m0=lzma2", "-md=256m", "-mfb=273", "-ms=on", "-mmt=on"]
FILE_ARG_KEYS = ("AbsolutePath", "TargetFile", "FilePath", "Path", "File", "path", "file_path", "DirectoryPath")
COMMAND_ARG_KEYS = ("CommandLine", "command", "Command")
REPO_RE = re.compile(r"github\.com[/:]([\w.-]+/[\w.-]+?)(?:\.git)?(?=[\s/\"'#)]|$)")
RELEASE_RE = re.compile(r"(?:github\.com/[\w.-]+/[\w.-]+/(?:releases|pull)/[\w./-]+|\bv\d+\.\d+\.\d+\b)")


class TransferError(RuntimeError):
    def __init__(self, kind: str, message: str, **details: Any):
        super().__init__(message)
        self.kind, self.details = kind, details


# ---------------------------------------------------------------- utilities

def exact_id(value: str | None, label: str) -> str:
    value = (value or "").strip()
    try:
        if str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise TransferError("invalid_id", f"{label} must be a complete lowercase UUID, not a title or prefix.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_reparse(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def load_json(path: Path | str, kind: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransferError(f"{kind}_unreadable", f"Cannot read {kind}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TransferError(f"{kind}_invalid", f"{kind} must be a JSON object")
    return payload


def write_json(path: Path | str, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def canonical_sha(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def iter_records(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            try:
                record = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(record, dict):
                yield number, record


def seven_zip(explicit: str | None) -> str:
    found = explicit or shutil.which("7z.exe") or shutil.which("7z")
    if not found:
        raise TransferError("seven_zip_missing", "7-Zip (7z.exe) is required.")
    return found


def run_7z(binary: str, *args: str, cwd: str | None = None) -> str:
    completed = subprocess.run([binary, *args], cwd=cwd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise TransferError("seven_zip_failed", f"7-Zip exited {completed.returncode}",
                            output=(completed.stdout + completed.stderr)[-2000:])
    return completed.stdout


def tree_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0


# ---------------------------------------------------------------- liveness / metadata

def running_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        raise TransferError("liveness_unsupported", "Live agy verification is Windows-only.")
    command = "Get-CimInstance Win32_Process | Select-Object Name,ProcessId,CommandLine | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, check=True)
    rows = json.loads(result.stdout or "[]")
    return rows if isinstance(rows, list) else [rows]


def live_processes() -> list[dict[str, Any]]:
    """Conservative: any agy/Antigravity/language_server process blocks pack and retirement."""
    return [{"name": row.get("Name"), "pid": row.get("ProcessId")} for row in running_processes()
            if LIVE_PROCESS_RE.search(row.get("Name") or "")]


def metadata(home: Path) -> dict[str, Any]:
    path = home / "cache" / "conversation_metadata.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    conversations = data.get("conversations") if isinstance(data, dict) else None
    return conversations if isinstance(conversations, dict) else {}


def summary_of(home: Path, conversation_id: str) -> dict[str, Any]:
    entry = metadata(home).get(conversation_id) or {}
    summary = entry.get("summary") or {}
    return {"title": summary.get("Title"), "steps": summary.get("NumSteps"), "updated": summary.get("UpdatedAt"),
            "workspaces": summary.get("WorkspaceURIs") or [], "last_modified_time": entry.get("last_modified_time"),
            "in_metadata_cache": bool(entry)}


def reframe_references(workspaces: list[str]) -> list[dict[str, Any]]:
    refs = []
    for uri in workspaces:
        local = re.sub(r"^file:///", "", str(uri))
        found = REFRAME_HOOK_RE.search(local)
        if found:
            refs.append({"workspace_uri": uri, "hook_directory": local, "hook_id": found.group(1),
                         "note": "Reframe tile reference; never edited by this helper."})
    return refs


def own_roots(home: Path, conversation_id: str) -> dict[str, Path]:
    return {"brain": home / "brain" / conversation_id,
            "database": home / "conversations" / f"{conversation_id}.db",
            "annotation": home / "annotations" / f"{conversation_id}.pbtxt"}


def shared_residuals(home: Path, conversation_id: str) -> list[dict[str, Any]]:
    """Shared index files that may still mention the conversation; reported, never edited."""
    found = []
    for relative in SHARED_FILES:
        path = home / relative
        if not path.is_file():
            continue
        if path.suffix in (".json", ".jsonl", ".pbtxt") and path.stat().st_size < 64 << 20:
            mentions = conversation_id in path.read_text(encoding="utf-8", errors="replace")
        else:
            mentions = None  # Binary index (SQLite): not opened; may still reference the id.
        if mentions is not False:
            found.append({"path": str(path), "mentions_id": mentions, "action": "left_unchanged"})
    return found


# ---------------------------------------------------------------- list / inspect

def list_conversations(home: Path) -> dict[str, Any]:
    meta = metadata(home)
    ids = set(meta) | {p.name for p in (home / "brain").glob("*") if p.is_dir()} | {
        p.stem for p in (home / "conversations").glob("*.db")}
    rows = []
    for cid in sorted(i for i in ids if re.fullmatch(r"[0-9a-f-]{36}", i)):
        info = summary_of(home, cid)
        roots = own_roots(home, cid)
        sizes = {name: tree_bytes(path) for name, path in roots.items()}
        rows.append({"id": cid, "title": info["title"], "steps": info["steps"], "updated": info["updated"],
                     "sizes": sizes, "total_bytes": sum(sizes.values())})
    rows.sort(key=lambda r: str(r["updated"] or ""), reverse=True)
    return {"schema": f"{PREFIX}.list.v1", "gemini_home": str(home), "count": len(rows), "conversations": rows,
            "note": "Select sources by exact id only, never by title."}


def owned_members(home: Path, conversation_id: str) -> tuple[list[Path], list[str]]:
    roots = own_roots(home, conversation_id)
    files, unsafe = [], []
    brain = roots["brain"]
    if brain.exists():
        if is_reparse(brain):
            unsafe.append(str(brain))
        else:
            for path in sorted(brain.rglob("*")):
                if is_reparse(path):
                    unsafe.append(str(path))
                elif path.is_file():
                    files.append(path)
    for name in ("database", "annotation"):
        path = roots[name]
        if path.exists() or path.is_symlink():
            (unsafe.append(str(path)) if is_reparse(path) else files.append(path))
    for extra in (Path(str(roots["database"]) + "-wal"), Path(str(roots["database"]) + "-shm")):
        if extra.is_file():
            files.append(extra)
    if not files:
        raise TransferError("source_not_found", "No brain, database or annotation files for this conversation.",
                            conversation_id=conversation_id)
    return files, unsafe


def destination_transcript(claude_home: Path, session_id: str) -> Path | None:
    found = sorted((claude_home / "projects").glob(f"*/{session_id}.jsonl"))
    return found[0] if len(found) == 1 else None


def inspect(home: Path, source_id: str, destination_id: str, archive_root: Path, claude_home: Path) -> dict[str, Any]:
    source_id, destination_id = exact_id(source_id, "source"), exact_id(destination_id, "destination")
    if source_id == destination_id:
        raise TransferError("source_is_destination", "The destination cannot be the source.")
    files, unsafe = owned_members(home, source_id)
    members = []
    for path in files:
        stat = path.stat()
        members.append({"path": str(path), "relative": path.relative_to(home).as_posix(),
                        "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": sha256(path)})
    blockers = []
    if unsafe:
        blockers.append("unsafe_members")
    live = live_processes()
    if live:
        blockers.append("source_live")
    destination = destination_transcript(claude_home, destination_id)
    if destination is None:
        blockers.append("destination_transcript_missing")
    info = summary_of(home, source_id)
    transcript = home / "brain" / source_id / TRANSCRIPT
    # agy stores each subagent as <conversation-id>.json (older layouts used a directory per id).
    subagents = sorted(p.stem if p.is_file() and p.suffix == ".json" else p.name
                       for p in (home / "brain" / source_id / ".system_generated" / "subagents").glob("*"))
    tasks = sorted(p.name for p in (home / "brain" / source_id).glob("task-*"))
    return {
        "schema": f"{PREFIX}.inspection.v1", "version": VERSION, "source_system": "gemini-antigravity-cli",
        "source_conversation_id": source_id, "destination_session_id": destination_id,
        "gemini_home": str(home), "archive_root": str(archive_root), "title": info["title"],
        "steps": info["steps"], "updated": info["updated"], "workspaces": info["workspaces"],
        "transcript": str(transcript) if transcript.is_file() else None,
        "members": members, "member_count": len(members), "total_bytes": sum(m["bytes"] for m in members),
        "subagent_ids": subagents, "task_directories": tasks, "unsafe_members": unsafe,
        "destination_transcript": str(destination) if destination else None,
        "source_live": bool(live), "live_processes": live,
        "reframe_tile_references": reframe_references(info["workspaces"]),
        "shared_index_residuals": shared_residuals(home, source_id),
        "blockers": blockers, "retirement_ready": not blockers, "mutations_performed": False,
    }


# ---------------------------------------------------------------- transcript parsing

def user_text(content: str) -> str:
    found = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, re.S)
    return found.group(1) if found else content


def entries_of(number: int, record: dict[str, Any], tools: bool) -> list[dict[str, Any]]:
    kind, content = record.get("type"), str(record.get("content") or "")
    base = {"line": number, "step": record.get("step_index"), "timestamp": record.get("created_at")}
    out = []
    if kind == "USER_INPUT" and content:
        out.append({**base, "kind": "user", "text": user_text(content)})
    elif kind == "CHECKPOINT" and content:
        out.append({**base, "kind": "checkpoint", "text": content})
    elif kind == "SYSTEM_MESSAGE" and content:
        out.append({**base, "kind": "system", "text": content})
    elif kind == "PLANNER_RESPONSE" and content:
        out.append({**base, "kind": "assistant", "text": content})
    elif kind == "GENERIC" and content and tools:
        out.append({**base, "kind": "tool_result", "text": content})
    if tools:
        for call in record.get("tool_calls") or []:
            if isinstance(call, dict):
                out.append({**base, "kind": "tool_use",
                            "text": f"{call.get('name')}: {json.dumps(call.get('args'), ensure_ascii=False)}"})
    return out


def arg_values(call: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    values = []
    for key in keys:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip().strip('"'))
    return values


def catalog(manifest: dict[str, Any], head: int, tail: int, milestones: int, chars: int,
            cap: int = 200) -> dict[str, Any]:
    transcript = manifest.get("transcript")
    if not transcript or not Path(transcript).is_file():
        raise TransferError("transcript_missing", "Source has no transcript.jsonl to catalog.")
    users, checkpoints = [], []
    first: list[dict[str, Any]] = []
    last: deque[dict[str, Any]] = deque(maxlen=tail)
    marked: deque[dict[str, Any]] = deque(maxlen=milestones)
    finals: deque[dict[str, Any]] = deque(maxlen=tail)
    files: dict[str, int] = {}
    commands: deque[str] = deque(maxlen=cap)
    repos: set[str] = set()
    releases: set[str] = set()
    total = 0
    pending_final = None
    for number, record in iter_records(Path(transcript)):
        for call in record.get("tool_calls") or []:
            if isinstance(call, dict):
                for value in arg_values(call, FILE_ARG_KEYS):
                    files[value] = files.get(value, 0) + 1
                commands.extend(c[:chars] for c in arg_values(call, COMMAND_ARG_KEYS))
        raw = json.dumps(record.get("tool_calls") or [], ensure_ascii=False) + str(record.get("content") or "")
        repos.update(REPO_RE.findall(raw))
        releases.update(RELEASE_RE.findall(raw))
        if record.get("type") == "USER_INPUT" and pending_final:
            finals.append(pending_final)
            pending_final = None
        for entry in entries_of(number, record, tools=False):
            text = entry.pop("text")
            entry |= {"excerpt": text[:chars], "truncated": len(text) > chars}
            total += 1
            if entry["kind"] == "user":
                users.append(entry)
            elif entry["kind"] == "checkpoint":
                checkpoints.append(entry)
            elif entry["kind"] == "assistant":
                pending_final = entry
            if entry["kind"] in ("user", "checkpoint") or any(t in entry["excerpt"].casefold() for t in MILESTONES):
                marked.append(entry)
            if len(first) < head:
                first.append(entry)
            else:
                last.append(entry)
    if pending_final:
        finals.append(pending_final)
    chosen = {e["line"]: e for e in [*first, *marked, *last]}
    top_files = sorted(files.items(), key=lambda kv: -kv[1])[:cap]
    return {"schema": f"{PREFIX}.catalog.v1", "source_conversation_id": manifest["source_conversation_id"],
            "title": manifest.get("title"), "transcript": transcript,
            "limits": {"head": head, "tail": tail, "milestones": milestones, "excerpt_chars": chars, "cap": cap},
            "user_requests": users[-cap:], "user_request_count": len(users), "checkpoints": checkpoints[-cap:],
            "final_assistant_messages": list(finals),
            "files_touched": [{"path": p, "calls": n} for p, n in top_files], "files_touched_count": len(files),
            "commands_recent": list(commands), "git_repositories": sorted(repos)[:cap],
            "releases_and_prs": sorted(releases)[:cap], "eligible_entries": total,
            "sampled_entries": [chosen[k] for k in sorted(chosen)], "truncated": len(chosen) < total}


def transcript_path(home: Path, conversation_id: str) -> Path:
    path = home / "brain" / exact_id(conversation_id, "conversation") / TRANSCRIPT
    if not path.is_file():
        raise TransferError("transcript_missing", "No transcript.jsonl for this conversation.", path=str(path))
    return path


def search(home: Path, conversation_id: str, pattern: str, kinds: set[str] | None, tools: bool,
           limit: int, chars: int, latest: bool) -> dict[str, Any]:
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise TransferError("invalid_pattern", f"Invalid regular expression: {exc}") from exc
    matches: deque[dict[str, Any]] | list[dict[str, Any]] = deque(maxlen=limit) if latest else []
    total = 0
    for number, record in iter_records(transcript_path(home, conversation_id)):
        for item in entries_of(number, record, tools):
            if kinds and item["kind"] not in kinds:
                continue
            hit = regex.search(item["text"])
            if not hit:
                continue
            total += 1
            if not latest and len(matches) >= limit:
                continue
            start = max(0, hit.start() - chars // 3)
            text = item.pop("text")
            matches.append({**item, "excerpt": text[start:start + chars], "offset": start, "length": len(text)})
    return {"conversation_id": conversation_id, "pattern": pattern, "total_matches": total,
            "returned": len(matches), "truncated": total > len(matches), "matches": list(matches)}


def show(home: Path, conversation_id: str, line: int, chars: int, offset: int) -> dict[str, Any]:
    for number, record in iter_records(transcript_path(home, conversation_id)):
        if number == line:
            parts = [e["text"] for e in entries_of(number, record, True)]
            if record.get("thinking"):
                parts.append(f"[thinking]\n{record['thinking']}")
            text = "\n\n".join(parts)
            return {"line": line, "type": record.get("type"), "step": record.get("step_index"),
                    "timestamp": record.get("created_at"), "length": len(text), "offset": offset,
                    "text": text[offset:offset + chars], "truncated": offset + chars < len(text)}
        if number > line:
            break
    raise TransferError("line_not_found", "No parsable record at that line.", line=line)


# ---------------------------------------------------------------- handoff / acceptance

def sections(markdown: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^#{1,3}\s+(.+?)\s*$", markdown))
    return {m.group(1).strip(): markdown[m.end():(matches[i + 1].start() if i + 1 < len(matches) else len(markdown))].strip()
            for i, m in enumerate(matches)}


def validate_handoff(manifest: dict[str, Any], handoff: Path) -> dict[str, Any]:
    if not handoff.is_file() or handoff.stat().st_size > 2 << 20:
        raise TransferError("handoff_invalid", "CONTEXT_TRANSFER.md is missing or exceeds 2 MiB.")
    body = sections(handoff.read_text(encoding="utf-8-sig"))
    missing = [name for name in REQUIRED_SECTIONS if not body.get(name, "").strip()]
    child = body.get("Gemini Subagent And Task Map", "")
    unmapped = [sid for sid in [*manifest.get("subagent_ids", []), *manifest.get("task_directories", [])]
                if not re.search(rf"(?m)^\s*(?:[-*]\s*)?`?{re.escape(sid)}`?\s*:", child)]
    if missing or unmapped:
        raise TransferError("handoff_incomplete", "Handoff contract not satisfied.",
                            missing_sections=missing, unmapped_subagents_or_tasks=unmapped)
    return {"schema": f"{PREFIX}.handoff_validation.v1", "ok": True,
            "source_conversation_id": manifest["source_conversation_id"], "handoff_path": str(handoff.resolve()),
            "handoff_sha256": sha256(handoff), "retirement_blockers": manifest["blockers"]}


def validate_acceptance(manifest: dict[str, Any], handoff: Path, acceptance: Path) -> dict[str, Any]:
    handoff_result = validate_handoff(manifest, handoff)
    payload = load_json(acceptance, "acceptance")
    expected = {"schema": f"{PREFIX}.destination_acceptance.v1",
                "source_conversation_id": manifest["source_conversation_id"],
                "destination_session_id": manifest["destination_session_id"],
                "handoff_sha256": handoff_result["handoff_sha256"], "handoff_ready": True}
    invalid = [key for key, value in expected.items() if payload.get(key) != value]
    for key in ("mapped_active_requirements", "evidence_sources_inspected", "repository_state_verified"):
        if not isinstance(payload.get(key), list) or not payload[key]:
            invalid.append(key)
    if not isinstance(payload.get("unresolved_uncertainties"), list):
        invalid.append("unresolved_uncertainties")
    if payload.get("critical_unmapped_objectives") != []:
        invalid.append("critical_unmapped_objectives")
    if not str(payload.get("first_continuation_action") or "").strip():
        invalid.append("first_continuation_action")
    if invalid:
        raise TransferError("acceptance_incomplete", "Destination acceptance is incomplete.",
                            invalid_fields=sorted(set(invalid)))
    return {"schema": f"{PREFIX}.acceptance_validation.v1", "ok": True,
            "source_conversation_id": manifest["source_conversation_id"],
            "destination_session_id": manifest["destination_session_id"],
            "acceptance_sha256": sha256(acceptance), "handoff_sha256": handoff_result["handoff_sha256"]}


# ---------------------------------------------------------------- pack / verify / restore

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:60] or "gemini-conversation"


def transfer_directory(manifest: dict[str, Any], explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    now = datetime.now()
    title = manifest.get("title") or manifest["source_conversation_id"]
    return Path(manifest["archive_root"]) / f"{now:%Y}" / f"{now:%Y-%m-%d}-{slug(str(title))}"


def refuse_c_drive(path: Path) -> None:
    drive = os.path.splitdrive(str(path.resolve() if path.exists() else path.absolute()))[0]
    if drive.upper() == "C:":
        raise TransferError("archive_root_on_c", "Archives never go to C:; pass a non-C --transfer-directory.",
                            path=str(path))


def recheck_members(manifest: dict[str, Any]) -> list[str]:
    changed = []
    for member in manifest["members"]:
        path = Path(member["path"])
        if not path.is_file() or path.stat().st_size != member["bytes"] or sha256(path) != member["sha256"]:
            changed.append(member["path"])
    files, _ = owned_members(Path(manifest["gemini_home"]), manifest["source_conversation_id"])
    known = {os.path.normcase(m["path"]) for m in manifest["members"]}
    changed += [str(p) for p in files if os.path.normcase(str(p)) not in known]
    return changed


def unrelated_live_record(evidence: str | None) -> dict[str, Any] | None:
    """Explicit override for agy processes the user confirmed belong to other conversations.

    agy exposes no per-process conversation id, so liveness is conservative. With an override the
    caller states the user's confirmation; member hashes are still rechecked before every step.
    """
    if evidence is None:
        return None
    if not evidence.strip():
        raise TransferError("override_evidence_missing", "--confirmed-unrelated-live needs the user's confirmation text.")
    return {"evidence": evidence.strip(), "live_processes": live_processes(),
            "recorded_at": datetime.now(timezone.utc).isoformat()}


def pack(manifest_path: Path, handoff: Path, directory: str | None, binary: str | None,
         unrelated_live: str | None = None) -> dict[str, Any]:
    manifest = load_json(manifest_path, "inspection")
    handoff_result = validate_handoff(manifest, handoff)
    override = unrelated_live_record(unrelated_live)
    live_blocked = (manifest["source_live"] or bool(live_processes())) and override is None
    if live_blocked or "unsafe_members" in manifest["blockers"]:
        raise TransferError("pack_blocked", "agy is running or the source has unsafe members.",
                            blockers=manifest["blockers"])
    changed = recheck_members(manifest)
    if changed:
        raise TransferError("source_changed", "Members changed since inspection; inspect again.", changed=changed[:50])
    tool = seven_zip(binary)
    root = transfer_directory(manifest, directory)
    anchor = Path(manifest["archive_root"]).anchor
    if not directory and (not anchor or not Path(anchor).exists()):
        raise TransferError("archive_root_unavailable", "Default archive drive is missing; pass an explicit non-C "
                            "--transfer-directory (for example on D:) and record the pending G: archive move.",
                            archive_root=manifest["archive_root"])
    refuse_c_drive(root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transaction = root / "Archives" / manifest["source_conversation_id"] / stamp
    staging = transaction / ".staging"
    transaction.mkdir(parents=True, exist_ok=False)
    (root / "Records").mkdir(exist_ok=True)
    archive = transaction / "conversation-tree.7z"
    try:
        for member in manifest["members"]:
            target = staging / "gemini-home" / member["relative"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(member["path"], target)
            if sha256(target) != member["sha256"]:
                raise TransferError("snapshot_changed", "Member changed while copying.", path=member["path"])
        shutil.copy2(handoff, staging / "CONTEXT_TRANSFER.md")
        archive_manifest = {"schema": f"{PREFIX}.archive_manifest.v1", "version": VERSION,
                            "source_conversation_id": manifest["source_conversation_id"],
                            "destination_session_id": manifest["destination_session_id"],
                            "gemini_home": manifest["gemini_home"], "title": manifest.get("title"),
                            "created_at": stamp, "inspection_sha256": sha256(manifest_path),
                            "handoff_sha256": handoff_result["handoff_sha256"], "members": manifest["members"],
                            "compression": COMPRESSION, "source_paths_passed_to_seven_zip": False}
        write_json(staging / "manifest.json", archive_manifest)
        run_7z(tool, "a", *COMPRESSION, str(archive), ".", cwd=str(staging))
        write_json(transaction / "manifest.json", archive_manifest)
        shutil.copy2(handoff, transaction / "CONTEXT_TRANSFER.md")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if staging.exists():
        raise TransferError("staging_residual", "Snapshot staging could not be removed.", path=str(staging))
    return {"schema": f"{PREFIX}.pack_result.v1", "ok": True, "transfer_directory": str(root),
            "archive": str(archive), "archive_sha256": sha256(archive), "archive_bytes": archive.stat().st_size,
            "source_bytes": manifest["total_bytes"], "member_count": manifest["member_count"], "staging_removed": True,
            "unrelated_live_override": override}


def extract_verified(archive: Path, binary: str | None, staging: Path) -> dict[str, Any]:
    tool = seven_zip(binary)
    side = load_json(archive.parent / "manifest.json", "archive_manifest")
    run_7z(tool, "t", str(archive))
    run_7z(tool, "x", str(archive), f"-o{staging}", "-y")
    inner = load_json(staging / "manifest.json", "inner_manifest")
    if inner != side:
        raise TransferError("manifest_mismatch", "Inner and external manifests differ.")
    mismatched = [m["relative"] for m in side["members"]
                  if not (staging / "gemini-home" / m["relative"]).is_file()
                  or sha256(staging / "gemini-home" / m["relative"]) != m["sha256"]]
    if mismatched:
        raise TransferError("member_hash_mismatch", "Extracted members differ from the manifest.", members=mismatched)
    return side


def verify(archive: Path, binary: str | None) -> dict[str, Any]:
    staging = archive.parent / ".verify"
    if staging.exists():
        raise TransferError("staging_exists", "A previous verification staging directory remains.", path=str(staging))
    try:
        side = extract_verified(archive, binary, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    result = {"schema": f"{PREFIX}.verification.v1", "ok": True, "archive": str(archive),
              "archive_sha256": sha256(archive), "source_conversation_id": side["source_conversation_id"],
              "destination_session_id": side["destination_session_id"], "members_verified": len(side["members"]),
              "manifest_sha256": sha256(archive.parent / "manifest.json"), "staging_removed": not staging.exists()}
    write_json(archive.parent / "verification.json", result)
    write_json(archive.parents[3] / "Records" / "verification.json", result)
    return result


def restore(archive: Path, binary: str | None) -> dict[str, Any]:
    staging = archive.parent / ".restore"
    if staging.exists():
        raise TransferError("staging_exists", "A previous restore staging directory remains.", path=str(staging))
    restored, identical, conflicts = [], [], []
    try:
        side = extract_verified(archive, binary, staging)
        for member in side["members"]:
            target = Path(member["path"])
            if target.exists():
                (identical if target.is_file() and sha256(target) == member["sha256"] else conflicts).append(str(target))
        if conflicts:
            raise TransferError("restore_conflict", "Existing different files were preserved; nothing restored.",
                                conflicts=conflicts)
        for member in side["members"]:
            target = Path(member["path"])
            if str(target) in identical:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with (staging / "gemini-home" / member["relative"]).open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            if sha256(target) != member["sha256"]:
                raise TransferError("restore_hash_mismatch", "Restored bytes differ.", path=str(target))
            restored.append(str(target))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"schema": f"{PREFIX}.restore.v1", "ok": True, "restored": restored, "skipped_identical": identical,
            "note": "agy rebuilds its shared metadata cache itself; the helper never writes shared indexes."}


# ---------------------------------------------------------------- retirement / completion

def retirement_plan(manifest_path: Path, handoff: Path, acceptance: Path, verification_path: Path,
                    unrelated_live: str | None = None) -> dict[str, Any]:
    manifest = load_json(manifest_path, "inspection")
    accepted = validate_acceptance(manifest, handoff, acceptance)
    verification = load_json(verification_path, "verification")
    archive = Path(verification.get("archive", ""))
    if not verification.get("ok") or not archive.is_file() or sha256(archive) != verification.get("archive_sha256"):
        raise TransferError("archive_unverified", "Verified archive is missing or changed.")
    side = load_json(archive.parent / "manifest.json", "archive_manifest")
    if side["source_conversation_id"] != manifest["source_conversation_id"] or \
            side["handoff_sha256"] != accepted["handoff_sha256"]:
        raise TransferError("archive_binding", "Archive is not bound to this source and accepted handoff.")
    live = live_processes()
    if live and unrelated_live_record(unrelated_live) is None:
        raise TransferError("source_live", "agy/Antigravity is running; close it before retirement, or pass "
                            "--confirmed-unrelated-live with the user's confirmation.", processes=live)
    home = Path(side["gemini_home"])
    files, unsafe = owned_members(home, side["source_conversation_id"])
    if unsafe:
        raise TransferError("unsafe_members", "Reparse points under the conversation; nothing deleted.", unsafe=unsafe)
    archived = {os.path.normcase(m["path"]): m["sha256"] for m in side["members"]}
    current = [{"path": str(p), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in files]
    unarchived = [f["path"] for f in current if archived.get(os.path.normcase(f["path"])) != f["sha256"]]
    if unarchived:
        raise TransferError("unarchived_members", "Current files are absent from or differ in the archive; "
                            "re-inspect and re-pack.", members=unarchived[:50])
    roots = own_roots(home, side["source_conversation_id"])
    plan = {"schema": f"{PREFIX}.retirement_plan.v1", "source_conversation_id": side["source_conversation_id"],
            "gemini_home": str(home), "archive": str(archive), "archive_sha256": verification["archive_sha256"],
            "acceptance_sha256": accepted["acceptance_sha256"], "brain_directory": str(roots["brain"]),
            "files": sorted(current, key=lambda f: f["path"]), "bytes": sum(f["bytes"] for f in current)}
    return plan


def retire(manifest_path: Path, handoff: Path, acceptance: Path, verification_path: Path, dry_run: bool,
           plan_sha: str | None, output: Path | None, unrelated_live: str | None = None) -> dict[str, Any]:
    plan = retirement_plan(manifest_path, handoff, acceptance, verification_path, unrelated_live)
    override = unrelated_live_record(unrelated_live)
    digest = canonical_sha(plan)
    manifest = load_json(manifest_path, "inspection")
    home = Path(plan["gemini_home"])
    if dry_run:
        return {"schema": f"{PREFIX}.retirement_dry_run.v1", "ok": True, "dry_run": True, "plan_sha256": digest,
                "files": len(plan["files"]), "bytes": plan["bytes"], "plan": plan,
                "next": "retire ... --plan-sha256 <plan_sha256>"}
    if plan_sha != digest:
        raise TransferError("plan_sha_mismatch", "Run --dry-run and quote its plan_sha256; state changed or missing.",
                            expected=digest, supplied=plan_sha)
    deleted, failed = [], []
    for entry in plan["files"]:
        try:
            Path(entry["path"]).unlink()
            deleted.append(entry)
        except OSError as exc:
            failed.append({"path": entry["path"], "error": str(exc)})
    brain = Path(plan["brain_directory"])
    if brain.is_dir() and not is_reparse(brain):
        for directory in sorted((p for p in brain.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            brain.rmdir()
        except OSError:
            pass
    remaining = [str(p) for p in brain.rglob("*")] if brain.exists() else []
    result = {"schema": f"{PREFIX}.retirement_result.v1", "ok": not failed, "complete": not failed and not remaining,
              "source_conversation_id": plan["source_conversation_id"], "plan_sha256": digest,
              "archive": plan["archive"], "files_deleted": len(deleted), "bytes_reclaimed": sum(f["bytes"] for f in deleted),
              "failed": failed, "remaining_under_brain": remaining[:50],
              "shared_index_residuals": shared_residuals(home, plan["source_conversation_id"]),
              "reframe_tile_references": manifest.get("reframe_tile_references", []),
              "unrelated_live_override": override,
              "note": "Shared indexes and Reframe hook directories were not edited."}
    if output:
        write_json(output, result)
    return result


def validate_completion(directory: Path) -> dict[str, Any]:
    records = directory / "Records"
    needed = {name: records / name for name in ("acceptance-validation.json", "verification.json")}
    missing = [n for n, p in needed.items() if not p.is_file()]
    if missing:
        raise TransferError("records_missing", "Completion records missing.", missing=missing)
    loaded = {n: load_json(p, n) for n, p in needed.items()}
    failures = [n for n, r in loaded.items() if r.get("ok") is not True]
    retirement, preservation = records / "retirement-result.json", records / "preservation-only.json"
    if retirement.is_file():
        endpoint = "takeover_retired" if load_json(retirement, "retirement").get("complete") is True else None
        if endpoint is None:
            failures.append("retirement-result.json")
    elif preservation.is_file():
        endpoint = "preservation_only"
    else:
        endpoint = None
        failures.append("endpoint_record")
    ids = {r.get("source_conversation_id") for r in loaded.values()}
    if retirement.is_file():
        ids.add(load_json(retirement, "retirement").get("source_conversation_id"))
    if len(ids) != 1:
        failures.append("source_id_mismatch")
    if failures:
        raise TransferError("completion_invalid", "Completion records inconsistent.", failures=failures)
    return {"schema": f"{PREFIX}.completion.v1", "ok": True, "endpoint": endpoint, "source_conversation_id": ids.pop(),
            "note": "Record consistency only; it does not re-run live checks."}


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    home_default = str(DEFAULT_GEMINI_HOME)
    p = sub.add_parser("list")
    p.add_argument("--gemini-home", default=home_default)
    p = sub.add_parser("inspect")
    p.add_argument("--source-conversation-id", required=True)
    p.add_argument("--destination-session-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    p.add_argument("--gemini-home", default=home_default)
    p.add_argument("--claude-home", default=str(DEFAULT_CLAUDE_HOME))
    p.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    p.add_argument("--output", required=True)
    p = sub.add_parser("catalog")
    p.add_argument("--manifest", required=True)
    p.add_argument("--head", type=int, default=15)
    p.add_argument("--tail", type=int, default=30)
    p.add_argument("--milestones", type=int, default=150)
    p.add_argument("--excerpt-chars", type=int, default=600)
    p.add_argument("--cap", type=int, default=200)
    p.add_argument("--output", required=True)
    p = sub.add_parser("validate-handoff")
    p.add_argument("--manifest", required=True)
    p.add_argument("--handoff", required=True)
    p = sub.add_parser("validate-acceptance")
    p.add_argument("--manifest", required=True)
    p.add_argument("--handoff", required=True)
    p.add_argument("--acceptance", required=True)
    p.add_argument("--output")
    p = sub.add_parser("pack")
    p.add_argument("--manifest", required=True)
    p.add_argument("--handoff", required=True)
    p.add_argument("--transfer-directory")
    p.add_argument("--seven-zip-path")
    p.add_argument("--confirmed-unrelated-live", metavar="EVIDENCE",
                   help="User-confirmed statement that every running agy belongs to another conversation.")
    for name in ("verify", "restore"):
        p = sub.add_parser(name)
        p.add_argument("--archive", required=True)
        p.add_argument("--seven-zip-path")
    p = sub.add_parser("retire")
    for flag in ("--manifest", "--handoff", "--acceptance", "--verification"):
        p.add_argument(flag, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--plan-sha256")
    p.add_argument("--confirmed-unrelated-live", metavar="EVIDENCE",
                   help="User-confirmed statement that every running agy belongs to another conversation.")
    p.add_argument("--output", help="retirement-result.json path (default Records/ beside verification.json)")
    p = sub.add_parser("validate-completion")
    p.add_argument("--transfer-directory", required=True)
    p = sub.add_parser("search", help="Regex search over a source conversation transcript.")
    p.add_argument("--conversation-id", required=True)
    p.add_argument("--pattern", required=True)
    p.add_argument("--gemini-home", default=home_default)
    p.add_argument("--kind", action="append", help="user, assistant, checkpoint, system, tool_use, tool_result.")
    p.add_argument("--tools", action="store_true", help="Also search tool calls and tool outputs.")
    p.add_argument("--latest", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--excerpt-chars", type=int, default=400)
    p = sub.add_parser("show", help="Expand one transcript line found by search.")
    p.add_argument("--conversation-id", required=True)
    p.add_argument("--line", type=int, required=True)
    p.add_argument("--gemini-home", default=home_default)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--chars", type=int, default=4000)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            result = list_conversations(Path(args.gemini_home))
        elif args.command == "inspect":
            result = inspect(Path(args.gemini_home), args.source_conversation_id, args.destination_session_id,
                             Path(args.archive_root), Path(args.claude_home))
            write_json(args.output, result)
            result = {k: result[k] for k in ("source_conversation_id", "destination_session_id", "title",
                                             "member_count", "total_bytes", "subagent_ids", "task_directories",
                                             "blockers", "retirement_ready", "reframe_tile_references",
                                             "live_processes")} | {"output": args.output}
        elif args.command == "catalog":
            result = catalog(load_json(args.manifest, "inspection"), args.head, args.tail, args.milestones,
                             args.excerpt_chars, args.cap)
            write_json(args.output, result)
            result = {"output": args.output, "user_request_count": result["user_request_count"],
                      "checkpoints": len(result["checkpoints"]), "files_touched_count": result["files_touched_count"],
                      "git_repositories": result["git_repositories"][:20], "truncated": result["truncated"]}
        elif args.command == "validate-handoff":
            result = validate_handoff(load_json(args.manifest, "inspection"), Path(args.handoff))
        elif args.command == "validate-acceptance":
            result = validate_acceptance(load_json(args.manifest, "inspection"), Path(args.handoff),
                                         Path(args.acceptance))
            if args.output:
                write_json(args.output, result)
        elif args.command == "pack":
            result = pack(Path(args.manifest), Path(args.handoff), args.transfer_directory, args.seven_zip_path,
                          args.confirmed_unrelated_live)
        elif args.command == "verify":
            result = verify(Path(args.archive), args.seven_zip_path)
        elif args.command == "restore":
            result = restore(Path(args.archive), args.seven_zip_path)
        elif args.command == "retire":
            output = Path(args.output) if args.output else Path(args.verification).parent / "retirement-result.json"
            result = retire(Path(args.manifest), Path(args.handoff), Path(args.acceptance), Path(args.verification),
                            args.dry_run, args.plan_sha256, None if args.dry_run else output,
                            args.confirmed_unrelated_live)
        elif args.command == "search":
            kinds = set(args.kind) if args.kind else None
            tools = args.tools or bool(kinds and kinds & {"tool_use", "tool_result"})
            result = search(Path(args.gemini_home), args.conversation_id, args.pattern, kinds, tools,
                            max(1, args.limit), max(40, args.excerpt_chars), args.latest)
        elif args.command == "show":
            result = show(Path(args.gemini_home), args.conversation_id, args.line, max(1, args.chars),
                          max(0, args.offset))
        else:
            result = validate_completion(Path(args.transfer_directory))
    except TransferError as exc:
        print(json.dumps({"ok": False, "error": exc.kind, "message": str(exc), "details": exc.details}, indent=2))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
