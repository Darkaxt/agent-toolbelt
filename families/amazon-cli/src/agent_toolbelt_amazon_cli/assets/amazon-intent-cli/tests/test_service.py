from datetime import UTC, datetime
import json

from amazon_intent_cli.models import BrowserSession, IntentMode, IntentProfile, ProductRecord, ReviewPage, SearchPage
from amazon_intent_cli.offers import OfferRecord
from amazon_intent_cli.service import AmazonService, build_comments_summary
from amazon_intent_cli.session import BrowserSessionError


def build_record(
    asin: str,
    title: str,
    brand: str,
    *,
    price: float | None = None,
    reviews: int = 0,
    rating: float | None = None,
    sponsored: bool = False,
) -> ProductRecord:
    return ProductRecord(
        asin=asin,
        url=f"https://www.amazon.de/dp/{asin}",
        title=title,
        brand=brand,
        marketplace="de",
        price=price,
        currency="EUR",
        prime=True,
        review_count=reviews,
        rating=rating,
        is_sponsored=sponsored,
    )


class FailingResolver:
    def resolve(self, query: str, marketplace: str, mode: IntentMode, *, refresh: bool = False) -> IntentProfile:
        raise AssertionError("Resolver should not be called")


class StaticResolver:
    def __init__(self, profile: IntentProfile) -> None:
        self.profile = profile
        self.calls: list[tuple[str, str, IntentMode, bool]] = []

    def resolve(self, query: str, marketplace: str, mode: IntentMode, *, refresh: bool = False) -> IntentProfile:
        self.calls.append((query, marketplace, mode, refresh))
        return self.profile


class MemorySessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, object] = {}

    def load(self, marketplace: str, portal: str = "retail"):
        return self.sessions.get(f"{marketplace}:{portal}") or self.sessions.get(marketplace)

    def save(self, session) -> None:
        key = getattr(session, "session_key", None) or f"{session.marketplace}:{getattr(session, 'portal', 'retail')}"
        self.sessions[key] = session


def managed_session(marketplace: str = "de", portal: str = "retail") -> BrowserSession:
    return BrowserSession(
        marketplace=marketplace,
        browser_executable=r"C:\Chrome\chrome.exe",
        user_agent="Mozilla/5.0 Managed",
        cookies=[{"name": "session-id", "value": "abc", "domain": f".amazon.{marketplace}", "path": "/"}],
        portal=portal,
        session_key=f"{marketplace}:{portal}",
        session_source="managed_profile",
        profile_dir=fr"C:\amazon-intent-cli\browser-profiles\{marketplace}__{portal}",
        final_url=f"https://www.amazon.{marketplace}/",
    )


class DummyBootstrapper:
    def __init__(self, store: MemorySessionStore) -> None:
        self.store = store
        self.calls: list[tuple] = []

    def login(
        self,
        marketplace: str,
        browser_executable: str | None,
        *,
        portal: str = "retail",
        headless: bool = False,
        url: str | None = None,
    ) -> dict:
        self.calls.append(("login", marketplace, portal, browser_executable, headless, url))
        self.store.save(managed_session(marketplace))
        return {
            "command": "session.bootstrap",
            "marketplace": marketplace,
            "portal": portal,
            "usable": True,
            "session_source": "managed_profile",
            "session_key": f"{marketplace}:{portal}",
            "final_url": url,
        }

    def bootstrap(self, marketplace: str, browser_executable: str | None, **kwargs) -> dict:
        return self.login(marketplace, browser_executable, **kwargs)

    def capture_page(
        self,
        marketplace: str,
        url: str,
        *,
        portal: str = "retail",
        headless: bool = True,
    ) -> dict:
        self.calls.append(("capture_page", marketplace, portal, headless, url))
        self.store.save(managed_session(marketplace))
        return {
            "page_html": "<html></html>",
            "final_url": url,
            "session_source": "managed_profile",
            "session_key": f"{marketplace}:{portal}",
        }


class DummyScraper:
    def __init__(
        self,
        session,
        first_records: list[ProductRecord],
        second_records: list[ProductRecord],
        page_records: dict[int, list[ProductRecord]] | None = None,
        review_pages: dict[int, list[dict]] | None = None,
        review_page_states: dict[int, dict] | None = None,
        review_sign_in: bool = False,
    ) -> None:
        self.session = session
        self.first_records = first_records
        self.second_records = second_records
        self.page_records = page_records
        self.review_pages = review_pages or {}
        self.review_page_states = review_page_states or {}
        self.review_sign_in = review_sign_in

    def build_search_url(
        self,
        base: str,
        *,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        page: int | None = None,
    ) -> str:
        parts = [part for part in (base, brand, model) if part]
        suffix = f"&page={page}" if page and page > 1 else ""
        return "https://www.amazon.de/s?k=" + "+".join(parts) + suffix

    def search_page(
        self,
        base: str,
        *,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        page: int = 1,
        url: str | None = None,
    ) -> SearchPage:
        if self.page_records is None:
            current = list(self.second_records if self.session is not None else self.first_records)
            available_pages = [1]
        else:
            current = list(self.page_records.get(page, []))
            available_pages = sorted(self.page_records)
        next_page_url = None
        if self.page_records is not None and (page + 1) in self.page_records:
            next_page_url = f"https://www.amazon.de/s?k={base}&page={page + 1}&ref=sr_pg_{page + 1}"
        return SearchPage(
            records=current,
            current_page=page,
            available_pages=available_pages,
            next_page_url=next_page_url,
            source_url=url or self.build_search_url(
                base,
                brand=brand,
                model=model,
                min_price=min_price,
                max_price=max_price,
            ),
        )

    def search(
        self,
        base: str,
        *,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> list[ProductRecord]:
        return list(self.second_records if self.session is not None else self.first_records)

    def get(self, identifier: str) -> ProductRecord:
        asin = identifier.rsplit("/", 1)[-1]
        for record in [*self.first_records, *self.second_records]:
            if record.asin == asin:
                return record
        marketplace = "fr" if "amazon.fr" in identifier else "es" if "amazon.es" in identifier else "de"
        if "B0GOOD" in identifier:
            record = build_record(
                "B0GOOD",
                "LG OLED55C47LA TV",
                "LG",
                price=549.0,
                reviews=1500,
                rating=4.5,
            )
            record.marketplace = marketplace
            return record
        if "B0FQP6YQJG" in identifier:
            record = build_record(
                "B0FQP6YQJG",
                "LG OLED65C54LA - EVO AI C5 OLED Smart TV",
                "LG",
                price=1399.0,
                reviews=51,
                rating=4.6,
            )
            record.marketplace = marketplace
            record.specs = {"Model Number": "OLED65C54LA"}
            record.specs_normalized = {"model_number": "OLED65C54LA"}
            return record
        record = build_record(
            asin,
            "Orbegozo MI 2115 Microwave",
            "Orbegozo",
            price=59.0,
            reviews=1400,
            rating=4.4,
        )
        record.marketplace = marketplace
        record.specs = {"Marca": "Orbegozo"}
        record.specs_normalized = {
            "brand_name": "Orbegozo",
            "model_name": "MI 2115",
            "microwave_power_w": 700,
        }
        record.review_insights = {"summary": "Customers like the image quality."}
        record.top_reviews = [
            {"review_id": "fallback-1", "author": "Fallback One", "title": "Visible 1", "body": "Visible review 1"},
            {"review_id": "fallback-2", "author": "Fallback Two", "title": "Visible 2", "body": "Visible review 2"},
        ]
        return record

    def build_reviews_url(self, identifier: str, *, page: int = 1) -> str:
        suffix = f"&pageNumber={page}" if page > 1 else ""
        return f"https://www.amazon.de/-/en/product-reviews/{identifier}?ie=UTF8{suffix}"

    def review_page(self, identifier: str, *, page: int = 1, url: str | None = None) -> ReviewPage:
        if self.review_sign_in:
            return ReviewPage(
                reviews=[],
                current_page=page,
                next_page_url=None,
                source_url=url or self.build_reviews_url(identifier, page=page),
                sign_in_required=True,
            )
        reviews = list(self.review_pages.get(page, []))
        next_page_url = None
        if (page + 1) in self.review_pages:
            next_page_url = self.build_reviews_url(identifier, page=page + 1)
        return ReviewPage(
            reviews=reviews,
            current_page=page,
            available_pages=sorted(self.review_pages),
            next_page_url=next_page_url,
            next_page_state=self.review_page_states.get(page, {}),
            available_review_count=637 if self.review_pages else 0,
            source_url=url or self.build_reviews_url(identifier, page=page),
            final_url=url or self.build_reviews_url(identifier, page=page),
            sign_in_required=False,
        )

    def review_ajax_page(self, next_page_state: dict, *, source_url: str | None = None) -> ReviewPage:
        page = int(next_page_state["pageNumber"])
        return self.review_page(next_page_state.get("asin", "B0TEST1234"), page=page, url=source_url)


class DummyService(AmazonService):
    def __init__(
        self,
        *,
        resolver,
        session_store: MemorySessionStore,
        first_records: list[ProductRecord],
        second_records: list[ProductRecord],
        page_records: dict[int, list[ProductRecord]] | None = None,
        review_pages: dict[int, list[dict]] | None = None,
        review_page_states: dict[int, dict] | None = None,
        review_sign_in: bool = False,
    ) -> None:
        super().__init__(resolver=resolver, session_store=session_store)
        self.bootstrapper = DummyBootstrapper(session_store)
        self.first_records = first_records
        self.second_records = second_records
        self.page_records = page_records
        self.review_pages = review_pages
        self.review_page_states = review_page_states
        self.review_sign_in = review_sign_in

    def _scraper(self, marketplace: str, portal: str = "retail") -> DummyScraper:
        return DummyScraper(
            self.session_store.load(marketplace, portal=portal),
            self.first_records,
            self.second_records,
            self.page_records,
            self.review_pages,
            self.review_page_states,
            self.review_sign_in,
        )


def test_plain_search_skips_resolver_and_filters_brand_and_price() -> None:
    service = DummyService(
        resolver=FailingResolver(),
        session_store=MemorySessionStore(),
        first_records=[
            build_record("B0AAA", "Toshiba Microwave", "Toshiba", price=99.0, reviews=3000, rating=4.5),
            build_record("B0BBB", "Samsung Microwave", "Samsung", price=89.0, reviews=1000, rating=4.4),
            build_record("B0CCC", "Toshiba Microwave Premium", "Toshiba", price=None, reviews=2000, rating=4.6),
        ],
        second_records=[],
    )

    result = service.search(
        "microwaves",
        "de",
        refresh_intent=False,
        mode="plain",
        brand="Toshiba",
        max_price=100.0,
    )

    assert result["mode"] == "plain"
    assert result["intent"] is None
    assert result["filters"] == {
        "base": "microwaves",
        "brand": "Toshiba",
        "model": None,
        "min_price": None,
        "max_price": 100.0,
    }
    assert [item["asin"] for item in result["results"]] == ["B0AAA"]
    assert result["pagination"]["pages_requested"] == 1
    assert result["pagination"]["pages_fetched"] == 1


def test_exact_search_uses_resolver_with_structured_query() -> None:
    resolver = StaticResolver(
        IntentProfile(
            query="tv LG C4",
            marketplace="de",
            mode=IntentMode.EXACT,
            canonical_brand="LG",
            canonical_family="C4",
            family_tokens=["C4"],
            allowed_variants=["C47LA"],
            allowed_fallback_models=["C3"],
            excluded_brands=[],
            similar_families=[],
            confidence=1.0,
            created_at=datetime.now(UTC),
        )
    )
    service = DummyService(
        resolver=resolver,
        session_store=MemorySessionStore(),
        first_records=[
            build_record("B0GOOD", "LG OLED55C47LA TV", "LG", price=549.0, reviews=1000, rating=4.4),
            build_record("B0ALT", "LG OLED55C37LA TV", "LG", price=499.0, reviews=1400, rating=4.3),
        ],
        second_records=[],
    )

    result = service.search(
        "tv",
        "de",
        refresh_intent=False,
        mode="exact",
        brand="LG",
        model="C4",
        max_price=560.0,
    )

    assert resolver.calls == [("tv LG C4", "de", IntentMode.EXACT, False)]
    assert result["search_query"] == "tv LG C4"
    assert [item["asin"] for item in result["results"]] == ["B0GOOD", "B0ALT"]


def test_exact_search_uses_deduplicated_structured_query() -> None:
    resolver = StaticResolver(
        IntentProfile(
            query="Pilexil Forte Max",
            marketplace="de",
            mode=IntentMode.EXACT,
            canonical_brand="Pilexil",
            canonical_family="Forte Max",
            family_tokens=["forte", "max"],
            allowed_variants=["drinkable"],
            allowed_fallback_models=[],
            excluded_brands=[],
            similar_families=[],
            confidence=1.0,
            created_at=datetime.now(UTC),
        )
    )
    service = DummyService(
        resolver=resolver,
        session_store=MemorySessionStore(),
        first_records=[
            build_record(
                "B0DHVGHPF9",
                "Pilexil Forte Max Drinkable Anti-Hair Loss Pack 2 x 45 Units",
                "PILEXIL",
                price=144.14,
                reviews=2,
                rating=2.8,
            )
        ],
        second_records=[],
    )

    result = service.search(
        "Pilexil Forte Max",
        "de",
        refresh_intent=False,
        mode="exact",
        brand="PILEXIL",
        model="Forte Max",
    )

    assert resolver.calls == [("Pilexil Forte Max", "de", IntentMode.EXACT, False)]
    assert result["search_query"] == "Pilexil Forte Max"


def test_exact_search_discloses_requested_and_resolved_model_variant() -> None:
    resolver = StaticResolver(
        IntentProfile(
            query="tv LG OLED65C5ELB",
            marketplace="es",
            mode=IntentMode.EXACT,
            canonical_brand="LG",
            canonical_family="OLED C5",
            family_tokens=["OLED", "C5", "65C5"],
            allowed_variants=["OLED65C5ELB", "OLED65C54LA"],
            allowed_fallback_models=[],
            excluded_brands=[],
            similar_families=[],
            confidence=0.98,
            created_at=datetime.now(UTC),
        )
    )
    service = DummyService(
        resolver=resolver,
        session_store=MemorySessionStore(),
        first_records=[
            build_record(
                "B0FQP6YQJG",
                "LG OLED65C54LA - EVO AI C5 OLED Smart TV",
                "LG",
                price=1399.0,
                reviews=51,
                rating=4.6,
            )
        ],
        second_records=[],
    )

    result = service.search(
        "tv",
        "es",
        refresh_intent=False,
        mode="exact",
        brand="LG",
        model="OLED65C5ELB",
    )

    item = result["results"][0]
    assert item["requested_model"] == "OLED65C5ELB"
    assert item["resolved_model"] == "OLED65C54LA"
    assert item["model_match"] == "variant"
    assert "Requested OLED65C5ELB" in item["model_disclosure"]


def test_detail_enrichment_preserves_search_brand_when_detail_brand_is_generic() -> None:
    service = AmazonService(resolver=FailingResolver(), session_store=MemorySessionStore())
    search_record = build_record(
        "B0DHVGHPF9",
        "Pilexil Forte Max Drinkable Anti-Hair Loss Pack 2 x 45 Units",
        "PILEXIL",
        price=144.14,
        reviews=2,
        rating=2.8,
    )
    detail_record = build_record(
        "B0DHVGHPF9",
        "Pilexil Forte Max Drinkable Anti-Hair Loss Pack 2 x 45 Units",
        "Brand",
        price=144.14,
        reviews=2,
        rating=2.8,
    )
    detail_record.specs = {"Brand Name": "PILEXIL"}
    detail_record.specs_normalized = {"brand_name": "PILEXIL"}

    class GenericBrandDetailScraper:
        def get(self, identifier: str) -> ProductRecord:
            return detail_record

    enriched = service._enrich_records_with_detail_targets(
        GenericBrandDetailScraper(),
        [search_record],
        [search_record],
    )

    assert enriched[0].brand == "PILEXIL"


def test_search_auto_bootstraps_when_results_are_empty_without_session() -> None:
    store = MemorySessionStore()
    service = DummyService(
        resolver=FailingResolver(),
        session_store=store,
        first_records=[],
        second_records=[build_record("B0ESP", "Toshiba Microondas", "Toshiba", price=79.99, reviews=500, rating=4.4)],
    )

    result = service.search(
        "microondas",
        "es",
        refresh_intent=False,
        mode="plain",
        max_price=100.0,
    )

    assert len(service.bootstrapper.calls) == 1
    assert service.bootstrapper.calls[0][0] == "capture_page"
    assert service.bootstrapper.calls[0][1] == "es"
    assert service.bootstrapper.calls[0][3] is True
    assert [item["asin"] for item in result["results"]] == ["B0ESP"]


def test_search_auto_bootstraps_when_saved_session_is_not_usable() -> None:
    store = MemorySessionStore()
    store.save(
        BrowserSession(
            marketplace="es",
            browser_executable=r"C:\Chrome\chrome.exe",
            user_agent="Mozilla/5.0 Broken",
            cookies=[{"name": "session-id", "value": "stale", "domain": ".amazon.es", "path": "/"}],
        )
    )
    service = DummyService(
        resolver=FailingResolver(),
        session_store=store,
        first_records=[],
        second_records=[build_record("B0ESP", "Toshiba Microondas", "Toshiba", price=79.99, reviews=500, rating=4.4)],
    )
    service._session_is_usable = lambda marketplace, target_url: False

    class SessionAwareScraper(DummyScraper):
        def search_page(
            self,
            base: str,
            *,
            brand: str | None = None,
            model: str | None = None,
            min_price: float | None = None,
            max_price: float | None = None,
            page: int = 1,
            url: str | None = None,
        ) -> SearchPage:
            if self.session is not None and getattr(self.session, "user_agent", "") == "Mozilla/5.0 Broken":
                return SearchPage(records=[], current_page=page, available_pages=[1], source_url=url)
            return super().search_page(
                base,
                brand=brand,
                model=model,
                min_price=min_price,
                max_price=max_price,
                page=page,
                url=url,
            )

    service._scraper = lambda marketplace, portal="retail": SessionAwareScraper(
        service.session_store.load(marketplace, portal=portal),
        service.first_records,
        service.second_records,
    )

    result = service.search(
        "microondas",
        "es",
        refresh_intent=False,
        mode="plain",
        max_price=100.0,
    )

    assert len(service.bootstrapper.calls) == 1
    assert service.bootstrapper.calls[0][0] == "capture_page"
    assert [item["asin"] for item in result["results"]] == ["B0ESP"]


def test_plain_search_merges_multiple_pages_before_ranking() -> None:
    service = DummyService(
        resolver=FailingResolver(),
        session_store=MemorySessionStore(),
        first_records=[],
        second_records=[],
        page_records={
            1: [
                build_record("B0ONE", "Microwave Alpha", "Orbegozo", price=70.0, reviews=1000, rating=4.4),
                build_record("B0TWO", "Microwave Beta", "Orbegozo", price=65.0, reviews=900, rating=4.3),
            ],
            2: [
                build_record("B0THREE", "Microwave Gamma", "Orbegozo", price=60.0, reviews=2000, rating=4.1),
                build_record("B0ONE", "Microwave Alpha", "Orbegozo", price=70.0, reviews=1000, rating=4.4),
            ],
        },
    )

    result = service.search(
        "microondas",
        "de",
        refresh_intent=False,
        mode="plain",
        max_price=100.0,
        pages=2,
    )

    assert result["pagination"] == {
        "pages_requested": 2,
        "pages_fetched": 2,
        "partial": False,
        "stopped_reason": None,
    }
    assert [item["asin"] for item in result["results"]] == ["B0THREE", "B0ONE", "B0TWO"]


def test_compare_supports_mixed_marketplace_urls_and_comparison_rows() -> None:
    service = DummyService(
        resolver=FailingResolver(),
        session_store=MemorySessionStore(),
        first_records=[],
        second_records=[],
    )

    result = service.compare(
        [
            "https://www.amazon.de/dp/B0DETEST01",
            "https://www.amazon.fr/dp/B0FRTEST01",
        ],
        "de",
    )

    assert result["marketplace"] is None
    assert result["marketplaces"] == ["de", "fr"]
    assert [item["marketplace"] for item in result["items"]] == ["de", "fr"]
    assert any(row["field"] == "price" for row in result["comparison_rows"])
    assert any("de:B0DETEST01" in row["values"] for row in result["comparison_rows"])


def test_offers_ranks_by_total_when_shipping_is_included_and_keeps_failures() -> None:
    service = AmazonService(resolver=FailingResolver(), session_store=MemorySessionStore())
    calls: list[tuple[str, str, str]] = []
    offers = {
        "de": OfferRecord(
            marketplace="de",
            domain="www.amazon.de",
            url="https://www.amazon.de/dp/B0TEST1234",
            asin="B0TEST1234",
            title="Current DE",
            price=90.0,
            currency="EUR",
            shipping=20.0,
            total=110.0,
            status="ok",
        ),
        "fr": OfferRecord(
            marketplace="fr",
            domain="www.amazon.fr",
            url="https://www.amazon.fr/dp/B0TEST1234",
            asin="B0TEST1234",
            title="FR",
            price=80.0,
            currency="EUR",
            shipping=5.0,
            total=85.0,
            status="ok",
        ),
        "es": OfferRecord(
            marketplace="es",
            domain="www.amazon.es",
            url="https://www.amazon.es/dp/B0TEST1234",
            asin="B0TEST1234",
            status="fetch_failed",
            failure_reason="network",
        ),
    }

    def fake_fetch_offer(target_marketplace: str, asin: str, *, portal: str) -> OfferRecord:
        calls.append((target_marketplace, asin, portal))
        return offers[target_marketplace]

    service._fetch_offer = fake_fetch_offer

    result = service.offers(
        "B0TEST1234",
        "de",
        portal="business",
        marketplaces=["de", "fr", "es"],
        include_shipping=True,
    )

    assert result["best_offer"]["marketplace"] == "fr"
    assert result["current_offer"]["marketplace"] == "de"
    assert [offer["marketplace"] for offer in result["offers"]] == ["fr", "de", "es"]
    assert [failure["marketplace"] for failure in result["failures"]] == ["es"]
    assert calls == [
        ("de", "B0TEST1234", "business"),
        ("fr", "B0TEST1234", "business"),
        ("es", "B0TEST1234", "business"),
    ]


def test_business_offers_auto_vat_mode_ranks_by_ex_vat_plus_shipping() -> None:
    service = AmazonService(resolver=FailingResolver(), session_store=MemorySessionStore())
    offers = {
        "de": OfferRecord(
            marketplace="de",
            domain="www.amazon.de",
            url="https://www.amazon.de/dp/B0TEST1234",
            asin="B0TEST1234",
            price=121.0,
            price_ex_vat=100.0,
            price_incl_vat=121.0,
            currency="EUR",
            shipping=12.0,
            total=133.0,
            status="ok",
        ),
        "es": OfferRecord(
            marketplace="es",
            domain="www.amazon.es",
            url="https://www.amazon.es/dp/B0TEST1234",
            asin="B0TEST1234",
            price=114.0,
            price_ex_vat=120.0,
            price_incl_vat=114.0,
            currency="EUR",
            shipping=0.0,
            total=114.0,
            status="ok",
        ),
    }
    service._fetch_offer = lambda target_marketplace, asin, *, portal: offers[target_marketplace]

    result = service.offers(
        "B0TEST1234",
        "de",
        portal="business",
        marketplaces=["de", "es"],
        include_shipping=True,
        vat_mode="auto",
    )

    assert result["trusted_best_offer"]["marketplace"] == "de"
    assert result["raw_best_offer"]["marketplace"] == "de"
    assert result["best_offer"]["marketplace"] == "de"
    assert result["offers"][0]["comparison_basis"] == "ex_vat"
    assert result["offers"][0]["comparison_price"] == 100.0
    assert result["offers"][0]["comparison_total"] == 112.0


def test_offers_excludes_address_mismatch_from_trusted_best() -> None:
    service = AmazonService(resolver=FailingResolver(), session_store=MemorySessionStore())
    offers = {
        "de": OfferRecord(
            marketplace="de",
            domain="www.amazon.de",
            url="https://www.amazon.de/dp/B0TEST1234",
            asin="B0TEST1234",
            price=120.0,
            currency="EUR",
            shipping=0.0,
            total=120.0,
            delivery_address={"line2": "Almería 04006", "postal_code": "04006", "normalized_key": "almeria 04006"},
            status="ok",
        ),
        "fr": OfferRecord(
            marketplace="fr",
            domain="www.amazon.fr",
            url="https://www.amazon.fr/dp/B0TEST1234",
            asin="B0TEST1234",
            price=80.0,
            currency="EUR",
            shipping=0.0,
            total=80.0,
            delivery_address={"line2": "Paris 75001", "postal_code": "75001", "normalized_key": "paris 75001"},
            status="ok",
        ),
    }
    service._fetch_offer = lambda target_marketplace, asin, *, portal: offers[target_marketplace]

    result = service.offers(
        "B0TEST1234",
        "de",
        marketplaces=["de", "fr"],
        include_shipping=True,
    )

    assert result["raw_best_offer"]["marketplace"] == "fr"
    assert result["trusted_best_offer"]["marketplace"] == "de"
    assert result["best_offer"]["marketplace"] == "de"
    assert result["address_consistency"]["status"] == "mismatch"
    assert result["address_consistency"]["mismatched_marketplaces"] == ["fr"]
    fr_offer = next(offer for offer in result["offers"] if offer["marketplace"] == "fr")
    assert fr_offer["address_match"] is False
    assert fr_offer["eligible_for_best"] is False
    assert "address_mismatch" in fr_offer["exclusion_reasons"]


def test_address_inspect_reports_missing_sessions_with_login_hints() -> None:
    service = AmazonService(resolver=FailingResolver(), session_store=MemorySessionStore())

    result = service.address_inspect(
        portal="business",
        marketplaces=["de", "fr"],
        reference_marketplace="de",
    )

    assert result["command"] == "address.inspect"
    assert result["address_consistency"]["status"] == "unknown"
    assert [record["status"] for record in result["addresses"]] == ["missing_session", "missing_session"]
    assert result["addresses"][0]["login_hint"] == "Run `amazon-cli session login --marketplace de --portal business`."
    assert result["addresses"][1]["login_hint"] == "Run `amazon-cli session login --marketplace fr --portal business`."


def test_address_inspect_treats_isolated_sessions_as_missing_managed_sessions() -> None:
    store = MemorySessionStore()
    session = managed_session("fr", portal="retail")
    session.session_source = "isolated"
    store.save(session)
    service = AmazonService(resolver=FailingResolver(), session_store=store)

    result = service.address_inspect(
        portal="retail",
        marketplaces=["fr"],
        reference_marketplace="fr",
    )

    assert result["address_consistency"]["status"] == "unknown"
    assert result["addresses"][0]["status"] == "missing_session"
    assert result["addresses"][0]["session_source"] == "isolated"
    assert result["addresses"][0]["failure_reason"] == "No managed retail session is available."
    assert result["addresses"][0]["login_hint"] == "Run `amazon-cli session login --marketplace fr --portal retail`."


def test_address_inspect_extracts_managed_session_addresses(monkeypatch) -> None:
    store = MemorySessionStore()
    store.save(managed_session("de", portal="business"))
    store.save(managed_session("fr", portal="business"))
    service = AmazonService(resolver=FailingResolver(), session_store=store)

    class FakeHttpClient:
        def __init__(self, marketplace, session=None) -> None:
            self.marketplace = marketplace

        def fetch_url_details(self, url: str) -> tuple[str, str]:
            return (
                """
                <html>
                  <span id="glow-ingress-line1">Deliver to José</span>
                  <span id="glow-ingress-line2">Almería 04006‌</span>
                </html>
                """,
                url,
            )

    monkeypatch.setattr("amazon_intent_cli.service.AmazonHttpClient", FakeHttpClient)

    result = service.address_inspect(
        portal="business",
        marketplaces=["de", "fr"],
        reference_marketplace="de",
    )

    assert result["address_consistency"]["status"] == "match"
    assert result["addresses"][0]["delivery_address"]["normalized_key"] == "almeria 04006"
    assert result["addresses"][1]["delivery_address"]["normalized_key"] == "almeria 04006"


def test_offers_ranks_by_price_when_shipping_is_excluded() -> None:
    service = AmazonService(resolver=FailingResolver(), session_store=MemorySessionStore())
    offers = {
        "de": OfferRecord(
            marketplace="de",
            domain="www.amazon.de",
            url="https://www.amazon.de/dp/B0TEST1234",
            asin="B0TEST1234",
            price=90.0,
            currency="EUR",
            shipping=0.0,
            total=90.0,
            status="ok",
        ),
        "fr": OfferRecord(
            marketplace="fr",
            domain="www.amazon.fr",
            url="https://www.amazon.fr/dp/B0TEST1234",
            asin="B0TEST1234",
            price=80.0,
            currency="EUR",
            shipping=40.0,
            total=120.0,
            status="ok",
        ),
    }
    service._fetch_offer = lambda target_marketplace, asin, *, portal: offers[target_marketplace]

    result = service.offers(
        "B0TEST1234",
        "de",
        marketplaces=["de", "fr"],
        include_shipping=False,
    )

    assert result["best_offer"]["marketplace"] == "fr"
    assert [offer["marketplace"] for offer in result["offers"]] == ["fr", "de"]


def test_fetch_offer_uses_target_marketplace_session_and_amazon_url(monkeypatch) -> None:
    store = MemorySessionStore()
    store.save(managed_session("fr", portal="business"))
    service = AmazonService(resolver=FailingResolver(), session_store=store)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, marketplace, session=None) -> None:
            captured["marketplace"] = marketplace.code
            captured["session_key"] = session.session_key if session is not None else None

        def fetch_url_details(self, url: str) -> tuple[str, str]:
            captured["url"] = url
            return (
                """
                <html>
                  <body>
                    <span id="productTitle">LG TV</span>
                    <input id="twister-plus-price-data-price" value="799.99">
                  </body>
                </html>
                """,
                url,
            )

    monkeypatch.setattr("amazon_intent_cli.service.AmazonHttpClient", FakeHttpClient)

    offer = service._fetch_offer("fr", "B0TEST1234", portal="business")

    assert captured == {
        "marketplace": "fr",
        "session_key": "fr:business",
        "url": "https://www.amazon.fr/dp/B0TEST1234?_encoding=UTF8&psc=1",
    }
    assert offer.status == "ok"
    assert "eurosaver" not in str(captured).lower()


def test_cart_add_requires_managed_session() -> None:
    service = AmazonService(resolver=FailingResolver(), session_store=MemorySessionStore())

    try:
        service.cart_add("B0TEST1234", "es", portal="business", confirm_cart_add=True)
    except BrowserSessionError as exc:
        assert "amazon-cli session login --marketplace es --portal business" in str(exc)
    else:
        raise AssertionError("Expected missing managed session to be rejected")


def test_cart_add_delegates_to_managed_browser_action() -> None:
    store = MemorySessionStore()
    store.save(managed_session("es", portal="business"))
    service = AmazonService(resolver=FailingResolver(), session_store=store)
    calls: list[tuple] = []

    class FakeBootstrapper:
        def add_to_cart(self, marketplace: str, asin: str, *, portal: str, quantity: int) -> dict:
            calls.append((marketplace, asin, portal, quantity))
            return {
                "status": "added",
                "asin": asin,
                "marketplace": marketplace,
                "portal": portal,
                "quantity": quantity,
                "title": "Pilexil Forte Max",
                "url": f"https://www.amazon.es/dp/{asin}",
                "final_url": f"https://www.amazon.es/cart/smart-wagon",
                "cart_confirmation_detected": True,
                "warnings": [],
                "safety": {
                    "checkout_performed": False,
                    "buy_now_clicked": False,
                },
            }

    service.bootstrapper = FakeBootstrapper()

    result = service.cart_add("B0TEST1234", "es", portal="business", quantity=2, confirm_cart_add=True)

    assert result["command"] == "cart.add"
    assert result["status"] == "added"
    assert result["safety"]["checkout_performed"] is False
    assert calls == [("es", "B0TEST1234", "business", 2)]


def test_cart_add_rejects_missing_confirmation() -> None:
    store = MemorySessionStore()
    store.save(managed_session("es", portal="business"))
    service = AmazonService(resolver=FailingResolver(), session_store=store)

    try:
        service.cart_add("B0TEST1234", "es", portal="business", confirm_cart_add=False)
    except ValueError as exc:
        assert "--confirm-cart-add" in str(exc)
    else:
        raise AssertionError("Expected cart add confirmation to be required")


def test_cart_remove_requires_managed_session() -> None:
    service = AmazonService(resolver=FailingResolver(), session_store=MemorySessionStore())

    try:
        service.cart_remove("B0TEST1234", "es", portal="business", confirm_cart_remove=True)
    except BrowserSessionError as exc:
        assert "amazon-cli session login --marketplace es --portal business" in str(exc)
    else:
        raise AssertionError("Expected missing managed session to be rejected")


def test_cart_remove_delegates_to_managed_browser_action() -> None:
    store = MemorySessionStore()
    store.save(managed_session("es", portal="business"))
    service = AmazonService(resolver=FailingResolver(), session_store=store)
    calls: list[tuple] = []

    class FakeBootstrapper:
        def remove_from_cart(self, marketplace: str, asin: str, *, portal: str, quantity: int) -> dict:
            calls.append((marketplace, asin, portal, quantity))
            return {
                "status": "removed",
                "asin": asin,
                "marketplace": marketplace,
                "portal": portal,
                "quantity_requested": quantity,
                "quantity_removed": quantity,
                "quantity_before": quantity,
                "quantity_after": 0,
                "title": "Pilexil Forte Max",
                "url": "https://www.amazon.es/cart",
                "final_url": "https://www.amazon.es/cart",
                "cart_removal_detected": True,
                "warnings": [],
                "safety": {
                    "checkout_performed": False,
                    "buy_now_clicked": False,
                },
            }

    service.bootstrapper = FakeBootstrapper()

    result = service.cart_remove("B0TEST1234", "es", portal="business", quantity=2, confirm_cart_remove=True)

    assert result["command"] == "cart.remove"
    assert result["status"] == "removed"
    assert result["safety"]["checkout_performed"] is False
    assert calls == [("es", "B0TEST1234", "business", 2)]


def test_cart_remove_rejects_missing_confirmation() -> None:
    store = MemorySessionStore()
    store.save(managed_session("es", portal="business"))
    service = AmazonService(resolver=FailingResolver(), session_store=store)

    try:
        service.cart_remove("B0TEST1234", "es", portal="business", confirm_cart_remove=False)
    except ValueError as exc:
        assert "--confirm-cart-remove" in str(exc)
    else:
        raise AssertionError("Expected cart remove confirmation to be required")


def test_pagination_returns_partial_results_when_later_page_fails() -> None:
    service = DummyService(
        resolver=FailingResolver(),
        session_store=MemorySessionStore(),
        first_records=[],
        second_records=[],
        page_records={
            1: [build_record("B0ONE", "Microwave Alpha", "Orbegozo", price=70.0, reviews=1000, rating=4.4)],
            2: [build_record("B0TWO", "Microwave Beta", "Orbegozo", price=65.0, reviews=900, rating=4.3)],
        },
    )
    original = service._search_page_with_recovery

    def failing_second_page(*args, **kwargs):
        if kwargs.get("page") == 2:
            raise BrowserSessionError("page 2 blocked")
        return original(*args, **kwargs)

    service._search_page_with_recovery = failing_second_page

    result = service.search(
        "microondas",
        "de",
        refresh_intent=False,
        mode="plain",
        max_price=100.0,
        pages=2,
    )

    assert [item["asin"] for item in result["results"]] == ["B0ONE"]
    assert result["pagination"]["pages_fetched"] == 1
    assert result["pagination"]["partial"] is True
    assert "page_2" in result["pagination"]["stopped_reason"]


def test_reviews_defaults_to_single_review_page_size() -> None:
    store = MemorySessionStore()
    store.save(managed_session("de"))
    service = DummyService(
        resolver=FailingResolver(),
        session_store=store,
        first_records=[],
        second_records=[],
        review_pages={
            1: [
                {"review_id": "r1", "author": "A", "title": "One", "body": "Body 1"},
                {"review_id": "r2", "author": "B", "title": "Two", "body": "Body 2"},
            ],
            2: [
                {"review_id": "r3", "author": "C", "title": "Three", "body": "Body 3"},
            ],
        },
    )

    result = service.reviews("B0TEST1234", "de")

    assert result["limit"] is None
    assert result["reviews_source"] == "product_reviews"
    assert result["session_source"] == "managed_profile"
    assert result["portal"] == "retail"
    assert result["final_url"].endswith("B0TEST1234?ie=UTF8")
    assert result["pagination"]["pages_fetched"] == 1
    assert [review["review_id"] for review in result["reviews"]] == ["r1", "r2"]


def test_reviews_collects_across_pages_when_limit_is_explicit() -> None:
    store = MemorySessionStore()
    store.save(managed_session("de"))
    service = DummyService(
        resolver=FailingResolver(),
        session_store=store,
        first_records=[],
        second_records=[],
        review_pages={
            1: [
                {"review_id": "r1", "author": "A", "title": "One", "body": "Body 1"},
                {"review_id": "r2", "author": "B", "title": "Two", "body": "Body 2"},
            ],
            2: [
                {"review_id": "r3", "author": "C", "title": "Three", "body": "Body 3"},
                {"review_id": "r4", "author": "D", "title": "Four", "body": "Body 4"},
            ],
        },
    )

    result = service.reviews("B0TEST1234", "de", limit=3)

    assert result["pagination"]["pages_fetched"] == 2
    assert [review["review_id"] for review in result["reviews"]] == ["r1", "r2", "r3"]


def test_build_comments_summary_aggregates_multilingual_reviews() -> None:
    reviews = [
        {
            "review_id": "r1",
            "author": "A",
            "rating": 5.0,
            "title": "Excellent image",
            "date": "Reviewed in France on 17 January 2026",
            "verified_purchase": True,
            "body": "Excellent image quality and very good sound. Great value.",
        },
        {
            "review_id": "r2",
            "author": "B",
            "rating": 4.0,
            "title": "Apps are annoying",
            "date": "Reviewed in Germany on 16 March 2026",
            "verified_purchase": True,
            "body": "Super Bildqualität, but the apps and remote are annoying.",
        },
        {
            "review_id": "r3",
            "author": "C",
            "rating": 2.0,
            "title": "Bad remote",
            "date": "Reviewed in Spain on 20 April 2026",
            "verified_purchase": False,
            "body": "The remote is bad and software is complicated.",
        },
    ]

    summary = build_comments_summary(reviews)

    assert summary["extracted_review_count"] == 3
    assert summary["average_rating"] == 3.7
    assert summary["rating_histogram"] == {"5": 1, "4": 1, "2": 1}
    assert summary["verified_purchase_count"] == 2
    assert summary["source_countries"] == {"France": 1, "Germany": 1, "Spain": 1}
    assert summary["positive_terms"][0] == {"term": "image quality", "count": 2}
    assert {"term": "remote", "count": 2} in summary["critical_terms"]
    assert summary["representative_positive_review"]["review_id"] == "r1"
    assert summary["representative_critical_review"]["review_id"] == "r3"


def test_build_comments_summary_handles_empty_reviews() -> None:
    summary = build_comments_summary([])

    assert summary == {
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


def test_reviews_payload_includes_comments_summary() -> None:
    store = MemorySessionStore()
    store.save(managed_session("de"))
    service = DummyService(
        resolver=FailingResolver(),
        session_store=store,
        first_records=[],
        second_records=[],
        review_pages={
            1: [
                {
                    "review_id": "r1",
                    "author": "A",
                    "rating": 5.0,
                    "title": "Excellent image",
                    "date": "Reviewed in France on 17 January 2026",
                    "verified_purchase": True,
                    "body": "Excellent image quality and very good sound.",
                }
            ],
        },
    )

    result = service.reviews("B0TEST1234", "de")

    assert result["comments_summary"]["extracted_review_count"] == 1
    assert result["comments_summary"]["average_rating"] == 5.0


def test_reviews_falls_back_to_product_page_when_review_collection_requires_sign_in() -> None:
    store = MemorySessionStore()
    store.save(managed_session("de"))
    service = DummyService(
        resolver=FailingResolver(),
        session_store=store,
        first_records=[],
        second_records=[],
        review_sign_in=True,
    )

    result = service.reviews("B0TEST1234", "de")

    assert result["reviews_source"] == "product_detail_fallback"
    assert result["deep_reviews_available"] is False
    assert result["session_status"] == "expired"
    assert "amazon-cli session login --marketplace de --portal retail" in result["session_hint"]
    assert "sign in" in result["fallback_reason"].lower()
    assert [review["review_id"] for review in result["reviews"]] == ["fallback-1", "fallback-2"]


def test_reviews_missing_managed_session_returns_login_hint_and_product_fallback() -> None:
    service = DummyService(
        resolver=FailingResolver(),
        session_store=MemorySessionStore(),
        first_records=[],
        second_records=[],
        review_pages={
            1: [{"review_id": "r1", "author": "A", "title": "One", "body": "Body 1"}],
        },
    )

    result = service.reviews("B0TEST1234", "de", limit=20)

    assert result["reviews_source"] == "product_detail_fallback"
    assert result["deep_reviews_available"] is False
    assert result["session_status"] == "missing"
    assert "amazon-cli session login --marketplace de --portal retail" in result["session_hint"]
    assert result["session_source"] is None
    assert "amazon-cli session login --marketplace de --portal retail" in result["fallback_reason"]
    assert service.bootstrapper.calls == []
    assert [review["review_id"] for review in result["reviews"]] == ["fallback-1", "fallback-2"]


def test_reviews_missing_business_session_returns_business_login_hint_and_product_fallback() -> None:
    service = DummyService(
        resolver=FailingResolver(),
        session_store=MemorySessionStore(),
        first_records=[],
        second_records=[],
    )

    result = service.reviews("B0TEST1234", "de", limit=20, portal="business")

    assert result["portal"] == "business"
    assert result["reviews_source"] == "product_detail_fallback"
    assert result["deep_reviews_available"] is False
    assert result["session_status"] == "missing"
    assert "amazon-cli session login --marketplace de --portal business" in result["session_hint"]
    assert "amazon-cli session login --marketplace de --portal business" in result["fallback_reason"]
    assert [review["review_id"] for review in result["reviews"]] == ["fallback-1", "fallback-2"]


def test_reviews_missing_fr_business_session_returns_fr_business_login_hint() -> None:
    service = DummyService(
        resolver=FailingResolver(),
        session_store=MemorySessionStore(),
        first_records=[],
        second_records=[],
    )

    result = service.reviews("B0TEST1234", "fr", limit=20, portal="business")

    assert result["marketplace"] == "fr"
    assert result["portal"] == "business"
    assert result["session_status"] == "missing"
    assert "amazon-cli session login --marketplace fr --portal business" in result["session_hint"]
    assert "amazon-cli session login --marketplace fr --portal business" in result["fallback_reason"]


def test_reviews_with_managed_business_session_uses_deep_review_collection() -> None:
    store = MemorySessionStore()
    store.save(managed_session("de", portal="business"))
    service = DummyService(
        resolver=FailingResolver(),
        session_store=store,
        first_records=[],
        second_records=[],
        review_pages={
            1: [
                {
                    "review_id": "business-r1",
                    "author": "A",
                    "rating": 5.0,
                    "title": "Excellent",
                    "date": "Reviewed in Germany on 21 April 2026",
                    "verified_purchase": True,
                    "body": "Excellent image quality.",
                }
            ],
        },
    )

    result = service.reviews("B0TEST1234", "de", portal="business")

    assert result["portal"] == "business"
    assert result["reviews_source"] == "product_reviews"
    assert result["deep_reviews_available"] is True
    assert result["session_status"] == "usable"
    assert result["session_source"] == "managed_profile"
    assert result["reviews"][0]["review_id"] == "business-r1"
    assert result["comments_summary"]["extracted_review_count"] == 1


def test_reviews_uses_ajax_show_more_state_for_explicit_limit() -> None:
    store = MemorySessionStore()
    store.save(managed_session("de", portal="business"))
    service = DummyService(
        resolver=FailingResolver(),
        session_store=store,
        first_records=[],
        second_records=[],
        review_pages={
            1: [
                {"review_id": "r1", "author": "A", "rating": 5.0, "title": "One", "body": "Body 1"},
                {"review_id": "r2", "author": "B", "rating": 4.0, "title": "Two", "body": "Body 2"},
            ],
            2: [
                {"review_id": "r3", "author": "C", "rating": 5.0, "title": "Three", "body": "Body 3"},
                {"review_id": "r4", "author": "D", "rating": 4.0, "title": "Four", "body": "Body 4"},
            ],
        },
        review_page_states={
            1: {
                "asin": "B0TEST1234",
                "pageNumber": "2",
                "nextPageToken": "page-two",
                "reviews_ajax_url": "/portal/customer-reviews/ajax/reviews/get/",
                "reviews_csrf_token": "csrf-token",
                "reftag": "cm_cr_arp_d_paging_btm",
            },
        },
    )

    result = service.reviews("B0TEST1234", "de", limit=4, portal="business")

    assert [review["review_id"] for review in result["reviews"]] == ["r1", "r2", "r3", "r4"]
    assert result["available_review_count"] == 637
    assert result["comments_summary"]["available_review_count"] == 637
    assert result["pagination"]["pages_fetched"] == 2
    assert result["pagination"]["partial"] is False
    assert result["pagination"]["diagnostics"] == {
        "ajax_requests": 1,
        "ajax_failures": 0,
        "duplicate_reviews_skipped": 0,
        "last_page_attempted": 2,
        "had_continuation_token": True,
    }
    serialized = json.dumps(result)
    assert "csrf-token" not in serialized
    assert "page-two" not in serialized


def test_reviews_returns_partial_safe_diagnostics_when_ajax_continuation_fails() -> None:
    class FailingAjaxScraper(DummyScraper):
        def review_ajax_page(self, next_page_state: dict, *, source_url: str | None = None) -> ReviewPage:
            raise BrowserSessionError("ajax endpoint changed")

    store = MemorySessionStore()
    store.save(managed_session("de", portal="business"))
    service = DummyService(
        resolver=FailingResolver(),
        session_store=store,
        first_records=[],
        second_records=[],
        review_pages={
            1: [
                {"review_id": "r1", "author": "A", "rating": 5.0, "title": "One", "body": "Body 1"},
                {"review_id": "r2", "author": "B", "rating": 4.0, "title": "Two", "body": "Body 2"},
            ],
        },
        review_page_states={
            1: {
                "asin": "B0TEST1234",
                "pageNumber": "2",
                "nextPageToken": "secret-token",
                "reviews_ajax_url": "/portal/customer-reviews/ajax/reviews/get/",
                "reviews_csrf_token": "secret-csrf",
                "reftag": "cm_cr_arp_d_paging_btm",
            },
        },
    )
    service._scraper = lambda marketplace, portal="retail": FailingAjaxScraper(
        service.session_store.load(marketplace, portal=portal),
        service.first_records,
        service.second_records,
        service.page_records,
        service.review_pages,
        service.review_page_states,
        service.review_sign_in,
    )

    result = service.reviews("B0TEST1234", "de", limit=4, portal="business")

    assert [review["review_id"] for review in result["reviews"]] == ["r1", "r2"]
    assert result["reviews_source"] == "product_reviews"
    assert result["deep_reviews_available"] is True
    assert result["pagination"]["pages_fetched"] == 1
    assert result["pagination"]["partial"] is True
    assert result["pagination"]["stopped_reason"] == "page_2: ajax endpoint changed"
    assert result["pagination"]["diagnostics"] == {
        "ajax_requests": 1,
        "ajax_failures": 1,
        "duplicate_reviews_skipped": 0,
        "last_page_attempted": 2,
        "had_continuation_token": True,
    }
    serialized = json.dumps(result)
    assert "secret-token" not in serialized
    assert "secret-csrf" not in serialized
