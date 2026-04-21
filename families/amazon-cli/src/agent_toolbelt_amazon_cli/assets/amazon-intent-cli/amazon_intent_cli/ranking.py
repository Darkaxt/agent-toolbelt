from __future__ import annotations

import re

from .amazon import normalize_text
from .models import IntentMode, IntentProfile, ProductRecord


SELLER_POSITIVE_MARKERS = ("amazon", "prime")


def _normalized_family_tokens(profile: IntentProfile) -> list[str]:
    tokens = [normalize_text(profile.canonical_family), *(normalize_text(token) for token in profile.family_tokens)]
    return [token for token in dict.fromkeys(tokens) if token]


def _usable_variant_tokens(profile: IntentProfile) -> list[str]:
    tokens = [normalize_text(token) for token in profile.allowed_variants]
    return [token for token in tokens if token and re.search(r"[a-z]", token)]


def _contains_any_token(title: str, tokens: list[str]) -> bool:
    return any(token in title for token in tokens if token)


def _score_exact(record: ProductRecord, profile: IntentProfile) -> tuple[int, str] | None:
    brand = normalize_text(record.brand)
    canonical_brand = normalize_text(profile.canonical_brand)
    if brand != canonical_brand:
        return None

    title = normalize_text(record.title)
    family_tokens = _normalized_family_tokens(profile)
    family_match = _contains_any_token(title, family_tokens)
    variant_match = family_match and _contains_any_token(title, _usable_variant_tokens(profile))
    fallback_match = _contains_any_token(title, [normalize_text(model) for model in profile.allowed_fallback_models])

    if variant_match:
        score = 1000
        tier = "exact_variant"
        reason = "Matched same brand/family variant."
    elif family_match:
        score = 930
        tier = "exact_family"
        reason = "Matched same brand/family."
    elif fallback_match:
        score = 820
        tier = "same_brand_fallback"
        reason = "Matched same brand fallback model."
    else:
        return None

    score += min(record.review_count // 100, 20)
    if record.brand_store_present:
        score += 25
    if record.prime:
        score += 10
    if any(marker in normalize_text(record.seller_summary) for marker in SELLER_POSITIVE_MARKERS):
        score += 15
    return score, f"{reason} Reviews/store/seller adjusted ranking."


def _score_similar(record: ProductRecord, profile: IntentProfile) -> tuple[int, str] | None:
    exact_score = _score_exact(record, profile)
    if exact_score is not None:
        return exact_score

    title = normalize_text(record.title)
    brand = normalize_text(record.brand)
    for family in profile.similar_families:
        family_brand = normalize_text(family.get("brand", ""))
        family_name = normalize_text(family.get("family", ""))
        if family_brand == brand and family_name and family_name in title:
            score = 780 + min(record.review_count // 100, 20)
            if record.brand_store_present:
                score += 20
            return score, "Matched Gemini-approved similar family."
    return None


def _plain_sort_key(record: ProductRecord) -> tuple[float, float, float, bool]:
    return (
        -record.review_count,
        -(record.rating if record.rating is not None else -1.0),
        record.price if record.price is not None else float("inf"),
        record.is_sponsored,
    )


def _plain_ranking_score(
    record: ProductRecord,
    *,
    max_reviews: int,
    min_price: float | None,
    max_price: float | None,
) -> int:
    review_score = 0.0 if max_reviews <= 0 else 60.0 * (record.review_count / max_reviews)
    rating_score = 30.0 * ((record.rating if record.rating is not None else 0.0) / 5.0)

    if record.price is None or min_price is None or max_price is None:
        price_score = 0.0
    elif max_price == min_price:
        price_score = 10.0
    else:
        price_score = 10.0 * (1.0 - ((record.price - min_price) / (max_price - min_price)))

    sponsor_penalty = 5.0 if record.is_sponsored else 0.0
    normalized = round(review_score + rating_score + price_score - sponsor_penalty)
    return max(0, min(100, normalized))


def _plain_score_reason(record: ProductRecord) -> str:
    rating = f"{record.rating:.1f}" if record.rating is not None else "n/a"
    price = f"{record.price:.2f}" if record.price is not None else "unknown"
    sponsorship_note = "non-sponsored preferred" if not record.is_sponsored else "sponsored lost the final tie-break"
    reason = (
        f"Normalized relevance {record.ranking_score}/100 from reviews={record.review_count}, rating={rating}, "
        f"price={price}, {sponsorship_note}."
    )
    trust_notes: list[str] = []
    if record.brand_store_present:
        trust_notes.append("brand store present")
    if record.prime:
        trust_notes.append("Prime")
    if any(marker in normalize_text(record.seller_summary) for marker in SELLER_POSITIVE_MARKERS):
        trust_notes.append("seller signal positive")
    if trust_notes:
        reason += " Trust notes: " + ", ".join(trust_notes) + "."
    return reason


def rank_plain_records(records: list[ProductRecord]) -> list[ProductRecord]:
    ranked = sorted(records, key=_plain_sort_key)
    max_reviews = max((record.review_count for record in ranked), default=0)
    known_prices = [record.price for record in ranked if record.price is not None]
    min_price = min(known_prices) if known_prices else None
    max_price = max(known_prices) if known_prices else None

    for record in ranked:
        record.match_tier = "plain_ranked"
        record.ranking_score = _plain_ranking_score(
            record,
            max_reviews=max_reviews,
            min_price=min_price,
            max_price=max_price,
        )
        record.score_reason = _plain_score_reason(record)
    return ranked


def _normalized_exact_ranking_score(record: ProductRecord) -> int:
    base_scores = {
        "exact_variant": 94,
        "exact_family": 90,
        "same_brand_fallback": 78,
        "similar_family": 72,
    }
    score = base_scores.get(record.match_tier, 70)
    score += min(record.review_count // 500, 4)
    if record.brand_store_present:
        score += 1
    if record.prime:
        score += 1
    if any(marker in normalize_text(record.seller_summary) for marker in SELLER_POSITIVE_MARKERS):
        score += 1
    return min(100, score)


def rank_records(records: list[ProductRecord], profile: IntentProfile) -> list[ProductRecord]:
    ranked: list[tuple[int, ProductRecord]] = []
    for record in records:
        result = _score_similar(record, profile) if profile.mode == IntentMode.SIMILAR else _score_exact(record, profile)
        if result is None:
            continue
        score, reason = result
        if profile.mode == IntentMode.SIMILAR and "similar family" in reason.lower():
            record.match_tier = "similar_family"
        elif "variant" in reason.lower():
            record.match_tier = "exact_variant"
        elif "fallback" in reason.lower():
            record.match_tier = "same_brand_fallback"
        else:
            record.match_tier = "exact_family"
        record.ranking_score = _normalized_exact_ranking_score(record)
        record.score_reason = f"{reason} Normalized relevance {record.ranking_score}/100."
        ranked.append((score, record))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [record for _, record in ranked]
