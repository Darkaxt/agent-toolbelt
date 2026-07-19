from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib import error, request

from . import runtime


WINDOWS_CREATE_NO_WINDOW = 0x08000000


class ProxyError(RuntimeError):
    """A structured failure in the helper-owned proxy lifecycle."""

    def __init__(self, failure_kind: str, message: str) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind


@dataclass(frozen=True)
class PreparedReview:
    packet_path: Path
    packet_sha256: str
    request_payload: dict[str, Any]


@dataclass(frozen=True)
class ProxyService:
    invocation_id: str
    pid: int
    port: int
    api_key: str
    binary: Path
    version: str


def hidden_creation_flags(platform_name: str | None = None) -> int:
    return WINDOWS_CREATE_NO_WINDOW if (platform_name or os.name) == "nt" else 0


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def build_proxy_config(paths: runtime.RuntimePaths, *, port: int, api_key: str) -> str:
    if port == runtime.CLAUDE_PROXY_PORT:
        raise runtime.IsolationError("Helper proxy cannot use the Claude proxy port.")
    auth_dir = paths.auth.as_posix()
    return "\n".join(
        [
            'host: "127.0.0.1"',
            f"port: {port}",
            "tls:",
            "  enable: false",
            "  cert: \"\"",
            "  key: \"\"",
            "remote-management:",
            "  allow-remote: false",
            "  secret-key: \"\"",
            "  disable-control-panel: true",
            "  disable-auto-update-panel: true",
            f"auth-dir: {_yaml_string(auth_dir)}",
            "api-keys:",
            f"  - {_yaml_string(api_key)}",
            "debug: false",
            "pprof:",
            "  enable: false",
            "  addr: \"127.0.0.1:0\"",
            "plugins:",
            "  enabled: false",
            "logging-to-file: false",
            "logs-max-total-size-mb: 0",
            "error-logs-max-files: 0",
            "usage-statistics-enabled: false",
            "request-retry: 0",
            "max-retry-credentials: 1",
            "max-retry-interval: 0",
            "disable-cooling: true",
            "save-cooldown-status: false",
            "transient-error-cooldown-seconds: -1",
            "disable-image-generation: true",
            "quota-exceeded:",
            "  switch-project: false",
            "  switch-preview-model: false",
            "  antigravity-credits: false",
            "routing:",
            '  strategy: "fill-first"',
            "  session-affinity: false",
            "ws-auth: true",
            "nonstream-keepalive-interval: 0",
            "",
        ]
    )


def _active_runtime(paths: runtime.RuntimePaths) -> tuple[Path, str]:
    active, warnings = runtime._read_active_release(paths)
    if warnings:
        raise ProxyError("runtime_unavailable", "; ".join(warnings))
    if not active:
        raise ProxyError(
            "runtime_unavailable",
            "No helper-owned CLIProxyAPI release is active; run update first.",
        )
    binary = Path(str(active["binary_path"]))
    if not binary.is_file():
        raise ProxyError("runtime_unavailable", "The active helper binary is missing.")
    return binary, str(active.get("version") or "unknown")


def _remove_run_directory(run_dir: Path, runs_root: Path) -> None:
    if run_dir.exists():
        shutil.rmtree(run_dir)
    try:
        runs_root.rmdir()
    except OSError:
        pass


def _prepare_run(
    paths: runtime.RuntimePaths,
    *,
    port: int,
    api_key: str,
) -> tuple[str, Path, Path]:
    invocation_id = str(uuid.uuid4())
    runs_root = paths.state / "runs"
    run_dir = runs_root / invocation_id
    run_dir.mkdir(parents=True)
    paths.auth.mkdir(parents=True, exist_ok=True)
    config = run_dir / "config.yaml"
    config.write_text(build_proxy_config(paths, port=port, api_key=api_key), encoding="utf-8")
    return invocation_id, run_dir, config


def run_login(
    paths: runtime.RuntimePaths | None = None,
    *,
    no_browser: bool = False,
    process_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    paths = paths or runtime.RuntimePaths.default()
    run_dir: Path | None = None
    runs_root = paths.state / "runs"
    try:
        binary, version = _active_runtime(paths)
        port = runtime.find_free_loopback_port()
        api_key = secrets.token_urlsafe(32)
        invocation_id, run_dir, config = _prepare_run(paths, port=port, api_key=api_key)
        runtime.assert_runtime_isolation(paths=paths, helper_binary=binary, helper_port=port)
        command = [str(binary), "-antigravity-login", "-config", str(config)]
        if no_browser:
            command.append("-no-browser")

        # OAuth is intentionally foreground and unbounded. The child owns its interactive output.
        completed = process_runner(command, cwd=str(run_dir), check=False)
        ok = completed.returncode == 0
        return {
            "ok": ok,
            "operation": "login",
            "invocation_id": invocation_id,
            "proxy_version": version,
            "auth_configured": _has_helper_auth(paths),
            "failure_kind": None if ok else "login_failed",
            "claude_proxy_untouched": True,
            "warnings": [],
            "errors": [] if ok else [f"Antigravity login exited with code {completed.returncode}."],
        }
    except (OSError, ProxyError, runtime.IsolationError) as exc:
        failure_kind = exc.failure_kind if isinstance(exc, ProxyError) else "login_failed"
        return _failure("login", failure_kind, str(exc))
    finally:
        if run_dir is not None:
            _remove_run_directory(run_dir, runs_root)


@contextmanager
def ephemeral_proxy(
    paths: runtime.RuntimePaths | None = None,
    *,
    process_factory: Callable[..., Any] = subprocess.Popen,
    readiness_probe: Callable[[int], bool] = runtime._port_is_open,
    port_selector: Callable[[set[int]], int] = runtime.find_free_loopback_port,
    api_key_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
) -> Iterator[ProxyService]:
    paths = paths or runtime.RuntimePaths.default()
    binary, version = _active_runtime(paths)
    port = port_selector({runtime.CLAUDE_PROXY_PORT})
    api_key = api_key_factory()
    invocation_id, run_dir, config = _prepare_run(paths, port=port, api_key=api_key)
    runs_root = paths.state / "runs"
    process = None
    try:
        runtime.assert_runtime_isolation(paths=paths, helper_binary=binary, helper_port=port)
        process = process_factory(
            [str(binary), "-config", str(config)],
            cwd=str(run_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=hidden_creation_flags(),
        )
        while not readiness_probe(port):
            return_code = process.poll()
            if return_code is not None:
                raise ProxyError(
                    "proxy_start_failed",
                    f"Helper proxy exited before readiness with code {return_code}.",
                )
            time.sleep(0.1)
        yield ProxyService(
            invocation_id=invocation_id,
            pid=int(process.pid),
            port=port,
            api_key=api_key,
            binary=binary,
            version=version,
        )
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        _remove_run_directory(run_dir, runs_root)


def _has_helper_auth(paths: runtime.RuntimePaths) -> bool:
    return paths.auth.is_dir() and any(path.is_file() for path in paths.auth.iterdir())


def _json_request(
    *,
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "agent-toolbelt-antigravity/0.1.0",
        },
    )
    try:
        with request.urlopen(http_request) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except OSError:
            detail = ""
        raise ProxyError(
            "upstream_request_failed",
            f"Proxy request failed: HTTP {exc.code} {detail}",
        ) from exc
    except (OSError, ValueError) as exc:
        raise ProxyError("proxy_request_failed", f"Proxy request failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ProxyError("invalid_response", "Proxy response was not a JSON object.")
    return result


def prepare_review(*, packet: Path, instruction: str, model: str) -> PreparedReview:
    resolved = packet.expanduser().resolve(strict=False)
    if not resolved.is_file():
        raise ProxyError("packet_unavailable", f"Review packet does not exist: {resolved}")
    if not instruction.strip():
        raise ProxyError("invalid_request", "Review instruction cannot be empty.")
    if not model.strip():
        raise ProxyError("invalid_request", "An exact model identifier is required.")
    raw_packet = resolved.read_bytes()
    try:
        packet_text = raw_packet.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProxyError("packet_invalid", "Review packet must be UTF-8 text.") from exc
    return PreparedReview(
        packet_path=resolved,
        packet_sha256=hashlib.sha256(raw_packet).hexdigest(),
        request_payload={
            "model": model,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": packet_text},
            ],
            "stream": False,
        },
    )


def _response_text(response_payload: dict[str, Any]) -> str | None:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [item.get("text") for item in content if isinstance(item, dict)]
        text_parts = [part for part in parts if isinstance(part, str)]
        return "\n".join(text_parts) if text_parts else None
    return None


def normalize_review_response(
    *,
    requested_model: str,
    response_payload: dict[str, Any],
) -> dict[str, Any]:
    reported = response_payload.get("model")
    reported_model = reported if isinstance(reported, str) and reported else None
    response_text = _response_text(response_payload)
    usage = response_payload.get("usage")
    normalized_usage = usage if isinstance(usage, dict) else {}
    if reported_model is None:
        return _review_failure(
            "model_attribution_missing",
            requested_model,
            None,
            response_text,
            normalized_usage,
            "The review response did not identify the model used.",
        )
    if reported_model != requested_model:
        return _review_failure(
            "model_mismatch",
            requested_model,
            reported_model,
            response_text,
            normalized_usage,
            "The reported model does not exactly match the requested model.",
        )
    if response_text is None:
        return _review_failure(
            "invalid_response",
            requested_model,
            reported_model,
            None,
            normalized_usage,
            "The review response did not contain assistant text.",
            model_verified=True,
        )
    return {
        "ok": True,
        "failure_kind": None,
        "model_requested": requested_model,
        "model_reported": reported_model,
        "model_verified": True,
        "response": response_text,
        "usage": normalized_usage,
        "warnings": [],
        "errors": [],
    }


def _review_failure(
    failure_kind: str,
    requested_model: str,
    reported_model: str | None,
    response_text: str | None,
    usage: dict[str, Any],
    message: str,
    *,
    model_verified: bool = False,
) -> dict[str, Any]:
    return {
        "ok": False,
        "failure_kind": failure_kind,
        "model_requested": requested_model,
        "model_reported": reported_model,
        "model_verified": model_verified,
        "response": response_text,
        "usage": usage,
        "warnings": [],
        "errors": [message],
    }


def run_models(paths: runtime.RuntimePaths | None = None) -> dict[str, Any]:
    paths = paths or runtime.RuntimePaths.default()
    if not _has_helper_auth(paths):
        return _failure(
            "models",
            "auth_unavailable",
            "No helper-owned Antigravity authentication is available; run login first.",
        )
    try:
        with ephemeral_proxy(paths) as service:
            response = _json_request(
                method="GET",
                url=f"http://127.0.0.1:{service.port}/v1/models",
                api_key=service.api_key,
            )
            models = response.get("data")
            if not isinstance(models, list):
                raise ProxyError("invalid_response", "Model catalog did not contain a data list.")
            return {
                "ok": True,
                "operation": "models",
                "invocation_id": service.invocation_id,
                "models": models,
                "model_count": len(models),
                "proxy_version": service.version,
                "proxy_pid": service.pid,
                "proxy_port": service.port,
                "claude_proxy_detected": runtime.detect_claude_proxy()["detected"],
                "claude_proxy_untouched": True,
                "warnings": [],
                "errors": [],
            }
    except (OSError, ProxyError, runtime.IsolationError) as exc:
        failure_kind = exc.failure_kind if isinstance(exc, ProxyError) else "models_failed"
        return _failure("models", failure_kind, str(exc))


def run_review(
    *,
    packet: Path,
    instruction: str,
    model: str,
    paths: runtime.RuntimePaths | None = None,
) -> dict[str, Any]:
    paths = paths or runtime.RuntimePaths.default()
    try:
        prepared = prepare_review(packet=packet, instruction=instruction, model=model)
        if not _has_helper_auth(paths):
            return _failure(
                "review",
                "auth_unavailable",
                "No helper-owned Antigravity authentication is available; run login first.",
                packet_path=str(prepared.packet_path),
                packet_sha256=prepared.packet_sha256,
                model_requested=model,
            )
        with ephemeral_proxy(paths) as service:
            response = _json_request(
                method="POST",
                url=f"http://127.0.0.1:{service.port}/v1/chat/completions",
                api_key=service.api_key,
                payload=prepared.request_payload,
            )
            normalized = normalize_review_response(
                requested_model=model,
                response_payload=response,
            )
            return {
                **normalized,
                "operation": "review",
                "invocation_id": service.invocation_id,
                "packet_path": str(prepared.packet_path),
                "packet_sha256": prepared.packet_sha256,
                "proxy_version": service.version,
                "proxy_pid": service.pid,
                "proxy_port": service.port,
                "claude_proxy_detected": runtime.detect_claude_proxy()["detected"],
                "claude_proxy_untouched": True,
            }
    except (OSError, ProxyError, runtime.IsolationError) as exc:
        failure_kind = exc.failure_kind if isinstance(exc, ProxyError) else "review_failed"
        return _failure("review", failure_kind, str(exc), model_requested=model)


def _failure(operation: str, failure_kind: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "operation": operation,
        "failure_kind": failure_kind,
        **extra,
        "claude_proxy_untouched": True,
        "warnings": [],
        "errors": [message],
    }
