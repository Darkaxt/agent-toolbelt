from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .cache import ReputationCache
from .observables import Observable, normalize_records, observable_to_dict
from .providers import default_providers

CACHE_KEY_VERSION = "v2"

VERDICT_ORDER = {
    "malicious": 5,
    "suspicious": 4,
    "error": 3,
    "clean": 2,
    "unknown": 1,
    "skipped": 0,
}

KNOWN_VERDICTS = ("malicious", "suspicious", "error", "clean", "unknown", "skipped")


def classify_observable(
    observable: Observable,
    *,
    provider_list=None,
    reputation_cache: ReputationCache | None = None,
) -> dict[str, Any]:
    provider_items = list(default_providers() if provider_list is None else provider_list)
    cache_key = provider_aware_cache_key(observable, provider_items)
    if reputation_cache is not None:
        cached = reputation_cache.get(cache_key)
        if cached is not None and cached_result_is_reusable(cached):
            cached.update(observable_fields(observable))
            cached["cached"] = True
            return cached

    provider_results = [provider.check(observable) for provider in provider_items]
    result = aggregate_results(observable, provider_results)
    if reputation_cache is not None and cached_result_is_reusable(result):
        reputation_cache.set(cache_key, result)
    return result


def classify_records(
    records,
    *,
    auto_detect: bool = False,
    provider_list=None,
    reputation_cache: ReputationCache | None = None,
) -> dict[str, Any]:
    provider_items = list(default_providers() if provider_list is None else provider_list)
    normalized, rejected = normalize_records(list(records), auto_detect=auto_detect)
    outputs = [
        classify_observable(observable, provider_list=provider_items, reputation_cache=reputation_cache)
        for observable in normalized
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "observables": outputs,
        "rejected_observables": rejected,
        "diagnostics": build_report_diagnostics(outputs, rejected, provider_items),
    }


def aggregate_results(observable, provider_results):
    if not provider_results:
        verdict = "unknown"
    elif all(result.verdict == "skipped" for result in provider_results):
        verdict = "skipped"
    else:
        verdict = max(provider_results, key=lambda result: VERDICT_ORDER.get(result.verdict, 0)).verdict

    score = max((result.score for result in provider_results), default=0)
    evidence = []
    errors = []
    for result in provider_results:
        evidence.extend({"provider": result.provider, **item} for item in result.evidence)
        errors.extend(f"{result.provider}: {error}" for error in result.errors)

    provider_summary = build_provider_summary(provider_results, evidence, errors)
    return {
        **observable_fields(observable),
        "verdict": verdict,
        "score": score,
        "providers": [result.to_dict() for result in provider_results],
        "provider_summary": provider_summary,
        "evidence": evidence,
        "errors": errors,
        "explanation": explain_result(verdict, provider_summary),
        "cached": False,
    }


def observable_fields(observable):
    return observable_to_dict(observable)


def build_provider_summary(provider_results, evidence: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    verdicts = {verdict: 0 for verdict in KNOWN_VERDICTS}
    provider_names = []
    for result in provider_results:
        provider_names.append(result.provider)
        verdicts[result.verdict] = verdicts.get(result.verdict, 0) + 1
    return {
        "providers": provider_names,
        "provider_count": len(provider_results),
        "configured_count": len(provider_results),
        "skipped_count": verdicts.get("skipped", 0),
        "error_count": verdicts.get("error", 0) + len(errors),
        "evidence_count": len(evidence),
        "verdicts": verdicts,
    }


def explain_result(verdict: str, provider_summary: dict[str, Any]) -> str:
    provider_count = provider_summary.get("provider_count", 0)
    evidence_count = provider_summary.get("evidence_count", 0)
    error_count = provider_summary.get("error_count", 0)
    skipped_count = provider_summary.get("skipped_count", 0)
    if provider_count == 0:
        return "No passive providers were configured; verdict is unknown."
    parts = [f"{verdict} verdict from {provider_count} passive provider result(s)"]
    if evidence_count:
        parts.append(f"{evidence_count} evidence item(s)")
    if skipped_count:
        parts.append(f"{skipped_count} skipped provider result(s)")
    if error_count:
        parts.append(f"{error_count} provider error(s)")
    return "; ".join(parts) + "."


def build_report_diagnostics(
    outputs: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    provider_items: list[Any],
) -> dict[str, Any]:
    provider_rows = [provider for output in outputs for provider in output.get("providers") or []]
    provider_verdicts = {verdict: 0 for verdict in KNOWN_VERDICTS}
    by_provider: dict[str, dict[str, Any]] = {}
    for row in provider_rows:
        provider_name = str(row.get("provider") or "unknown")
        verdict = str(row.get("verdict") or "unknown")
        provider_verdicts[verdict] = provider_verdicts.get(verdict, 0) + 1
        provider_stats = by_provider.setdefault(
            provider_name,
            {
                "result_count": 0,
                "skipped_count": 0,
                "error_count": 0,
                "evidence_count": 0,
                "verdicts": {item: 0 for item in KNOWN_VERDICTS},
            },
        )
        provider_stats["result_count"] += 1
        provider_stats["verdicts"][verdict] = provider_stats["verdicts"].get(verdict, 0) + 1
        if verdict == "skipped":
            provider_stats["skipped_count"] += 1
        if verdict == "error" or row.get("errors"):
            provider_stats["error_count"] += 1
        provider_stats["evidence_count"] += len(row.get("evidence") or [])

    skipped_count = sum(1 for row in provider_rows if row.get("verdict") == "skipped")
    error_count = sum(1 for row in provider_rows if row.get("verdict") == "error" or row.get("errors"))
    cache_hit_count = sum(1 for output in outputs if output.get("cached"))
    return {
        "observable_count": len(outputs),
        "rejected_observable_count": len(rejected),
        "cache": {
            "hit_count": cache_hit_count,
            "miss_count": len(outputs) - cache_hit_count,
        },
        "providers": {
            "configured_count": len(provider_items),
            "result_count": len(provider_rows),
            "skipped_count": skipped_count,
            "error_count": error_count,
            "verdicts": provider_verdicts,
            "by_provider": by_provider,
        },
    }


def provider_aware_cache_key(observable, provider_items):
    provider_tokens = ";".join(provider_cache_token(provider) for provider in provider_items)
    return f"{CACHE_KEY_VERSION}|{observable.cache_key}|providers={provider_tokens}"


def provider_cache_token(provider):
    name = str(getattr(provider, "name", provider.__class__.__name__))
    state_parts = []
    for attr in ("dqs_key", "auth_key", "api_key"):
        if hasattr(provider, attr):
            state_parts.append(f"{attr}:{'set' if getattr(provider, attr) else 'missing'}")
    return f"{name}({','.join(state_parts)})"


def cached_result_is_reusable(result):
    if result.get("verdict") == "error" or result.get("errors"):
        return False
    for provider in result.get("providers") or []:
        if provider.get("verdict") == "error" or provider.get("errors"):
            return False
    return True
