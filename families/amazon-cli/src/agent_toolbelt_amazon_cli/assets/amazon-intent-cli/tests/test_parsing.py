from pathlib import Path

import pytest

from amazon_intent_cli.amazon import (
    AmazonBlockedError,
    AmazonHttpClient,
    AmazonParser,
    AmazonScraper,
    compose_search_query,
    parse_float_from_text,
    parse_review_count,
)
from amazon_intent_cli.marketplaces import get_marketplace


FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_search_results_de_fixture() -> None:
    parser = AmazonParser(get_marketplace("de"))

    results = parser.parse_search_results(fixture_text("search_de.html"))

    assert [item.asin for item in results] == ["B0HISENSE65", "B0LGC4DE65", "B0LGC3DE65"]
    assert results[0].is_sponsored is True
    assert results[1].brand == "LG"
    assert results[1].prime is True
    assert results[1].review_count == 1543


@pytest.mark.parametrize(
    ("marketplace_code", "fixture_name", "expected_asin"),
    [("es", "search_es.html", "B0LGC4ES55"), ("fr", "search_fr.html", "B0LGC4FR55")],
)
def test_parse_search_results_for_supported_marketplaces(
    marketplace_code: str,
    fixture_name: str,
    expected_asin: str,
) -> None:
    parser = AmazonParser(get_marketplace(marketplace_code))

    results = parser.parse_search_results(fixture_text(fixture_name))

    assert results[0].asin == expected_asin
    assert results[0].marketplace == marketplace_code


def test_parse_search_results_live_like_fixture() -> None:
    parser = AmazonParser(get_marketplace("de"))

    results = parser.parse_search_results(fixture_text("search_de_live_like.html"))

    assert [item.asin for item in results] == ["B0CYQ16XRR", "B0HISENSE65"]
    assert results[0].title.startswith("OLED48C47LA")
    assert results[0].brand == "LG"
    assert results[0].price == 1277.17
    assert results[0].review_count == 1500
    assert results[0].prime is True
    assert results[1].is_sponsored is True


def test_parse_search_results_ignores_non_brand_labels() -> None:
    parser = AmazonParser(get_marketplace("es"))
    html = """
    <div data-component-type="s-search-result" data-asin="B01N09DY8M">
      <h2 class="a-size-mini">Sponsored</h2>
      <h2><a href="/dp/B01N09DY8M"><span>Sponsored Ad – Orbegozo MI 2115 Microondas 20L</span></a></h2>
      <span class="a-price"><span class="a-offscreen">€75.65</span></span>
      <span class="a-icon-alt">4.3 out of 5 stars</span>
      <span class="s-underline-text">22,900</span>
    </div>
    """

    results = parser.parse_search_results(html)

    assert len(results) == 1
    assert results[0].brand == "Orbegozo"


def test_parse_detail_page_extracts_store_seller_and_specs() -> None:
    parser = AmazonParser(get_marketplace("de"))

    item = parser.parse_product_detail(
        fixture_text("detail_lg_c4_de.html"),
        source_url="https://www.amazon.de/dp/B0LGC4DE65",
        asin="B0LGC4DE65",
    )

    assert item.brand_store_present is True
    assert item.seller_summary == "Verkauf durch Amazon EU S.a.r.L."
    assert item.specs["Modellname"] == "OLED65C47LA"
    assert item.review_count == 1543


def test_parse_detail_page_extracts_review_insights_and_top_reviews() -> None:
    parser = AmazonParser(get_marketplace("de"))

    item = parser.parse_product_detail(
        fixture_text("detail_reviews_de.html"),
        source_url="https://www.amazon.de/dp/B0F2JCZPB4",
        asin="B0F2JCZPB4",
    )

    assert item.review_insights["summary"].startswith("Customers like the image quality")
    assert item.review_insights["histogram"] == {"5": 79, "4": 11, "3": 4, "2": 1, "1": 5}
    assert item.review_insights["topics"][0] == {
        "topic": "Image quality",
        "mentions": 329,
        "sentiment": "positive",
        "summary": "Customers are satisfied with the image quality of the television.",
    }
    assert len(item.top_reviews) == 2
    assert item.top_reviews[0]["author"] == "Dynamite"
    assert item.top_reviews[0]["rating"] == 5.0
    assert item.top_reviews[0]["title"] == "Grandioser OLED TV!!"
    assert item.top_reviews[0]["verified_purchase"] is True
    assert item.top_reviews[0]["helpful_count"] == 1
    assert item.top_reviews[0]["body"].startswith("Dieser Fernseher hat bei mir")


def test_parse_review_page_extracts_reviews_and_next_page() -> None:
    parser = AmazonParser(get_marketplace("de"))

    page = parser.parse_review_page(
        fixture_text("review_page_de.html"),
        source_url="https://www.amazon.de/-/en/product-reviews/B0F2JCZPB4/ref=cm_cr_dp_d_show_all_btm?ie=UTF8",
    )

    assert page.sign_in_required is False
    assert page.current_page == 1
    assert page.next_page_url == "https://www.amazon.de/-/en/product-reviews/B0F2JCZPB4/ref=cm_cr_get_next_paging_btm?ie=UTF8&pageNumber=2"
    assert [review["review_id"] for review in page.reviews] == ["RRHMQTG8MPY91", "R2EXAMPLE123"]
    assert page.reviews[0]["author"] == "Dynamite"
    assert page.reviews[0]["helpful_count"] == 1


def test_parse_review_page_extracts_available_count_and_show_more_state() -> None:
    parser = AmazonParser(get_marketplace("de"))
    html = """
    <html>
      <body>
        <span id="cr-state-object" data-state='{
          "reviewsCsrfToken":"csrf-token",
          "reviewsAjaxUrl":"/portal/customer-reviews/ajax/reviews/get/",
          "asin":"B0F2JCZPB4",
          "reviewerType":"",
          "filterByStar":"",
          "filterByAge":"",
          "filterByLanguage":"",
          "filterByKeyword":"",
          "formatType":""
        }'></span>
        <div data-hook="cr-filter-info-review-rating-count">637 customer reviews</div>
        <a data-hook="show-more-button"
           data-reftag="cm_cr_arp_d_paging_btm"
           data-reviews-state-param='{
             "shouldAppend":"true",
             "deviceType":"desktop",
             "canShowIntHeader":"true",
             "nextPageToken":"next-token",
             "pageNumber":"2"
           }'
           href="/-/en/product-reviews/B0F2JCZPB4/ref=cm_cr_arp_d_paging_btm">Show 10 more reviews</a>
      </body>
    </html>
    """

    page = parser.parse_review_page(html, source_url="https://www.amazon.de/-/en/product-reviews/B0F2JCZPB4")

    assert page.available_review_count == 637
    assert page.next_page_state["reviews_ajax_url"] == "/portal/customer-reviews/ajax/reviews/get/"
    assert page.next_page_state["reviews_csrf_token"] == "csrf-token"
    assert page.next_page_state["reftag"] == "cm_cr_arp_d_paging_btm"
    assert page.next_page_state["asin"] == "B0F2JCZPB4"
    assert page.next_page_state["pageNumber"] == "2"
    assert page.next_page_state["nextPageToken"] == "next-token"


def test_parse_ajax_review_page_stream_extracts_reviews_count_and_next_state() -> None:
    parser = AmazonParser(get_marketplace("de"))
    html = """
["update","#filter-info-section","<div data-hook=\\"cr-filter-info-review-rating-count\\">637 customer reviews</div>"]
&&&
["append","#cm_cr-review_list","<ul><li id=\\"RNEW1\\" data-hook=\\"review\\"><span class=\\"a-profile-name\\">James</span><i data-hook=\\"review-star-rating\\"><span class=\\"a-icon-alt\\">5.0 out of 5 stars</span></i><a data-hook=\\"review-title\\"><span>Top Fernseher</span></a><span data-hook=\\"review-date\\">Reviewed in Germany on 15 April 2026</span><span data-hook=\\"avp-badge\\">Verified Purchase</span><span data-hook=\\"review-body\\"><span>Sehr gutes Bild.</span></span></li></ul>"]
&&&
["append","#cm_cr-review_list","<a data-hook=\\"show-more-button\\" data-reftag=\\"cm_cr_arp_d_paging_btm\\" data-reviews-state-param='{\\"shouldAppend\\":\\"true\\",\\"deviceType\\":\\"desktop\\",\\"canShowIntHeader\\":\\"true\\",\\"nextPageToken\\":\\"page-three\\",\\"pageNumber\\":\\"3\\"}'>Show 10 more reviews</a>"]
    """

    page = parser.parse_review_page(
        html,
        source_url="https://www.amazon.de/portal/customer-reviews/ajax/reviews/get/ref=cm_cr_arp_d_paging_btm",
    )

    assert page.available_review_count == 637
    assert [review["review_id"] for review in page.reviews] == ["RNEW1"]
    assert page.next_page_state["pageNumber"] == "3"
    assert page.next_page_state["nextPageToken"] == "page-three"


def test_parse_review_page_extracts_data_hook_review_cards_without_legacy_ids() -> None:
    parser = AmazonParser(get_marketplace("es"))
    html = """
    <html>
      <body>
        <div data-hook="review">
          <span class="a-profile-name">Cliente Amazon</span>
          <i data-hook="review-star-rating"><span class="a-icon-alt">5.0 out of 5 stars</span></i>
          <a data-hook="review-title"><span>Imagen excelente</span></a>
          <span data-hook="review-date">Reviewed in Spain on 20 April 2026</span>
          <span data-hook="avp-badge">Verified Purchase</span>
          <span data-hook="review-body"><span>Contraste perfecto y sonido muy bueno.</span></span>
        </div>
      </body>
    </html>
    """

    page = parser.parse_review_page(
        html,
        source_url="https://www.amazon.es/-/en/product-reviews/B0FQP6YQJG/ref=cm_cr_dp_d_show_all_btm?ie=UTF8",
    )

    assert len(page.reviews) == 1
    assert page.reviews[0]["author"] == "Cliente Amazon"
    assert page.reviews[0]["rating"] == 5.0
    assert page.reviews[0]["title"] == "Imagen excelente"
    assert page.reviews[0]["verified_purchase"] is True
    assert page.reviews[0]["body"] == "Contraste perfecto y sonido muy bueno."


def test_parse_review_page_deduplicates_cards_matching_legacy_id_and_data_hook() -> None:
    parser = AmazonParser(get_marketplace("de"))
    html = """
    <html>
      <body>
        <li id="RDUPLICATE1" data-hook="review">
          <div id="RDUPLICATE1-review-card">
            <div id="customer_review-RDUPLICATE1">
              <span class="a-profile-name">Dynamite</span>
              <i data-hook="review-star-rating"><span class="a-icon-alt">5.0 out of 5 stars</span></i>
              <a data-hook="review-title"><span>Grandioser OLED TV!!</span></a>
              <span data-hook="review-date">Reviewed in Germany on 23 March 2026</span>
              <span data-hook="avp-badge">Verified Purchase</span>
              <span data-hook="review-body"><span>Sehr gutes Bild und guter Sound.</span></span>
            </div>
          </div>
        </li>
      </body>
    </html>
    """

    page = parser.parse_review_page(
        html,
        source_url="https://www.amazon.de/-/en/product-reviews/B0F2JCZPB4/ref=cm_cr_dp_d_show_all_btm?ie=UTF8",
    )

    assert [review["review_id"] for review in page.reviews] == ["RDUPLICATE1"]


def test_parse_review_page_detects_sign_in_gate() -> None:
    parser = AmazonParser(get_marketplace("de"))

    page = parser.parse_review_page(
        fixture_text("review_page_signin.html"),
        source_url="https://www.amazon.de/-/en/product-reviews/B0F2JCZPB4/ref=cm_cr_dp_d_show_all_btm?ie=UTF8",
    )

    assert page.sign_in_required is True
    assert page.reviews == []


@pytest.mark.parametrize(
    ("marketplace_code", "fixture_name"),
    [
        ("de", "detail_microwave_de.html"),
        ("fr", "detail_microwave_fr.html"),
        ("es", "detail_microwave_es.html"),
    ],
)
def test_parse_detail_page_normalizes_microwave_specs(
    marketplace_code: str,
    fixture_name: str,
) -> None:
    parser = AmazonParser(get_marketplace(marketplace_code))

    item = parser.parse_product_detail(
        fixture_text(fixture_name),
        source_url=f"https://www.amazon.{marketplace_code}/dp/B0TEST1234",
        asin="B0TEST1234",
    )

    assert item.specs_normalized["capacity_l"] == 20
    assert item.specs_normalized["microwave_power_w"] == 700
    assert item.specs_normalized["power_levels"] == 6
    assert item.specs_normalized["defrost"] is True
    assert item.specs_normalized["timer_minutes"] == 30
    assert item.specs_normalized["dimensions_cm"] == {"depth": 35.3, "width": 44.6, "height": 24.3}
    assert item.specs_normalized["weight_kg"] == 9.9
    assert item.specs_normalized["turntable_cm"] == 24.5
    assert item.specs_normalized["install_type"] == "freestanding"
    assert item.specs_normalized["control_type"] == "manual"
    assert item.specs_normalized["color"] == "white"
    assert item.specs_normalized["brand_name"] == "Orbegozo"
    assert item.specs_normalized["model_name"] == "MI 2115"
    assert item.specs_normalized["manufacturer"] == "Orbegozo"
    assert item.specs
    assert item.specs == item.specs_raw


def test_scraper_get_normalizes_bare_asin_to_canonical_product_url(monkeypatch: pytest.MonkeyPatch) -> None:
    scraper = AmazonScraper("de")
    monkeypatch.setattr(
        AmazonHttpClient,
        "fetch_product_page",
        lambda self, identifier: fixture_text("detail_lg_c4_de.html"),
    )

    item = scraper.get("B0LGC4DE65")

    assert item.url == "https://www.amazon.de/dp/B0LGC4DE65"


def test_fetch_search_page_builds_structured_query_and_price_params(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AmazonHttpClient(get_marketplace("de"))
    captured: dict[str, str] = {}

    def fake_fetch(self, url: str) -> str:
        captured["url"] = url
        return ""

    monkeypatch.setattr(AmazonHttpClient, "fetch_url", fake_fetch)

    client.fetch_search_page("tv", brand="LG", model="C4", min_price=100, max_price=560)

    assert "k=tv+LG+C4" in captured["url"]
    assert "rnid=12419339031" in captured["url"]
    assert "low-price=100" in captured["url"]
    assert "high-price=560" in captured["url"]


def test_compose_search_query_orders_base_brand_model() -> None:
    assert compose_search_query("tv", brand="LG", model="C4") == "tv LG C4"


def test_compose_search_query_skips_brand_and_model_already_present_in_base() -> None:
    assert compose_search_query("Pilexil Forte Max", brand="PILEXIL", model="Forte Max") == "Pilexil Forte Max"


def test_compose_search_query_keeps_missing_brand_and_model_context() -> None:
    assert compose_search_query("hair loss", brand="PILEXIL", model="Forte Max") == "hair loss PILEXIL Forte Max"


def test_parse_search_results_extracts_pagination_links() -> None:
    parser = AmazonParser(get_marketplace("de"))
    html = """
    <html>
      <body>
        <div data-component-type="s-search-result" data-asin="B0AAA">
          <h2><a href="/dp/B0AAA"><span>Orbegozo MI 2115 Microwave</span></a></h2>
          <span class="a-price"><span class="a-offscreen">€51.98</span></span>
        </div>
        <div class="s-pagination-strip">
          <span class="s-pagination-item s-pagination-selected">1</span>
          <a class="s-pagination-item s-pagination-button" href="/s?k=microondas&page=2&ref=sr_pg_2">2</a>
          <a class="s-pagination-item s-pagination-next s-pagination-button" href="/s?k=microondas&page=2&ref=sr_pg_2">Next</a>
        </div>
      </body>
    </html>
    """

    page = parser.parse_search_page(html)

    assert [item.asin for item in page.records] == ["B0AAA"]
    assert page.current_page == 1
    assert page.available_pages == [1, 2]
    assert page.next_page_url == "https://www.amazon.de/s?k=microondas&page=2&ref=sr_pg_2"


def test_blocked_pages_raise_explicit_error() -> None:
    parser = AmazonParser(get_marketplace("de"))

    with pytest.raises(AmazonBlockedError):
        parser.parse_search_results(fixture_text("blocked_503.html"))

    with pytest.raises(AmazonBlockedError):
        parser.parse_search_results(
            '<html><head><meta http-equiv="refresh" content="5; URL=\'/s?k=test&bm-verify=token\'" /></head>'
            "<body><script>triggerInterstitialChallenge()</script></body></html>"
        )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("€1.277,17", 1277.17), ("€1,277.17", 1277.17), ("4.5 out of 5 stars", 4.5), ("4,5 von 5 Sternen", 4.5)],
)
def test_parse_float_from_text_handles_eu_and_us_number_formats(raw_value: str, expected: float) -> None:
    assert parse_float_from_text(raw_value) == expected


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("(1.5K)", 1500), ("1,543 ratings", 1543), ("943", 943)],
)
def test_parse_review_count_handles_abbreviated_counts(raw_value: str, expected: int) -> None:
    assert parse_review_count(raw_value) == expected
