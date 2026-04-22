from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from .cache import ReputationCache
from .observables import Observable, normalize_observable
from .providers import ProviderResult, default_providers


VERDICT_ORDER = {
    "malicious": 5,
    "suspicious": 4,
    "error": 3,
    "clean": 2,
    "unknown": 1,
    "skipped": 0,
}


def classify_observable(
    observable: Observable,
    *,
    provider_list: Iterable[Any] | None = None,
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
    records: Iterable[dict[str, Any]],
    *,
    provider_list: Iterable[Any] | None = None,
    reputation_cache: ReputationCache | None = None,
) -> dict[str, Any]:
    provider_items = list(default_providers() if provider_list is None else provider_list)
    outputs = []
    for record in records:
        observable = normalize_observable(record)
        outputs.append(
            classify_observable(
                observable,
                provider_list=provider_items,
                reputation_cache=reputation_cache,
            )
        )
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "observables": outputs}


def aggregate_results(observable: Observable, provider_results: list[ProviderResult]) -> dict[str, Any]:
    if not provider_results:
        verdict = "unknown"
    elif all(result.verdict == "skipped" for result in provider_results):
        verdict = "skipped"
    else:
        verdict = max(provider_results, key=lambda result: VERDICT_ORDER.get(result.verdict, 0)).verdict

    score = max((result.score for result in provider_results), default=0)
    evidence: list[dict[str, Any]] = []
    errors: list[str] = []
    for result in provider_results:
        evidence.extend({"provider": result.provider, **item} for item in result.evidence)
        errors.extend(f"{result.provider}: {error}" for error in result.errors)

    return {
        **observable_fields(observable),
        "verdict": verdict,
        "score": score,
        "providers": [result.to_dict() for result in provider_results],
        "evidence": evidence,
        "errors": errors,
        "cached": False,
    }


def observable_fields(observable: Observable) -> dict[str, Any]:
    return {
        "type": observable.type,
        "value": observable.value,
        "source": observable.source,
        "context": observable.context,
        "domain": observable.domain,
    }


def provider_aware_cache_key(observable: Observable, provider_items: Iterable[Any]) -> str:
    provider_tokens = ";".join(provider_cache_token(provider) for provider in provider_items)
    return f"{observable.cache_key}|providers={provider_tokens}"


def provider_cache_token(provider: Any) -> str:
    name = str(getattr(provider, "name", provider.__class__.__name__))
    state_parts = []
    for attr in ("dqs_key", "auth_key", "api_key"):
        if hasattr(provider, attr):
            state_parts.append(f"{attr}:{'set' if getattr(provider, attr) else 'missing'}")
    return f"{name}({','.join(state_parts)})"


def cached_result_is_reusable(result: dict[str, Any]) -> bool:
    if result.get("verdict") == "error" or result.get("errors"):
        return False
    for provider in result.get("providers") or []:
        if provider.get("verdict") == "error" or provider.get("errors"):
            return False
    return True
