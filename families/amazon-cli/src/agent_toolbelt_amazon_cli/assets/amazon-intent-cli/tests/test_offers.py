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


def test_parse_business_offer_html_extracts_vat_delivery_date_and_address() -> None:
    html = """
    <html>
      <body>
        <span id="productTitle">Pilexil Forte Max Drinkable Anti-Hair Loss Pack 2 x 45 Units</span>
        <div id="corePrice_feature_div">
          <div class="a-section a-spacing-micro">
            <span id="price_vat_excl" class="a-price a-text-price">
              <span class="a-offscreen">€116.89</span>
            </span>
            <span class="a-size-base a-color-price a-text-normal">
              (<span class="a-price a-text-price"><span class="a-offscreen">141.44</span></span> incl. VAT)
            </span>
          </div>
        </div>
        <input type="hidden" id="twister-plus-price-data-price" value="141.44">
        <div id="mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE">
          <span
            data-csa-c-delivery-price="€7.90"
            data-csa-c-delivery-time="28 - 29 April">€7.90 delivery 28 - 29 April</span>
        </div>
        <a id="contextualIngressPtLink" aria-label="Deliver to José - Almería 04006‌" href="#">
          <div id="contextualIngressPtLabel_deliveryShortLine">
            <span>Deliver to José -&nbsp;</span><span>Almería 04006‌</span>
          </div>
        </a>
      </body>
    </html>
    """

    offer = parse_offer_html(html, marketplace="de", asin="B0DHVGHPF9", url="https://www.amazon.de/dp/B0DHVGHPF9")

    assert offer.price == 141.44
    assert offer.price_ex_vat == 116.89
    assert offer.price_incl_vat == 141.44
    assert offer.vat_amount == 24.55
    assert offer.vat_rate == 21.0
    assert offer.shipping == 7.90
    assert offer.delivery_date_text == "28 - 29 April"
    assert offer.deliverable is True
    assert offer.delivery_address is not None
    assert offer.delivery_address["line2"] == "Almería 04006"
    assert offer.delivery_address["postal_code"] == "04006"
    assert offer.delivery_address["normalized_key"] == "almeria 04006"


def test_parse_offer_html_extracts_search_header_address() -> None:
    html = """
    <html>
      <body>
        <span id="productTitle">Address test</span>
        <input id="twister-plus-price-data-price" value="10.00">
        <span id="glow-ingress-line1">Deliver to José</span>
        <span id="glow-ingress-line2">Almería 04006‌</span>
      </body>
    </html>
    """

    offer = parse_offer_html(html, marketplace="de", asin="B0TEST1234", url="https://www.amazon.de/dp/B0TEST1234")

    assert offer.delivery_address is not None
    assert offer.delivery_address["line1"] == "Deliver to José"
    assert offer.delivery_address["line2"] == "Almería 04006"
    assert offer.delivery_address["normalized_key"] == "almeria 04006"


def test_parse_offer_html_strips_delivery_prefix_from_unsplit_contextual_address() -> None:
    html = """
    <html>
      <body>
        <span id="productTitle">Address test</span>
        <input id="twister-plus-price-data-price" value="10.00">
        <a id="contextualIngressPtLink" aria-label="Deliver to Luxembourg" href="#"></a>
      </body>
    </html>
    """

    offer = parse_offer_html(html, marketplace="es", asin="B0TEST1234", url="https://www.amazon.es/dp/B0TEST1234")

    assert offer.delivery_address is not None
    assert offer.delivery_address["line2"] == "Luxembourg"
    assert offer.delivery_address["normalized_key"] == "luxembourg"


def test_parse_offer_html_marks_non_deliverable_offer() -> None:
    html = """
    <html>
      <body>
        <span id="productTitle">Unavailable delivery test</span>
        <input id="twister-plus-price-data-price" value="10.00">
        <div id="deliveryBlockMessage">This item cannot be shipped to your selected delivery location.</div>
      </body>
    </html>
    """

    offer = parse_offer_html(html, marketplace="uk", asin="B0TEST1234", url="https://www.amazon.co.uk/dp/B0TEST1234")

    assert offer.status == "ok"
    assert offer.deliverable is False


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
