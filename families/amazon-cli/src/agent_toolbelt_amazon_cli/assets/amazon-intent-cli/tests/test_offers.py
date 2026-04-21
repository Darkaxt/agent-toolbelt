import json

from amazon_intent_cli.offers import (
    AMAZON_SELLER_IDS,
    DEFAULT_OFFER_MARKETPLACES,
    build_offer_url,
    parse_offer_html,
)


def test_default_offer_marketplaces_match_eurosaver_coverage() -> None:
    assert DEFAULT_OFFER_MARKETPLACES == ["de", "fr", "it", "es", "nl", "se", "uk", "be", "pl", "ie"]
    assert set(AMAZON_SELLER_IDS) == set(DEFAULT_OFFER_MARKETPLACES)


def test_build_offer_url_uses_same_asin_amazon_dp_url() -> None:
    assert build_offer_url("B0F2JCZPB4", "uk") == (
        "https://www.amazon.co.uk/dp/B0F2JCZPB4?_encoding=UTF8&psc=1"
    )


def test_parse_offer_html_extracts_price_shipping_store_image_and_amazon_seller() -> None:
    html = """
    <html>
      <body>
        <span id="productTitle" class="a-size-large product-title-word-break">LG OLED65C5ELB TV</span>
        <input id="twister-plus-price-data-price" value="999.99">
        <a id="bylineInfo" href="/stores/LG/page/ABC">Visit the LG Store</a>
        <div id="imgTagWrapperId"><img src="https://example.test/tv.jpg"></div>
        <div id="merchantInfoFeature_feature_div">Sold by Amazon EU S.a.r.L.</div>
        <a id="sellerProfileTriggerId" href="/sp?seller=A3JWKAKR8XB7XF">Amazon EU S.a.r.L.</a>
        <div id="mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE">
          <span data-csa-c-delivery-price="€12.34">Delivery €12.34</span>
        </div>
      </body>
    </html>
    """

    offer = parse_offer_html(html, marketplace="de", asin="B0F2JCZPB4", url="https://www.amazon.de/dp/B0F2JCZPB4")

    assert offer.status == "ok"
    assert offer.price == 999.99
    assert offer.shipping == 12.34
    assert offer.total == 1012.33
    assert offer.title == "LG OLED65C5ELB TV"
    assert offer.store_slug == "LG"
    assert offer.seller_summary == "Sold by Amazon EU S.a.r.L. Amazon EU S.a.r.L."
    assert offer.sold_by_amazon is True
    assert offer.image == "https://example.test/tv.jpg"


def test_parse_offer_html_uses_price_whole_fraction_fallback_and_free_shipping() -> None:
    html = """
    <html>
      <body>
        <span id="productTitle">Samsung Microwave</span>
        <span class="a-price aok-align-center" data-a-size="l">
          <span aria-hidden="true">
            <span class="a-price-whole">49</span><span class="a-price-fraction">90</span>
          </span>
        </span>
        <div id="mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE">
          <span data-csa-c-delivery-price="">FREE delivery</span>
        </div>
      </body>
    </html>
    """

    offer = parse_offer_html(html, marketplace="fr", asin="B0TEST1234", url="https://www.amazon.fr/dp/B0TEST1234")

    assert offer.status == "ok"
    assert offer.price == 49.90
    assert offer.shipping == 0.0
    assert offer.total == 49.90


def test_parse_offer_html_returns_parse_failed_without_price() -> None:
    offer = parse_offer_html(
        "<html><body><span id='productTitle'>Unavailable</span></body></html>",
        marketplace="es",
        asin="B0TEST1234",
        url="https://www.amazon.es/dp/B0TEST1234",
    )

    assert offer.status == "parse_failed"
    assert offer.price is None
    assert offer.total is None


def test_offer_output_does_not_contain_eurosaver_backend_urls() -> None:
    offer = parse_offer_html(
        "<html><body><input id='twister-plus-price-data-price' value='10.00'></body></html>",
        marketplace="de",
        asin="B0TEST1234",
        url="https://www.amazon.de/dp/B0TEST1234",
    )

    serialized = json.dumps(offer.to_dict())
    assert "eurosaver.net" not in serialized
    assert "realtime.eurosaver.net" not in serialized
