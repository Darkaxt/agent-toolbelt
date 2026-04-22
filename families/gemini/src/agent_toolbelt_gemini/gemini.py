import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent_toolbelt_core.common import (
    core_asset_path,
    extract_payload,
    normalize_host,
    validate_public_url,
)


WORKSPACE_DIR = core_asset_path("gemini-workspace")

DEFAULT_MODEL_LADDER = [
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    None,
]

MODEL_STRATEGY = "highest-with-fallback"

BILLING_ENV_VARS = {
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_APPLICATION_CREDENTIALS",
}

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

REDDIT_HOSTS = {
    "reddit.com",
    "www.reddit.com",
    "old.reddit.com",
    "redd.it",
}

TYPO_FIXES = {
    "reccomend": "recommend",
    "recomend": "recommend",
    "commnity": "community",
    "comparision": "comparison",
    "teh": "the",
}

ENTITY_CONTEXT_HINTS = {
    "going medieval": "Going Medieval (the 2021 PC colony sim game)",
}


def classify_source_type(url: str) -> str:
    parsed = urlparse(url)
    host = normalize_host(parsed.hostname)
    path = parsed.path or "/"

    if host in {"youtu.be", "www.youtu.be"} and path.strip("/"):
        return "youtube"
    if host in YOUTUBE_HOSTS and (
        path == "/watch" or path.startswith("/shorts/") or path.startswith("/embed/")
    ):
        return "youtube"
    if host in {"redd.it"} and path.strip("/"):
        return "reddit"
    if host in REDDIT_HOSTS:
        return "reddit"
    return "web"


def build_url_prompt(url: str, instruction: str, source_type: str) -> str:
    policy = (
        "Use only public web or URL-access capabilities. "
        "Do not use shell commands, local files, or private network access. "
    )
    if source_type in {"youtube", "reddit"}:
        label = "YouTube URL" if source_type == "youtube" else "Reddit URL"
        return (
            f"Inspect the public {label} {url}. "
            "Treat it as a trusted Gemini input unless access fails. "
            f"{policy}"
            "Answer the user's request directly, confidently, and without generic disclaimers. "
            "If the page, thread, video, or transcript is inaccessible, say that explicitly. "
            f"User request: {instruction}"
        )

    return (
        f"Inspect the public URL {url}. "
        f"{policy}"
        "Use the page content as evidence for the answer. "
        "If access fails, say that explicitly. "
        f"User request: {instruction}"
    )


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def replace_known_typos(text: str) -> str:
    corrected = text
    for typo, replacement in TYPO_FIXES.items():
        corrected = re.sub(
            rf"\b{re.escape(typo)}\b",
            replacement,
            corrected,
            flags=re.IGNORECASE,
        )
    return corrected


def add_entity_context(text: str) -> str:
    updated = text
    lowered = updated.casefold()
    for phrase, replacement in ENTITY_CONTEXT_HINTS.items():
        if phrase not in lowered:
            continue
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        updated = pattern.sub(replacement, updated, count=1)
        lowered = updated.casefold()
    return updated


def normalize_research_question(question: str) -> dict[str, str]:
    original = collapse_whitespace(question.strip())
    if not original:
        raise ValueError("Research question must not be empty.")

    normalized = replace_known_typos(original)
    normalized = add_entity_context(normalized)
    normalized = collapse_whitespace(normalized)
    return {
        "original_question": original,
        "normalized_question": normalized,
    }


def build_research_prompt(*, original_question: str, normalized_question: str) -> str:
    return (
        "You are an independent Gemini research companion for Codex. "
        "Use only public web research capabilities such as web fetch or web search. "
        "Do not use shell commands, local files, or private network access. "
        "Do not assume any prior Codex findings, draft answer, selected source list, or interpretation. "
        "Run an independent second-pass research check from the normalized question only, and use the original question only as audit context. "
        "Return a concise research brief with the likely answer, notable contradictions or uncertainties, and public references worth checking directly. "
        f"Original question: {original_question} "
        f"Normalized question: {normalized_question}"
    )


def resolve_npx_executable() -> str | None:
    return shutil.which("npx") or shutil.which("npx.cmd")


def build_command(npx_executable: str, prompt: str, model: str | None) -> list[str]:
    command = [
        npx_executable,
        "--yes",
        "@google/gemini-cli",
        "-p",
        prompt,
        "--output-format",
        "json",
        "-e",
        "none",
        "--approval-mode",
        "yolo",
    ]
    if model:
        command.extend(["--model", model])
    return command


def model_display_name(model: str | None) -> str:
    return model or "cli-default"


def build_model_ladder(model: str | None) -> list[str | None]:
    ladder: list[str | None] = []
    if model:
        ladder.append(model)
    for candidate in DEFAULT_MODEL_LADDER:
        if candidate not in ladder:
            ladder.append(candidate)
    return ladder


def build_gemini_env(*, allow_env_credentials: bool) -> tuple[dict[str, str], bool]:
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    sanitized = not allow_env_credentials
    if not allow_env_credentials:
        for key in BILLING_ENV_VARS:
            env.pop(key, None)
    return env, sanitized


def is_model_fallback_error(response_text: str, stderr: str, exit_code: int) -> bool:
    combined = f"{response_text}\n{stderr}\n{exit_code}".casefold()
    auth_failures = (
        "auth method",
        "authenticate",
        "authentication",
        "oauth",
        "credentials missing",
        "api key",
        "application default credentials",
    )
    if any(marker in combined for marker in auth_failures):
        return False

    generic_limit_markers = (
        "quota",
        "rate limit",
        "ratelimit",
        "resource_exhausted",
        "exhausted",
        "429",
        "capacity",
        "overloaded",
        "high demand",
        "temporarily unavailable",
    )
    if any(marker in combined for marker in generic_limit_markers):
        return True

    model_access_markers = (
        "not available",
        "not found",
        "unsupported",
        "not supported",
        "permission denied",
        "does not have access",
        "don't have access",
        "access denied",
    )
    return "model" in combined and any(marker in combined for marker in model_access_markers)


def make_attempt_summary(
    *,
    model: str | None,
    actual_model: str | None,
    ok: bool,
    exit_code: int,
    response: str,
    fallback_eligible: bool,
) -> dict[str, Any]:
    return {
        "model": model_display_name(model),
        "actual_model": actual_model,
        "ok": ok,
        "exit_code": exit_code,
        "fallback_eligible": fallback_eligible,
        "response_excerpt": response[:300],
    }


def infer_main_model_from_stats(stats: dict[str, Any]) -> str | None:
    models = stats.get("models")
    if not isinstance(models, dict):
        return None
    for model_name, model_stats in models.items():
        if not isinstance(model_stats, dict):
            continue
        roles = model_stats.get("roles")
        if isinstance(roles, dict) and "main" in roles:
            return str(model_name)
    for model_name in models:
        return str(model_name)
    return None


def run_gemini_with_model_fallback(
    *,
    npx_executable: str,
    prompt: str,
    model: str | None,
    timeout_sec: int,
    env: dict[str, str],
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    last_result: dict[str, Any] | None = None
    ladder = build_model_ladder(model)

    for index, model_candidate in enumerate(ladder):
        try:
            completed = subprocess.run(
                build_command(npx_executable, prompt, model_candidate),
                cwd=WORKSPACE_DIR,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=env,
                check=False,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "response": "Failed to start Gemini CLI because `npx` was not found.",
                "stats": {},
                "stderr": "",
                "exit_code": 127,
                "model_used": None,
                "model_attempts": attempts,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "response": f"Gemini CLI timed out after {timeout_sec} seconds.",
                "stats": {},
                "stderr": exc.stderr or "",
                "exit_code": 124,
                "model_used": None,
                "model_attempts": attempts,
            }

        try:
            payload = extract_payload(completed.stdout, completed.stderr)
        except ValueError as exc:
            stderr_text = completed.stderr.strip()
            response_text = stderr_text or str(exc)
            return {
                "ok": False,
                "response": response_text,
                "stats": {},
                "stderr": completed.stderr,
                "exit_code": completed.returncode,
                "model_used": None,
                "model_attempts": attempts,
            }

        response_text = payload.get("response", "")
        error_payload = payload.get("error")
        if not response_text and error_payload:
            if isinstance(error_payload, dict) and error_payload.get("message"):
                response_text = str(error_payload["message"])
            else:
                response_text = json.dumps(error_payload)

        ok = completed.returncode == 0 and bool(response_text)
        if not ok and not response_text:
            response_text = "Gemini CLI returned no response."

        stats = payload.get("stats", {})
        actual_model = infer_main_model_from_stats(stats)
        fallback_eligible = (
            not ok
            and index < len(ladder) - 1
            and is_model_fallback_error(response_text, completed.stderr, completed.returncode)
        )
        attempts.append(
            make_attempt_summary(
                model=model_candidate,
                actual_model=actual_model,
                ok=ok,
                exit_code=completed.returncode,
                response=response_text,
                fallback_eligible=fallback_eligible,
            )
        )

        last_result = {
            "ok": ok,
            "response": response_text,
            "stats": stats,
            "stderr": completed.stderr,
            "exit_code": completed.returncode,
            "model_used": (actual_model or model_display_name(model_candidate)) if ok else None,
            "model_attempts": attempts,
        }
        if ok or not fallback_eligible:
            return last_result

    if last_result is not None:
        return last_result
    return {
        "ok": False,
        "response": "Gemini CLI returned no response.",
        "stats": {},
        "stderr": "",
        "exit_code": 1,
        "model_used": None,
        "model_attempts": attempts,
    }


def invoke_gemini_url(
    url: str,
    instruction: str,
    model: str | None = None,
    timeout_sec: int = 180,
    allow_env_credentials: bool = False,
) -> dict[str, Any]:
    validated_url = validate_public_url(url)
    source_type = classify_source_type(validated_url)
    prompt = build_url_prompt(validated_url, instruction, source_type)

    npx_executable = resolve_npx_executable()
    if npx_executable is None:
        return {
            "ok": False,
            "response": "`npx` is not available on PATH.",
            "stats": {},
            "stderr": "",
            "exit_code": 127,
            "source_type": source_type,
            "model_strategy": MODEL_STRATEGY,
            "model_attempts": [],
            "model_used": None,
            "auth_env_sanitized": False,
        }

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    env, auth_env_sanitized = build_gemini_env(allow_env_credentials=allow_env_credentials)

    result = run_gemini_with_model_fallback(
        npx_executable=npx_executable,
        prompt=prompt,
        model=model,
        timeout_sec=timeout_sec,
        env=env,
    )
    result.update(
        {
            "model_strategy": MODEL_STRATEGY,
            "auth_env_sanitized": auth_env_sanitized,
        }
    )
    return {
        **result,
        "source_type": source_type,
    }


def make_research_result(
    *,
    ok: bool,
    response: str,
    stats: dict[str, Any],
    stderr: str,
    exit_code: int,
    original_question: str,
    normalized_question: str,
    model_strategy: str = MODEL_STRATEGY,
    model_attempts: list[dict[str, Any]] | None = None,
    model_used: str | None = None,
    auth_env_sanitized: bool = False,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "response": response,
        "stats": stats,
        "stderr": stderr,
        "exit_code": exit_code,
        "mode": "research",
        "original_question": original_question,
        "normalized_question": normalized_question,
        "model_strategy": model_strategy,
        "model_attempts": model_attempts or [],
        "model_used": model_used,
        "auth_env_sanitized": auth_env_sanitized,
    }


def invoke_gemini_research(
    question: str,
    model: str | None = None,
    timeout_sec: int = 180,
    allow_env_credentials: bool = False,
) -> dict[str, Any]:
    normalized = normalize_research_question(question)
    prompt = build_research_prompt(
        original_question=normalized["original_question"],
        normalized_question=normalized["normalized_question"],
    )

    npx_executable = resolve_npx_executable()
    if npx_executable is None:
        return make_research_result(
            ok=False,
            response="`npx` is not available on PATH.",
            stats={},
            stderr="",
            exit_code=127,
            original_question=normalized["original_question"],
            normalized_question=normalized["normalized_question"],
        )

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    env, auth_env_sanitized = build_gemini_env(allow_env_credentials=allow_env_credentials)
    result = run_gemini_with_model_fallback(
        npx_executable=npx_executable,
        prompt=prompt,
        model=model,
        timeout_sec=timeout_sec,
        env=env,
    )

    return make_research_result(
        ok=result["ok"],
        response=result["response"],
        stats=result["stats"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
        original_question=normalized["original_question"],
        normalized_question=normalized["normalized_question"],
        model_attempts=result["model_attempts"],
        model_used=result["model_used"],
        auth_env_sanitized=auth_env_sanitized,
    )


def build_url_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect a public URL through Gemini CLI.")
    parser.add_argument("--url", required=True, help="Public http(s) URL to inspect.")
    parser.add_argument("--instruction", required=True, help="Task instruction for Gemini.")
    parser.add_argument("--model", help="Optional Gemini model override.")
    parser.add_argument("--timeout-sec", type=int, default=180, help="Timeout in seconds.")
    parser.add_argument(
        "--allow-env-credentials",
        action="store_true",
        help="Allow Gemini API key or Vertex environment variables instead of forcing OAuth-only.",
    )
    parser.add_argument("--output", choices=("json", "text"), default="json")
    return parser


def build_research_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an independent Gemini research pass from a question."
    )
    parser.add_argument("--question", required=True, help="Research question to inspect.")
    parser.add_argument("--model", help="Optional Gemini model override.")
    parser.add_argument("--timeout-sec", type=int, default=180, help="Timeout in seconds.")
    parser.add_argument(
        "--allow-env-credentials",
        action="store_true",
        help="Allow Gemini API key or Vertex environment variables instead of forcing OAuth-only.",
    )
    parser.add_argument("--output", choices=("json", "text"), default="json")
    return parser
