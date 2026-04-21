from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .cache import IntentCache
from .models import IntentMode, IntentProfile


class IntentResolutionError(RuntimeError):
    """Raised when Gemini cannot produce a usable intent profile."""


def _default_cache_dir() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
    return local_app_data / "amazon-intent-cli" / "intent-cache"


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw_text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw_text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise IntentResolutionError("Gemini did not return a JSON object.")


class GeminiIntentResolver:
    def __init__(self, cache: IntentCache | None = None) -> None:
        self.cache = cache or IntentCache(_default_cache_dir())

    def resolve(
        self,
        query: str,
        marketplace: str,
        mode: IntentMode,
        *,
        refresh: bool = False,
    ) -> IntentProfile:
        if not refresh:
            cached = self.cache.load(query, marketplace, mode)
            if cached is not None:
                return cached

        profile = self._resolve_with_gemini(query, marketplace, mode)
        self.cache.save(profile)
        return profile

    def _resolve_with_gemini(self, query: str, marketplace: str, mode: IntentMode) -> IntentProfile:
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if npx is None:
            raise IntentResolutionError("Gemini CLI requires `npx` on PATH.")

        mode_instruction = (
            "Focus on same-brand exact-family retrieval and same-brand fallbacks only."
            if mode == IntentMode.EXACT
            else "Focus on legitimate comparable competitor families only."
        )
        prompt = (
            "You are resolving structured shopping intent for an Amazon CLI. "
            "Return raw JSON only, with no markdown fences and no explanatory text. "
            "Use this schema: "
            "{"
            '"canonical_brand": string, '
            '"canonical_family": string, '
            '"family_tokens": string[], '
            '"allowed_variants": string[], '
            '"allowed_fallback_models": string[], '
            '"excluded_brands": string[], '
            '"similar_families": [{"brand": string, "family": string}], '
            '"confidence": number'
            "}. "
            f"Marketplace: {marketplace}. "
            f"Mode: {mode.value}. "
            f"Rules: {mode_instruction} "
            f"Query: {query}"
        )

        completed = subprocess.run(
            [
                npx,
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
            ],
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "NO_COLOR": "1"},
            check=False,
        )
        if completed.returncode != 0:
            raise IntentResolutionError(completed.stderr.strip() or "Gemini CLI failed.")

        payload = _extract_json_object(completed.stdout or completed.stderr)
        response_text = payload.get("response", "")
        data = _extract_json_object(response_text if isinstance(response_text, str) else json.dumps(response_text))
        return IntentProfile(
            query=query,
            marketplace=marketplace,
            mode=mode,
            canonical_brand=data["canonical_brand"],
            canonical_family=data["canonical_family"],
            family_tokens=[str(item) for item in data.get("family_tokens", [])],
            allowed_variants=[str(item) for item in data.get("allowed_variants", [])],
            allowed_fallback_models=[str(item) for item in data.get("allowed_fallback_models", [])],
            excluded_brands=[str(item) for item in data.get("excluded_brands", [])],
            similar_families=[
                {"brand": str(item.get("brand", "")), "family": str(item.get("family", ""))}
                for item in data.get("similar_families", [])
                if isinstance(item, dict)
            ],
            confidence=float(data.get("confidence", 0.0)),
        )
