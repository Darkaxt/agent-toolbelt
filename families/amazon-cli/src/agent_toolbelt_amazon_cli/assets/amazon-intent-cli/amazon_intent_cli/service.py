from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from .amazon import (
    AmazonBlockedError,
    AmazonHttpClient,
    AmazonScraper,
    compose_search_query,
    extract_asin,
    find_spec_value,
    is_probably_blocked_html,
    is_probably_sign_in_html,
    marketplace_from_identifier,
    normalize_text,
)
from .intent import GeminiIntentResolver
from .marketplaces import get_marketplace
from .models import IntentMode, ProductRecord, SearchPage
from .offers import DEFAULT_OFFER_MARKETPLACES, OfferRecord, build_offer_url, parse_offer_html
from .ranking import rank_plain_records, rank_records
from .session import BrowserSessionBootstrapper, BrowserSessionError, BrowserSessionStore, make_session_key


DETAIL_FETCH_LIMIT = 5

POSITIVE_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "image quality": ("image quality", "picture quality", "bildqualität", "qualité d'image", "calidad de imagen"),
    "sound": ("sound", "klang", "son", "sonido"),
    "value": ("value", "rapport qualité prix", "preis", "precio"),
    "black levels": ("black", "schwarz", "noir", "negro"),
    "setup": ("setup", "einrichtung", "installation", "configuración"),
    "gaming": ("gaming", "144hz", "game", "zocken", "juegos"),
    "delivery": ("delivery", "lieferung", "livraison", "entrega"),
}

CRITICAL_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "remote": ("remote", "fernbedienung", "télécommande", "mando"),
    "apps": ("apps", "applications", "aplicaciones"),
    "software": ("software", "webos", "lg channels"),
    "ads or prompts": ("advertising", "publicitaire", "prompts", "redirection"),
    "complex controls": ("complicated", "complex", "kompliziert", "compliqué", "gewöhnungsbedürftig"),
}


def _review_text(review: dict[str, Any]) -> str:
    return normalize_text(f"{review.get('title', '')} {review.get('body', '')}")


def _term_counts(reviews: list[dict[str, Any]], aliases: dict[str, tuple[str, ...]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for review in reviews:
        text = _review_text(review)
        for term, term_aliases in aliases.items():
            if any(normalize_text(alias) in text for alias in term_aliases):
                counts[term] = counts.get(term, 0) + 1
    return [
        {"term": term, "count": count}
        for term, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _country_from_review_date(date: str) -> str | None:
    match = re.search(r"\bReviewed in (?P<country>.+?) on\b", date or "", flags=re.IGNORECASE)
    if not match:
        return None
    return " ".join(match.group("country").split())


def _compact_review(review: dict[str, Any] | None) -> dict[str, Any] | None:
    if review is None:
        return None
    return {
        "review_id": review.get("review_id", ""),
        "author": review.get("author", ""),
        "rating": review.get("rating"),
        "title": review.get("title", ""),
        "body": review.get("body", ""),
    }


def _rating_value(review: dict[str, Any], *, default: float) -> float:
    rating = review.get("rating")
    if isinstance(rating, int | float):
        return float(rating)
    return default


def build_comments_summary(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    if not reviews:
        return {
            "extracted_review_count": 0,
            "average_rating": None,
            "rating_histogram": {},
            "verified_purchase_count": 0,
            "source_countries": {},
            "positive_terms": [],
            "critical_terms": [],
            "representative_positive_review": None,
            "representative_critical_review": None,
        }

    ratings = [float(review["rating"]) for review in reviews if isinstance(review.get("rating"), int | float)]
    rating_histogram: dict[str, int] = {}
    for rating in ratings:
        key = str(int(rating))
        rating_histogram[key] = rating_histogram.get(key, 0) + 1

    countries: dict[str, int] = {}
    for review in reviews:
        country = _country_from_review_date(str(review.get("date", "")))
        if country:
            countries[country] = countries.get(country, 0) + 1

    positive_terms = _term_counts(reviews, POSITIVE_TERM_ALIASES)
    critical_terms = _term_counts(reviews, CRITICAL_TERM_ALIASES)
    critical_term_names = {item["term"] for item in critical_terms}

    positive_candidates = [review for review in reviews if _rating_value(review, default=0.0) >= 4.0]
    representative_positive = max(
        positive_candidates or reviews,
        key=lambda review: (
            _rating_value(review, default=0.0),
            len(str(review.get("body", ""))),
            str(review.get("review_id", "")),
        ),
    )

    critical_candidates = [
        review
        for review in reviews
        if any(
            any(alias in _review_text(review) for alias in CRITICAL_TERM_ALIASES[term])
            for term in critical_term_names
        )
    ]
    representative_critical = min(
        critical_candidates or reviews,
        key=lambda review: (
            _rating_value(review, default=6.0),
            -len(str(review.get("body", ""))),
            str(review.get("review_id", "")),
        ),
    )

    return {
        "extracted_review_count": len(reviews),
        "average_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "rating_histogram": dict(sorted(rating_histogram.items(), key=lambda item: int(item[0]), reverse=True)),
        "verified_purchase_count": sum(1 for review in reviews if review.get("verified_purchase")),
        "source_countries": dict(sorted(countries.items())),
        "positive_terms": positive_terms,
        "critical_terms": critical_terms,
        "representative_positive_review": _compact_review(representative_positive),
        "representative_critical_review": _compact_review(representative_critical),
    }


def _model_token(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _model_common_prefix(left: str, right: str) -> int:
    count = 0
    for left_char, right_char in zip(left, right, strict=False):
        if left_char != right_char:
            break
        count += 1
    return count


def _infer_resolved_model(record: ProductRecord, requested_model: str | None = None) -> str | None:
    for value in (
        record.specs_normalized.get("model_number"),
        record.specs_normalized.get("model_name"),
        find_spec_value(record.specs, "Model Number", "Model Name", "Manufacturer Part Number", "Modelo"),
    ):
        if value:
            return str(value)

    requested_token = _model_token(requested_model)
    candidates = [
        token
        for token in re.findall(r"\b[A-Z0-9][A-Z0-9.-]{4,}\b", record.title.upper())
        if any(char.isdigit() for char in token) and any(char.isalpha() for char in token)
    ]
    if not candidates:
        return None
    if requested_token:
        return max(candidates, key=lambda token: (_model_common_prefix(_model_token(token), requested_token), len(token)))
    return candidates[0]


def _model_match_kind(requested_model: str, resolved_model: str | None) -> str:
    requested_token = _model_token(requested_model)
    resolved_token = _model_token(resolved_model)
    if not requested_token or not resolved_token:
        return "unknown"
    if requested_token == resolved_token:
        return "exact"
    common_prefix = _model_common_prefix(requested_token, resolved_token)
    if common_prefix >= min(7, len(requested_token), len(resolved_token)):
        return "variant"
    return "different"


def _safe_page_stop_reason(page_number: int, reason: object) -> str:
    message = " ".join(str(reason).split()) or reason.__class__.__name__
    return f"page_{page_number}: {message[:120]}"


class AmazonService:
    def __init__(
        self,
        resolver: GeminiIntentResolver | None = None,
        session_store: BrowserSessionStore | None = None,
        recovery_headless: bool = True,
    ) -> None:
        self.resolver = resolver or GeminiIntentResolver()
        self.session_store = session_store or BrowserSessionStore()
        self.bootstrapper = BrowserSessionBootstrapper(self.session_store)
        self.recovery_headless = recovery_headless

    def _scraper(self, marketplace: str, portal: str = "retail") -> AmazonScraper:
        return AmazonScraper(marketplace, session=self.session_store.load(marketplace, portal=portal))

    def _detail_target_records(self, records: list, profile) -> list:
        ranked = rank_records(list(records), profile)
        if ranked:
            return ranked[:DETAIL_FETCH_LIMIT]

        allowed_brands = {normalize_text(profile.canonical_brand)}
        if profile.mode == IntentMode.SIMILAR:
            allowed_brands.update(normalize_text(item.get("brand", "")) for item in profile.similar_families)
        filtered = [record for record in records if normalize_text(record.brand) in allowed_brands]
        return filtered[:DETAIL_FETCH_LIMIT]

    def _enrich_records_with_detail_targets(self, scraper: AmazonScraper, records: list, detail_targets: list) -> list:
        enriched_by_asin = {record.asin: record for record in records}

        for record in detail_targets:
            try:
                detail = scraper.get(record.url or record.asin)
            except AmazonBlockedError:
                continue
            except Exception:  # noqa: BLE001
                continue

            enriched_by_asin[record.asin] = replace(
                detail,
                asin=record.asin or detail.asin,
                url=record.url or detail.url,
                marketplace=record.marketplace,
                is_sponsored=record.is_sponsored,
                price=detail.price if detail.price is not None else record.price,
                currency=detail.currency or record.currency,
                prime=detail.prime or record.prime,
                seller_summary=detail.seller_summary or record.seller_summary,
                review_count=max(detail.review_count, record.review_count),
                rating=detail.rating if detail.rating is not None else record.rating,
            )

        return list(enriched_by_asin.values())

    def _enrich_with_detail_pass(self, scraper: AmazonScraper, records: list, profile) -> list:
        return self._enrich_records_with_detail_targets(
            scraper,
            records,
            self._detail_target_records(records, profile),
        )

    def _enrich_plain_records(self, scraper: AmazonScraper, records: list) -> list:
        ranked = rank_plain_records(list(records))
        return self._enrich_records_with_detail_targets(scraper, records, ranked[:DETAIL_FETCH_LIMIT])

    def _add_exact_model_disclosures(self, records: list[ProductRecord], requested_model: str | None) -> list[ProductRecord]:
        if not requested_model:
            return records
        for record in records:
            resolved_model = _infer_resolved_model(record, requested_model)
            match_kind = _model_match_kind(requested_model, resolved_model)
            record.requested_model = requested_model
            record.resolved_model = resolved_model
            record.model_match = match_kind
            if resolved_model:
                record.model_disclosure = (
                    f"Requested {requested_model}; resolved listing model {resolved_model} ({match_kind})."
                )
            else:
                record.model_disclosure = f"Requested {requested_model}; no listing model could be resolved."
        return records

    def _apply_price_filter(
        self,
        records: list,
        *,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> list:
        if min_price is None and max_price is None:
            return list(records)

        filtered = []
        for record in records:
            if record.price is None:
                continue
            if min_price is not None and record.price < min_price:
                continue
            if max_price is not None and record.price > max_price:
                continue
            filtered.append(record)
        return filtered

    def _apply_plain_filters(
        self,
        records: list,
        *,
        brand: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> list:
        filtered = list(records)
        if brand:
            normalized_brand = normalize_text(brand)
            filtered = [record for record in filtered if normalize_text(record.brand) == normalized_brand]
        return self._apply_price_filter(filtered, min_price=min_price, max_price=max_price)

    def _session_is_usable(self, marketplace: str, target_url: str, *, portal: str = "retail") -> bool:
        session = self.session_store.load(marketplace, portal=portal)
        if session is None:
            return False
        client = AmazonHttpClient(get_marketplace(marketplace), session=session)
        try:
            html = client.fetch_url(target_url)
        except Exception:  # noqa: BLE001
            return False
        return not is_probably_blocked_html(html) and not is_probably_sign_in_html(html)

    def _session_login_hint(self, marketplace: str, portal: str) -> str:
        return f"Run `amazon-cli session login --marketplace {marketplace} --portal {portal}`."

    def _records_from_bootstrap_payload(self, scraper: AmazonScraper, payload: dict, *, source_url: str) -> SearchPage | None:
        page_html = payload.get("page_html")
        if not isinstance(page_html, str) or not page_html.strip():
            return None
        parser = getattr(scraper, "parser", None)
        if parser is None:
            return None
        try:
            return parser.parse_search_page(page_html, source_url=source_url)
        except AmazonBlockedError:
            return None

    def _bootstrap_search_page(
        self,
        marketplace: str,
        search_url: str,
        *,
        base: str,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        page: int = 1,
        portal: str = "retail",
        bootstrap_kwargs: dict[str, Any] | None = None,
    ) -> tuple[AmazonScraper, SearchPage]:
        attempts = [self.recovery_headless]
        if self.recovery_headless:
            attempts.append(False)

        last_scraper = self._scraper(marketplace, portal=portal)
        bootstrap_kwargs = dict(bootstrap_kwargs or {})
        for headless in attempts:
            payload = self.bootstrapper.capture_page(
                marketplace,
                search_url,
                portal=portal,
                headless=headless,
            )
            last_scraper = self._scraper(marketplace, portal=portal)
            parsed_page = self._records_from_bootstrap_payload(last_scraper, payload, source_url=search_url)
            if parsed_page is not None and parsed_page.records:
                return last_scraper, parsed_page
            try:
                page_result = last_scraper.search_page(
                    base,
                    brand=brand,
                    model=model,
                    min_price=min_price,
                    max_price=max_price,
                    page=page,
                    url=search_url,
                )
            except AmazonBlockedError:
                page_result = SearchPage(records=[], current_page=page, source_url=search_url)
            if page_result.records:
                return last_scraper, page_result

        raise BrowserSessionError("Amazon search returned no results after browser session initialization.")

    def _search_page_with_recovery(
        self,
        marketplace: str,
        *,
        base: str,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        page: int = 1,
        url: str | None = None,
        portal: str = "retail",
        bootstrap_kwargs: dict[str, Any] | None = None,
    ) -> tuple[AmazonScraper, SearchPage]:
        current_session = self.session_store.load(marketplace, portal=portal)
        had_session = current_session is not None
        scraper = self._scraper(marketplace, portal=portal)
        search_url = url or scraper.build_search_url(
            base,
            brand=brand,
            model=model,
            min_price=min_price,
            max_price=max_price,
            page=page,
        )

        try:
            page_result = scraper.search_page(
                base,
                brand=brand,
                model=model,
                min_price=min_price,
                max_price=max_price,
                page=page,
                url=search_url,
            )
        except AmazonBlockedError as exc:
            try:
                return self._bootstrap_search_page(
                    marketplace,
                    search_url,
                    base=base,
                    brand=brand,
                    model=model,
                    min_price=min_price,
                    max_price=max_price,
                    page=page,
                    portal=portal,
                    bootstrap_kwargs=bootstrap_kwargs,
                )
            except BrowserSessionError:
                raise exc

        if page_result.records:
            return scraper, page_result

        if (
            had_session
            and current_session is not None
            and current_session.session_source == "managed_profile"
            and self._session_is_usable(marketplace, search_url, portal=portal)
        ):
            return scraper, page_result

        return self._bootstrap_search_page(
            marketplace,
            search_url,
            base=base,
            brand=brand,
            model=model,
            min_price=min_price,
            max_price=max_price,
            page=page,
            portal=portal,
            bootstrap_kwargs=bootstrap_kwargs,
        )

    def _bootstrap_review_page(
        self,
        marketplace: str,
        review_url: str,
        *,
        identifier: str,
        page: int = 1,
        portal: str = "retail",
        bootstrap_kwargs: dict[str, Any] | None = None,
    ):
        attempts = [self.recovery_headless]
        if self.recovery_headless:
            attempts.append(False)

        last_scraper = self._scraper(marketplace, portal=portal)
        bootstrap_kwargs = dict(bootstrap_kwargs or {})
        for headless in attempts:
            payload = self.bootstrapper.capture_page(
                marketplace,
                review_url,
                portal=portal,
                headless=headless,
            )
            last_scraper = self._scraper(marketplace, portal=portal)
            page_html = payload.get("page_html")
            parsed_page = None
            parser = getattr(last_scraper, "parser", None)
            if parser is not None and isinstance(page_html, str) and page_html.strip():
                try:
                    parsed_page = parser.parse_review_page(
                        page_html,
                        source_url=review_url,
                        final_url=payload.get("final_url"),
                    )
                except AmazonBlockedError:
                    parsed_page = None
            if parsed_page is not None and (parsed_page.reviews or parsed_page.sign_in_required):
                return last_scraper, parsed_page
            try:
                page_result = last_scraper.review_page(identifier, page=page, url=review_url)
            except AmazonBlockedError:
                page_result = None
            if page_result is not None and (page_result.reviews or page_result.sign_in_required):
                return last_scraper, page_result

        raise BrowserSessionError("Amazon review collection page was not usable after browser session initialization.")

    def _review_page_with_recovery(
        self,
        marketplace: str,
        *,
        identifier: str,
        page: int = 1,
        url: str | None = None,
        portal: str = "retail",
        bootstrap_kwargs: dict[str, Any] | None = None,
    ):
        current_session = self.session_store.load(marketplace, portal=portal)
        had_session = current_session is not None
        scraper = self._scraper(marketplace, portal=portal)
        review_url = url or scraper.build_reviews_url(identifier, page=page)

        try:
            page_result = scraper.review_page(identifier, page=page, url=review_url)
        except AmazonBlockedError as exc:
            try:
                return self._bootstrap_review_page(
                    marketplace,
                    review_url,
                    identifier=identifier,
                    page=page,
                    portal=portal,
                    bootstrap_kwargs=bootstrap_kwargs,
                )
            except BrowserSessionError:
                raise exc

        if page_result.reviews or page_result.sign_in_required:
            return scraper, page_result

        if (
            had_session
            and current_session is not None
            and current_session.session_source == "managed_profile"
            and self._session_is_usable(marketplace, review_url, portal=portal)
        ):
            return scraper, page_result

        return self._bootstrap_review_page(
            marketplace,
            review_url,
            identifier=identifier,
            page=page,
            portal=portal,
            bootstrap_kwargs=bootstrap_kwargs,
        )

    def _merge_records(self, records: list[ProductRecord]) -> list[ProductRecord]:
        merged: dict[str, ProductRecord] = {}
        for record in records:
            existing = merged.get(record.asin)
            if existing is None:
                merged[record.asin] = record
                continue
            merged[record.asin] = replace(
                existing,
                url=existing.url or record.url,
                title=existing.title if len(existing.title) >= len(record.title) else record.title,
                brand=existing.brand or record.brand,
                price=existing.price if existing.price is not None else record.price,
                currency=existing.currency or record.currency,
                prime=existing.prime or record.prime,
                seller_summary=existing.seller_summary or record.seller_summary,
                review_count=max(existing.review_count, record.review_count),
                rating=existing.rating if existing.rating is not None else record.rating,
                brand_store_present=existing.brand_store_present or record.brand_store_present,
                is_sponsored=existing.is_sponsored and record.is_sponsored,
                specs=existing.specs or record.specs,
                specs_normalized=existing.specs_normalized or record.specs_normalized,
            )
        return list(merged.values())

    def _search_pages_with_recovery(
        self,
        marketplace: str,
        *,
        base: str,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        pages: int = 1,
    ) -> tuple[AmazonScraper, list[ProductRecord], dict[str, Any]]:
        scraper, first_page = self._search_page_with_recovery(
            marketplace,
            base=base,
            brand=brand,
            model=model,
            min_price=min_price,
            max_price=max_price,
            page=1,
        )
        fetched_pages = 1
        partial = False
        stopped_reason: str | None = None
        combined_records = list(first_page.records)
        next_page_url = first_page.next_page_url

        for page_number in range(2, pages + 1):
            target_url = next_page_url or scraper.build_search_url(
                base,
                brand=brand,
                model=model,
                min_price=min_price,
                max_price=max_price,
                page=page_number,
            )
            try:
                scraper, page_result = self._search_page_with_recovery(
                    marketplace,
                    base=base,
                    brand=brand,
                    model=model,
                    min_price=min_price,
                    max_price=max_price,
                    page=page_number,
                    url=target_url,
                )
            except (AmazonBlockedError, BrowserSessionError) as exc:
                partial = True
                stopped_reason = f"page_{page_number}: {exc}"
                break

            fetched_pages += 1
            combined_records.extend(page_result.records)
            next_page_url = page_result.next_page_url

            if not page_result.records and page_result.next_page_url is None and page_number < pages:
                stopped_reason = f"Reached last available page at {page_number}."
                break

        return scraper, self._merge_records(combined_records), {
            "pages_requested": pages,
            "pages_fetched": fetched_pages,
            "partial": partial,
            "stopped_reason": stopped_reason,
        }

    def search(
        self,
        base: str,
        marketplace: str,
        refresh_intent: bool,
        mode: str,
        *,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        pages: int = 1,
    ) -> dict:
        filters = {
            "base": base,
            "brand": brand,
            "model": model,
            "min_price": min_price,
            "max_price": max_price,
        }
        scraper, records, pagination = self._search_pages_with_recovery(
            marketplace,
            base=base,
            brand=brand,
            model=model,
            min_price=min_price,
            max_price=max_price,
            pages=pages,
        )

        if mode == "plain":
            filtered_records = self._apply_plain_filters(
                records,
                brand=brand,
                min_price=min_price,
                max_price=max_price,
            )
            enriched_records = self._enrich_plain_records(scraper, filtered_records)
            final_records = self._apply_plain_filters(
                enriched_records,
                brand=brand,
                min_price=min_price,
                max_price=max_price,
            )
            ranked = rank_plain_records(final_records)
            profile = None
        else:
            structured_query = compose_search_query(base, brand=brand, model=model)
            intent_mode = IntentMode(mode)
            profile = self.resolver.resolve(structured_query, marketplace, intent_mode, refresh=refresh_intent)
            enriched_records = self._enrich_with_detail_pass(scraper, records, profile)
            final_records = self._apply_price_filter(
                enriched_records,
                min_price=min_price,
                max_price=max_price,
            )
            ranked = rank_records(final_records, profile)
            if mode == "exact":
                ranked = self._add_exact_model_disclosures(ranked, model)

        return {
            "command": "search",
            "query": base,
            "marketplace": marketplace,
            "mode": mode,
            "filters": filters,
            "pagination": pagination,
            "intent": profile.to_dict() if profile is not None else None,
            "results": [record.to_dict(include_specs=False) for record in ranked],
        }

    def get(self, identifier: str, marketplace: str) -> dict:
        resolved_marketplace = marketplace_from_identifier(identifier, marketplace)
        scraper = self._scraper(resolved_marketplace)
        item = scraper.get(identifier)
        return {"command": "get", "marketplace": resolved_marketplace, "item": item.to_dict()}

    def _normalize_offer_marketplaces(self, marketplaces: list[str] | None) -> list[str]:
        requested = marketplaces or DEFAULT_OFFER_MARKETPLACES
        normalized: list[str] = []
        for marketplace in requested:
            code = marketplace.strip().lower()
            if not code:
                continue
            get_marketplace(code)
            if code not in normalized:
                normalized.append(code)
        return normalized

    def _fetch_offer(self, target_marketplace: str, asin: str, *, portal: str = "retail") -> OfferRecord:
        market = get_marketplace(target_marketplace)
        url = build_offer_url(asin, target_marketplace)
        session = self.session_store.load(target_marketplace, portal=portal)
        client = AmazonHttpClient(market, session=session)
        try:
            html, final_url = client.fetch_url_details(url)
        except Exception as exc:  # noqa: BLE001
            return OfferRecord(
                marketplace=target_marketplace,
                domain=market.domain,
                url=url,
                asin=asin,
                currency=market.currency,
                status="fetch_failed",
                failure_reason=str(exc),
            )

        if is_probably_blocked_html(html):
            return OfferRecord(
                marketplace=target_marketplace,
                domain=market.domain,
                url=final_url or url,
                asin=asin,
                currency=market.currency,
                status="blocked",
                failure_reason="Amazon returned a blocked or captcha page.",
            )
        if is_probably_sign_in_html(html):
            return OfferRecord(
                marketplace=target_marketplace,
                domain=market.domain,
                url=final_url or url,
                asin=asin,
                currency=market.currency,
                status="sign_in_required",
                failure_reason="Amazon returned a sign-in page.",
            )
        return parse_offer_html(html, marketplace=target_marketplace, asin=asin, url=final_url or url)

    def offers(
        self,
        identifier: str,
        marketplace: str,
        *,
        portal: str = "retail",
        marketplaces: list[str] | None = None,
        include_shipping: bool = True,
    ) -> dict:
        make_session_key(marketplace, portal)
        resolved_marketplace = marketplace_from_identifier(identifier, marketplace)
        asin = extract_asin(identifier)
        if not asin:
            raise ValueError(f"Could not determine ASIN from identifier: {identifier}")

        target_marketplaces = self._normalize_offer_marketplaces(marketplaces)
        indexed_offers: list[tuple[int, OfferRecord]] = []
        for index, target_marketplace in enumerate(target_marketplaces):
            indexed_offers.append((index, self._fetch_offer(target_marketplace, asin, portal=portal)))

        def rank_key(item: tuple[int, OfferRecord]) -> tuple[int, float, int]:
            index, offer = item
            if offer.status != "ok" or offer.price is None:
                return (1, float("inf"), index)
            value = offer.total if include_shipping else offer.price
            return (0, value if value is not None else float("inf"), index)

        sorted_offers = [offer for _, offer in sorted(indexed_offers, key=rank_key)]
        ok_offers = [offer for offer in sorted_offers if offer.status == "ok" and offer.price is not None]
        failures = [offer for offer in sorted_offers if offer.status != "ok"]
        current_offer = next((offer for offer in sorted_offers if offer.marketplace == resolved_marketplace), None)
        best_offer = ok_offers[0] if ok_offers else None

        return {
            "command": "offers",
            "marketplace": resolved_marketplace,
            "portal": portal,
            "asin": asin,
            "include_shipping": include_shipping,
            "requested_marketplaces": target_marketplaces,
            "best_offer": best_offer.to_dict() if best_offer is not None else None,
            "current_offer": current_offer.to_dict() if current_offer is not None else None,
            "offers": [offer.to_dict() for offer in sorted_offers],
            "failures": [offer.to_dict() for offer in failures],
        }

    def reviews(
        self,
        identifier: str,
        marketplace: str,
        limit: int | None = None,
        *,
        portal: str = "retail",
        user_data_dir: str | None = None,
        profile_directory: str | None = None,
        isolated: bool = False,
    ) -> dict:
        make_session_key(marketplace, portal)
        resolved_marketplace = marketplace_from_identifier(identifier, marketplace)
        scraper = self._scraper(resolved_marketplace, portal=portal)
        item = scraper.get(identifier)
        review_url = scraper.build_reviews_url(identifier)
        bootstrap_kwargs: dict[str, Any] = {"portal": portal}
        login_hint = self._session_login_hint(resolved_marketplace, portal)

        fallback_reason: str | None = None
        reviews_source = "product_reviews"
        deep_reviews_available = True
        session_status = "usable"
        session_hint: str | None = None
        pages_fetched = 0
        stopped_reason: str | None = None
        partial = False
        final_url = review_url
        available_review_count = 0
        pagination_diagnostics: dict[str, Any] = {
            "ajax_requests": 0,
            "ajax_failures": 0,
            "duplicate_reviews_skipped": 0,
            "last_page_attempted": 0,
            "had_continuation_token": False,
        }

        existing_session = self.session_store.load(resolved_marketplace, portal=portal)
        if existing_session is None or existing_session.session_source != "managed_profile":
            session_status = "missing"
            session_hint = login_hint
            fallback_reason = f"Managed {portal} session is missing. {login_hint}"
            reviews = list(item.top_reviews if limit is None else item.top_reviews[:limit])
            return {
                "command": "reviews",
                "marketplace": resolved_marketplace,
                "portal": portal,
                "asin": item.asin,
                "limit": limit,
                "item": item.to_dict(include_specs=False),
                "review_insights": item.review_insights,
                "reviews_source": "product_detail_fallback",
                "deep_reviews_available": False,
                "session_status": session_status,
                "session_hint": session_hint,
                "session_source": existing_session.session_source if existing_session is not None else None,
                "final_url": final_url,
                "available_review_count": available_review_count,
                "fallback_reason": fallback_reason,
                "pagination": {
                    "pages_fetched": pages_fetched,
                    "partial": partial,
                    "stopped_reason": "missing_managed_session",
                    "diagnostics": pagination_diagnostics,
                },
                "comments_summary": build_comments_summary(reviews),
                "reviews": reviews,
            }

        reviews: list[dict[str, Any]]
        try:
            scraper, first_page = self._review_page_with_recovery(
                resolved_marketplace,
                identifier=identifier,
                page=1,
                url=review_url,
                portal=portal,
                bootstrap_kwargs=bootstrap_kwargs,
            )
            final_url = first_page.final_url or first_page.source_url or final_url
            if first_page.sign_in_required:
                deep_reviews_available = False
                reviews_source = "product_detail_fallback"
                session_status = "expired"
                session_hint = login_hint
                fallback_reason = "Amazon review collection page requires sign in."
                reviews = list(item.top_reviews if limit is None else item.top_reviews[:limit])
                stopped_reason = "expired_managed_session"
            else:
                target_limit = limit if limit is not None else len(first_page.reviews)
                available_review_count = first_page.available_review_count
                reviews = []
                seen_review_ids: set[str] = set()

                def append_unique_reviews(candidates: list[dict[str, Any]]) -> None:
                    for review in candidates:
                        review_id = str(review.get("review_id") or "")
                        if review_id and review_id in seen_review_ids:
                            pagination_diagnostics["duplicate_reviews_skipped"] += 1
                            continue
                        if review_id:
                            seen_review_ids.add(review_id)
                        reviews.append(review)
                        if len(reviews) >= target_limit:
                            break

                append_unique_reviews(first_page.reviews)
                pages_fetched = 1
                next_page_url = first_page.next_page_url
                next_page_state = dict(first_page.next_page_state)
                pagination_diagnostics["had_continuation_token"] = bool(next_page_state or next_page_url)
                pagination_diagnostics["last_page_attempted"] = 1
                page_number = 2
                while len(reviews) < target_limit and (next_page_state or next_page_url):
                    pagination_diagnostics["last_page_attempted"] = page_number
                    if next_page_state:
                        pagination_diagnostics["ajax_requests"] += 1
                        try:
                            page_result = scraper.review_ajax_page(next_page_state, source_url=final_url)
                        except (AmazonBlockedError, BrowserSessionError, ValueError) as exc:
                            pagination_diagnostics["ajax_failures"] += 1
                            partial = True
                            stopped_reason = _safe_page_stop_reason(page_number, exc)
                            break
                    else:
                        try:
                            scraper, page_result = self._review_page_with_recovery(
                                resolved_marketplace,
                                identifier=identifier,
                                page=page_number,
                                url=next_page_url,
                                portal=portal,
                                bootstrap_kwargs=bootstrap_kwargs,
                            )
                        except (AmazonBlockedError, BrowserSessionError, ValueError) as exc:
                            partial = True
                            stopped_reason = _safe_page_stop_reason(page_number, exc)
                            break
                    final_url = page_result.final_url or page_result.source_url or final_url
                    if page_result.sign_in_required:
                        session_status = "expired"
                        session_hint = login_hint
                        partial = True
                        stopped_reason = f"page_{page_number}: sign_in_required"
                        break
                    pages_fetched += 1
                    if page_result.available_review_count:
                        available_review_count = page_result.available_review_count
                    append_unique_reviews(page_result.reviews)
                    next_page_url = page_result.next_page_url
                    if page_result.next_page_state:
                        next_page_state = {**next_page_state, **page_result.next_page_state}
                        pagination_diagnostics["had_continuation_token"] = True
                    else:
                        next_page_state = {}
                    page_number += 1
                reviews = reviews[:target_limit]
                if len(reviews) < target_limit and stopped_reason is None and not next_page_url and not next_page_state:
                    stopped_reason = "Reached last available review page."
        except (AmazonBlockedError, BrowserSessionError, ValueError) as exc:
            deep_reviews_available = False
            reviews_source = "product_detail_fallback"
            session_status = "blocked" if isinstance(exc, AmazonBlockedError) else "expired"
            session_hint = login_hint
            fallback_reason = str(exc)
            if limit is None:
                reviews = list(item.top_reviews)
            else:
                reviews = list(item.top_reviews[:limit])

        session = self.session_store.load(resolved_marketplace, portal=portal)
        comments_summary = build_comments_summary(reviews)
        if available_review_count:
            comments_summary["available_review_count"] = available_review_count
        return {
            "command": "reviews",
            "marketplace": resolved_marketplace,
            "portal": portal,
            "asin": item.asin,
            "limit": limit,
            "item": item.to_dict(include_specs=False),
            "review_insights": item.review_insights,
            "reviews_source": reviews_source,
            "deep_reviews_available": deep_reviews_available,
            "session_status": session_status,
            "session_hint": session_hint,
            "session_source": session.session_source if session is not None else None,
            "final_url": final_url,
            "available_review_count": available_review_count,
            "fallback_reason": fallback_reason,
            "pagination": {
                "pages_fetched": pages_fetched,
                "partial": partial,
                "stopped_reason": stopped_reason,
                "diagnostics": pagination_diagnostics,
            },
            "comments_summary": comments_summary,
            "reviews": reviews,
        }

    def _compare_value_rows(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        base_fields = [
            ("title", "Title"),
            ("brand", "Brand"),
            ("price", "Price"),
            ("currency", "Currency"),
            ("prime", "Prime"),
            ("seller_summary", "Seller"),
            ("rating", "Rating"),
            ("review_count", "Review count"),
        ]
        normalized_field_labels = {
            "brand_name": "Brand name",
            "model_name": "Model name",
            "model_number": "Model number",
            "manufacturer": "Manufacturer",
            "capacity_l": "Capacity (L)",
            "microwave_power_w": "Microwave power (W)",
            "grill": "Grill",
            "grill_power_w": "Grill power (W)",
            "convection": "Convection",
            "power_levels": "Power levels",
            "defrost": "Defrost",
            "timer_minutes": "Timer (minutes)",
            "dimensions_cm": "Dimensions (cm)",
            "weight_kg": "Weight (kg)",
            "turntable_cm": "Turntable (cm)",
            "install_type": "Install type",
            "control_type": "Control type",
            "color": "Color",
        }

        rows: list[dict[str, Any]] = []
        item_keys = [f"{item['marketplace']}:{item['asin']}" for item in items]
        for field_name, label in base_fields:
            values = {
                item_key: item.get(field_name)
                for item_key, item in zip(item_keys, items, strict=False)
            }
            rows.append({"field": field_name, "label": label, "values": values})

        normalized_fields: list[str] = []
        for item in items:
            normalized_fields.extend(item.get("specs_normalized", {}).keys())
        for field_name in dict.fromkeys(normalized_fields):
            values = {
                item_key: item.get("specs_normalized", {}).get(field_name)
                for item_key, item in zip(item_keys, items, strict=False)
            }
            rows.append(
                {
                    "field": field_name,
                    "label": normalized_field_labels.get(field_name, field_name.replace("_", " ").title()),
                    "values": values,
                }
            )
        return rows

    def compare(self, identifiers: list[str], marketplace: str) -> dict:
        items = []
        marketplaces: list[str] = []
        for identifier in identifiers:
            resolved_marketplace = marketplace_from_identifier(identifier, marketplace, strict_url=True)
            scraper = self._scraper(resolved_marketplace)
            item = scraper.get(identifier).to_dict()
            items.append(item)
            if resolved_marketplace not in marketplaces:
                marketplaces.append(resolved_marketplace)
        comparison_marketplace = marketplaces[0] if len(marketplaces) == 1 else None
        return {
            "command": "compare",
            "marketplace": comparison_marketplace,
            "marketplaces": marketplaces,
            "items": items,
            "comparison_rows": self._compare_value_rows(items),
        }

    def bootstrap_session(
        self,
        marketplace: str,
        browser_executable: str | None,
        headless: bool,
        url: str | None,
        *,
        portal: str = "retail",
        user_data_dir: str | None = None,
        profile_directory: str | None = None,
        isolated: bool = False,
    ) -> dict:
        return self.bootstrapper.login(
            marketplace,
            browser_executable,
            portal=portal,
            headless=headless,
            url=url,
        )
