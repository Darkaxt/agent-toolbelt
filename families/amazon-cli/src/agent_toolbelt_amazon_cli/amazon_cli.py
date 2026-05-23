import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agent_toolbelt_core.common import merge_messages, run_process, windows_local_tools_dir


CLIENT_HOME_ENV = "AMAZON_INTENT_CLI_HOME"
CLIENT_FOLDER_NAME = "amazon-intent-cli"
CLIENT_ENTRYPOINT = "amazon-cli"
DEFAULT_TIMEOUT_SEC = 600


def package_root() -> Path:
    return Path(__file__).resolve().parent


def bundled_client_home() -> Path:
    return package_root() / "assets" / "amazon-intent-cli"


def runtime_venv_dir() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "agent-toolbelt" / "amazon-cli" / "uv-env"
    cache_home = os.getenv("XDG_CACHE_HOME")
    root = Path(cache_home).expanduser() if cache_home else Path.home() / ".cache"
    return root / "agent-toolbelt" / "amazon-cli" / "uv-env"


def runtime_work_dir() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "agent-toolbelt" / "amazon-cli" / "uv-work"
    cache_home = os.getenv("XDG_CACHE_HOME")
    root = Path(cache_home).expanduser() if cache_home else Path.home() / ".cache"
    return root / "agent-toolbelt" / "amazon-cli" / "uv-work"


def make_result(
    *,
    ok: bool,
    operation: str,
    result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    stderr: str = "",
    exit_code: int = 0,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "operation": operation,
        "result": result or {},
        "warnings": warnings or [],
        "stderr": stderr,
        "exit_code": exit_code,
    }


def resolve_client_home(explicit_home: str | None = None) -> Path | None:
    if explicit_home:
        candidate = Path(explicit_home).expanduser().resolve()
        if candidate.is_dir():
            return candidate

    env_value = os.getenv(CLIENT_HOME_ENV)
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        if candidate.is_dir():
            return candidate

    bundled_home = bundled_client_home().resolve()
    if (bundled_home / "pyproject.toml").is_file():
        return bundled_home

    tools_dir = windows_local_tools_dir()
    if tools_dir is None:
        return None

    candidate = (tools_dir / CLIENT_FOLDER_NAME).resolve()
    if candidate.is_dir():
        return candidate
    return None


def resolve_uv_executable() -> str | None:
    return shutil.which("uv.exe") or shutil.which("uv")


def build_client_command(
    *,
    client_home: Path,
    operation_args: list[str],
    uv_executable: str,
) -> list[str]:
    return [
        uv_executable,
        "run",
        "--quiet",
        "--with-editable",
        str(client_home),
        CLIENT_ENTRYPOINT,
        *operation_args,
    ]


def build_client_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT_ENVIRONMENT"] = str(runtime_venv_dir())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def parse_payload(stdout: str) -> dict[str, Any] | None:
    stripped = stdout.strip()
    if not stripped:
        return None
    parsed = json.loads(stripped)
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def _unique_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        unique.append(warning)
    return unique


def _offer_key(offer: Any) -> tuple[Any, ...] | None:
    if not isinstance(offer, dict):
        return None
    return (
        offer.get("marketplace"),
        offer.get("total_price"),
        offer.get("effective_price"),
        offer.get("price"),
        offer.get("shipping_price"),
        offer.get("currency"),
    )


def _collect_offer_warnings(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    trusted_offer = payload.get("trusted_best_offer")
    raw_offer = payload.get("raw_best_offer")
    current_offer = payload.get("current_offer")
    offers = payload.get("offers")
    has_offer_evidence = bool(raw_offer or current_offer or offers)

    if has_offer_evidence and trusted_offer is None:
        warnings.append("trusted_best_offer is missing; verify address_consistency before recommending a cheapest offer.")

    trusted_key = _offer_key(trusted_offer)
    raw_key = _offer_key(raw_offer)
    current_key = _offer_key(current_offer)
    if trusted_key is not None and raw_key is not None and trusted_key != raw_key:
        warnings.append("raw_best_offer differs from trusted_best_offer; raw cheapest may be address-mismatched or non-deliverable.")
    if trusted_key is not None and current_key is not None and trusted_key != current_key:
        warnings.append("trusted_best_offer differs from current_offer; verify marketplace before recommending.")

    address_consistency = payload.get("address_consistency")
    if isinstance(address_consistency, dict):
        status = str(address_consistency.get("status") or "").strip().lower()
        if status and status not in {"match", "consistent"}:
            warnings.append(
                f"address_consistency status is {status}; cross-market prices may not share the same destination."
            )
    return warnings


def _collect_search_warnings(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    pagination = payload.get("pagination")
    if isinstance(pagination, dict) and pagination.get("partial"):
        reason = pagination.get("stopped_reason") or "unknown"
        warnings.append(f"Search pagination is partial: {reason}")

    results = payload.get("results")
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, dict):
                continue
            model_match = str(result.get("model_match") or "").strip().lower()
            if model_match not in {"variant", "different"}:
                continue
            asin = result.get("asin") or "unknown ASIN"
            disclosure = result.get("model_disclosure") or "inspect title/model details before treating this as an exact match."
            warnings.append(f"Search result {asin} has model_match={model_match}: {disclosure}")
    return warnings


def _collect_reviews_warnings(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if payload.get("deep_reviews_available") is False or payload.get("reviews_source") == "product_detail_fallback":
        session_status = payload.get("session_status") or "unknown"
        warnings.append(
            f"Deep review collection is unavailable; reviews are from fallback evidence (session_status={session_status})."
        )

    pagination = payload.get("pagination")
    if isinstance(pagination, dict) and pagination.get("partial"):
        reason = pagination.get("stopped_reason") or "unknown"
        warnings.append(f"Review pagination is partial: {reason}")
    return warnings


def collect_payload_warnings(payload: dict[str, Any] | None, operation: str) -> list[str]:
    if payload is None:
        return []

    warnings: list[str] = []
    payload_warnings = payload.get("warnings")
    if isinstance(payload_warnings, list):
        warnings.extend(warning for warning in payload_warnings if isinstance(warning, str))

    command = str(payload.get("command") or operation).strip()
    if command == "offers":
        warnings.extend(_collect_offer_warnings(payload))
    elif command == "search":
        warnings.extend(_collect_search_warnings(payload))
    elif command == "reviews":
        warnings.extend(_collect_reviews_warnings(payload))

    return _unique_warnings(warnings)


def normalize_payload(
    *,
    payload: dict[str, Any] | None,
    raw_stdout: str,
    operation: str,
    stderr: str,
    exit_code: int,
) -> dict[str, Any]:
    if payload is None:
        result = {"raw_stdout": raw_stdout.strip()} if raw_stdout.strip() else {}
    else:
        result = payload

    return make_result(
        ok=exit_code == 0,
        operation=operation,
        result=result,
        warnings=collect_payload_warnings(payload, operation),
        stderr=stderr,
        exit_code=exit_code,
    )


def invoke_client(
    *,
    operation_args: list[str],
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    client_home: str | None = None,
) -> dict[str, Any]:
    operation = operation_args[0] if operation_args else "unknown"
    resolved_home = resolve_client_home(explicit_home=client_home)
    if resolved_home is None:
        return make_result(
            ok=False,
            operation=operation,
            stderr=(
                "Amazon CLI client not available. "
                f"Restore the bundled client, set the {CLIENT_HOME_ENV} environment override, "
                "or provide the client project root with --client-home. The legacy "
                "%LOCALAPPDATA%\\Tools project root remains a compatibility fallback."
            ),
            exit_code=127,
        )

    uv_executable = resolve_uv_executable()
    if uv_executable is None:
        return make_result(
            ok=False,
            operation=operation,
            stderr="uv is not available on PATH.",
            exit_code=127,
        )

    command = build_client_command(
        client_home=resolved_home,
        operation_args=operation_args,
        uv_executable=uv_executable,
    )
    work_dir = runtime_work_dir()
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        completed = run_process(command, cwd=str(work_dir), timeout_sec=timeout_sec, env=build_client_env())
    except FileNotFoundError as exc:
        return make_result(
            ok=False,
            operation=operation,
            stderr=str(exc),
            exit_code=127,
        )
    except subprocess.TimeoutExpired as exc:
        return make_result(
            ok=False,
            operation=operation,
            stderr=merge_messages(exc.stderr or "", "Amazon CLI client timed out."),
            exit_code=124,
        )

    try:
        payload = parse_payload(completed.stdout)
    except json.JSONDecodeError:
        payload = None

    return normalize_payload(
        payload=payload,
        raw_stdout=completed.stdout,
        operation=operation,
        stderr=merge_messages(completed.stderr),
        exit_code=completed.returncode,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge into the local Amazon CLI client."
    )
    parser.add_argument("--client-home", help="Path to the standalone amazon-intent-cli project.")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument(
        "operation_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed through to amazon-cli. Use `--` before amazon-cli flags.",
    )
    return parser


def build_operation_args(args: argparse.Namespace) -> list[str]:
    operation_args = list(args.operation_args)
    if operation_args and operation_args[0] == "--":
        operation_args = operation_args[1:]
    return operation_args
