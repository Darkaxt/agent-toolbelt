from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import stat
from typing import Any

from . import archive


class RestoreError(RuntimeError):
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


def _normalized(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((_normalized(path), _normalized(root))) == _normalized(root)
    except ValueError:
        return False


def _is_reparse_or_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    if not path.exists():
        return False
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _has_reparse_component(path: Path, boundary: Path) -> bool:
    current = path
    while _is_within(current, boundary):
        if _is_reparse_or_symlink(current):
            return True
        if _normalized(current) == _normalized(boundary):
            break
        current = current.parent
    return False


def _validate_target(path: Path, codex_home: Path) -> None:
    allowed_roots = (codex_home / "sessions", codex_home / "archived_sessions")
    containing_root = next((root for root in allowed_roots if _is_within(path, root)), None)
    if containing_root is None:
        raise RestoreError("unsafe_restore_path", f"Restore path is outside Codex rollout roots: {path}")
    if _has_reparse_component(path.parent, containing_root):
        raise RestoreError("unsafe_restore_path", f"Restore path crosses a reparse point: {path}")


def _metadata_state(codex_home: Path, thread_ids: list[str]) -> tuple[list[str], list[str]]:
    database_path = codex_home / "state_5.sqlite"
    if not database_path.is_file():
        return sorted(thread_ids), ["state_database_missing"]
    try:
        connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        with closing(connection):
            placeholders = ",".join("?" for _ in thread_ids)
            rows = connection.execute(
                f"SELECT id FROM threads WHERE id IN ({placeholders})",
                thread_ids,
            ).fetchall()
        present = {str(row[0]) for row in rows}
        return sorted(set(thread_ids) - present), []
    except sqlite3.Error as exc:
        return sorted(thread_ids), [f"state_database_unavailable:{type(exc).__name__}"]


def _restore_no_overwrite(source: Path, destination: Path, expected_hash: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.context-transfer-{secrets.token_hex(8)}.partial"
    )
    try:
        with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        if _sha256_file(temporary) != expected_hash:
            raise RestoreError(
                "restore_staging_hash_mismatch",
                f"Temporary restored file did not verify: {destination}",
            )
        if destination.exists():
            raise FileExistsError(str(destination))
        if os.name == "nt":
            os.rename(temporary, destination)
        else:
            os.link(temporary, destination)
            temporary.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()


def restore_recovery_archive(
    *,
    archive_path: str | os.PathLike[str],
    seven_zip_path: str | None = None,
) -> dict[str, Any]:
    archive_file = Path(archive_path).resolve()
    transaction_root = archive_file.parent
    if os.name == "nt" and transaction_root.drive.casefold() == "c:":
        raise RestoreError("unsafe_restore_staging", "Restore staging must not use C:.")
    try:
        verified = archive.verify_recovery_archive(
            archive_file,
            seven_zip_path=seven_zip_path,
        )
    except archive.ArchiveError as exc:
        raise RestoreError(exc.kind, str(exc), details=exc.details) from exc
    if not verified.get("ok"):
        raise RestoreError("archive_verification_failed", "Recovery archive did not verify.")

    manifest_path = transaction_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RestoreError("manifest_invalid", f"Could not read archive manifest: {exc}") from exc
    if manifest.get("schema") != "agent_toolbelt_context_transfer.archive_manifest.v1":
        raise RestoreError("manifest_invalid", "Unsupported archive manifest schema.")
    codex_home = Path(str(manifest["codex_home"])).resolve()
    rollouts = list(manifest.get("rollouts", []))
    if not rollouts:
        raise RestoreError("manifest_invalid", "Archive manifest contains no rollouts.")

    preflight: list[dict[str, Any]] = []
    missing_by_anchor: dict[str, int] = {}
    for item in rollouts:
        destination = Path(str(item["original_path"]))
        _validate_target(destination, codex_home)
        state = {
            "thread_id": item["thread_id"],
            "original_path": str(destination),
            "archive_path": item["archive_path"],
            "size": int(item["size"]),
            "sha256": item["sha256"],
            "mtime_ns": int(item["mtime_ns"]),
            "status": "missing",
        }
        if destination.exists():
            if _is_reparse_or_symlink(destination) or not destination.is_file():
                raise RestoreError("restore_conflict", f"Existing path is not a regular file: {destination}")
            if destination.stat().st_size != int(item["size"]) or _sha256_file(destination) != item[
                "sha256"
            ]:
                raise RestoreError("restore_conflict", f"Existing rollout conflicts: {destination}")
            state["status"] = "identical_existing"
        else:
            anchor = destination.anchor
            if not anchor:
                raise RestoreError("unsafe_restore_path", f"Restore destination has no volume: {destination}")
            missing_by_anchor[anchor] = missing_by_anchor.get(anchor, 0) + int(item["size"])
        preflight.append(state)

    for anchor, required_bytes in missing_by_anchor.items():
        free_bytes = shutil.disk_usage(anchor).free
        if free_bytes < required_bytes:
            raise RestoreError(
                "insufficient_restore_space",
                f"Insufficient free space on {anchor}.",
                details={"required_bytes": required_bytes, "free_bytes": free_bytes},
            )

    staging = transaction_root / ".restore-staging"
    if staging.exists():
        raise RestoreError(
            "restore_staging_exists",
            f"Restore staging already exists and requires inspection: {staging}",
        )
    staging.mkdir()
    seven_zip = (
        seven_zip_path
        or json.loads((transaction_root / "verification.json").read_text(encoding="utf-8-sig")).get(
            "seven_zip_path"
        )
        or shutil.which("7z.exe")
        or shutil.which("7z")
    )
    if not seven_zip:
        shutil.rmtree(staging)
        raise RestoreError("seven_zip_missing", "7-Zip was not found.")

    restored_paths: list[tuple[Path, str]] = []
    try:
        try:
            archive._run_seven_zip(
                [str(seven_zip), "x", "-y", f"-o{staging}", str(archive_file)]
            )
        except archive.ArchiveError as exc:
            raise RestoreError("archive_extraction_failed", str(exc), details=exc.details) from exc

        for item in preflight:
            extracted = staging.joinpath(*str(item["archive_path"]).split("/"))
            if not extracted.is_file() or _sha256_file(extracted) != item["sha256"]:
                raise RestoreError(
                    "restore_staging_hash_mismatch",
                    f"Extracted rollout did not verify: {item['archive_path']}",
                )

        for item in preflight:
            if item["status"] == "identical_existing":
                continue
            destination = Path(item["original_path"])
            extracted = staging.joinpath(*str(item["archive_path"]).split("/"))
            try:
                _restore_no_overwrite(extracted, destination, str(item["sha256"]))
            except FileExistsError as exc:
                if (
                    destination.is_file()
                    and destination.stat().st_size == item["size"]
                    and _sha256_file(destination) == item["sha256"]
                ):
                    item["status"] = "identical_existing"
                    continue
                raise RestoreError(
                    "restore_conflict",
                    f"Restore destination appeared concurrently: {destination}",
                ) from exc
            os.utime(
                destination,
                ns=(destination.stat().st_atime_ns, int(item["mtime_ns"])),
            )
            if _sha256_file(destination) != item["sha256"]:
                raise RestoreError("restore_hash_mismatch", f"Restored rollout did not verify: {destination}")
            item["status"] = "restored"
            restored_paths.append((destination, str(item["sha256"])))
    except Exception:
        for destination, expected_hash in reversed(restored_paths):
            if destination.is_file() and _sha256_file(destination) == expected_hash:
                destination.unlink()
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    thread_ids = [str(item["thread_id"]) for item in rollouts]
    missing_metadata, warnings = _metadata_state(codex_home, thread_ids)
    return {
        "schema": "agent_toolbelt_context_transfer.restore_result.v1",
        "ok": True,
        "archive_path": str(archive_file),
        "archive_sha256": verified["archive_sha256"],
        "files": preflight,
        "restored_file_count": sum(1 for item in preflight if item["status"] == "restored"),
        "identical_file_count": sum(
            1 for item in preflight if item["status"] == "identical_existing"
        ),
        "conflict_file_count": 0,
        "missing_metadata_thread_ids": missing_metadata,
        "warnings": warnings,
        "sqlite_mutation_performed": False,
        "next_action": "Unarchive the source task through the Codex task API if desired.",
    }
