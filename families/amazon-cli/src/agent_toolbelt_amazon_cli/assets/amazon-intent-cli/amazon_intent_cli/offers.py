from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .amazon import detect_currency, is_probably_sign_in_html, normalize_text, parse_float_from_text
from .marketplaces import get_marketplace


DEFAULT_OFFER_MARKETPLACES = ["de", "fr", "it", "es", "nl", "se", "uk", "be", "pl", "ie"]

AMAZON_SELLER_IDS = {
    "uk": "A3P5ROKL5A1OLE",
    "de": "A3JWKAKR8XB7XF",
    "fr": "A1X6FK5RDHNB96",
    "it": "A11IL2PNWYJU7H",
    "es": "A1AT7YVPFBWXBL",
    "be": "A3Q3FYJVX702M2",
    "nl": "A17D2BRD4YMT0X",
    "pl": "A2R2221NX79QZP",
    "se": "ANU9KP01APNAG",
    "ie": "A2QHQAREJ10JUZ",
}

UNAVAILABLE_MARKERS = (
    "currently unavailable",
    "derzeit nicht verfügbar",
    "actuellement indisponible",
    "no disponible",
    "non disponibile",
    "momenteel niet verkrijgbaar",
    "obecnie niedostępny",
    "för närvarande inte tillgänglig",
)


@dataclass(slots=True)
class OfferRecord:
    marketplace: str
    domain: str
    url: str
    asin: str
    title: str = ""
    price: float | None = None
    currency: str | None = None
    shipping: float | None = None
    total: float | None = None
    store_slug: str = ""
    seller_summary: str = ""
    sold_by_amazon: bool = False
    image: str = ""
    status: str = "ok"
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_offer_url(asin: str, marketplace: str) -> str:
    domain = get_marketplace(marketplace).domain
    return f"https://{domain}/dp/{asin}?{urlencode({'_encoding': 'UTF8', 'psc': '1'})}"


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def _parse_price_whole_fraction(soup: BeautifulSoup) -> float | None:
    for node in soup.select(".a-price.aok-align-center"):
        data_size = (node.get("data-a-size") or "").strip()
        if data_size not in {"l", "xl"} or "reinventPricePriceToPayMargin" in " ".join(node.get("class", [])):
            continue
        whole = node.select_one(".a-price-whole")
        fraction = node.select_one(".a-price-fraction")
        if whole is None or fraction is None:
            continue
        whole_text = re.sub(r"[^\d]", "", _text(whole))
        fraction_text = re.sub(r"[^\d]", "", _text(fraction))
        if whole_text and fraction_text:
            return parse_float_from_text(f"{whole_text}.{fraction_text}")
    return None


def _extract_price(soup: BeautifulSoup) -> tuple[float | None, str]:
    hidden_price = soup.select_one("#twister-plus-price-data-price[value]")
    if hidden_price is not None:
        value = hidden_price.get("value", "")
        parsed = parse_float_from_text(value)
        if parsed is not None:
            return parsed, value

    selectors = (
        ".a-price.a-text-price.a-size-medium.apexPriceToPay [aria-hidden='true']",
        ".a-price.a-offscreen",
        ".a-size-medium.a-color-price.header-price.a-text-normal",
    )
    for selector in selectors:
        node = soup.select_one(selector)
        value = _text(node)
        parsed = parse_float_from_text(value)
        if parsed is not None:
            return parsed, value

    whole_fraction = _parse_price_whole_fraction(soup)
    if whole_fraction is not None:
        return whole_fraction, ""

    return None, ""


def _extract_title(soup: BeautifulSoup) -> str:
    for selector in ("#productTitle", ".a-size-large.product-title-word-break"):
        node = soup.select_one(selector)
        value = _text(node)
        if value:
            return re.sub(r"&[a-zA-Z]+;", "", value).strip()
    hidden_title = soup.select_one("input#productTitle[value]")
    return (hidden_title.get("value") or "").strip() if hidden_title is not None else ""


def _extract_store_slug(soup: BeautifulSoup) -> str:
    href = soup.select_one("#bylineInfo[href]")
    if href is None:
        return ""
    match = re.search(r"/stores/([^/?#]+)", href.get("href", ""))
    return match.group(1) if match else ""


def _extract_image(soup: BeautifulSoup) -> str:
    node = soup.select_one("#imgTagWrapperId img[src], #landingImage[src]")
    return node.get("src", "") if node is not None else ""


def _extract_shipping(soup: BeautifulSoup) -> float:
    delivery = soup.select_one("#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE")
    price_text = ""
    if delivery is not None:
        priced = delivery.select_one("[data-csa-c-delivery-price]")
        if priced is not None:
            price_text = priced.get("data-csa-c-delivery-price", "") or _text(priced)
        else:
            price_text = _text(delivery)
    if not price_text or "free" in normalize_text(price_text):
        return 0.0
    return parse_float_from_text(price_text) or 0.0


def _extract_seller_summary(soup: BeautifulSoup) -> str:
    values: list[str] = []
    for selector in ("#merchantInfoFeature_feature_div", "#sellerProfileTriggerId"):
        value = _text(soup.select_one(selector))
        if value and value not in values:
            values.append(value)
    return " ".join(values)


def _sold_by_amazon(soup: BeautifulSoup, marketplace: str, seller_summary: str) -> bool:
    seller_id = AMAZON_SELLER_IDS.get(marketplace, "")
    html = str(soup)
    if seller_id and seller_id in html:
        return True
    normalized = normalize_text(seller_summary)
    return "amazon" in normalized


def _is_unavailable(soup: BeautifulSoup) -> bool:
    body = normalize_text(soup.get_text(" ", strip=True))
    return any(normalize_text(marker) in body for marker in UNAVAILABLE_MARKERS)


def parse_offer_html(html: str, *, marketplace: str, asin: str, url: str) -> OfferRecord:
    market = get_marketplace(marketplace)
    soup = BeautifulSoup(html, "html.parser")
    if is_probably_sign_in_html(html):
        return OfferRecord(
            marketplace=marketplace,
            domain=market.domain,
            url=url,
            asin=asin,
            currency=market.currency,
            status="sign_in_required",
        )

    price, price_text = _extract_price(soup)
    currency = detect_currency(price_text) or market.currency
    shipping = _extract_shipping(soup)
    title = _extract_title(soup)
    seller_summary = _extract_seller_summary(soup)
    status = "ok"
    failure_reason = None
    if price is None:
        status = "unavailable" if _is_unavailable(soup) else "parse_failed"
        failure_reason = "No price could be parsed."

    return OfferRecord(
        marketplace=marketplace,
        domain=market.domain,
        url=url,
        asin=asin,
        title=title,
        price=price,
        currency=currency,
        shipping=shipping if price is not None else None,
        total=round(price + shipping, 2) if price is not None else None,
        store_slug=_extract_store_slug(soup),
        seller_summary=seller_summary,
        sold_by_amazon=_sold_by_amazon(soup, marketplace, seller_summary),
        image=_extract_image(soup),
        status=status,
        failure_reason=failure_reason,
    )
