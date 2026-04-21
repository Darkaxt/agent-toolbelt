from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class IntentMode(StrEnum):
    EXACT = "exact"
    SIMILAR = "similar"


@dataclass(slots=True)
class IntentProfile:
    query: str
    marketplace: str
    mode: IntentMode
    canonical_brand: str
    canonical_family: str
    family_tokens: list[str]
    allowed_variants: list[str]
    allowed_fallback_models: list[str]
    excluded_brands: list[str]
    similar_families: list[dict[str, str]]
    confidence: float
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        payload["created_at"] = self.created_at.astimezone(UTC).isoformat()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IntentProfile":
        return cls(
            query=payload["query"],
            marketplace=payload["marketplace"],
            mode=IntentMode(payload["mode"]),
            canonical_brand=payload["canonical_brand"],
            canonical_family=payload["canonical_family"],
            family_tokens=list(payload.get("family_tokens", [])),
            allowed_variants=list(payload.get("allowed_variants", [])),
            allowed_fallback_models=list(payload.get("allowed_fallback_models", [])),
            excluded_brands=list(payload.get("excluded_brands", [])),
            similar_families=list(payload.get("similar_families", [])),
            confidence=float(payload.get("confidence", 0.0)),
            created_at=datetime.fromisoformat(payload["created_at"]),
        )


@dataclass(slots=True)
class ProductRecord:
    asin: str
    url: str
    title: str
    brand: str
    marketplace: str
    price: float | None = None
    currency: str | None = None
    prime: bool = False
    seller_summary: str = ""
    review_count: int = 0
    rating: float | None = None
    brand_store_present: bool = False
    is_sponsored: bool = False
    match_tier: str = ""
    score_reason: str = ""
    ranking_score: int = 0
    requested_model: str | None = None
    resolved_model: str | None = None
    model_match: str | None = None
    model_disclosure: str | None = None
    specs: dict[str, str] = field(default_factory=dict)
    specs_normalized: dict[str, Any] = field(default_factory=dict)
    review_insights: dict[str, Any] = field(default_factory=dict)
    top_reviews: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_specs: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if include_specs:
            payload["specs_raw"] = dict(self.specs)
            payload["specs"] = dict(self.specs)
            payload["specs_normalized"] = dict(self.specs_normalized)
        else:
            payload.pop("specs", None)
            payload.pop("specs_normalized", None)
        return payload

    @property
    def specs_raw(self) -> dict[str, str]:
        return self.specs


@dataclass(slots=True)
class SearchPage:
    records: list[ProductRecord]
    current_page: int = 1
    available_pages: list[int] = field(default_factory=list)
    next_page_url: str | None = None
    source_url: str | None = None


@dataclass(slots=True)
class ReviewPage:
    reviews: list[dict[str, Any]]
    current_page: int = 1
    available_pages: list[int] = field(default_factory=list)
    next_page_url: str | None = None
    next_page_state: dict[str, Any] = field(default_factory=dict)
    available_review_count: int = 0
    source_url: str | None = None
    final_url: str | None = None
    sign_in_required: bool = False


@dataclass(slots=True)
class BrowserSession:
    marketplace: str
    browser_executable: str
    user_agent: str
    cookies: list[dict[str, Any]]
    session_source: str = "isolated"
    portal: str = "retail"
    session_key: str | None = None
    profile_dir: str | None = None
    final_url: str | None = None
    user_data_dir: str | None = None
    profile_directory: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["session_key"] = self.session_key or f"{self.marketplace}:{self.portal}"
        payload["created_at"] = self.created_at.astimezone(UTC).isoformat()
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BrowserSession":
        portal = str(payload.get("portal", "retail"))
        marketplace = payload["marketplace"]
        return cls(
            marketplace=marketplace,
            browser_executable=payload["browser_executable"],
            user_agent=payload["user_agent"],
            cookies=list(payload.get("cookies", [])),
            session_source=str(payload.get("session_source", "isolated")),
            portal=portal,
            session_key=payload.get("session_key") or f"{marketplace}:{portal}",
            profile_dir=payload.get("profile_dir"),
            final_url=payload.get("final_url"),
            user_data_dir=payload.get("user_data_dir"),
            profile_directory=payload.get("profile_directory"),
            created_at=datetime.fromisoformat(payload["created_at"]),
        )
