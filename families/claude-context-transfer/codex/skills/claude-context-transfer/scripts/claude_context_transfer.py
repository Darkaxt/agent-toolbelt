"""Claude Code session takeover: inspect, catalog, handoff, verified archive, retirement gate, restore.

Read-only toward live Claude state. Deletion is delegated to the installed
thread-cleanup skill; this helper only proves that everything it would delete is
archived and accepted.
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
PREFIX = "agent_toolbelt_claude_context_transfer"
DEFAULT_ARCHIVE_ROOT = Path(r"G:\Archives\Claude\ContextTransfers")
DEFAULT_REFRAME_STATE = Path(r"D:\Tools\Reframe\profiles\ClaudeGPT\state.json")
UUID_RE = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
REQUIRED_SECTIONS = (
    "Current Objective",
    "Authoritative Specifications And Plans",
    "Completed Work With Evidence",
    "Active Stage And Exact Next Actions",
    "Unresolved Blockers And Required Deferrals",
    "Durable Decisions And User Constraints",
    "Failed Approaches Not To Repeat",
    "Repositories Branches And Artifacts",
    "Subagent Contribution Map",
    "Uncertainties Requiring Verification",
    "Archive And Recall References",
)
MILESTONES = ("decision", "blocker", "failed", "error", "tests passed", "verified", "commit ",
              "merged", "pushed", "released", "next action", "plan")
COMPRESSION = ["-t7z", "-mx=9", "-m0=lzma2", "-md=256m", "-mfb=273", "-ms=on", "-mmt=on"]


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


def run_7z(binary: str, *args: str) -> str:
    completed = subprocess.run([binary, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise TransferError("seven_zip_failed", f"7-Zip exited {completed.returncode}",
                            output=(completed.stdout + completed.stderr)[-2000:])
    return completed.stdout


# ---------------------------------------------------------------- liveness

def running_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        raise TransferError("liveness_unsupported", "Live Claude session verification is Windows-only.")
    command = "Get-CimInstance Win32_Process | Select-Object Name,ProcessId,CommandLine | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, check=True)
    rows = json.loads(result.stdout or "[]")
    return rows if isinstance(rows, list) else [rows]


def live_session_ids(home: Path) -> set[str]:
    """Registered sessions with a running pid plus explicit command-line UUID references."""
    processes = running_processes()
    pids = {row.get("ProcessId") for row in processes}
    live: set[str] = set()
    for path in (home / "sessions").glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if record.get("pid") in pids and record.get("sessionId"):
            live.add(str(record["sessionId"]))
    for row in processes:
        name, command = (row.get("Name") or "").casefold(), row.get("CommandLine") or ""
        if name == "claude.exe" or (name == "node.exe" and "claude-code" in command.casefold()):
            live.update(UUID_RE.findall(command))
    return live


def reframe_references(state_path: Path | None, session_id: str) -> list[dict[str, Any]]:
    if not state_path or not state_path.is_file():
        return []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [{"error": "reframe_state_unreadable", "path": str(state_path)}]
    tiles = (state.get("sessions") or {}).values()
    return [{"tile_id": tile.get("id"), "name": tile.get("name") or tile.get("claudeName"),
             "lifecycle": tile.get("lifecycle"), "state_path": str(state_path)}
            for tile in tiles if isinstance(tile, dict) and tile.get("claudeSessionId") == session_id]


# ---------------------------------------------------------------- inspect

def owned_members(home: Path, session_id: str) -> tuple[Path, list[Path], list[str]]:
    mains = sorted((home / "projects").glob(f"*/{session_id}.jsonl"))
    if len(mains) != 1:
        raise TransferError("source_not_found", "Source must resolve to exactly one project transcript.",
                            matches=[str(p) for p in mains])
    main = mains[0]
    files, unsafe = [main], []
    roots = [main.with_suffix(""), home / "file-history" / session_id,
             home / "session-env" / session_id, home / "tasks" / session_id]
    for root in roots:
        if not root.exists():
            continue
        if is_reparse(root):
            unsafe.append(str(root))
            continue
        for path in sorted(root.rglob("*")):
            if is_reparse(path):
                unsafe.append(str(path))
            elif path.is_file():
                files.append(path)
    for extra in (home / "debug" / f"{session_id}.txt", home / f"security_warnings_state_{session_id}.json"):
        if extra.is_file():
            files.append(extra)
    return main, files, unsafe


def titles(path: Path) -> dict[str, Any]:
    custom = ai = None
    for _, record in iter_records(path):
        if record.get("type") == "custom-title":
            custom = record.get("customTitle")
        elif record.get("type") == "ai-title":
            ai = record.get("aiTitle")
    return {"custom_title": custom, "ai_title": ai}


def destination_dependency(path: Path, source_id: str) -> int:
    count = 0
    for _, record in iter_records(path):
        if record.get("sessionId") == source_id:
            count += 1
    return count


def inspect(home: Path, source_id: str, destination_id: str, archive_root: Path,
            reframe_state: Path | None) -> dict[str, Any]:
    source_id, destination_id = exact_id(source_id, "source"), exact_id(destination_id, "destination")
    blockers: list[str] = []
    if source_id == destination_id:
        raise TransferError("source_is_destination", "The destination session cannot retire itself.")
    main, files, unsafe = owned_members(home, source_id)
    members = []
    for path in files:
        stat = path.stat()
        members.append({"path": str(path), "relative": path.relative_to(home).as_posix(),
                        "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": sha256(path)})
    if unsafe:
        blockers.append("unsafe_members")
    live = live_session_ids(home)
    if source_id in live:
        blockers.append("source_live")
    destinations = sorted((home / "projects").glob(f"*/{destination_id}.jsonl"))
    dependent = 0
    if len(destinations) != 1:
        blockers.append("destination_transcript_missing")
    else:
        dependent = destination_dependency(destinations[0], source_id)
        if dependent:
            blockers.append("destination_is_history_dependent")
    subagents = sorted(p.stem for p in main.with_suffix("").glob("subagents/*.jsonl"))
    return {
        "schema": f"{PREFIX}.inspection.v1", "version": VERSION, "source_system": "claude",
        "source_session_id": source_id, "destination_session_id": destination_id,
        "claude_home": str(home), "archive_root": str(archive_root), "project_directory": main.parent.name,
        "source_titles": titles(main), "members": members, "member_count": len(members),
        "total_bytes": sum(m["bytes"] for m in members), "subagent_ids": subagents,
        "unsafe_members": unsafe, "destination_transcript": str(destinations[0]) if len(destinations) == 1 else None,
        "destination_dependent_records": dependent, "source_live": source_id in live,
        "reframe_tile_references": reframe_references(reframe_state, source_id),
        "blockers": blockers, "retirement_ready": not blockers, "mutations_performed": False,
    }


# ---------------------------------------------------------------- catalog

def text_of(record: dict[str, Any]) -> str | None:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
        return "\n".join(p for p in parts if p) or None
    return None


def entry_for(number: int, record: dict[str, Any], chars: int) -> dict[str, Any] | None:
    kind = record.get("type")
    if kind in ("user", "assistant") and not record.get("isMeta"):
        text = text_of(record)
        if not text or text.startswith("<command-") or text.startswith("<local-command"):
            return None
        automated = kind == "user" and text.lstrip().startswith(("<task-notification", "<system-reminder", "<tool-use"))
        label = "compact_summary" if record.get("isCompactSummary") else ("automated_event" if automated else kind)
    elif kind == "system" and (record.get("level") == "error" or record.get("error")):
        label, text = "system_error", str(record.get("content") or record.get("error"))
    elif kind == "pr-link":
        label, text = "pr_link", str(record.get("prUrl"))
    elif kind == "custom-title":
        label, text = "title", str(record.get("customTitle"))
    else:
        return None
    return {"line": number, "kind": label, "timestamp": record.get("timestamp"), "excerpt": text[:chars],
            "truncated": len(text) > chars}


def catalog_file(path: Path, head: int, tail: int, milestones: int, chars: int) -> dict[str, Any]:
    first: list[dict[str, Any]] = []
    last: deque[dict[str, Any]] = deque(maxlen=tail)
    marked: deque[dict[str, Any]] = deque(maxlen=milestones)
    total, current_title = 0, None
    for number, record in iter_records(path):
        entry = entry_for(number, record, chars)
        if entry is None:
            continue
        if entry["kind"] == "title":
            if entry["excerpt"] == current_title:
                continue  # Claude re-appends the same title on every resume.
            current_title = entry["excerpt"]
        total += 1
        if entry["kind"] in ("compact_summary", "pr_link", "title", "system_error") or (
                entry["kind"] == "user" or any(t in entry["excerpt"].casefold() for t in MILESTONES)):
            marked.append(entry)
        if len(first) < head:
            first.append(entry)
        else:
            last.append(entry)
    chosen = {e["line"]: e for e in [*first, *marked, *last]}
    entries = [chosen[k] for k in sorted(chosen)]
    return {"path": str(path), "eligible_entries": total, "sampled_entries": len(entries),
            "truncated": len(entries) < total, "entries": entries}


def catalog(manifest: dict[str, Any], head: int, tail: int, milestones: int, chars: int) -> dict[str, Any]:
    transcripts = [Path(m["path"]) for m in manifest["members"] if m["path"].endswith(".jsonl")]
    return {"schema": f"{PREFIX}.catalog.v1", "source_session_id": manifest["source_session_id"],
            "limits": {"head": head, "tail": tail, "milestones": milestones, "excerpt_chars": chars},
            "transcripts": [catalog_file(p, head, tail, milestones, chars) for p in transcripts]}


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
    child = body.get("Subagent Contribution Map", "")
    unmapped = [sid for sid in manifest.get("subagent_ids", [])
                if not re.search(rf"(?m)^\s*(?:[-*]\s*)?`?{re.escape(sid)}`?\s*:", child)]
    if missing or unmapped:
        raise TransferError("handoff_incomplete", "Handoff contract not satisfied.",
                            missing_sections=missing, unmapped_subagents=unmapped)
    return {"schema": f"{PREFIX}.handoff_validation.v1", "ok": True,
            "source_session_id": manifest["source_session_id"], "handoff_path": str(handoff.resolve()),
            "handoff_sha256": sha256(handoff), "retirement_blockers": manifest["blockers"]}


def validate_acceptance(manifest: dict[str, Any], handoff: Path, acceptance: Path) -> dict[str, Any]:
    handoff_result = validate_handoff(manifest, handoff)
    payload = load_json(acceptance, "acceptance")
    invalid = []
    expected = {"schema": f"{PREFIX}.destination_acceptance.v1", "source_session_id": manifest["source_session_id"],
                "destination_session_id": manifest["destination_session_id"],
                "handoff_sha256": handoff_result["handoff_sha256"], "handoff_ready": True}
    invalid += [key for key, value in expected.items() if payload.get(key) != value]
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
        raise TransferError("acceptance_incomplete", "Destination acceptance is incomplete.", invalid_fields=sorted(set(invalid)))
    return {"schema": f"{PREFIX}.acceptance_validation.v1", "ok": True,
            "source_session_id": manifest["source_session_id"],
            "destination_session_id": manifest["destination_session_id"],
            "acceptance_sha256": sha256(acceptance), "handoff_sha256": handoff_result["handoff_sha256"]}


# ---------------------------------------------------------------- pack / verify / restore

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:60] or "claude-session"


def transfer_directory(manifest: dict[str, Any], explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    now = datetime.now()
    title = manifest["source_titles"].get("custom_title") or manifest["source_titles"].get("ai_title") or manifest["source_session_id"]
    return Path(manifest["archive_root"]) / f"{now:%Y}" / f"{now:%Y-%m-%d}-{slug(str(title))}"


def recheck_members(manifest: dict[str, Any]) -> list[str]:
    changed = []
    for member in manifest["members"]:
        path = Path(member["path"])
        if not path.is_file() or path.stat().st_size != member["bytes"] or sha256(path) != member["sha256"]:
            changed.append(member["path"])
    return changed


def pack(manifest_path: Path, handoff: Path, directory: str | None, binary: str | None) -> dict[str, Any]:
    manifest = load_json(manifest_path, "inspection")
    handoff_result = validate_handoff(manifest, handoff)
    if manifest["source_live"] or "unsafe_members" in manifest["blockers"]:
        raise TransferError("pack_blocked", "Source is live or has unsafe members.", blockers=manifest["blockers"])
    changed = recheck_members(manifest)
    if changed:
        raise TransferError("source_changed", "Members changed since inspection; inspect again.", changed=changed)
    tool = seven_zip(binary)
    root = transfer_directory(manifest, directory)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transaction = root / "Archives" / manifest["source_session_id"] / stamp
    staging = transaction / ".staging"
    transaction.mkdir(parents=True, exist_ok=False)
    archive = transaction / "session-tree.7z"
    try:
        for member in manifest["members"]:
            target = staging / "claude-home" / member["relative"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(member["path"], target)
            if sha256(target) != member["sha256"]:
                raise TransferError("snapshot_changed", "Member changed while copying.", path=member["path"])
        shutil.copy2(handoff, staging / "CONTEXT_TRANSFER.md")
        archive_manifest = {"schema": f"{PREFIX}.archive_manifest.v1", "version": VERSION,
                            "source_session_id": manifest["source_session_id"],
                            "destination_session_id": manifest["destination_session_id"],
                            "claude_home": manifest["claude_home"], "created_at": stamp,
                            "inspection_sha256": sha256(manifest_path), "handoff_sha256": handoff_result["handoff_sha256"],
                            "members": manifest["members"], "compression": COMPRESSION,
                            "source_paths_passed_to_seven_zip": False}
        write_json(staging / "manifest.json", archive_manifest)
        subprocess_cwd_7z(tool, archive, staging)
        write_json(transaction / "manifest.json", archive_manifest)
        shutil.copy2(handoff, transaction / "CONTEXT_TRANSFER.md")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if staging.exists():
        raise TransferError("staging_residual", "Snapshot staging could not be removed.", path=str(staging))
    return {"schema": f"{PREFIX}.pack_result.v1", "ok": True, "transfer_directory": str(root),
            "archive": str(archive), "archive_sha256": sha256(archive), "archive_bytes": archive.stat().st_size,
            "source_bytes": manifest["total_bytes"], "member_count": manifest["member_count"],
            "staging_removed": True}


def subprocess_cwd_7z(tool: str, archive: Path, staging: Path) -> None:
    completed = subprocess.run([tool, "a", *COMPRESSION, str(archive), "."], cwd=str(staging),
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise TransferError("seven_zip_failed", f"7-Zip exited {completed.returncode}",
                            output=(completed.stdout + completed.stderr)[-2000:])


def extract_verified(archive: Path, binary: str | None, staging: Path) -> dict[str, Any]:
    tool = seven_zip(binary)
    side = load_json(archive.parent / "manifest.json", "archive_manifest")
    run_7z(tool, "t", str(archive))
    run_7z(tool, "x", str(archive), f"-o{staging}", "-y")
    inner = load_json(staging / "manifest.json", "inner_manifest")
    if inner != side:
        raise TransferError("manifest_mismatch", "Inner and external manifests differ.")
    mismatched = [m["relative"] for m in side["members"]
                  if not (staging / "claude-home" / m["relative"]).is_file()
                  or sha256(staging / "claude-home" / m["relative"]) != m["sha256"]]
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
              "archive_sha256": sha256(archive), "source_session_id": side["source_session_id"],
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
            raise TransferError("restore_conflict", "Existing different files were preserved; nothing restored.", conflicts=conflicts)
        for member in side["members"]:
            target = Path(member["path"])
            if str(target) in identical:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with (staging / "claude-home" / member["relative"]).open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            if sha256(target) != member["sha256"]:
                raise TransferError("restore_hash_mismatch", "Restored bytes differ.", path=str(target))
            restored.append(str(target))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"schema": f"{PREFIX}.restore.v1", "ok": True, "restored": restored, "skipped_identical": identical,
            "note": "Resume the session with `claude --resume <id>`; Reframe tiles are not recreated."}


# ---------------------------------------------------------------- retirement gate / title / completion

def retirement_check(manifest_path: Path, handoff: Path, acceptance: Path, verification_path: Path,
                     plan_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path, "inspection")
    accepted = validate_acceptance(manifest, handoff, acceptance)
    verification = load_json(verification_path, "verification")
    archive = Path(verification.get("archive", ""))
    if not verification.get("ok") or not archive.is_file() or sha256(archive) != verification.get("archive_sha256"):
        raise TransferError("archive_unverified", "Verified archive is missing or changed.")
    side = load_json(archive.parent / "manifest.json", "archive_manifest")
    if side["source_session_id"] != manifest["source_session_id"] or side["handoff_sha256"] != accepted["handoff_sha256"]:
        raise TransferError("archive_binding", "Archive is not bound to this source and accepted handoff.")
    home = Path(manifest["claude_home"])
    if manifest["source_session_id"] in live_session_ids(home):
        raise TransferError("source_live", "Source session is live; close it before retirement.")
    plan = load_json(plan_path, "cleanup_plan")
    snapshot = plan.get("snapshot", {})
    if plan.get("schema") != "thread_cleanup.plan.v1" or plan.get("system") != "claude" or snapshot.get("id") != manifest["source_session_id"]:
        raise TransferError("plan_mismatch", "Expected a thread-cleanup Claude plan for the same source.")
    protected = set(plan.get("protected_ids", []))
    if manifest["destination_session_id"] not in protected:
        raise TransferError("destination_unprotected", "The cleanup plan must --protect-id the destination session.")
    archived = {os.path.normcase(m["path"]): m["sha256"] for m in side["members"]}
    unarchived = [f["path"] for f in snapshot.get("files", [])
                  if archived.get(os.path.normcase(f["path"])) != f.get("sha256")]
    if unarchived:
        raise TransferError("unarchived_members", "Plan would delete files absent from or different in the archive; re-inspect and re-pack.",
                            members=unarchived)
    return {"schema": f"{PREFIX}.retirement_gate.v1", "ok": True, "source_session_id": manifest["source_session_id"],
            "plan_sha256": sha256(plan_path), "archive_sha256": verification["archive_sha256"],
            "files_bound": len(snapshot.get("files", [])),
            "reframe_tile_references": manifest.get("reframe_tile_references", []),
            "next": "thread-cleanup delete-claude --plan <plan> --plan-sha256 <plan_sha256> --confirm-thread-id <source>"}


def title_status(home: Path, session_id: str, expected: str, reframe_state: Path | None) -> dict[str, Any]:
    session_id = exact_id(session_id, "session")
    mains = sorted((home / "projects").glob(f"*/{session_id}.jsonl"))
    if len(mains) != 1:
        raise TransferError("session_not_found", "Session transcript not found.")
    found = titles(mains[0])
    tiles = reframe_references(reframe_state, session_id)
    return {"schema": f"{PREFIX}.title_status.v1", "session_id": session_id, "expected": expected, **found,
            "reframe_tiles": tiles, "ok": found["custom_title"] == expected or any(t.get("name") == expected for t in tiles)}


def validate_completion(directory: Path) -> dict[str, Any]:
    records = directory / "Records"
    needed = {name: records / name for name in ("acceptance-validation.json", "verification.json", "title-status.json")}
    missing = [n for n, p in needed.items() if not p.is_file()]
    if missing:
        raise TransferError("records_missing", "Completion records missing.", missing=missing)
    loaded = {n: load_json(p, n) for n, p in needed.items()}
    failures = [n for n, r in loaded.items() if r.get("ok") is not True]
    retirement = records / "retirement-result.json"
    preservation = records / "preservation-only.json"
    if retirement.is_file():
        result = load_json(retirement, "retirement")
        result = result.get("result", result) if result.get("ok") is not False else result  # thread-cleanup envelope
        endpoint = "takeover_retired" if result.get("complete") is True else None
        if endpoint is None:
            failures.append("retirement-result.json")
    elif preservation.is_file():
        endpoint = "preservation_only"
    else:
        endpoint = None
        failures.append("endpoint_record")
    ids = {r.get("source_session_id") for r in (loaded["acceptance-validation.json"], loaded["verification.json"])}
    if len(ids) != 1:
        failures.append("source_id_mismatch")
    if failures:
        raise TransferError("completion_invalid", "Completion records inconsistent.", failures=failures)
    return {"schema": f"{PREFIX}.completion.v1", "ok": True, "endpoint": endpoint, "source_session_id": ids.pop(),
            "note": "Record consistency only; it does not re-run live checks."}


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    home_default = str(Path.home() / ".claude")
    p = sub.add_parser("inspect")
    p.add_argument("--source-session-id", required=True)
    p.add_argument("--destination-session-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    p.add_argument("--claude-home", default=home_default)
    p.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    p.add_argument("--reframe-state", default=str(DEFAULT_REFRAME_STATE))
    p.add_argument("--output", required=True)
    p = sub.add_parser("catalog")
    p.add_argument("--manifest", required=True)
    p.add_argument("--head", type=int, default=15)
    p.add_argument("--tail", type=int, default=40)
    p.add_argument("--milestones", type=int, default=150)
    p.add_argument("--excerpt-chars", type=int, default=600)
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
    for name in ("verify", "restore"):
        p = sub.add_parser(name)
        p.add_argument("--archive", required=True)
        p.add_argument("--seven-zip-path")
    p = sub.add_parser("retirement-check")
    for flag in ("--manifest", "--handoff", "--acceptance", "--verification", "--cleanup-plan"):
        p.add_argument(flag, required=True)
    p = sub.add_parser("title-status")
    p.add_argument("--session-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    p.add_argument("--expected", required=True)
    p.add_argument("--claude-home", default=home_default)
    p.add_argument("--reframe-state", default=str(DEFAULT_REFRAME_STATE))
    p.add_argument("--output")
    p = sub.add_parser("validate-completion")
    p.add_argument("--transfer-directory", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect(Path(args.claude_home), args.source_session_id, args.destination_session_id,
                             Path(args.archive_root), Path(args.reframe_state) if args.reframe_state else None)
            write_json(args.output, result)
            result = {k: result[k] for k in ("source_session_id", "destination_session_id", "member_count",
                                             "total_bytes", "subagent_ids", "source_titles", "blockers",
                                             "retirement_ready", "reframe_tile_references")} | {"output": args.output}
        elif args.command == "catalog":
            result = catalog(load_json(args.manifest, "inspection"), args.head, args.tail, args.milestones, args.excerpt_chars)
            write_json(args.output, result)
            result = {"output": args.output, "transcripts": [{k: t[k] for k in ("path", "eligible_entries", "sampled_entries", "truncated")}
                                                              for t in result["transcripts"]]}
        elif args.command == "validate-handoff":
            result = validate_handoff(load_json(args.manifest, "inspection"), Path(args.handoff))
        elif args.command == "validate-acceptance":
            result = validate_acceptance(load_json(args.manifest, "inspection"), Path(args.handoff), Path(args.acceptance))
            if args.output:
                write_json(args.output, result)
        elif args.command == "pack":
            result = pack(Path(args.manifest), Path(args.handoff), args.transfer_directory, args.seven_zip_path)
        elif args.command == "verify":
            result = verify(Path(args.archive), args.seven_zip_path)
        elif args.command == "restore":
            result = restore(Path(args.archive), args.seven_zip_path)
        elif args.command == "retirement-check":
            result = retirement_check(Path(args.manifest), Path(args.handoff), Path(args.acceptance),
                                      Path(args.verification), Path(args.cleanup_plan))
        elif args.command == "title-status":
            result = title_status(Path(args.claude_home), args.session_id, args.expected,
                                  Path(args.reframe_state) if args.reframe_state else None)
            if args.output:
                write_json(args.output, result)
        else:
            result = validate_completion(Path(args.transfer_directory))
    except TransferError as exc:
        print(json.dumps({"ok": False, "error": exc.kind, "message": str(exc), "details": exc.details}, indent=2))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
