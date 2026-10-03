from __future__ import annotations

import hashlib
import json
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from . import context_transfer as ct


INACTIVE_STATUSES = frozenset({"idle", "notLoaded", "closed", "completed", "failed", "cancelled", "canceled"})
STATUS_TOOLS = frozenset({"list_threads", "read_thread", "wait_threads", "list_archived_threads"})


def _valid_observation(item: Any) -> bool:
    if (not isinstance(item, dict) or not isinstance(item.get("thread_id"), str)
            or not isinstance(item.get("status"), str) or item.get("host_id") != "local"
            or not isinstance(item.get("tool"), str) or item["tool"] not in STATUS_TOOLS
            or not isinstance(item.get("observed_at"), str)):
        return False
    try:
        return datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def tree_fingerprint(records: list[dict[str, Any]], edges: list[dict[str, str]]) -> str:
    state = {
        "threads": sorted([
            {"thread_id": item["thread_id"], "rollout_path": item["rollout_path"],
             "updated_at": item["metadata"].get("updated_at"),
             "archived": item["metadata"].get("archived")}
            for item in records
        ], key=lambda item: item["thread_id"]),
        "edges": sorted(edges, key=lambda item: (item["parent_thread_id"], item["child_thread_id"])),
    }
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def validate_current_state(inventory: dict[str, Any]) -> None:
    """Validate state transitions, not elapsed time since a status observation."""
    home = ct._native_windows_path(inventory["codex_home"])
    with closing(ct._open_read_only_database(home / "state_5.sqlite")) as connection:
        connection.execute("BEGIN")
        rows = connection.execute(
            "SELECT parent_thread_id, child_thread_id, status FROM thread_spawn_edges"
        ).fetchall()
        order, edges, cycles = ct._collect_tree(inventory["source_thread_id"], rows)
        records = []
        for thread_id, _ in order:
            row = ct._thread_row(connection, thread_id)
            if row is None:
                raise ct.ContextTransferError("activity_state_changed", "Task-tree metadata is unavailable.")
            records.append({"thread_id": thread_id, "rollout_path": str(ct._native_windows_path(row["rollout_path"])),
                            "metadata": ct._metadata_from_row(row)})
        if cycles or tree_fingerprint(records, edges) != inventory.get("tree_state_sha256"):
            raise ct.ContextTransferError("activity_state_changed", "Task tree changed; inspect and capture status again.")
    for item in ct.iter_rollout_records(inventory):
        if item.get("file_state") != "readable":
            continue
        path = ct._native_windows_path(item["rollout_path"])
        try:
            stat = path.stat()
            if ct._is_reparse_or_symlink(path) or stat.st_size != item["size"] or stat.st_mtime_ns != item["mtime_ns"]:
                raise OSError("rollout identity changed")
        except OSError as exc:
            raise ct.ContextTransferError("activity_state_changed", "Rollout changed; inspect and capture status again.") from exc


def reconcile_activity(*, inspection_manifest_path: str, activity_evidence_path: str) -> dict[str, Any]:
    from . import archive

    manifest_path = Path(inspection_manifest_path)
    inventory = archive._load_inspection(manifest_path)
    try:
        evidence = json.loads(Path(activity_evidence_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ct.ContextTransferError("activity_evidence_invalid", "Could not read task activity evidence.") from exc
    if (not isinstance(evidence, dict)
            or evidence.get("schema") != "agent_toolbelt_context_transfer.activity_evidence.v1"
            or evidence.get("evidence_source") != "codex_task_api"
            or evidence.get("inspection_sha256") != ct._sha256_file(manifest_path)
            or evidence.get("source_thread_id") != inventory["source_thread_id"]
            or evidence.get("destination_thread_id") != inventory.get("destination_thread_id")
            or not isinstance(evidence.get("observations"), list)):
        raise ct.ContextTransferError("activity_evidence_invalid", "Evidence must bind to this exact inspected task tree.")
    validate_current_state(inventory)
    observations = {}
    for item in evidence["observations"]:
        if not _valid_observation(item) or item["thread_id"] in observations:
            raise ct.ContextTransferError("activity_evidence_invalid", "Use unique explicit local task-status observations.")
        observations[item["thread_id"]] = item
    expected = {inventory["source_thread_id"], *(item["child_thread_id"] for item in inventory["edges"])}
    if set(observations) - expected:
        raise ct.ContextTransferError("activity_evidence_invalid", "Evidence contains tasks outside the inspected tree.")
    unresolved = sorted(thread_id for thread_id in expected
                        if observations.get(thread_id, {}).get("status") not in INACTIVE_STATUSES)
    stale_inactive = sorted(thread_id for thread_id in inventory.get("non_terminal_child_ids", [])
                            if thread_id not in unresolved)
    blockers = [item for item in inventory["blockers"] if item != "non_terminal_children"]
    if unresolved:
        blockers.append("task_activity_unverified_or_active")
    inventory.update({
        "blockers": blockers, "retirement_ready": not blockers,
        "stale_inactive_child_ids": stale_inactive,
        "unresolved_activity_thread_ids": unresolved,
        "activity_reconciliation": {
            "schema": "agent_toolbelt_context_transfer.activity_reconciliation.v1",
            "evidence_source": "codex_task_api",
            "inspection_sha256": evidence["inspection_sha256"],
            "evidence_sha256": ct._sha256_file(Path(activity_evidence_path)),
            "observations": [observations[key] for key in sorted(observations)],
            "sqlite_mutated": False,
        },
    })
    return inventory


def validate_reconciled_inventory(inventory: dict[str, Any]) -> None:
    reconciliation = inventory.get("activity_reconciliation")
    if not reconciliation:
        return
    expected = {inventory["source_thread_id"], *(item["child_thread_id"] for item in inventory["edges"])}
    observations = reconciliation.get("observations", [])
    if (reconciliation.get("schema") != "agent_toolbelt_context_transfer.activity_reconciliation.v1"
            or reconciliation.get("evidence_source") != "codex_task_api"
            or not isinstance(observations, list)
            or any(not _valid_observation(item) for item in observations)
            or len(observations) != len(expected)
            or {item.get("thread_id") for item in observations} != expected
            or any(item["status"] not in INACTIVE_STATUSES for item in observations)):
        raise ct.ContextTransferError("activity_evidence_invalid", "Packaging requires complete inactive task-status evidence.")
    validate_current_state(inventory)
