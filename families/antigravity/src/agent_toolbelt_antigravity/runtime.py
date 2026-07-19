from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


TOOL_DIR_NAME = "antigravity-review"
CLAUDE_PROXY_PORT = 8317


class IsolationError(ValueError):
    """Raised when helper-owned state overlaps the external Claude proxy."""


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
