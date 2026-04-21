import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent_toolbelt_core.common import core_asset_path


PACKAGED_UVRUN_PS1_PATH = core_asset_path("uvrun.ps1")
PACKAGED_UVRUN_BAT_PATH = core_asset_path("uvrun.bat")
PACKAGED_UVRUN_HELPER_PATH = core_asset_path("uvrun_helper.py")

PROJECT_MARKER_NAMES = {
    ".git",
    "Pipfile",
    "pixi.toml",
    "poetry.lock",
    "pyproject.toml",
    "uv.lock",
}
PROJECT_MARKER_GLOBS = ("requirements*.txt", "requirements*.in")
DEFAULT_TIMEOUT_SEC = 180


def make_result(
    *,
    ok: bool,
    eligible: bool,
    backend: str,
    script: str,
    reason: str,
    command: list[str],
    cwd: str,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "eligible": eligible,
        "backend": backend,
        "script": script,
        "reason": reason,
        "command": command,
        "cwd": cwd,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }


def resolve_powershell_executable() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell")


def resolve_uv_executable() -> str | None:
    return shutil.which("uv.exe") or shutil.which("uv")


def resolve_uvrun_executable() -> Path | None:
    powershell = resolve_powershell_executable()
    if powershell and PACKAGED_UVRUN_PS1_PATH.exists():
        return PACKAGED_UVRUN_PS1_PATH
    if PACKAGED_UVRUN_BAT_PATH.exists():
        return PACKAGED_UVRUN_BAT_PATH
    if powershell:
        discovered_ps1 = shutil.which("uvrun.ps1")
        if discovered_ps1:
            return Path(discovered_ps1)
    discovered_bat = shutil.which("uvrun.bat") or shutil.which("uvrun")
    return Path(discovered_bat) if discovered_bat else None


def resolve_script_path(script: str) -> Path:
    return Path(script).expanduser().resolve()


def find_project_marker(script_path: Path) -> Path | None:
    current = script_path.parent.resolve()
    while True:
        for marker_name in PROJECT_MARKER_NAMES:
            candidate = current / marker_name
            if candidate.exists():
                return candidate
        for pattern in PROJECT_MARKER_GLOBS:
            for candidate in sorted(current.glob(pattern)):
                return candidate
        if current.parent == current:
            return None
        current = current.parent


def build_python_command(script_path: Path, script_args: list[str]) -> list[str]:
    return [sys.executable, str(script_path), *script_args]


def is_powershell_launcher(uvrun_path: Path) -> bool:
    return uvrun_path.suffix.lower() == ".ps1"


def build_uvrun_command(uvrun_path: Path, script_path: Path, script_args: list[str]) -> list[str]:
    if is_powershell_launcher(uvrun_path):
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(uvrun_path),
            str(script_path),
            *script_args,
        ]
    return ["cmd.exe", "/c", str(uvrun_path), str(script_path), *script_args]


def plan_execution(
    *,
    script: str,
    script_args: list[str] | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    script_path = resolve_script_path(script)
    if not script_path.exists():
        raise ValueError(f"Script not found: {script_path}")

    args = list(script_args or [])
    resolved_cwd = str(Path(cwd).resolve()) if cwd else str(script_path.parent)
    marker = find_project_marker(script_path)
    if marker is not None:
        return make_result(
            ok=True,
            eligible=False,
            backend="direct-python",
            script=str(script_path),
            reason=f"Script is project-managed because nearby marker {marker.name} was found at {marker.parent}.",
            command=build_python_command(script_path, args),
            cwd=resolved_cwd,
        )

    uvrun_path = resolve_uvrun_executable()
    uv_path = resolve_uv_executable()
    if uvrun_path and uv_path:
        backend = "uvrun" if is_powershell_launcher(uvrun_path) else "uvrun-batch-compat"
        reason = (
            "Eligible standalone script; using uvrun.ps1."
            if backend == "uvrun"
            else "Eligible standalone script; using deprecated uvrun.bat compatibility shim because uvrun.ps1 was unavailable."
        )
        return make_result(
            ok=True,
            eligible=True,
            backend=backend,
            script=str(script_path),
            reason=reason,
            command=build_uvrun_command(uvrun_path, script_path, args),
            cwd=resolved_cwd,
        )

    missing_parts = []
    if not uvrun_path:
        missing_parts.append("uvrun.ps1/uvrun.bat")
    if not uv_path:
        missing_parts.append("uv")
    missing = " and ".join(missing_parts) or "uv path"
    return make_result(
        ok=True,
        eligible=True,
        backend="direct-python",
        script=str(script_path),
        reason=f"Eligible standalone script, but the uv path was unavailable ({missing}); fell back to direct Python.",
        command=build_python_command(script_path, args),
        cwd=resolved_cwd,
    )


def invoke_script(
    *,
    script: str,
    script_args: list[str] | None = None,
    cwd: str | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    check_only: bool = False,
) -> dict[str, Any]:
    plan = plan_execution(script=script, script_args=script_args, cwd=cwd)
    if check_only:
        return plan

    try:
        completed = subprocess.run(
            plan["command"],
            cwd=plan["cwd"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except FileNotFoundError as exc:
        return {**plan, "ok": False, "stderr": str(exc), "exit_code": 127}
    except subprocess.TimeoutExpired as exc:
        return {
            **plan,
            "ok": False,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "exit_code": 124,
        }

    return {
        **plan,
        "ok": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    tokens = list(sys.argv[1:] if argv is None else argv)
    if "--" in tokens:
        separator_index = tokens.index("--")
        parser_tokens = tokens[:separator_index]
        script_args = tokens[separator_index + 1 :]
    else:
        parser_tokens = tokens
        script_args = []

    parser = argparse.ArgumentParser(
        description="Prefer uvrun.ps1 for standalone Python scripts and fall back cleanly when needed."
    )
    parser.add_argument("script", help="Standalone Python script to inspect or run.")
    parser.add_argument("--cwd", help="Optional working directory override.")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args, remaining = parser.parse_known_args(parser_tokens)
    args.script_args = [*remaining, *script_args]
    return args
