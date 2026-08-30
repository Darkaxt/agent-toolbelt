from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from typing import Any

from . import archive


class RetirementError(RuntimeError):
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


def _load_json(path: Path, *, kind: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetirementError(kind, f"Could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RetirementError(kind, f"Expected a JSON object in {path}.")
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def compute_ticket_id(ticket: dict[str, Any]) -> str:
    bound = {key: value for key, value in ticket.items() if key != "ticket_id"}
    return hashlib.sha256(_canonical_json(bound)).hexdigest()


def _normalized(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((_normalized(path), _normalized(root))) == _normalized(root)
    except ValueError:
        return False


def _is_allowed_rollout(path: Path, codex_home: Path) -> bool:
    return any(
        _is_within(path, root)
        for root in (codex_home / "sessions", codex_home / "archived_sessions")
    )


def _validate_acceptance(
    acceptance: dict[str, Any],
    *,
    source_thread_id: str,
    destination_thread_id: str | None,
    handoff_sha256: str,
) -> None:
    invalid: list[str] = []
    if acceptance.get("schema") != "agent_toolbelt_context_transfer.destination_acceptance.v1":
        invalid.append("schema")
    if acceptance.get("source_thread_id") != source_thread_id:
        invalid.append("source_thread_id")
    if acceptance.get("destination_thread_id") != destination_thread_id:
        invalid.append("destination_thread_id")
    if acceptance.get("handoff_ready") is not True:
        invalid.append("handoff_ready")
    for field in (
        "mapped_active_requirements",
        "evidence_sources_inspected",
        "repository_state_verified",
    ):
        if not isinstance(acceptance.get(field), list) or not acceptance[field]:
            invalid.append(field)
    if not isinstance(acceptance.get("unresolved_uncertainties"), list):
        invalid.append("unresolved_uncertainties")
    if not isinstance(acceptance.get("critical_unmapped_objectives"), list) or acceptance[
        "critical_unmapped_objectives"
    ]:
        invalid.append("critical_unmapped_objectives")
    if not isinstance(acceptance.get("first_continuation_action"), str) or not acceptance[
        "first_continuation_action"
    ].strip():
        invalid.append("first_continuation_action")
    if acceptance.get("handoff_sha256") != handoff_sha256:
        invalid.append("handoff_sha256")
    if invalid:
        raise RetirementError(
            "acceptance_incomplete",
            "Destination acceptance is incomplete or inconsistent.",
            details={"invalid_fields": sorted(set(invalid))},
        )


def issue_deletion_ticket(
    *,
    verification_path: str | os.PathLike[str],
    acceptance_path: str | os.PathLike[str],
    archived_state_path: str | os.PathLike[str],
    confirm_live_retirement: bool,
) -> dict[str, Any]:
    if not confirm_live_retirement:
        raise RetirementError(
            "live_retirement_confirmation_required",
            "Ticket issuance requires explicit live-retirement confirmation.",
        )

    verification_file = Path(verification_path).resolve()
    transaction_root = verification_file.parent
    verification = _load_json(verification_file, kind="verification_invalid")
    if verification.get("schema") != "agent_toolbelt_context_transfer.verification.v1":
        raise RetirementError("verification_invalid", "Unsupported verification schema.")
    archive_path = Path(str(verification.get("archive_path", ""))).resolve()
    try:
        verified = archive.verify_recovery_archive(archive_path)
    except archive.ArchiveError as exc:
        raise RetirementError(exc.kind, str(exc), details=exc.details) from exc
    if not verified.get("ok") or verified.get("archive_sha256") != verification.get(
        "archive_sha256"
    ):
        raise RetirementError("archive_verification_failed", "Archive verification did not match.")

    manifest_path = transaction_root / "manifest.json"
    handoff_path = transaction_root / "CONTEXT_TRANSFER.md"
    threads_path = transaction_root / "threads.json"
    edges_path = transaction_root / "spawn-edges.json"
    for required in (manifest_path, handoff_path, threads_path, edges_path):
        if not required.is_file():
            raise RetirementError(
                "recovery_artifact_missing",
                f"Recovery artifact is missing: {required}",
            )
    manifest = _load_json(manifest_path, kind="manifest_invalid")
    if manifest.get("schema") != "agent_toolbelt_context_transfer.archive_manifest.v1":
        raise RetirementError("manifest_invalid", "Unsupported archive manifest schema.")
    if _sha256_file(manifest_path) != verification.get("manifest_sha256"):
        raise RetirementError("manifest_hash_mismatch", "Archive manifest changed after verification.")
    if _sha256_file(handoff_path) != verification.get("handoff_sha256"):
        raise RetirementError("handoff_hash_mismatch", "Handoff changed after verification.")

    acceptance_file = Path(acceptance_path).resolve()
    acceptance = _load_json(acceptance_file, kind="acceptance_invalid")
    _validate_acceptance(
        acceptance,
        source_thread_id=str(manifest["source_thread_id"]),
        destination_thread_id=manifest.get("destination_thread_id"),
        handoff_sha256=str(verification["handoff_sha256"]),
    )

    archived_file = Path(archived_state_path).resolve()
    archived_state = _load_json(archived_file, kind="archived_state_invalid")
    if (
        archived_state.get("schema") != "agent_toolbelt_context_transfer.archived_state.v1"
        or archived_state.get("source_thread_id") != manifest["source_thread_id"]
        or archived_state.get("archived") is not True
        or archived_state.get("evidence_source") != "codex_task_api"
        or not archived_state.get("verified_at")
    ):
        raise RetirementError(
            "source_not_archived",
            "Archived-state evidence does not prove the selected source is archived.",
        )

    codex_home = Path(str(manifest["codex_home"])).resolve()
    files: list[dict[str, Any]] = []
    normalized_paths: set[str] = set()
    for item in manifest.get("rollouts", []):
        path = Path(str(item["original_path"]))
        normalized = _normalized(path)
        if normalized in normalized_paths:
            raise RetirementError("duplicate_ticket_path", f"Duplicate rollout path: {path}")
        normalized_paths.add(normalized)
        if not _is_allowed_rollout(path, codex_home):
            raise RetirementError("unsafe_ticket_path", f"Unsafe rollout path: {path}")
        files.append(
            {
                "thread_id": item["thread_id"],
                "original_path": str(path),
                "size": item["size"],
                "mtime_ns": item["mtime_ns"],
                "sha256": item["sha256"],
            }
        )
    if not files:
        raise RetirementError("manifest_invalid", "Archive manifest contains no rollout files.")

    thread_rows = json.loads(threads_path.read_text(encoding="utf-8-sig"))
    thread_ids = sorted(str(item["thread_id"]) for item in thread_rows)
    ticket_path = transaction_root / "deletion-ticket.json"
    if ticket_path.exists():
        raise RetirementError("ticket_exists", f"Deletion ticket already exists: {ticket_path}")
    ticket: dict[str, Any] = {
        "schema": "agent_toolbelt_context_transfer.deletion_ticket.v1",
        "source_thread_id": manifest["source_thread_id"],
        "destination_thread_id": manifest.get("destination_thread_id"),
        "thread_ids": thread_ids,
        "codex_home": str(codex_home),
        "archive_path": str(archive_path),
        "archive_sha256": verification["archive_sha256"],
        "manifest_sha256": verification["manifest_sha256"],
        "handoff_sha256": verification["handoff_sha256"],
        "verification_path": str(verification_file),
        "verification_sha256": _sha256_file(verification_file),
        "acceptance_path": str(acceptance_file),
        "acceptance_sha256": _sha256_file(acceptance_file),
        "archived_state_path": str(archived_file),
        "archived_state_sha256": _sha256_file(archived_file),
        "files": files,
        "cache_files": [],
        "cache_ownership": "none_proven",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "nonce": secrets.token_hex(32),
        "single_use": True,
        "live_retirement_confirmed": True,
    }
    ticket["ticket_id"] = compute_ticket_id(ticket)
    _write_json_atomic(ticket_path, ticket)
    return {
        "schema": "agent_toolbelt_context_transfer.ticket_issue_result.v1",
        "ok": True,
        "ticket_path": str(ticket_path),
        "ticket_id": ticket["ticket_id"],
        "file_count": len(files),
        "total_bytes": sum(int(item["size"]) for item in files),
        "cache_file_count": 0,
        "destructive_mutation_performed": False,
    }


def _verify_ticket_evidence(ticket: dict[str, Any]) -> None:
    evidence = (
        ("archive_path", "archive_sha256"),
        ("verification_path", "verification_sha256"),
        ("acceptance_path", "acceptance_sha256"),
        ("archived_state_path", "archived_state_sha256"),
    )
    for path_field, hash_field in evidence:
        path = Path(str(ticket.get(path_field, "")))
        if not path.is_file() or _sha256_file(path) != ticket.get(hash_field):
            raise RetirementError(
                "ticket_evidence_changed",
                f"Ticket-bound evidence changed or disappeared: {path}",
                details={"path_field": path_field},
            )
    manifest_path = Path(str(ticket["verification_path"])).parent / "manifest.json"
    handoff_path = Path(str(ticket["verification_path"])).parent / "CONTEXT_TRANSFER.md"
    if not manifest_path.is_file() or _sha256_file(manifest_path) != ticket.get("manifest_sha256"):
        raise RetirementError("ticket_evidence_changed", "Ticket-bound manifest changed.")
    if not handoff_path.is_file() or _sha256_file(handoff_path) != ticket.get("handoff_sha256"):
        raise RetirementError("ticket_evidence_changed", "Ticket-bound handoff changed.")


def apply_deletion_ticket(
    *,
    ticket_path: str | os.PathLike[str],
    ticket_id: str,
    confirm_delete: bool,
) -> dict[str, Any]:
    if not confirm_delete:
        raise RetirementError(
            "deletion_confirmation_required",
            "Applying a reviewed deletion ticket requires --confirm-delete.",
        )
    path = Path(ticket_path).resolve()
    ticket = _load_json(path, kind="ticket_invalid")
    transaction_root = path.parent
    consumed_marker = transaction_root / "deletion-ticket.applied.json"
    if consumed_marker.exists():
        raise RetirementError("ticket_already_used", "Deletion ticket has already been consumed.")
    if ticket.get("ticket_id") != ticket_id:
        raise RetirementError(
            "ticket_id_mismatch",
            "The supplied reviewed ticket ID does not match deletion-ticket.json.",
        )
    if (
        ticket.get("schema") != "agent_toolbelt_context_transfer.deletion_ticket.v1"
        or ticket.get("single_use") is not True
        or ticket.get("live_retirement_confirmed") is not True
        or ticket.get("ticket_id") != compute_ticket_id(ticket)
    ):
        raise RetirementError("ticket_integrity_failed", "Deletion ticket integrity check failed.")
    _verify_ticket_evidence(ticket)

    codex_home = Path(str(ticket["codex_home"])).resolve()
    seen_paths: set[str] = set()
    results: list[dict[str, Any]] = []
    deleted_bytes = 0
    residual_bytes = 0
    for reviewed in ticket.get("files", []):
        file_path = Path(str(reviewed["original_path"]))
        normalized = _normalized(file_path)
        if normalized in seen_paths or not _is_allowed_rollout(file_path, codex_home):
            raise RetirementError("unsafe_ticket_path", f"Unsafe ticket path: {file_path}")
        seen_paths.add(normalized)
        result = {
            "thread_id": reviewed["thread_id"],
            "original_path": str(file_path),
            "reviewed_size": reviewed["size"],
            "status": "pending",
        }
        if not file_path.exists():
            result["status"] = "already_missing"
            results.append(result)
            continue
        if file_path.is_symlink() or not file_path.is_file():
            result["status"] = "unsafe_skipped"
            residual_bytes += int(file_path.stat().st_size) if file_path.is_file() else 0
            results.append(result)
            continue
        try:
            initial_stat = file_path.stat()
            actual_hash = _sha256_file(file_path)
            identity = {
                "size": initial_stat.st_size,
                "mtime_ns": initial_stat.st_mtime_ns,
                "sha256": actual_hash,
            }
            expected = {
                "size": reviewed["size"],
                "mtime_ns": reviewed["mtime_ns"],
                "sha256": reviewed["sha256"],
            }
            final_stat = file_path.stat()
            if (
                identity != expected
                or final_stat.st_size != initial_stat.st_size
                or final_stat.st_mtime_ns != initial_stat.st_mtime_ns
            ):
                result["status"] = "changed_skipped"
                result["actual_size"] = final_stat.st_size
                residual_bytes += int(final_stat.st_size)
            else:
                file_path.unlink()
                if file_path.exists():
                    raise OSError("file remained after unlink")
                result["status"] = "deleted"
                deleted_bytes += int(reviewed["size"])
        except OSError as exc:
            result["status"] = "error_skipped"
            result["error"] = f"{type(exc).__name__}: {exc}"
            if file_path.exists() and file_path.is_file():
                residual_bytes += int(file_path.stat().st_size)
        results.append(result)

    residual_count = sum(
        1
        for item in results
        if item["status"] in {"changed_skipped", "unsafe_skipped", "error_skipped"}
    )
    result_payload = {
        "schema": "agent_toolbelt_context_transfer.deletion_result.v1",
        "ok": True,
        "status": "complete" if residual_count == 0 else "partial",
        "ticket_id": ticket["ticket_id"],
        "ticket_path": str(path),
        "files": results,
        "deleted_file_count": sum(1 for item in results if item["status"] == "deleted"),
        "deleted_bytes": deleted_bytes,
        "residual_file_count": residual_count,
        "residual_bytes": residual_bytes,
        "new_unlisted_files_ignored": True,
        "sqlite_mutation_performed": False,
        "cache_files_deleted": 0,
        "applied_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    result_path = transaction_root / "deletion-result.json"
    _write_json_atomic(result_path, result_payload)
    marker = {
        "schema": "agent_toolbelt_context_transfer.ticket_consumption.v1",
        "ticket_id": ticket["ticket_id"],
        "deletion_result_path": str(result_path),
        "deletion_result_sha256": _sha256_file(result_path),
        "status": result_payload["status"],
        "consumed_at": result_payload["applied_at"],
    }
    _write_json_atomic(consumed_marker, marker)
    result_payload["result_path"] = str(result_path)
    result_payload["consumed_marker_path"] = str(consumed_marker)
    return result_payload
