from __future__ import annotations

from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from . import archive


REQUIRED_HANDOFF_SECTIONS = (
    "Current Objective",
    "Authoritative Specifications And Plans",
    "Completed Work With Evidence",
    "Active Stage And Exact Next Actions",
    "Unresolved Blockers And Required Deferrals",
    "Durable Decisions And User Constraints",
    "Failed Approaches Not To Repeat",
    "Repositories Branches And Artifacts",
    "Child-Agent Contribution Map",
    "Uncertainties Requiring Verification",
)
MILESTONE_TOKENS = (
    "decision:",
    "blocker",
    "failed",
    "error",
    "tests passed",
    "validated",
    "commit ",
    "merged",
    "pushed",
    "deployed",
    "exact next action",
    "please implement this plan",
    "<proposed_plan>",
)


class HandoffError(RuntimeError):
    def __init__(
        self,
        kind: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_inspection(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        inventory = archive._load_inspection(Path(path))
    except archive.ArchiveError as exc:
        raise HandoffError(exc.kind, str(exc), details=exc.details) from exc
    if not inventory.get("retirement_ready") or inventory.get("blockers"):
        raise HandoffError(
            "inspection_not_ready",
            "Inspection has blockers and cannot produce a retirement handoff.",
            details={"blockers": inventory.get("blockers", [])},
        )
    return inventory


def _payload_text(record: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    entry_type = str(record.get("type") or "")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None, None, None
    payload_type = str(payload.get("type") or "")
    role = payload.get("role")
    fragments: list[str] = []
    content = payload.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                fragments.append(item["text"])
    for key in ("message", "text", "summary", "last_agent_message"):
        value = payload.get(key)
        if isinstance(value, str):
            fragments.append(value)
    text = "\n".join(fragment for fragment in fragments if fragment.strip()).strip()
    if not role:
        if payload_type == "user_message":
            role = "user"
        elif payload_type in {"agent_message", "task_complete"}:
            role = "assistant"
    return (text or None), (str(role) if role else None), f"{entry_type}:{payload_type}"


def _content_class(text: str) -> str:
    lowered = text.casefold()
    if "please implement this plan" in lowered or "<proposed_plan>" in lowered:
        return "plan"
    if any(token in lowered for token in ("blocker", "failed", "error", "exception")):
        return "blocker"
    if any(token in lowered for token in ("tests passed", "validated", "commit ", "merged", "pushed", "deployed")):
        return "verification"
    if any(token in lowered for token in ("decision:", "do not ", "prefer ", "must ")):
        return "decision"
    return "work"


def _catalog_thread(
    record: dict[str, Any],
    *,
    max_entries: int,
    excerpt_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = Path(str(record["rollout_path"]))
    first: list[dict[str, Any]] = []
    milestones: deque[dict[str, Any]] = deque(maxlen=max_entries)
    recent: deque[dict[str, Any]] = deque(maxlen=3)
    malformed = 0
    substantive = 0
    milestone_matches = 0
    line_number = 0
    with path.open("rb") as handle:
        while True:
            byte_start = handle.tell()
            raw_line = handle.readline()
            if not raw_line:
                break
            byte_end = handle.tell()
            line_number += 1
            try:
                parsed = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                malformed += 1
                continue
            if not isinstance(parsed, dict):
                continue
            text, role, type_key = _payload_text(parsed)
            if not text or role not in {"user", "assistant"}:
                continue
            substantive += 1
            normalized = re.sub(r"\s+", " ", text).strip()
            item = {
                "thread_id": record["thread_id"],
                "rollout_path": str(path),
                "rollout_line": line_number,
                "byte_start": byte_start,
                "byte_end": byte_end,
                "timestamp": parsed.get("timestamp"),
                "role": role,
                "entry_type": type_key,
                "content_class": _content_class(normalized),
                "excerpt": normalized[:excerpt_chars],
                "entry_sha256": hashlib.sha256(raw_line).hexdigest(),
            }
            if len(first) < 2:
                first.append(item)
            if any(token in normalized.casefold() for token in MILESTONE_TOKENS):
                milestone_matches += 1
                milestones.append(item)
            recent.append(item)

    combined: dict[int, tuple[int, dict[str, Any]]] = {}
    for priority, items in ((3, milestones), (2, first), (1, list(recent))):
        for item in items:
            line = int(item["rollout_line"])
            existing = combined.get(line)
            if existing is None or priority > existing[0]:
                combined[line] = (priority, item)
    ranked = sorted(
        combined.values(),
        key=lambda value: (-value[0], -int(value[1]["rollout_line"])),
    )
    selected = [value[1] for value in ranked[:max_entries]]
    selected.sort(key=lambda item: int(item["rollout_line"]))
    return selected, {
        "thread_id": record["thread_id"],
        "rollout_path": str(path),
        "lines_scanned": line_number,
        "substantive_entries_seen": substantive,
        "selected_entries": len(selected),
        "malformed_lines": malformed,
        "selection_truncated": milestone_matches > len(milestones) or len(combined) > len(selected),
    }


def build_evidence_catalog(
    *,
    inspection_manifest_path: str | os.PathLike[str],
    max_entries_per_thread: int = 12,
    max_total_entries: int = 1200,
    excerpt_chars: int = 600,
) -> dict[str, Any]:
    if not 1 <= max_entries_per_thread <= 50:
        raise HandoffError("invalid_catalog_limit", "max_entries_per_thread must be between 1 and 50.")
    if not 1 <= max_total_entries <= 5000:
        raise HandoffError("invalid_catalog_limit", "max_total_entries must be between 1 and 5000.")
    if not 40 <= excerpt_chars <= 2000:
        raise HandoffError("invalid_excerpt_limit", "excerpt_chars must be between 40 and 2000.")

    inventory = _load_inspection(inspection_manifest_path)
    entries: list[dict[str, Any]] = []
    thread_stats: list[dict[str, Any]] = []
    total_selected_before_limit = 0
    for record in inventory["threads"]:
        if record.get("file_state") != "readable":
            continue
        selected, stats = _catalog_thread(
            record,
            max_entries=max_entries_per_thread,
            excerpt_chars=excerpt_chars,
        )
        entries.extend(selected)
        thread_stats.append(stats)
        total_selected_before_limit += len(selected)

    if len(entries) > max_total_entries:
        entries = entries[:max_total_entries]
    malformed_count = sum(int(item["malformed_lines"]) for item in thread_stats)
    return {
        "schema": "agent_toolbelt_context_transfer.evidence_catalog.v1",
        "source_thread_id": inventory["source_thread_id"],
        "destination_thread_id": inventory.get("destination_thread_id"),
        "storage": "bounded_excerpts_and_source_offsets",
        "raw_rollouts_remain_source_of_truth": True,
        "permanent_full_text_index_created": False,
        "thread_count": len(thread_stats),
        "entry_count": len(entries),
        "max_entries_per_thread": max_entries_per_thread,
        "max_total_entries": max_total_entries,
        "excerpt_chars": excerpt_chars,
        "malformed_line_count": malformed_count,
        "truncated": (
            total_selected_before_limit > len(entries)
            or any(item["selection_truncated"] for item in thread_stats)
        ),
        "entries": entries,
        "thread_stats": thread_stats,
    }


def _section_bodies(markdown: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^##[ \t]+(.+?)[ \t]*$", markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections[match.group(1).strip()] = markdown[match.end() : end].strip()
    return sections


def validate_handoff(
    *,
    handoff_path: str | os.PathLike[str],
    inspection_manifest_path: str | os.PathLike[str],
) -> dict[str, Any]:
    inventory = _load_inspection(inspection_manifest_path)
    path = Path(handoff_path)
    if not path.is_file():
        raise HandoffError("handoff_missing", f"Handoff file was not found: {path}")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise HandoffError("handoff_unbounded", "CONTEXT_TRANSFER.md exceeds the 2 MiB handoff limit.")
    content = path.read_text(encoding="utf-8-sig")
    sections = _section_bodies(content)
    missing_sections = [
        section
        for section in REQUIRED_HANDOFF_SECTIONS
        if not sections.get(section, "").strip()
    ]
    child_section = sections.get("Child-Agent Contribution Map", "")
    child_ids = sorted(
        {
            str(edge["child_thread_id"])
            for edge in inventory.get("edges", [])
        }
    )
    missing_child_ids = [
        child_id
        for child_id in child_ids
        if not re.search(
            rf"(?m)^\s*(?:[-*]\s*)?{re.escape(child_id)}\s*:",
            child_section,
        )
    ]
    if missing_sections or missing_child_ids:
        raise HandoffError(
            "handoff_incomplete",
            "CONTEXT_TRANSFER.md does not satisfy the destination handoff contract.",
            details={
                "missing_sections": missing_sections,
                "missing_child_thread_ids": missing_child_ids,
            },
        )
    return {
        "schema": "agent_toolbelt_context_transfer.handoff_validation.v1",
        "ok": True,
        "source_thread_id": inventory["source_thread_id"],
        "destination_thread_id": inventory.get("destination_thread_id"),
        "handoff_path": str(path.resolve()),
        "handoff_sha256": _sha256_file(path),
        "handoff_bytes": path.stat().st_size,
        "required_sections": list(REQUIRED_HANDOFF_SECTIONS),
        "missing_sections": [],
        "mapped_child_thread_count": len(child_ids),
        "missing_child_thread_ids": [],
    }


def validate_destination_acceptance(
    *,
    acceptance_path: str | os.PathLike[str],
    handoff_path: str | os.PathLike[str],
    inspection_manifest_path: str | os.PathLike[str],
) -> dict[str, Any]:
    inventory = _load_inspection(inspection_manifest_path)
    handoff_validation = validate_handoff(
        handoff_path=handoff_path,
        inspection_manifest_path=inspection_manifest_path,
    )
    path = Path(acceptance_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError(
            "acceptance_invalid",
            f"Could not read destination acceptance: {exc}",
        ) from exc
    invalid_fields: list[str] = []
    if payload.get("schema") != "agent_toolbelt_context_transfer.destination_acceptance.v1":
        invalid_fields.append("schema")
    if payload.get("source_thread_id") != inventory["source_thread_id"]:
        invalid_fields.append("source_thread_id")
    if payload.get("destination_thread_id") != inventory.get("destination_thread_id"):
        invalid_fields.append("destination_thread_id")
    if payload.get("handoff_ready") is not True:
        invalid_fields.append("handoff_ready")
    for field in (
        "mapped_active_requirements",
        "evidence_sources_inspected",
        "repository_state_verified",
    ):
        if not isinstance(payload.get(field), list) or not payload[field]:
            invalid_fields.append(field)
    if not isinstance(payload.get("unresolved_uncertainties"), list):
        invalid_fields.append("unresolved_uncertainties")
    critical = payload.get("critical_unmapped_objectives")
    if not isinstance(critical, list) or critical:
        invalid_fields.append("critical_unmapped_objectives")
    if not isinstance(payload.get("first_continuation_action"), str) or not payload[
        "first_continuation_action"
    ].strip():
        invalid_fields.append("first_continuation_action")
    if payload.get("handoff_sha256") != handoff_validation["handoff_sha256"]:
        invalid_fields.append("handoff_sha256")
    if invalid_fields:
        raise HandoffError(
            "acceptance_incomplete",
            "Destination acceptance is incomplete or inconsistent.",
            details={"invalid_fields": sorted(set(invalid_fields))},
        )
    return {
        "schema": "agent_toolbelt_context_transfer.acceptance_validation.v1",
        "ok": True,
        "handoff_ready": True,
        "source_thread_id": inventory["source_thread_id"],
        "destination_thread_id": inventory.get("destination_thread_id"),
        "acceptance_path": str(path.resolve()),
        "acceptance_sha256": _sha256_file(path),
        "handoff_sha256": handoff_validation["handoff_sha256"],
        "critical_unmapped_objectives": [],
        "first_continuation_action": payload["first_continuation_action"],
    }
