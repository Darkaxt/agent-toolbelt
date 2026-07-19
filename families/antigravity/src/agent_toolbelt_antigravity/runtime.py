from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import socket
import subprocess
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import request


TOOL_DIR_NAME = "antigravity-review"
CLAUDE_PROXY_PORT = 8317
RELEASE_REPOSITORY = "router-for-me/CLIProxyAPI"
RELEASE_API_ROOT = f"https://api.github.com/repos/{RELEASE_REPOSITORY}/releases"


class IsolationError(ValueError):
    """Raised when helper-owned state overlaps the external Claude proxy."""


class UpdateError(RuntimeError):
    """Raised when a helper-owned CLIProxyAPI release cannot be validated."""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    published_at: str
    asset_name: str
    asset_url: str
    asset_size: int
    sha256: str


@dataclass(frozen=True)
class RuntimePaths:
    base: Path
    releases: Path
    state: Path
    auth: Path
    current: Path

    @classmethod
    def from_base(cls, base: Path) -> "RuntimePaths":
        resolved = base.expanduser().resolve(strict=False)
        state = resolved / "state"
        return cls(
            base=resolved,
            releases=resolved / "releases",
            state=state,
            auth=resolved / "auth",
            current=state / "current.json",
        )

    @classmethod
    def default(cls) -> "RuntimePaths":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            root = Path(local_app_data)
        else:
            root = Path.home() / "AppData" / "Local"
        return cls.from_base(root / "Tools" / TOOL_DIR_NAME)


def _normalized(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _overlaps(first: Path, second: Path) -> bool:
    first_value = _normalized(first)
    second_value = _normalized(second)
    separator = os.sep
    return (
        first_value == second_value
        or first_value.startswith(second_value.rstrip(separator) + separator)
        or second_value.startswith(first_value.rstrip(separator) + separator)
    )


def default_claude_binary() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_app_data / "Programs" / "CLIProxyAPI" / "cli-proxy-api.exe"


def default_claude_auth() -> Path:
    return Path.home() / ".cli-proxy-api"


def assert_runtime_isolation(
    *,
    paths: RuntimePaths,
    helper_binary: Path,
    helper_port: int,
    claude_binary: Path | None = None,
    claude_auth: Path | None = None,
    claude_port: int = CLAUDE_PROXY_PORT,
) -> None:
    claude_binary = claude_binary or default_claude_binary()
    claude_auth = claude_auth or default_claude_auth()

    if _overlaps(paths.base, claude_binary) or _normalized(helper_binary) == _normalized(
        claude_binary
    ):
        raise IsolationError("Helper runtime overlaps the Claude CLIProxyAPI binary.")
    if _overlaps(paths.base, claude_auth) or _overlaps(paths.auth, claude_auth):
        raise IsolationError("Helper auth directory overlaps the Claude CLIProxyAPI auth directory.")
    if helper_port == claude_port:
        raise IsolationError("Helper proxy port overlaps the Claude CLIProxyAPI port.")


def find_free_loopback_port(forbidden_ports: set[int] | None = None) -> int:
    forbidden = set(forbidden_ports or ())
    forbidden.add(CLAUDE_PROXY_PORT)
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            selected = int(listener.getsockname()[1])
        if selected not in forbidden:
            return selected


def _port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.2)
        return client.connect_ex(("127.0.0.1", port)) == 0


def detect_claude_proxy() -> dict[str, Any]:
    binary = default_claude_binary()
    return {
        "detected": _port_is_open(CLAUDE_PROXY_PORT),
        "port": CLAUDE_PROXY_PORT,
        "pid": None,
        "binary_path": str(binary),
        "binary_exists": binary.is_file(),
        "ownership": "external_claude_proxy",
    }


def _read_active_release(paths: RuntimePaths) -> tuple[dict[str, Any] | None, list[str]]:
    if not paths.current.is_file():
        return None, []
    try:
        payload = json.loads(paths.current.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"current_release_unreadable: {exc}"]

    binary_value = payload.get("binary_path")
    if not isinstance(binary_value, str):
        return None, ["current_release_missing_binary_path"]
    binary = Path(binary_value)
    if not _overlaps(binary, paths.releases):
        return None, ["current_release_outside_helper_root"]
    return {
        "version": payload.get("version"),
        "binary_path": str(binary),
        "binary_exists": binary.is_file(),
        "manifest_path": payload.get("manifest_path"),
    }, []


def collect_status(
    paths: RuntimePaths | None = None,
    *,
    claude_detector: Callable[[], dict[str, Any]] = detect_claude_proxy,
) -> dict[str, Any]:
    paths = paths or RuntimePaths.default()
    active_release, warnings = _read_active_release(paths)
    auth_file_count = 0
    if paths.auth.is_dir():
        auth_file_count = sum(1 for path in paths.auth.iterdir() if path.is_file())

    return {
        "ok": not warnings,
        "operation": "status",
        "runtime_root": str(paths.base),
        "active_release": active_release,
        "auth": {
            "configured": auth_file_count > 0,
            "file_count": auth_file_count,
        },
        "claude_proxy": claude_detector(),
        "claude_proxy_untouched": True,
        "warnings": warnings,
        "errors": [],
    }


def parse_github_release(payload: dict[str, Any]) -> ReleaseInfo:
    tag = str(payload.get("tag_name") or "").strip()
    version = tag.removeprefix("v")
    if not version or payload.get("prerelease"):
        raise UpdateError("Release is missing a stable version tag.")

    expected_pattern = re.compile(
        rf"^CLIProxyAPI_{re.escape(version)}_windows_amd64\.zip$",
        re.IGNORECASE,
    )
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("Release does not contain an asset list.")

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if not expected_pattern.fullmatch(name):
            continue
        digest = str(asset.get("digest") or "")
        if not digest.casefold().startswith("sha256:"):
            raise UpdateError("Windows AMD64 release asset is missing a SHA-256 digest.")
        sha256 = digest.split(":", 1)[1].casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise UpdateError("Windows AMD64 release asset has an invalid SHA-256 digest.")
        url = str(asset.get("browser_download_url") or "")
        if not url.startswith("https://github.com/"):
            raise UpdateError("Windows AMD64 release asset has an unexpected download URL.")
        return ReleaseInfo(
            version=version,
            tag=tag,
            published_at=str(payload.get("published_at") or ""),
            asset_name=name,
            asset_url=url,
            asset_size=int(asset.get("size") or 0),
            sha256=sha256,
        )
    raise UpdateError(f"Release {tag} does not include a Windows AMD64 ZIP asset.")


def fetch_release(version: str | None = None) -> ReleaseInfo:
    if version:
        normalized = version.removeprefix("v")
        endpoint = f"{RELEASE_API_ROOT}/tags/v{normalized}"
    else:
        endpoint = f"{RELEASE_API_ROOT}/latest"
    http_request = request.Request(
        endpoint,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "agent-toolbelt-antigravity/0.1.0",
        },
    )
    try:
        with request.urlopen(http_request) as response:
            payload = json.load(response)
    except (OSError, ValueError) as exc:
        raise UpdateError(f"Failed to read CLIProxyAPI release metadata: {exc}") from exc
    if not isinstance(payload, dict):
        raise UpdateError("CLIProxyAPI release metadata was not a JSON object.")
    return parse_github_release(payload)


def check_update(paths: RuntimePaths, release: ReleaseInfo) -> dict[str, Any]:
    active, warnings = _read_active_release(paths)
    active_version = active.get("version") if active else None
    return {
        "ok": not warnings,
        "operation": "update.check",
        "active_version": active_version,
        "latest_version": release.version,
        "update_available": active_version != release.version,
        "asset_name": release.asset_name,
        "asset_sha256": release.sha256,
        "claude_proxy_untouched": True,
        "warnings": warnings,
        "errors": [],
    }


def _download_file(url: str, destination: Path) -> None:
    http_request = request.Request(
        url,
        headers={"User-Agent": "agent-toolbelt-antigravity/0.1.0"},
    )
    try:
        with request.urlopen(http_request) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    except OSError as exc:
        raise UpdateError(f"Failed to download CLIProxyAPI release: {exc}") from exc


def _validate_archive_members(bundle: zipfile.ZipFile) -> None:
    for member in bundle.infolist():
        member_path = Path(member.filename.replace("\\", "/"))
        if member_path.is_absolute() or ".." in member_path.parts:
            raise UpdateError(f"Release contains unsafe archive path: {member.filename}")


def _probe_binary_version(binary: Path) -> str:
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [str(binary), "-help"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=creation_flags,
        )
    except OSError as exc:
        raise UpdateError(f"Failed to execute downloaded CLIProxyAPI binary: {exc}") from exc
    combined = f"{completed.stdout}\n{completed.stderr}"
    match = re.search(r"CLIProxyAPI Version:\s*([^,\s]+)", combined)
    if not match:
        raise UpdateError("Downloaded CLIProxyAPI binary did not report a version.")
    return match.group(1).removeprefix("v")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _current_version(paths: RuntimePaths) -> str | None:
    active, _ = _read_active_release(paths)
    if not active:
        return None
    value = active.get("version")
    return str(value) if value else None


def _prune_releases(paths: RuntimePaths, retained_versions: set[str]) -> None:
    if not paths.releases.is_dir():
        return
    for candidate in paths.releases.iterdir():
        if not candidate.is_dir() or candidate.name in retained_versions:
            continue
        if not _overlaps(candidate, paths.releases):
            raise UpdateError(f"Refusing to prune release outside helper root: {candidate}")
        shutil.rmtree(candidate)


def install_release(
    paths: RuntimePaths,
    release: ReleaseInfo,
    *,
    downloader: Callable[[str, Path], Any] = _download_file,
    version_probe: Callable[[Path], str] = _probe_binary_version,
) -> dict[str, Any]:
    previous_version = _current_version(paths)
    paths.releases.mkdir(parents=True, exist_ok=True)
    paths.state.mkdir(parents=True, exist_ok=True)
    staging_root = paths.state / "staging" / uuid.uuid4().hex
    staging_root.mkdir(parents=True)
    archive = staging_root / release.asset_name
    extracted = staging_root / "extracted"

    try:
        downloader(release.asset_url, archive)
        if not archive.is_file():
            raise UpdateError("Release downloader did not create the expected archive.")
        if release.asset_size and archive.stat().st_size != release.asset_size:
            raise UpdateError("Release asset size does not match GitHub metadata.")
        archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
        if archive_sha256.casefold() != release.sha256.casefold():
            raise UpdateError("Release asset digest does not match GitHub metadata.")

        try:
            with zipfile.ZipFile(archive) as bundle:
                _validate_archive_members(bundle)
                bundle.extractall(extracted)
        except zipfile.BadZipFile as exc:
            raise UpdateError(f"Release asset is not a valid ZIP archive: {exc}") from exc

        binaries = list(extracted.rglob("cli-proxy-api.exe"))
        if len(binaries) != 1:
            raise UpdateError("Release must contain exactly one cli-proxy-api.exe binary.")
        reported_version = version_probe(binaries[0]).removeprefix("v")
        if reported_version != release.version:
            raise UpdateError(
                "Downloaded CLIProxyAPI reported version "
                f"{reported_version}, expected {release.version}."
            )

        release_root = paths.releases / release.version
        release_root.mkdir(parents=True, exist_ok=True)
        binary = release_root / "cli-proxy-api.exe"
        shutil.copy2(binaries[0], binary)
        manifest_path = release_root / "release.json"
        manifest = {
            "version": release.version,
            "tag": release.tag,
            "published_at": release.published_at,
            "asset_name": release.asset_name,
            "asset_url": release.asset_url,
            "asset_size": release.asset_size,
            "archive_sha256": archive_sha256,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "binary_path": str(binary),
        }
        _write_json_atomic(manifest_path, manifest)
        current = {
            "version": release.version,
            "binary_path": str(binary),
            "manifest_path": str(manifest_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json_atomic(paths.current, current)

        retained = {release.version}
        if previous_version:
            retained.add(previous_version)
        _prune_releases(paths, retained)
        return {
            "ok": True,
            "operation": "update",
            "version": release.version,
            "binary_path": str(binary),
            "manifest_path": str(manifest_path),
            "archive_sha256": archive_sha256,
            "previous_version": previous_version,
            "claude_proxy_untouched": True,
            "warnings": [
                "CLIProxyAPI release assets are not Authenticode-signed; "
                "the GitHub-provided SHA-256 digest was verified."
            ],
            "errors": [],
        }
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def run_update(
    paths: RuntimePaths | None = None,
    *,
    check_only: bool = False,
    version: str | None = None,
) -> dict[str, Any]:
    paths = paths or RuntimePaths.default()
    try:
        release = fetch_release(version)
        if check_only:
            return check_update(paths, release)
        return install_release(paths, release)
    except UpdateError as exc:
        return {
            "ok": False,
            "operation": "update.check" if check_only else "update",
            "failure_kind": "update_failed",
            "claude_proxy_untouched": True,
            "warnings": [],
            "errors": [str(exc)],
        }
