from datetime import UTC, datetime

from amazon_intent_cli.models import IntentMode, IntentProfile, ProductRecord
from amazon_intent_cli.ranking import rank_plain_records, rank_records


def build_record(
    asin: str,
    title: str,
    brand: str,
    review_count: int,
    *,
    sponsored: bool = False,
    store: bool = False,
    seller: str = "",
) -> ProductRecord:
    return ProductRecord(
        asin=asin,
        url=f"https://www.amazon.de/dp/{asin}",
        title=title,
        brand=brand,
        marketplace="de",
        price=1000.0,
        currency="EUR",
        prime=True,
        seller_summary=seller,
        review_count=review_count,
        rating=4.6,
        brand_store_present=store,
        is_sponsored=sponsored,
    )


def exact_profile() -> IntentProfile:
    return IntentProfile(
        query="LG C4",
        marketplace="de",
        mode=IntentMode.EXACT,
        canonical_brand="LG",
        canonical_family="C4",
        family_tokens=["lg", "c4"],
        allowed_variants=["c47la", "c46la", "c45la"],
        allowed_fallback_models=["c3", "g4", "b4"],
        excluded_brands=["hisense", "tcl"],
        similar_families=[{"brand": "Samsung", "family": "S90D"}],
        confidence=0.93,
        created_at=datetime.now(UTC),
    )


def test_exact_ranking_excludes_other_brands_and_prefers_exact_family() -> None:
    records = [
        build_record("B0HISENSE65", "Hisense 65E7Q TV", "Hisense", 500, sponsored=True),
        build_record("B0LGC3DE65", "LG OLED65C37LA 65 Zoll OLED evo TV", "LG", 2301),
        build_record(
            "B0LGC4DE65",
            "LG OLED65C47LA 65 Zoll OLED evo AI TV",
            "LG",
            1543,
            store=True,
            seller="Verkauf durch Amazon EU S.a.r.L.",
        ),
    ]

    ranked = rank_records(records, exact_profile())

    assert [item.asin for item in ranked] == ["B0LGC4DE65", "B0LGC3DE65"]
    assert ranked[0].match_tier == "exact_variant"
    assert "brand/family" in ranked[0].score_reason


def test_similar_ranking_can_include_configured_competitors() -> None:
    profile = exact_profile()
    profile.mode = IntentMode.SIMILAR
    records = [
        build_record("B0SMS90D", "Samsung S90D OLED 65 Zoll", "Samsung", 600, store=True),
        build_record("B0TCL98", "TCL 98 Zoll QLED TV", "TCL", 700, sponsored=True),
    ]

    ranked = rank_records(records, profile)

    assert [item.asin for item in ranked] == ["B0SMS90D"]
    assert ranked[0].match_tier == "similar_family"


def test_exact_ranking_does_not_treat_size_tokens_as_family_variants() -> None:
    profile = IntentProfile(
        query="LG C4",
        marketplace="de",
        mode=IntentMode.EXACT,
        canonical_brand="LG",
        canonical_family="C4",
        family_tokens=["C4"],
        allowed_variants=["42", "48", "55", "65", "77", "83"],
        allowed_fallback_models=["C3", "G4", "B4"],
        excluded_brands=[],
        similar_families=[],
        confidence=1.0,
        created_at=datetime.now(UTC),
    )
    records = [
        build_record("B0F2JB8LDX", "LG OLED55C5ELB 55 Inch OLED evo TV", "LG", 1500),
        build_record("B0CYQ16XRR", "LG OLED48C47LA 48 Inch OLED evo TV", "LG", 1500),
    ]

    ranked = rank_records(records, profile)

    assert [item.asin for item in ranked] == ["B0CYQ16XRR"]
    assert ranked[0].match_tier in {"exact_family", "exact_variant"}


def test_plain_ranking_uses_reviews_then_rating_then_price_then_non_sponsored() -> None:
    records = [
        build_record("B0AAA", "Microwave A", "Toshiba", 1000, sponsored=True),
        build_record("B0BBB", "Microwave B", "Samsung", 1000, sponsored=False),
        build_record("B0CCC", "Microwave C", "Comfee", 1200, sponsored=False),
        build_record("B0DDD", "Microwave D", "Candy", 1000, sponsored=False),
    ]
    records[0].rating = 4.4
    records[0].price = 70.0
    records[1].rating = 4.4
    records[1].price = 70.0
    records[2].rating = 4.2
    records[2].price = 60.0
    records[3].rating = 4.5
    records[3].price = 80.0

    ranked = rank_plain_records(records)

    assert [item.asin for item in ranked] == ["B0CCC", "B0DDD", "B0BBB", "B0AAA"]
    assert ranked[0].match_tier == "plain_ranked"
    assert ranked[0].ranking_score > ranked[1].ranking_score
    assert 0 <= ranked[0].ranking_score <= 100
    assert "Normalized relevance" in ranked[0].score_reason
