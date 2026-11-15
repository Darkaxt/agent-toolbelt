"""ADB endpoint binding and command execution for adb-saf.

Inside an LLM Coordinator device reservation the gate sets
COORDINATOR_ADB_TRANSPORT_ID; every command is then pinned with `adb -t` to
that exact transport, and the serial the gate appended must match it. Outside
a reservation the helper binds `-s <serial>` and refuses to guess between
several ready endpoints.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Sequence


class SafError(RuntimeError):
    def __init__(self, kind: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


@dataclass
class Completed:
    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")

    @property
    def error_text(self) -> str:
        return self.stderr.decode("utf-8", errors="replace")


# runner(argv, stdin_bytes, stdout_file) -> Completed. When stdout_file is given
# the runner streams stdout into it and Completed.stdout is empty.
Runner = Callable[[Sequence[str], bytes | None, BinaryIO | None], Completed]

COMMAND_TIMEOUT_SECONDS = 1800


def run_process(argv: Sequence[str], stdin: bytes | None = None, stdout_file: BinaryIO | None = None) -> Completed:
    try:
        completed = subprocess.run(
            list(argv),
            input=stdin,
            stdout=stdout_file if stdout_file is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SafError("adb_timeout", f"ADB command exceeded {COMMAND_TIMEOUT_SECONDS}s: {argv[1:4]}") from exc
    return Completed(completed.returncode, completed.stdout or b"", completed.stderr or b"")


def resolve_adb(explicit: str | None = None) -> str:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    for variable in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        value = os.getenv(variable)
        if value:
            candidates.append(Path(value) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb"))
    local = os.getenv("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    found = shutil.which("adb")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise SafError("adb_unavailable", "ADB executable not found; set ANDROID_SDK_ROOT or pass --adb.")


def parse_devices(output: str) -> list[dict[str, str]]:
    endpoints = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        endpoint = {"serial": parts[0], "state": parts[1]}
        for token in parts[2:]:
            if ":" in token:
                key, value = token.split(":", 1)
                endpoint[key] = value
        endpoints.append(endpoint)
    return endpoints


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


class Device:
    """One bound ADB endpoint. All device commands go through `shell` or `adb`."""

    def __init__(self, adb: str, selector: list[str], serial: str, runner: Runner = run_process):
        self.adb_path = adb
        self.selector = selector
        self.serial = serial
        self.runner = runner
        self._identity: dict[str, str] | None = None

    @classmethod
    def bind(cls, *, serial: str | None, adb: str | None = None, runner: Runner = run_process) -> "Device":
        adb_path = resolve_adb(adb)
        transport = os.getenv("COORDINATOR_ADB_TRANSPORT_ID", "").strip()
        if transport:
            device = cls(adb_path, ["-t", transport], serial or "", runner)
            actual = device.adb("get-serialno").text.strip()
            expected = serial or os.getenv("COORDINATOR_ADB_SERIAL", "").strip()
            if not actual or (expected and actual != expected):
                raise SafError("device_binding_mismatch", "Reserved transport does not match the reserved serial.",
                               details={"transport_id": transport, "expected": expected, "actual": actual})
            device.serial = actual
            return device
        reserved = os.getenv("COORDINATOR_ADB_SERIAL", "").strip()
        if reserved:
            # Emulator lease: the gate names the serial; no endpoint enumeration.
            if serial and serial != reserved:
                raise SafError("device_binding_mismatch", "Requested serial differs from the reserved serial.",
                               details={"expected": reserved, "actual": serial})
            device = cls(adb_path, ["-s", reserved], reserved, runner)
            if device.adb("get-state").text.strip() != "device":
                raise SafError("device_not_ready", f"Reserved endpoint {reserved!r} is not ready.")
            return device
        listing = parse_devices(runner([adb_path, "devices", "-l"], None, None).stdout.decode("utf-8", "replace"))
        ready = [item for item in listing if item["state"] == "device"]
        if serial:
            match = [item for item in listing if item["serial"] == serial]
            if not match:
                raise SafError("device_unavailable", f"ADB endpoint {serial!r} is not connected.",
                               details={"candidates": listing})
            if match[0]["state"] != "device":
                raise SafError("device_not_ready", f"ADB endpoint {serial!r} is {match[0]['state']!r}.")
            return cls(adb_path, ["-s", serial], serial, runner)
        if not ready:
            raise SafError("device_unavailable", "No ready ADB endpoint is connected.", details={"candidates": listing})
        if len(ready) > 1:
            raise SafError("ambiguous_device", "Several ready ADB endpoints; pass --serial.", details={"candidates": ready})
        return cls(adb_path, ["-s", ready[0]["serial"]], ready[0]["serial"], runner)

    def adb(self, *arguments: str, stdin: bytes | None = None, stdout_file: BinaryIO | None = None) -> Completed:
        return self.runner([self.adb_path, *self.selector, *arguments], stdin, stdout_file)

    def shell(self, command: str, *, stdout_file: BinaryIO | None = None) -> Completed:
        # `adb shell` keeps stderr separate and preserves the exit status, but on
        # Windows it writes stdout in text mode (LF becomes CRLF). Use it for text
        # only; binary content goes through `exec_out`.
        return self.adb("shell", command, stdout_file=stdout_file)

    def exec_out(self, command: str, *, stdout_file: BinaryIO) -> Completed:
        # Byte-exact stdout, but no exit status and no separate stderr: callers
        # must verify the bytes independently (hash and size).
        return self.adb("exec-out", command, stdout_file=stdout_file)

    def identity(self) -> dict[str, str]:
        if self._identity is None:
            keys = ["ro.serialno", "ro.product.model", "ro.product.device", "ro.build.fingerprint", "ro.build.version.sdk"]
            out = self.shell(" ; ".join(f"getprop {key}" for key in keys))
            values = out.text.splitlines()
            if out.returncode != 0 or len(values) < len(keys):
                raise SafError("device_unavailable", "Could not read device identity.", details={"stderr": out.error_text})
            identity = {key: values[index].strip() for index, key in enumerate(keys)}
            identity["adb_serial"] = self.serial
            identity["identity_hash"] = hashlib.sha256(
                json.dumps({k: identity[k] for k in ("ro.serialno", "ro.product.model", "ro.build.fingerprint")},
                           sort_keys=True).encode()).hexdigest()
            self._identity = identity
        return self._identity
