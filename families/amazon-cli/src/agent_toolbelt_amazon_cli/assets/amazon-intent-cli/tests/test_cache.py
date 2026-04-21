from datetime import UTC, datetime, timedelta

from amazon_intent_cli.cache import IntentCache
from amazon_intent_cli.models import IntentMode, IntentProfile


def test_cache_round_trip(tmp_path) -> None:
    cache = IntentCache(tmp_path)
    profile = IntentProfile(
        query="LG C4",
        marketplace="de",
        mode=IntentMode.EXACT,
        canonical_brand="LG",
        canonical_family="C4",
        family_tokens=["lg", "c4"],
        allowed_variants=["c47la"],
        allowed_fallback_models=["c3", "g4"],
        excluded_brands=["Hisense"],
        similar_families=[],
        confidence=0.92,
        created_at=datetime.now(UTC),
    )

    cache.save(profile)
    loaded = cache.load("LG C4", "de", IntentMode.EXACT)

    assert loaded is not None
    assert loaded.canonical_brand == "LG"
    assert loaded.allowed_fallback_models == ["c3", "g4"]


def test_cache_expires_stale_profiles(tmp_path) -> None:
    cache = IntentCache(tmp_path, ttl=timedelta(hours=24))
    profile = IntentProfile(
        query="LG C4",
        marketplace="de",
        mode=IntentMode.EXACT,
        canonical_brand="LG",
        canonical_family="C4",
        family_tokens=["lg", "c4"],
        allowed_variants=[],
        allowed_fallback_models=[],
        excluded_brands=[],
        similar_families=[],
        confidence=0.5,
        created_at=datetime.now(UTC) - timedelta(days=2),
    )

    cache.save(profile)

    assert cache.load("LG C4", "de", IntentMode.EXACT) is None
