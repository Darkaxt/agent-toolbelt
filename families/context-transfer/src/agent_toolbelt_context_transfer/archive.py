from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, TextIO


DICTIONARY_CANDIDATES_MIB = (1536, 1024, 768, 512, 384, 256, 192, 128, 96, 64, 32)
ENCODER_MEMORY_FACTOR = 11


class ArchiveError(RuntimeError):
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


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def compression_arguments(dictionary_mib: int) -> list[str]:
    if dictionary_mib <= 0:
        raise ArchiveError("invalid_dictionary", "Dictionary size must be positive.")
    return [
        "-t7z",
        "-mx=9",
        "-m0=lzma2",
        f"-md={dictionary_mib}m",
        "-mfb=273",
        "-ms=on",
        "-mmt=on",
    ]


def select_dictionary_mib(
    *,
    total_memory_bytes: int,
    available_memory_bytes: int,
) -> int:
    if total_memory_bytes <= 0 or available_memory_bytes <= 0:
        raise ArchiveError(
            "memory_detection_failed",
            "Physical and available memory must both be positive.",
        )
    memory_budget = min(total_memory_bytes // 4, available_memory_bytes // 2)
    safe_dictionary_mib = memory_budget // (ENCODER_MEMORY_FACTOR * 1024**2)
    for candidate in DICTIONARY_CANDIDATES_MIB:
        if candidate <= safe_dictionary_mib:
            return candidate
    raise ArchiveError(
        "insufficient_compression_memory",
        "Available memory is too low for the minimum supported LZMA2 dictionary policy.",
        details={"safe_dictionary_mib": safe_dictionary_mib},
    )


def detect_memory_bytes() -> tuple[int, int]:
    if os.name == "nt":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ArchiveError("memory_detection_failed", "GlobalMemoryStatusEx failed.")
        return int(status.ullTotalPhys), int(status.ullAvailPhys)

    page_size = os.sysconf("SC_PAGE_SIZE")
    total = page_size * os.sysconf("SC_PHYS_PAGES")
    available = page_size * os.sysconf("SC_AVPHYS_PAGES")
    return int(total), int(available)


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:64] or "task"


def _load_inspection(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveError(
            "inspection_manifest_invalid",
            f"Could not read inspection manifest: {exc}",
        ) from exc
    if isinstance(payload, dict) and payload.get("operation") == "inspect" and "result" in payload:
        payload = payload["result"]
    if not isinstance(payload, dict) or payload.get("schema") != "agent_toolbelt_context_transfer.inventory.v1":
        raise ArchiveError(
            "inspection_manifest_invalid",
            "Inspection manifest has an unsupported schema.",
        )
    return payload


def _validated_rollouts(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    if not inventory.get("retirement_ready") or inventory.get("blockers"):
        raise ArchiveError(
            "inspection_not_ready",
            "Inspection has blockers and cannot be packaged.",
            details={"blockers": inventory.get("blockers", [])},
        )

    codex_home = Path(str(inventory["codex_home"])).resolve()
    validated: list[dict[str, Any]] = []
    for record in inventory.get("threads", []):
        path = Path(str(record["rollout_path"]))
        try:
            relative = path.resolve().relative_to(codex_home)
        except (OSError, ValueError) as exc:
            raise ArchiveError(
                "unsafe_source_path",
                f"Rollout is outside CODEX_HOME: {path}",
            ) from exc
        if not relative.parts or relative.parts[0].casefold() not in {
            "sessions",
            "archived_sessions",
        }:
            raise ArchiveError(
                "unsafe_source_path",
                f"Rollout is outside an allowed Codex rollout root: {path}",
            )
        if path.is_symlink() or not path.is_file():
            raise ArchiveError("source_file_changed", f"Rollout is no longer a regular file: {path}")
        stat_result = path.stat()
        actual_hash = _sha256_file(path)
        expected = {
            "size": record.get("size"),
            "mtime_ns": record.get("mtime_ns"),
            "sha256": record.get("sha256"),
        }
        actual = {
            "size": stat_result.st_size,
            "mtime_ns": stat_result.st_mtime_ns,
            "sha256": actual_hash,
        }
        if expected != actual:
            raise ArchiveError(
                "source_file_changed",
                f"Rollout changed after inspection: {path}",
                details={"thread_id": record.get("thread_id")},
            )
        validated.append(
            {
                "thread_id": record["thread_id"],
                "original_path": str(path),
                "archive_path": relative.as_posix(),
                **actual,
            }
        )
    if not validated:
        raise ArchiveError("inspection_not_ready", "Inspection contains no readable rollouts.")
    return validated


def _run_seven_zip(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    heartbeat_stream: TextIO | None = None,
) -> str:
    stream = heartbeat_stream or sys.stderr
    process = subprocess.Popen(
        arguments,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            output.append(line)
            if line.strip():
                print(f"[context-transfer] {line.rstrip()}", file=stream, flush=True)
    finally:
        process.stdout.close()
    return_code = process.wait()
    combined = "".join(output)
    if return_code != 0:
        raise ArchiveError(
            "seven_zip_failed",
            f"7-Zip exited with code {return_code}.",
            details={"exit_code": return_code, "output_excerpt": combined[-2000:]},
        )
    return combined


def _seven_zip_version(seven_zip_path: str) -> str:
    completed = subprocess.run(
        [seven_zip_path],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    for line in output.splitlines():
        if line.strip():
            return line.strip()
    return "unknown"


def _representative_members(rollouts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexes = sorted({0, len(rollouts) // 2, len(rollouts) - 1})
    return [rollouts[index] for index in indexes]


def _extract_and_compare(
    *,
    archive_path: Path,
    transaction_root: Path,
    manifest: dict[str, Any],
    seven_zip_path: str,
) -> dict[str, Any]:
    staging = transaction_root / ".verification-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        metadata_members = [
            "context-transfer/manifest.json",
            "context-transfer/CONTEXT_TRANSFER.md",
            "context-transfer/threads.json",
            "context-transfer/spawn-edges.json",
        ]
        _run_seven_zip(
            [seven_zip_path, "x", "-y", f"-o{staging}", str(archive_path), *metadata_members]
        )
        internal_manifest = staging / "context-transfer" / "manifest.json"
        internal_handoff = staging / "context-transfer" / "CONTEXT_TRANSFER.md"
        external_manifest = transaction_root / "manifest.json"
        external_handoff = transaction_root / "CONTEXT_TRANSFER.md"
        internal_threads = staging / "context-transfer" / "threads.json"
        internal_edges = staging / "context-transfer" / "spawn-edges.json"
        external_threads = transaction_root / "threads.json"
        external_edges = transaction_root / "spawn-edges.json"
        if _sha256_file(internal_manifest) != _sha256_file(external_manifest):
            raise ArchiveError("manifest_hash_mismatch", "Internal and external manifests differ.")
        if _sha256_file(internal_handoff) != _sha256_file(external_handoff):
            raise ArchiveError("handoff_hash_mismatch", "Internal and external handoffs differ.")
        if _sha256_file(internal_threads) != _sha256_file(external_threads):
            raise ArchiveError("threads_hash_mismatch", "Internal and external thread exports differ.")
        if _sha256_file(internal_edges) != _sha256_file(external_edges):
            raise ArchiveError("spawn_edges_hash_mismatch", "Internal and external edge exports differ.")

        representatives = _representative_members(manifest["rollouts"])
        _run_seven_zip(
            [
                seven_zip_path,
                "x",
                "-y",
                f"-o{staging}",
                str(archive_path),
                *(item["archive_path"] for item in representatives),
            ]
        )
        for item in representatives:
            extracted = staging.joinpath(*item["archive_path"].split("/"))
            if not extracted.is_file() or _sha256_file(extracted) != item["sha256"]:
                raise ArchiveError(
                    "representative_extraction_mismatch",
                    f"Representative rollout did not verify: {item['archive_path']}",
                )
        return {
            "internal_manifest_matches": True,
            "internal_handoff_matches": True,
            "internal_threads_matches": True,
            "internal_spawn_edges_matches": True,
            "representative_extractions_verified": len(representatives),
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def pack_recovery(
    *,
    inspection_manifest_path: str | os.PathLike[str],
    handoff_path: str | os.PathLike[str],
    archive_root: str | os.PathLike[str],
    seven_zip_path: str | None = None,
    dictionary_mib: int | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    inspection_path = Path(inspection_manifest_path)
    handoff_source = Path(handoff_path)
    inventory = _load_inspection(inspection_path)
    rollouts = _validated_rollouts(inventory)
    if not handoff_source.is_file():
        raise ArchiveError("handoff_missing", f"Handoff file was not found: {handoff_source}")

    root = Path(archive_root).resolve()
    if os.name == "nt" and root.drive.casefold() == "c:":
        raise ArchiveError("unsafe_archive_root", "Recovery archives must not be staged on C:.")
    seven_zip = seven_zip_path or shutil.which("7z.exe") or shutil.which("7z")
    if not seven_zip:
        raise ArchiveError("seven_zip_missing", "7-Zip was not found.")
    if dictionary_mib is None:
        total_memory, available_memory = detect_memory_bytes()
        dictionary_mib = select_dictionary_mib(
            total_memory_bytes=total_memory,
            available_memory_bytes=available_memory,
        )

    current_time = (now or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc)
    source_id = str(inventory["source_thread_id"])
    source_record = next(
        (item for item in inventory["threads"] if item["thread_id"] == source_id),
        inventory["threads"][0],
    )
    title = str(source_record.get("metadata", {}).get("title") or source_id)
    transaction_root = (
        root
        / f"{current_time.year:04d}"
        / f"{source_id}--{_safe_slug(title)}"
        / current_time.strftime("%Y%m%dT%H%M%SZ")
    )
    if transaction_root.exists():
        raise ArchiveError("transaction_exists", f"Transaction already exists: {transaction_root}")

    transaction_root.mkdir(parents=True)
    payload_root = transaction_root / ".payload" / "context-transfer"
    payload_root.mkdir(parents=True)
    external_handoff = transaction_root / "CONTEXT_TRANSFER.md"
    shutil.copy2(handoff_source, external_handoff)

    manifest = {
        "schema": "agent_toolbelt_context_transfer.archive_manifest.v1",
        "source_thread_id": source_id,
        "destination_thread_id": inventory.get("destination_thread_id"),
        "created_at": current_time.isoformat().replace("+00:00", "Z"),
        "codex_home": inventory["codex_home"],
        "inspection_schema": inventory["schema"],
        "inspection_thread_count": inventory["thread_count"],
        "inspection_edge_count": inventory["edge_count"],
        "total_rollout_bytes": inventory["total_rollout_bytes"],
        "handoff_sha256": _sha256_file(external_handoff),
        "rollouts": rollouts,
        "privacy_warning": (
            "The archive contains raw historical task rollouts and may include secrets "
            "that were present in the original conversations."
        ),
    }
    external_manifest = transaction_root / "manifest.json"
    _write_json(external_manifest, manifest)
    _write_json(transaction_root / "threads.json", inventory["threads"])
    _write_json(transaction_root / "spawn-edges.json", inventory["edges"])

    shutil.copy2(external_manifest, payload_root / "manifest.json")
    shutil.copy2(external_handoff, payload_root / "CONTEXT_TRANSFER.md")
    shutil.copy2(transaction_root / "threads.json", payload_root / "threads.json")
    shutil.copy2(transaction_root / "spawn-edges.json", payload_root / "spawn-edges.json")

    rollout_list = transaction_root / ".rollouts.lst"
    rollout_list.write_text(
        "".join(f'"{item["archive_path"].replace("/", os.sep)}"\n' for item in rollouts),
        encoding="utf-8",
        newline="\n",
    )
    metadata_list = transaction_root / ".metadata.lst"
    metadata_list.write_text(
        "".join(
            f'"context-transfer{os.sep}{name}"\n'
            for name in ("manifest.json", "CONTEXT_TRANSFER.md", "threads.json", "spawn-edges.json")
        ),
        encoding="utf-8",
        newline="\n",
    )

    partial_archive = transaction_root / "thread-tree.7z.partial"
    final_archive = transaction_root / "thread-tree.7z"
    compression = compression_arguments(dictionary_mib)
    common_switches = [*compression, "-scsUTF-8", "-y", "-bb1", "-bso1", "-bse1", "-bsp1"]
    commands: list[list[str]] = []
    try:
        rollout_command = [
            seven_zip,
            "a",
            *common_switches,
            str(partial_archive),
            f"@{rollout_list}",
        ]
        commands.append(rollout_command)
        _run_seven_zip(rollout_command, cwd=Path(str(inventory["codex_home"])))

        metadata_command = [
            seven_zip,
            "a",
            *common_switches,
            str(partial_archive),
            f"@{metadata_list}",
        ]
        commands.append(metadata_command)
        _run_seven_zip(metadata_command, cwd=payload_root.parent)

        test_command = [seven_zip, "t", "-y", str(partial_archive)]
        commands.append(test_command)
        _run_seven_zip(test_command)
        extraction = _extract_and_compare(
            archive_path=partial_archive,
            transaction_root=transaction_root,
            manifest=manifest,
            seven_zip_path=seven_zip,
        )
        archive_sha256 = _sha256_file(partial_archive)
        os.replace(partial_archive, final_archive)
        verification = {
            "schema": "agent_toolbelt_context_transfer.verification.v1",
            "ok": True,
            "transaction_root": str(transaction_root),
            "archive_path": str(final_archive),
            "archive_sha256": archive_sha256,
            "archive_test_passed": True,
            "manifest_sha256": _sha256_file(external_manifest),
            "handoff_sha256": _sha256_file(external_handoff),
            "threads_sha256": _sha256_file(transaction_root / "threads.json"),
            "spawn_edges_sha256": _sha256_file(transaction_root / "spawn-edges.json"),
            "seven_zip_path": str(seven_zip),
            "seven_zip_version": _seven_zip_version(str(seven_zip)),
            "compression": {
                "dictionary_mib": dictionary_mib,
                "arguments": compression,
                "policy": "maximum_lzma2_solid_safe_memory_budget",
            },
            "commands": commands,
            "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **extraction,
        }
        _write_json(transaction_root / "verification.json", verification)
        return verification
    finally:
        for path in (rollout_list, metadata_list):
            if path.exists():
                path.unlink()
        if payload_root.parent.exists():
            shutil.rmtree(payload_root.parent)


def verify_recovery_archive(
    archive_path: str | os.PathLike[str],
    *,
    seven_zip_path: str | None = None,
) -> dict[str, Any]:
    archive_file = Path(archive_path).resolve()
    transaction_root = archive_file.parent
    verification_path = transaction_root / "verification.json"
    manifest_path = transaction_root / "manifest.json"
    handoff_path = transaction_root / "CONTEXT_TRANSFER.md"
    threads_path = transaction_root / "threads.json"
    edges_path = transaction_root / "spawn-edges.json"
    for required in (
        archive_file,
        verification_path,
        manifest_path,
        handoff_path,
        threads_path,
        edges_path,
    ):
        if not required.is_file():
            raise ArchiveError("recovery_artifact_missing", f"Recovery artifact is missing: {required}")
    verification = json.loads(verification_path.read_text(encoding="utf-8-sig"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    compression = verification.get("compression", {})
    dictionary_mib = compression.get("dictionary_mib")
    if (
        not isinstance(dictionary_mib, int)
        or compression.get("arguments") != compression_arguments(dictionary_mib)
        or compression.get("policy") != "maximum_lzma2_solid_safe_memory_budget"
    ):
        raise ArchiveError(
            "compression_policy_mismatch",
            "Recorded compression evidence does not match the required maximum LZMA2 solid policy.",
        )
    if _sha256_file(archive_file) != verification.get("archive_sha256"):
        raise ArchiveError("archive_hash_mismatch", "Archive SHA-256 does not match verification.json.")
    if _sha256_file(manifest_path) != verification.get("manifest_sha256"):
        raise ArchiveError("manifest_hash_mismatch", "External manifest SHA-256 changed.")
    if _sha256_file(handoff_path) != verification.get("handoff_sha256"):
        raise ArchiveError("handoff_hash_mismatch", "External handoff SHA-256 changed.")
    if _sha256_file(threads_path) != verification.get("threads_sha256"):
        raise ArchiveError("threads_hash_mismatch", "External thread export SHA-256 changed.")
    if _sha256_file(edges_path) != verification.get("spawn_edges_sha256"):
        raise ArchiveError("spawn_edges_hash_mismatch", "External edge export SHA-256 changed.")

    seven_zip = (
        seven_zip_path
        or verification.get("seven_zip_path")
        or shutil.which("7z.exe")
        or shutil.which("7z")
    )
    if not seven_zip:
        raise ArchiveError("seven_zip_missing", "7-Zip was not found.")
    try:
        _run_seven_zip([str(seven_zip), "t", "-y", str(archive_file)])
    except ArchiveError as exc:
        raise ArchiveError("archive_test_failed", str(exc), details=exc.details) from exc
    extraction = _extract_and_compare(
        archive_path=archive_file,
        transaction_root=transaction_root,
        manifest=manifest,
        seven_zip_path=str(seven_zip),
    )
    return {
        "schema": "agent_toolbelt_context_transfer.verify_result.v1",
        "ok": True,
        "archive_path": str(archive_file),
        "archive_sha256": verification["archive_sha256"],
        "archive_test_passed": True,
        **extraction,
    }
