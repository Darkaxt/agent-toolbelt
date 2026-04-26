import argparse
import json
import os
import shutil
import subprocess
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from agent_toolbelt_core.common import merge_messages, resolve_windows_tool, run_process


DEFAULT_MAX_RESULTS = 50
DEFAULT_TIMEOUT_SEC = 30


def make_result(
    *,
    ok: bool,
    backend: str,
    query: str,
    results: list[str],
    stderr: str = "",
    exit_code: int = 0,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "backend": backend,
        "query": query,
        "results": results,
        "stderr": stderr,
        "exit_code": exit_code,
    }


def add_diagnostics(
    result: dict[str, Any],
    *,
    requested_mode: str,
    root: str | None,
    max_results: int,
    match_path: bool,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    es_path: str | None = None,
) -> dict[str, Any]:
    payload = dict(result)
    payload["diagnostics"] = {
        "requested_mode": requested_mode,
        "selected_backend": payload.get("backend"),
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "searched_root": str(Path(root or os.getcwd()).resolve()) if requested_mode != "path-resolve" else None,
        "es_available": es_path is not None if requested_mode == "global" else None,
        "es_path": es_path,
        "match_path": match_path,
        "max_results": max_results,
    }
    return payload


def has_glob_pattern(query: str) -> bool:
    return any(char in query for char in "*?[]")


def matches_query(candidate: str, query: str, match_path: bool) -> bool:
    target = candidate if match_path else Path(candidate).name
    target_lower = target.lower()
    query_lower = query.lower()

    if has_glob_pattern(query_lower):
        return fnmatch(target_lower, query_lower)
    return query_lower == target_lower or query_lower in target_lower


def resolve_es_executable(explicit_path: str | None = None) -> str | None:
    return resolve_windows_tool(
        explicit_path=explicit_path,
        env_var="AGENT_TOOLBELT_ES",
        path_names=("es.exe", "es"),
        local_tool_name="es.exe",
    )


def parse_everything_stdout(stdout: str) -> list[str]:
    stripped = stdout.strip()
    if not stripped:
        return []

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    if not isinstance(payload, list):
        return []

    results: list[str] = []
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("filename"), str):
            results.append(item["filename"])
        elif isinstance(item, str):
            results.append(item)
    return results


def search_with_everything(
    *,
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    match_path: bool = False,
    es_path: str | None = None,
) -> dict[str, Any]:
    executable = resolve_es_executable(explicit_path=es_path)
    if executable is None:
        return make_result(
            ok=False,
            backend="everything",
            query=query,
            results=[],
            stderr="Everything CLI not available.",
            exit_code=127,
        )

    command = [executable, "-json", "-n", str(max_results)]
    if match_path:
        command.append("-p")
    command.append(query)

    try:
        completed = run_process(command, timeout_sec=DEFAULT_TIMEOUT_SEC)
    except FileNotFoundError:
        return make_result(
            ok=False,
            backend="everything",
            query=query,
            results=[],
            stderr="Failed to start Everything CLI.",
            exit_code=127,
        )
    except subprocess.TimeoutExpired:
        return make_result(
            ok=False,
            backend="everything",
            query=query,
            results=[],
            stderr="Everything CLI timed out.",
            exit_code=124,
        )

    return make_result(
        ok=completed.returncode == 0,
        backend="everything",
        query=query,
        results=parse_everything_stdout(completed.stdout),
        stderr=completed.stderr.strip(),
        exit_code=completed.returncode,
    )


def search_with_where(*, query: str, max_results: int = DEFAULT_MAX_RESULTS) -> dict[str, Any]:
    try:
        completed = run_process(["where.exe", query], timeout_sec=DEFAULT_TIMEOUT_SEC)
    except FileNotFoundError:
        try:
            completed = run_process(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f"(Get-Command '{query}' -ErrorAction Stop).Source",
                ],
                timeout_sec=DEFAULT_TIMEOUT_SEC,
            )
        except FileNotFoundError:
            return make_result(
                ok=False,
                backend="fallback-where",
                query=query,
                results=[],
                stderr="Neither where.exe nor Get-Command is available.",
                exit_code=127,
            )
        except subprocess.TimeoutExpired:
            return make_result(
                ok=False,
                backend="fallback-where",
                query=query,
                results=[],
                stderr="PATH resolution timed out.",
                exit_code=124,
            )
    except subprocess.TimeoutExpired:
        return make_result(
            ok=False,
            backend="fallback-where",
            query=query,
            results=[],
            stderr="PATH resolution timed out.",
            exit_code=124,
        )

    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return make_result(
        ok=completed.returncode == 0,
        backend="fallback-where",
        query=query,
        results=lines[:max_results],
        stderr=completed.stderr.strip(),
        exit_code=completed.returncode,
    )


def search_with_rg(
    *,
    query: str,
    root: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    match_path: bool = False,
) -> dict[str, Any]:
    rg_executable = shutil.which("rg")
    if rg_executable is None:
        return make_result(
            ok=False,
            backend="fallback-rg",
            query=query,
            results=[],
            stderr="`rg` is not available on PATH.",
            exit_code=127,
        )

    root_path = Path(root).resolve()
    if not root_path.exists():
        return make_result(
            ok=False,
            backend="fallback-rg",
            query=query,
            results=[],
            stderr=f"Search root does not exist: {root_path}",
            exit_code=2,
        )

    try:
        completed = run_process([rg_executable, "--files"], cwd=str(root_path), timeout_sec=DEFAULT_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return make_result(
            ok=False,
            backend="fallback-rg",
            query=query,
            results=[],
            stderr="`rg --files` timed out.",
            exit_code=124,
        )

    all_paths = [
        str((root_path / line.strip()).resolve())
        for line in completed.stdout.splitlines()
        if line.strip()
    ]
    filtered = [path for path in all_paths if matches_query(path, query, match_path)]
    return make_result(
        ok=completed.returncode == 0,
        backend="fallback-rg",
        query=query,
        results=filtered[:max_results],
        stderr=completed.stderr.strip(),
        exit_code=completed.returncode,
    )


def search_with_powershell(
    *,
    query: str,
    root: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    match_path: bool = False,
    stderr_prefix: str = "",
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    if not root_path.exists():
        return make_result(
            ok=False,
            backend="fallback-powershell",
            query=query,
            results=[],
            stderr=merge_messages(stderr_prefix, f"Search root does not exist: {root_path}"),
            exit_code=2,
        )

    escaped_root = str(root_path).replace("'", "''")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        (
            f"$root = '{escaped_root}'; "
            "Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty FullName"
        ),
    ]

    try:
        completed = run_process(command, timeout_sec=max(DEFAULT_TIMEOUT_SEC, 120))
    except FileNotFoundError:
        return make_result(
            ok=False,
            backend="fallback-powershell",
            query=query,
            results=[],
            stderr=merge_messages(stderr_prefix, "PowerShell is not available."),
            exit_code=127,
        )
    except subprocess.TimeoutExpired:
        return make_result(
            ok=False,
            backend="fallback-powershell",
            query=query,
            results=[],
            stderr=merge_messages(stderr_prefix, "Scoped PowerShell search timed out."),
            exit_code=124,
        )

    all_paths = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    filtered = [path for path in all_paths if matches_query(path, query, match_path)]
    return make_result(
        ok=completed.returncode == 0,
        backend="fallback-powershell",
        query=query,
        results=filtered[:max_results],
        stderr=merge_messages(stderr_prefix, completed.stderr),
        exit_code=completed.returncode,
    )


def lookup(
    *,
    query: str,
    mode: str = "global",
    root: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    match_path: bool = False,
    es_path: str | None = None,
) -> dict[str, Any]:
    if mode == "path-resolve":
        return add_diagnostics(
            search_with_where(query=query, max_results=max_results),
            requested_mode=mode,
            root=None,
            max_results=max_results,
            match_path=match_path,
        )

    if mode == "repo-local":
        search_root = root or os.getcwd()
        return add_diagnostics(
            search_with_rg(
                query=query,
                root=search_root,
                max_results=max_results,
                match_path=match_path,
            ),
            requested_mode=mode,
            root=search_root,
            max_results=max_results,
            match_path=match_path,
        )

    if mode == "dir-scope":
        search_root = root or os.getcwd()
        return add_diagnostics(
            search_with_powershell(
                query=query,
                root=search_root,
                max_results=max_results,
                match_path=match_path,
                stderr_prefix="Scoped directory search requested.",
            ),
            requested_mode=mode,
            root=search_root,
            max_results=max_results,
            match_path=match_path,
        )

    if mode != "global":
        raise ValueError(f"Unsupported mode: {mode}")

    search_root = root or os.getcwd()
    resolved_es = resolve_es_executable(explicit_path=es_path)
    if resolved_es is None:
        return add_diagnostics(
            search_with_powershell(
                query=query,
                root=search_root,
                max_results=max_results,
                match_path=match_path,
                stderr_prefix="Everything CLI not available; searched only within the provided root.",
            ),
            requested_mode=mode,
            root=search_root,
            max_results=max_results,
            match_path=match_path,
            fallback_used=True,
            fallback_reason="Everything CLI not available.",
            es_path=None,
        )

    everything_result = search_with_everything(
        query=query,
        max_results=max_results,
        match_path=match_path,
        es_path=resolved_es,
    )
    if everything_result["ok"]:
        return add_diagnostics(
            everything_result,
            requested_mode=mode,
            root=search_root,
            max_results=max_results,
            match_path=match_path,
            es_path=resolved_es,
        )

    return add_diagnostics(
        search_with_powershell(
            query=query,
            root=search_root,
            max_results=max_results,
            match_path=match_path,
            stderr_prefix=merge_messages(
                everything_result["stderr"],
                "Everything CLI failed. Fell back to scoped PowerShell search.",
            ),
        ),
        requested_mode=mode,
        root=search_root,
        max_results=max_results,
        match_path=match_path,
        fallback_used=True,
        fallback_reason=everything_result["stderr"] or "Everything CLI failed.",
        es_path=resolved_es,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find filenames and paths with Everything-first lookup and safe fallbacks."
    )
    parser.add_argument("--query", required=True, help="Filename or path search query.")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument("--match-path", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--mode",
        choices=("global", "repo-local", "path-resolve", "dir-scope"),
        default="global",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--root", help="Optional scoped root.")
    parser.add_argument("--es-path", help=argparse.SUPPRESS)
    return parser
