from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import stat
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


TINY_MAX_BYTES = 64 * 1024 * 1024
LARGE_MIN_BYTES = 1024**3
BUNDLE_MAX_BYTES = 4 * 1024**3
MANIFEST_SCHEMA_VERSION = 1
PROTECTED_REMOTE_DESTINATIONS = {
    "/",
    "/data",
    "/mnt",
    "/odm",
    "/product",
    "/sdcard",
    "/storage",
    "/system",
    "/vendor",
}


class TransferError(RuntimeError):
    def __init__(self, kind: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


CommandRunner = Callable[[list[str], str | None], subprocess.CompletedProcess[str]]


def run_process(command: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def resolve_adb_executable(explicit_path: str | None = None) -> str:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    for variable in ("ADB_PATH", "ANDROID_ADB"):
        value = os.getenv(variable)
        if value:
            candidates.append(Path(value).expanduser())
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.getenv(variable)
        if value:
            candidates.append(Path(value).expanduser() / "platform-tools" / "adb.exe")
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe")

    which_adb = shutil.which("adb.exe") or shutil.which("adb")
    if which_adb:
        candidates.append(Path(which_adb))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    raise TransferError(
        "adb_unavailable",
        "ADB executable was not found. Pass --adb-path or configure the Android SDK.",
    )


def adb_command(adb_path: str, serial: str, *arguments: str) -> list[str]:
    if not serial.strip():
        raise TransferError("device_unavailable", "An explicit ADB serial is required for a device command.")
    return [adb_path, "-s", serial, *arguments]


def parse_adb_devices(output: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("list of devices attached") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        endpoint: dict[str, Any] = {
            "serial": parts[0],
            "state": parts[1],
            "product": "",
            "model": "",
            "device": "",
            "transport_id": "",
        }
        for token in parts[2:]:
            if ":" not in token:
                continue
            key, value = token.split(":", 1)
            if key in {"product", "model", "device", "transport_id"}:
                endpoint[key] = value
        devices.append(endpoint)
    return devices


def select_device(devices: list[dict[str, Any]], *, serial: str | None = None) -> dict[str, Any]:
    if serial:
        matches = [item for item in devices if str(item.get("serial")) == serial]
        if not matches:
            raise TransferError(
                "device_unavailable",
                f"ADB endpoint {serial!r} is not connected.",
                details={"candidates": devices},
            )
        selected = matches[0]
        if selected.get("state") != "device":
            raise TransferError(
                "device_not_ready",
                f"ADB endpoint {serial!r} is {selected.get('state')!r}, not ready.",
                details={"endpoint": selected},
            )
        return dict(selected)

    ready = [dict(item) for item in devices if item.get("state") == "device"]
    if not ready:
        raise TransferError(
            "device_unavailable",
            "No ready ADB endpoint is connected.",
            details={"candidates": devices},
        )
    if len(ready) > 1:
        raise TransferError(
            "ambiguous_device",
            "Multiple ready ADB endpoints are connected; rerun with --serial.",
            details={"candidates": ready},
        )
    return ready[0]


GETPROP_PATTERN = re.compile(r"^\[([^]]+)\]:\s*\[(.*)\]$")


def parse_getprop(output: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    for line in output.splitlines():
        match = GETPROP_PATTERN.match(line.strip())
        if match:
            properties[match.group(1)] = match.group(2)
    return properties


def stable_identity_hash(endpoint: dict[str, Any]) -> str:
    identity = {
        "adb_serial": str(endpoint.get("serial") or ""),
        "android_serial": str(endpoint.get("android_serial") or ""),
        "model": str(endpoint.get("model") or ""),
        "product": str(endpoint.get("product") or ""),
        "device": str(endpoint.get("device") or ""),
        "build_fingerprint": str(endpoint.get("build_fingerprint") or ""),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def enrich_endpoint_identity(endpoint: dict[str, Any], getprop_output: str) -> dict[str, Any]:
    properties = parse_getprop(getprop_output)
    enriched = {
        **endpoint,
        "android_serial": properties.get("ro.serialno", ""),
        "model": properties.get("ro.product.model", str(endpoint.get("model") or "")),
        "product": properties.get("ro.product.name", str(endpoint.get("product") or "")),
        "device": properties.get("ro.product.device", str(endpoint.get("device") or "")),
        "build_fingerprint": properties.get("ro.build.fingerprint", ""),
    }
    enriched["identity_hash"] = stable_identity_hash(enriched)
    return enriched


def parse_toybox_capabilities(output: str) -> dict[str, bool]:
    commands = set(output.replace("[", " ").replace("]", " ").split())
    capabilities = {
        "tar": "tar" in commands,
        "sha256sum": "sha256sum" in commands,
        "gzip": "gzip" in commands,
        "mv": "mv" in commands,
        "rm": "rm" in commands,
        "mkdir": "mkdir" in commands,
    }
    capabilities["transfer_ready"] = all(
        capabilities[name] for name in ("tar", "sha256sum", "mv", "rm")
    )
    return capabilities


def validate_remote_destination(destination: str) -> tuple[str, str]:
    if not destination or "\n" in destination or "\r" in destination or "\t" in destination:
        raise TransferError("unsafe_destination", "Remote destination is empty or contains control characters.")
    normalized = posixpath.normpath(destination.replace("\\", "/"))
    if not normalized.startswith("/") or normalized in PROTECTED_REMOTE_DESTINATIONS:
        raise TransferError(
            "unsafe_destination",
            f"Remote destination is not a safe absolute child path: {destination!r}",
        )
    parent = posixpath.dirname(normalized)
    if not parent or parent in {"/"}:
        raise TransferError("unsafe_destination", f"Remote destination parent is unsafe: {parent!r}")
    return normalized, parent


def parse_df_available_bytes(output: str) -> int:
    rows = [line.split() for line in output.splitlines() if line.strip()]
    for fields in reversed(rows):
        if len(fields) < 4 or not fields[3].isdigit():
            continue
        return int(fields[3]) * 1024
    raise TransferError("capacity_unavailable", "Could not parse destination free space from df output.")


def inventory_devices(
    *,
    adb_path: str,
    runner: CommandRunner = run_process,
) -> list[dict[str, Any]]:
    listed = runner([adb_path, "devices", "-l"], None)
    if listed.returncode != 0:
        raise TransferError(
            "adb_failed",
            "ADB endpoint inventory failed.",
            details={"stderr": listed.stderr.strip(), "exit_code": listed.returncode},
        )
    devices = parse_adb_devices(listed.stdout)
    enriched: list[dict[str, Any]] = []
    for endpoint in devices:
        if endpoint.get("state") != "device":
            enriched.append(endpoint)
            continue
        serial = str(endpoint["serial"])
        properties = runner(adb_command(adb_path, serial, "shell", "getprop"), None)
        toybox = runner(adb_command(adb_path, serial, "shell", "toybox"), None)
        identity = enrich_endpoint_identity(endpoint, properties.stdout if properties.returncode == 0 else "")
        identity["capabilities"] = parse_toybox_capabilities(
            toybox.stdout if toybox.returncode == 0 else ""
        )
        enriched.append(identity)
    return enriched




def classify_size(
    size: int,
    *,
    tiny_max_bytes: int = TINY_MAX_BYTES,
    large_min_bytes: int = LARGE_MIN_BYTES,
) -> tuple[str, str]:
    if size >= large_min_bytes:
        return "direct", "large_file_direct"
    if size <= tiny_max_bytes:
        return "packed", "tiny_file"
    return "direct", "medium_file_direct"


def validate_thresholds(
    *,
    tiny_max_bytes: int,
    large_min_bytes: int,
    bundle_max_bytes: int,
) -> None:
    if min(tiny_max_bytes, large_min_bytes, bundle_max_bytes) <= 0:
        raise TransferError("invalid_thresholds", "Transfer size thresholds must be positive.")
    if tiny_max_bytes >= large_min_bytes:
        raise TransferError(
            "invalid_thresholds",
            "The tiny-file threshold must be smaller than the large-file threshold.",
        )
    if bundle_max_bytes < tiny_max_bytes:
        raise TransferError(
            "invalid_thresholds",
            "The bundle cap must be at least as large as the tiny-file threshold.",
        )


def validate_relative_path(relative_path: str) -> None:
    normalized = relative_path.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        raise ValueError(f"Invalid relative path: {relative_path!r}")
    if "\n" in normalized or "\r" in normalized or "\t" in normalized:
        raise ValueError(f"Relative paths may not contain tabs or newlines: {relative_path!r}")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError(f"Relative path escapes or ambiguously addresses the source: {relative_path!r}")


def validate_unique_relative_paths(files: list[dict[str, Any]]) -> None:
    seen: dict[str, str] = {}
    for item in files:
        relative_path = str(item["relative_path"]).replace("\\", "/")
        validate_relative_path(relative_path)
        key = relative_path.casefold()
        if key in seen:
            raise ValueError(
                "Detected case-insensitive relative path collision: "
                f"{seen[key]!r} and {relative_path!r}"
            )
        seen[key] = relative_path


def estimate_tar_bytes(files: list[dict[str, Any]]) -> int:
    payload_blocks = sum((int(item["size"]) + 511) // 512 for item in files)
    header_blocks = len(files)
    end_blocks = 2
    return (payload_blocks + header_blocks + end_blocks) * 512


def assign_bundles(
    files: list[dict[str, Any]],
    *,
    tiny_max_bytes: int = TINY_MAX_BYTES,
    large_min_bytes: int = LARGE_MIN_BYTES,
    bundle_max_bytes: int = BUNDLE_MAX_BYTES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validate_unique_relative_paths(files)
    ordered = [dict(item) for item in sorted(files, key=lambda item: str(item["relative_path"]).casefold())]
    tiny_indexes: list[int] = []
    for index, item in enumerate(ordered):
        mode, reason = classify_size(
            int(item["size"]),
            tiny_max_bytes=tiny_max_bytes,
            large_min_bytes=large_min_bytes,
        )
        item["transfer_mode"] = mode
        item["classification_reason"] = reason
        if mode == "packed":
            tiny_indexes.append(index)

    if len(tiny_indexes) == 1:
        item = ordered[tiny_indexes[0]]
        item["transfer_mode"] = "direct"
        item["classification_reason"] = "single_tiny_file_direct"
        return ordered, []

    bundles: list[dict[str, Any]] = []
    current_members: list[dict[str, Any]] = []
    current_bytes = 0

    def finalize_bundle() -> None:
        nonlocal current_members, current_bytes
        if not current_members:
            return
        bundle_name = f"bundle-{len(bundles) + 1:04d}.tar"
        for member in current_members:
            member["bundle"] = bundle_name
        bundles.append(
            {
                "name": bundle_name,
                "archive_format": "tar",
                "compression": "none",
                "payload_bytes": current_bytes,
                "estimated_archive_bytes": estimate_tar_bytes(current_members),
                "members": [str(member["relative_path"]) for member in current_members],
            }
        )
        current_members = []
        current_bytes = 0

    for index in tiny_indexes:
        item = ordered[index]
        size = int(item["size"])
        if current_members and current_bytes + size > bundle_max_bytes:
            finalize_bundle()
        current_members.append(item)
        current_bytes += size
    finalize_bundle()
    return ordered, bundles


def is_reparse_point(path: Path) -> bool:
    metadata = path.lstat()
    file_attributes = int(getattr(metadata, "st_file_attributes", 0))
    reparse_attribute = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return path.is_symlink() or bool(file_attributes & reparse_attribute)


def hash_file(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, *, source_root: Path, relative_path: str) -> dict[str, Any]:
    if is_reparse_point(path):
        raise ValueError(f"Source symbolic links or reparse points are not supported: {path}")
    metadata = path.stat()
    if not path.is_file():
        raise ValueError(f"Source entry is not a regular file: {path}")
    relative_path = relative_path.replace("\\", "/")
    validate_relative_path(relative_path)
    resolved = path.resolve()
    try:
        resolved.relative_to(source_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Source entry escapes the source root: {path}") from exc
    return {
        "relative_path": relative_path,
        "size": int(metadata.st_size),
        "mtime_ns": int(metadata.st_mtime_ns),
        "sha256": hash_file(path),
    }


def scan_source(source: str | Path) -> list[dict[str, Any]]:
    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        raise ValueError(f"Source does not exist: {source_path}")
    if is_reparse_point(source_path):
        raise ValueError(f"Source symbolic links or reparse points are not supported: {source_path}")

    if source_path.is_file():
        records = [
            file_record(
                source_path,
                source_root=source_path.parent,
                relative_path=source_path.name,
            )
        ]
    elif source_path.is_dir():
        records = []
        for root_text, dir_names, file_names in os.walk(source_path, followlinks=False):
            root = Path(root_text)
            for name in sorted(dir_names, key=str.casefold):
                candidate = root / name
                if is_reparse_point(candidate):
                    raise ValueError(
                        f"Source symbolic links or reparse points are not supported: {candidate}"
                    )
            for name in sorted(file_names, key=str.casefold):
                path = root / name
                records.append(
                    file_record(
                        path,
                        source_root=source_path,
                        relative_path=path.relative_to(source_path).as_posix(),
                    )
                )
    else:
        raise ValueError(f"Source must be a regular file or directory: {source_path}")

    if not records:
        raise ValueError(f"Source contains no files: {source_path}")
    records.sort(key=lambda item: str(item["relative_path"]).casefold())
    validate_unique_relative_paths(records)
    return records


def source_snapshot_hash(files: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "relative_path": str(item["relative_path"]).replace("\\", "/"),
            "size": int(item["size"]),
            "mtime_ns": int(item["mtime_ns"]),
            "sha256": str(item["sha256"]),
        }
        for item in sorted(files, key=lambda item: str(item["relative_path"]).casefold())
    ]
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_manifest_json(manifest: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_path", "manifest_sha256"}
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def manifest_hash(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_json(manifest).encode("utf-8")).hexdigest()


def resolve_seven_zip_executable(explicit_path: str | None = None) -> str:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    for variable in ("SEVEN_ZIP", "SEVEN_ZIP_PATH"):
        value = os.getenv(variable)
        if value:
            candidates.append(Path(value).expanduser())
    for executable_name in ("7z.exe", "7z", "NanaZipC.exe"):
        resolved = shutil.which(executable_name)
        if resolved:
            candidates.append(Path(resolved))
    user_profile = os.getenv("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / "scoop" / "apps" / "7zip" / "current" / "7z.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    raise TransferError(
        "seven_zip_unavailable",
        "7-Zip was not found. Pass --seven-zip-path or install a 7z/NanaZip command alias.",
    )


def remote_shell_command(adb_path: str, serial: str, script: str) -> list[str]:
    # adb shell reconstructs a remote command line, so quote the complete -c
    # payload rather than relying on local argv boundaries surviving transport.
    return adb_command(adb_path, serial, "shell", "sh", "-c", shlex.quote(script))


def require_success(
    completed: subprocess.CompletedProcess[str],
    *,
    kind: str,
    message: str,
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    if completed.returncode != 0:
        raise TransferError(
            kind,
            message,
            details={
                "command": command,
                "exit_code": completed.returncode,
                "stderr": completed.stderr.strip(),
                "stdout": completed.stdout.strip(),
            },
        )
    return completed


def selected_endpoint(
    *,
    adb_path: str,
    serial: str | None,
    runner: CommandRunner,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    devices = inventory_devices(adb_path=adb_path, runner=runner)
    selected = select_device(devices, serial=serial)
    capabilities = selected.get("capabilities") or {}
    if not capabilities.get("transfer_ready"):
        raise TransferError(
            "device_capability_missing",
            "Selected endpoint lacks native tar, sha256sum, mv, or rm support.",
            details={"endpoint": selected, "capabilities": capabilities},
        )
    return selected, devices


def remote_preflight(
    *,
    adb_path: str,
    serial: str,
    destination: str,
    parent: str,
    required_bytes: int,
    runner: CommandRunner,
) -> dict[str, Any]:
    parent_quoted = shlex.quote(parent)
    destination_quoted = shlex.quote(destination)
    parent_command = remote_shell_command(
        adb_path,
        serial,
        f"test -d {parent_quoted} && test -w {parent_quoted}",
    )
    require_success(
        runner(parent_command, None),
        kind="destination_unavailable",
        message="Remote destination parent does not exist or is not writable.",
        command=parent_command,
    )
    absent_command = remote_shell_command(adb_path, serial, f"test ! -e {destination_quoted}")
    require_success(
        runner(absent_command, None),
        kind="destination_exists",
        message="Remote destination already exists; v1 does not merge or replace destinations.",
        command=absent_command,
    )
    df_command = remote_shell_command(
        adb_path,
        serial,
        f"df -Pk {shlex.quote(parent)}",
    )
    df_result = require_success(
        runner(df_command, None),
        kind="capacity_unavailable",
        message="Unable to inspect remote destination capacity.",
        command=df_command,
    )
    available_bytes = parse_df_available_bytes(df_result.stdout)
    if available_bytes < required_bytes:
        raise TransferError(
            "insufficient_space",
            "Remote destination does not have enough free space for staged transfer and extraction.",
            details={"available_bytes": available_bytes, "required_bytes": required_bytes},
        )
    return {
        "parent_writable": True,
        "destination_absent": True,
        "available_bytes": available_bytes,
        "required_bytes": required_bytes,
    }


def default_temp_root() -> Path:
    return Path(r"D:\Temp\adb-archive-transfer")


def write_manifest(manifest: dict[str, Any], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest["manifest_path"] = str(manifest_path.resolve())
    manifest["manifest_sha256"] = manifest_hash(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransferError("manifest_unavailable", f"Unable to read transfer manifest: {manifest_path}") from exc
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise TransferError("manifest_invalid", "Unsupported transfer manifest schema version.")
    expected = str(manifest.get("manifest_sha256") or "")
    actual = manifest_hash(manifest)
    if not expected or expected != actual:
        raise TransferError(
            "manifest_changed",
            "Transfer manifest integrity check failed.",
            details={"expected": expected, "actual": actual},
        )
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def plan_transfer(
    *,
    source: str | Path,
    destination: str,
    serial: str | None = None,
    manifest_path: str | Path | None = None,
    temp_root: str | Path | None = None,
    adb_path: str | None = None,
    seven_zip_path: str | None = None,
    tiny_max_bytes: int = TINY_MAX_BYTES,
    large_min_bytes: int = LARGE_MIN_BYTES,
    bundle_max_bytes: int = BUNDLE_MAX_BYTES,
    runner: CommandRunner = run_process,
) -> dict[str, Any]:
    validate_thresholds(
        tiny_max_bytes=tiny_max_bytes,
        large_min_bytes=large_min_bytes,
        bundle_max_bytes=bundle_max_bytes,
    )
    source_path = Path(source).expanduser().resolve()
    try:
        files = scan_source(source_path)
        files, bundles = assign_bundles(
            files,
            tiny_max_bytes=tiny_max_bytes,
            large_min_bytes=large_min_bytes,
            bundle_max_bytes=bundle_max_bytes,
        )
    except ValueError as exc:
        raise TransferError("source_invalid", str(exc)) from exc
    resolved_adb = resolve_adb_executable(adb_path)
    resolved_seven_zip = resolve_seven_zip_executable(seven_zip_path) if bundles else None
    endpoint, candidates = selected_endpoint(adb_path=resolved_adb, serial=serial, runner=runner)
    normalized_destination, destination_parent = validate_remote_destination(destination)
    required_bytes = sum(int(item["size"]) for item in files) + sum(
        int(bundle["estimated_archive_bytes"]) for bundle in bundles
    )
    capacity = remote_preflight(
        adb_path=resolved_adb,
        serial=str(endpoint["serial"]),
        destination=normalized_destination,
        parent=destination_parent,
        required_bytes=required_bytes,
        runner=runner,
    )

    transfer_id = uuid.uuid4().hex
    root = Path(temp_root).expanduser().resolve() if temp_root else default_temp_root().resolve()
    selected_manifest_path = (
        Path(manifest_path).expanduser().resolve()
        if manifest_path
        else root / "manifests" / f"{transfer_id}.json"
    )
    source_root = source_path if source_path.is_dir() else source_path.parent
    source_kind = "directory" if source_path.is_dir() else "file"
    remote_stage = posixpath.join(destination_parent, f".adb-archive-transfer-{transfer_id}")
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "transfer_id": transfer_id,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": str(source_path),
        "source_root": str(source_root.resolve()),
        "source_kind": source_kind,
        "source_snapshot_hash": source_snapshot_hash(files),
        "device": endpoint,
        "device_candidates": candidates,
        "destination": normalized_destination,
        "destination_parent": destination_parent,
        "remote_stage": remote_stage,
        "local_stage": str((root / transfer_id).resolve()),
        "adb_path": resolved_adb,
        "seven_zip_path": resolved_seven_zip,
        "thresholds": {
            "tiny_max_bytes": tiny_max_bytes,
            "large_min_bytes": large_min_bytes,
            "bundle_max_bytes": bundle_max_bytes,
        },
        "archive_policy": {"format": "tar", "compression": "none", "creator": "7zip"},
        "files": files,
        "bundles": bundles,
        "capacity": capacity,
    }
    write_manifest(manifest, selected_manifest_path)
    return {
        "ok": True,
        "operation": "plan",
        "manifest_path": str(selected_manifest_path),
        "manifest_sha256": manifest["manifest_sha256"],
        "transfer_id": transfer_id,
        "device": endpoint,
        "destination": normalized_destination,
        "file_count": len(files),
        "packed_file_count": sum(item["transfer_mode"] == "packed" for item in files),
        "direct_file_count": sum(item["transfer_mode"] == "direct" for item in files),
        "bundle_count": len(bundles),
        "capacity": capacity,
        "mutation_performed": False,
        "warnings": [],
        "errors": [],
    }


def verify_manifest_source(manifest: dict[str, Any]) -> None:
    source_root = Path(str(manifest["source_root"])).resolve()
    verified: list[dict[str, Any]] = []
    for expected in manifest["files"]:
        relative_path = str(expected["relative_path"])
        path = (source_root / Path(relative_path)).resolve()
        try:
            path.relative_to(source_root)
        except ValueError as exc:
            raise TransferError("source_changed", f"Manifest source path escapes the source root: {relative_path}") from exc
        if not path.is_file() or is_reparse_point(path):
            raise TransferError("source_changed", f"Manifest source file is missing or unsafe: {relative_path}")
        metadata = path.stat()
        actual = {
            "relative_path": relative_path,
            "size": int(metadata.st_size),
            "mtime_ns": int(metadata.st_mtime_ns),
            "sha256": hash_file(path),
        }
        for key in ("size", "mtime_ns", "sha256"):
            if actual[key] != expected[key]:
                raise TransferError(
                    "source_changed",
                    f"Manifest source file changed after planning: {relative_path}",
                    details={"field": key, "expected": expected[key], "actual": actual[key]},
                )
        verified.append(actual)
    if source_snapshot_hash(verified) != manifest["source_snapshot_hash"]:
        raise TransferError("source_changed", "Source snapshot no longer matches the transfer manifest.")


def build_seven_zip_command(
    seven_zip_path: str,
    *,
    archive_path: Path,
    list_path: Path,
) -> list[str]:
    return [
        seven_zip_path,
        "a",
        "-ttar",
        "-scsUTF-8",
        str(archive_path),
        f"@{list_path}",
    ]


def create_archives(
    manifest: dict[str, Any],
    *,
    runner: CommandRunner,
) -> dict[str, dict[str, Any]]:
    if not manifest["bundles"]:
        return {}
    seven_zip_path = str(manifest.get("seven_zip_path") or "")
    if not seven_zip_path:
        raise TransferError("seven_zip_unavailable", "Manifest requires TAR bundles but has no 7-Zip executable.")
    local_stage = Path(str(manifest["local_stage"]))
    local_stage.mkdir(parents=True, exist_ok=True)
    source_root = str(manifest["source_root"])
    archives: dict[str, dict[str, Any]] = {}
    for bundle in manifest["bundles"]:
        bundle_name = str(bundle["name"])
        archive_path = local_stage / bundle_name
        list_path = local_stage / f"{bundle_name}.files.txt"
        list_path.write_text("\n".join(str(item) for item in bundle["members"]) + "\n", encoding="utf-8")
        command = build_seven_zip_command(
            seven_zip_path,
            archive_path=archive_path,
            list_path=list_path,
        )
        require_success(
            runner(command, source_root),
            kind="archive_failed",
            message=f"7-Zip failed to create uncompressed TAR bundle {bundle_name}.",
            command=command,
        )
        if not archive_path.is_file():
            raise TransferError("archive_failed", f"7-Zip did not create expected TAR bundle: {archive_path}")
        archives[bundle_name] = {
            "path": archive_path,
            "size": archive_path.stat().st_size,
            "sha256": hash_file(archive_path),
        }
    return archives


def safe_remove_local_stage(manifest: dict[str, Any]) -> None:
    local_stage = Path(str(manifest["local_stage"])).resolve()
    transfer_id = str(manifest["transfer_id"])
    if local_stage.name != transfer_id:
        raise TransferError("unsafe_cleanup", f"Local staging root is not bound to transfer id: {local_stage}")
    if local_stage.exists():
        shutil.rmtree(local_stage)


def validate_manifest_remote_stage(manifest: dict[str, Any]) -> str:
    transfer_id = str(manifest["transfer_id"])
    expected = posixpath.join(
        str(manifest["destination_parent"]),
        f".adb-archive-transfer-{transfer_id}",
    )
    actual = str(manifest["remote_stage"])
    if actual != expected:
        raise TransferError("unsafe_cleanup", "Remote staging root is not bound to the manifest destination.")
    return actual


def apply_transfer(
    manifest_path: str | Path,
    *,
    confirm_transfer: bool,
    keep_manifest: bool = False,
    runner: CommandRunner = run_process,
) -> dict[str, Any]:
    if not confirm_transfer:
        raise TransferError("confirmation_required", "Transfer requires --confirm-transfer.")
    manifest = load_manifest(manifest_path)
    verify_manifest_source(manifest)

    adb_path = str(manifest["adb_path"])
    serial = str(manifest["device"]["serial"])
    endpoint, _candidates = selected_endpoint(adb_path=adb_path, serial=serial, runner=runner)
    if endpoint["identity_hash"] != manifest["device"]["identity_hash"]:
        raise TransferError(
            "device_identity_changed",
            "Connected ADB endpoint does not match the endpoint bound to this manifest.",
            details={"expected": manifest["device"], "actual": endpoint},
        )

    archives = create_archives(manifest, runner=runner)
    exact_required = sum(int(item["size"]) for item in manifest["files"]) + sum(
        int(item["size"]) for item in archives.values()
    )
    remote_preflight(
        adb_path=adb_path,
        serial=serial,
        destination=str(manifest["destination"]),
        parent=str(manifest["destination_parent"]),
        required_bytes=exact_required,
        runner=runner,
    )

    remote_stage = validate_manifest_remote_stage(manifest)
    remote_payload = posixpath.join(remote_stage, "payload")
    stage_absent_command = remote_shell_command(
        adb_path,
        serial,
        f"test ! -e {shlex.quote(remote_stage)}",
    )
    require_success(
        runner(stage_absent_command, None),
        kind="staging_exists",
        message="Manifest-owned remote staging already exists; inspect or clean it before retrying.",
        command=stage_absent_command,
    )
    create_script = f"mkdir -p {shlex.quote(remote_payload)}"
    create_command = remote_shell_command(adb_path, serial, create_script)
    require_success(
        runner(create_command, None),
        kind="remote_stage_failed",
        message="Unable to create remote transfer staging directory.",
        command=create_command,
    )

    source_root = Path(str(manifest["source_root"]))
    for item in manifest["files"]:
        if item["transfer_mode"] != "direct":
            continue
        relative_path = str(item["relative_path"])
        remote_path = posixpath.join(remote_payload, relative_path)
        remote_parent = posixpath.dirname(remote_path)
        mkdir_command = remote_shell_command(
            adb_path,
            serial,
            f"mkdir -p {shlex.quote(remote_parent)}",
        )
        require_success(
            runner(mkdir_command, None),
            kind="remote_stage_failed",
            message=f"Unable to create staged parent for {relative_path}.",
            command=mkdir_command,
        )
        push_command = adb_command(
            adb_path,
            serial,
            "push",
            str((source_root / Path(relative_path)).resolve()),
            remote_path,
        )
        require_success(
            runner(push_command, None),
            kind="push_failed",
            message=f"ADB push failed for direct file {relative_path}.",
            command=push_command,
        )

    for bundle_name, archive in archives.items():
        remote_archive = posixpath.join(remote_stage, bundle_name)
        push_command = adb_command(
            adb_path,
            serial,
            "push",
            str(archive["path"]),
            remote_archive,
        )
        require_success(
            runner(push_command, None),
            kind="push_failed",
            message=f"ADB push failed for TAR bundle {bundle_name}.",
            command=push_command,
        )
        hash_command = remote_shell_command(
            adb_path,
            serial,
            f"toybox sha256sum {shlex.quote(remote_archive)}",
        )
        hash_result = require_success(
            runner(hash_command, None),
            kind="remote_hash_failed",
            message=f"Unable to hash remote TAR bundle {bundle_name}.",
            command=hash_command,
        )
        remote_hash = hash_result.stdout.strip().split()[0] if hash_result.stdout.strip() else ""
        if remote_hash.lower() != str(archive["sha256"]).lower():
            raise TransferError(
                "remote_hash_mismatch",
                f"Remote TAR bundle hash does not match local bundle: {bundle_name}",
                details={"expected": archive["sha256"], "actual": remote_hash},
            )
        extract_command = remote_shell_command(
            adb_path,
            serial,
            "toybox tar --restrict -xf "
            f"{shlex.quote(remote_archive)} -C {shlex.quote(remote_payload)}",
        )
        require_success(
            runner(extract_command, None),
            kind="extract_failed",
            message=f"Unable to extract remote TAR bundle {bundle_name}.",
            command=extract_command,
        )

    local_stage = Path(str(manifest["local_stage"]))
    local_stage.mkdir(parents=True, exist_ok=True)
    checks_path = local_stage / "sha256sums.txt"
    checks_path.write_text(
        "".join(f"{item['sha256']}  {item['relative_path']}\n" for item in manifest["files"]),
        encoding="utf-8",
    )
    remote_checks = posixpath.join(remote_stage, "sha256sums.txt")
    checks_push = adb_command(adb_path, serial, "push", str(checks_path), remote_checks)
    require_success(
        runner(checks_push, None),
        kind="push_failed",
        message="Unable to push extracted-file verification manifest.",
        command=checks_push,
    )
    verify_script = (
        f"cd {shlex.quote(remote_payload)} && "
        f"toybox sha256sum -c {shlex.quote(remote_checks)}"
    )
    verify_command = remote_shell_command(adb_path, serial, verify_script)
    require_success(
        runner(verify_command, None),
        kind="verification_failed",
        message="Remote extracted-file SHA-256 verification failed.",
        command=verify_command,
    )

    placement_script = (
        f"mv -- {shlex.quote(remote_payload)} {shlex.quote(str(manifest['destination']))}"
    )
    placement_command = remote_shell_command(adb_path, serial, placement_script)
    require_success(
        runner(placement_command, None),
        kind="placement_failed",
        message="Unable to place verified payload at the final destination.",
        command=placement_command,
    )
    cleanup_command = remote_shell_command(
        adb_path,
        serial,
        f"toybox rm -rf -- {shlex.quote(remote_stage)}",
    )
    require_success(
        runner(cleanup_command, None),
        kind="cleanup_failed",
        message="Verified destination was placed, but remote staging cleanup failed.",
        command=cleanup_command,
    )

    safe_remove_local_stage(manifest)
    manifest_file = Path(str(manifest["manifest_path"]))
    if not keep_manifest and manifest_file.exists():
        manifest_file.unlink()
    return {
        "ok": True,
        "operation": "apply",
        "transfer_id": manifest["transfer_id"],
        "device": endpoint,
        "destination": manifest["destination"],
        "file_count": len(manifest["files"]),
        "bundle_count": len(manifest["bundles"]),
        "verified": True,
        "placed": True,
        "remote_stage_removed": True,
        "local_stage_removed": True,
        "manifest_removed": not keep_manifest,
        "mutation_performed": True,
        "warnings": [],
        "errors": [],
    }


def cleanup_transfer(
    manifest_path: str | Path,
    *,
    confirm_cleanup: bool,
    runner: CommandRunner = run_process,
) -> dict[str, Any]:
    if not confirm_cleanup:
        raise TransferError("confirmation_required", "Staging cleanup requires --confirm-cleanup.")
    manifest = load_manifest(manifest_path)
    adb_path = str(manifest["adb_path"])
    serial = str(manifest["device"]["serial"])
    endpoint, _candidates = selected_endpoint(adb_path=adb_path, serial=serial, runner=runner)
    if endpoint["identity_hash"] != manifest["device"]["identity_hash"]:
        raise TransferError("device_identity_changed", "Cleanup endpoint does not match the manifest.")
    remote_stage = validate_manifest_remote_stage(manifest)
    cleanup_command = remote_shell_command(
        adb_path,
        serial,
        f"toybox rm -rf -- {shlex.quote(remote_stage)}",
    )
    require_success(
        runner(cleanup_command, None),
        kind="cleanup_failed",
        message="Unable to remove manifest-owned remote staging.",
        command=cleanup_command,
    )
    safe_remove_local_stage(manifest)
    return {
        "ok": True,
        "operation": "cleanup",
        "transfer_id": manifest["transfer_id"],
        "device": endpoint,
        "remote_stage": remote_stage,
        "destination_untouched": True,
        "source_untouched": True,
        "warnings": [],
        "errors": [],
    }


def failure_payload(operation: str, exc: TransferError) -> dict[str, Any]:
    return {
        "ok": False,
        "operation": operation,
        "failure_kind": exc.kind,
        "warnings": [],
        "errors": [str(exc)],
        "details": exc.details,
    }


def devices_command(
    *,
    adb_path: str | None = None,
    runner: CommandRunner = run_process,
) -> dict[str, Any]:
    try:
        resolved_adb = resolve_adb_executable(adb_path)
        devices = inventory_devices(adb_path=resolved_adb, runner=runner)
    except TransferError as exc:
        return {
            "ok": False,
            "operation": "devices",
            "devices": [],
            "adb_path": adb_path,
            "failure_kind": exc.kind,
            "warnings": [],
            "errors": [str(exc)],
            "details": exc.details,
        }
    return {
        "ok": True,
        "operation": "devices",
        "devices": devices,
        "adb_path": resolved_adb,
        "ready_count": sum(item.get("state") == "device" for item in devices),
        "failure_kind": None,
        "warnings": [],
        "errors": [],
    }
