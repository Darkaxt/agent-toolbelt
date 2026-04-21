import json
import os
import shutil
import subprocess
import ipaddress
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def core_package_root() -> Path:
    return Path(__file__).resolve().parent


def core_asset_path(*parts: str) -> Path:
    return core_package_root().joinpath("assets", *parts)


def normalize_host(hostname: str | None) -> str:
    if not hostname:
        raise ValueError("URL must include a hostname.")
    return hostname.rstrip(".").lower()


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only public http(s) URLs are allowed.")

    host = normalize_host(parsed.hostname)
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost"):
        raise ValueError("Localhost URLs are not allowed.")
    if host.endswith(".local"):
        raise ValueError("`.local` hosts are not allowed.")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return url

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise ValueError("Private-network IP targets are not allowed.")

    return url


def windows_local_tools_dir() -> Path | None:
    local_appdata = os.getenv("LOCALAPPDATA")
    if not local_appdata:
        return None
    return Path(local_appdata) / "Tools"


def resolve_windows_tool(
    *,
    explicit_path: str | None = None,
    env_var: str | None = None,
    path_names: tuple[str, ...] = (),
    local_tool_name: str | None = None,
) -> str | None:
    """Resolve a Windows tool with PATH as the primary machine-wide mechanism.

    The `%LOCALAPPDATA%\\Tools` lookup is kept as a compatibility fallback for
    older local installs; public docs should not present it as a required path.
    """
    if explicit_path:
        candidate = Path(explicit_path).expanduser().resolve()
        if candidate.exists():
            return str(candidate)

    if env_var:
        env_path = os.getenv(env_var)
        if env_path:
            candidate = Path(env_path).expanduser().resolve()
            if candidate.exists():
                return str(candidate)

    for name in path_names:
        discovered = shutil.which(name)
        if discovered:
            return discovered

    if local_tool_name:
        tools_dir = windows_local_tools_dir()
        if tools_dir is not None:
            candidate = (tools_dir / local_tool_name).resolve()
            if candidate.exists():
                return str(candidate)

    return None


def run_process(
    command: list[str],
    *,
    cwd: str | None = None,
    timeout_sec: int,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        env=env,
        check=False,
    )


def extract_json_object(raw_output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw_output):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw_output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Failed to parse Gemini CLI JSON output.")


def extract_payload(stdout: str, stderr: str) -> dict[str, Any]:
    for stream in (stdout, stderr):
        if not stream:
            continue
        try:
            return extract_json_object(stream)
        except ValueError:
            continue
    raise ValueError("Failed to parse Gemini CLI JSON output.")


def merge_messages(*messages: str) -> str:
    parts: list[str] = []
    for message in messages:
        cleaned = message.strip()
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return " ".join(parts)
