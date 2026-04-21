from __future__ import annotations

from dataclasses import asdict, dataclass, field
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

NON_DELIVERABLE_MARKERS = (
    "cannot be shipped to your selected delivery location",
    "can't be shipped to your selected delivery location",
    "cannot be delivered to your selected delivery location",
    "not deliverable to your selected delivery location",
    "kann nicht an den ausgewählten lieferort versendet werden",
    "kann nicht an ihren lieferort versendet werden",
    "no se puede enviar a la ubicación de entrega seleccionada",
    "no se puede entregar en la ubicación seleccionada",
    "ne peut pas être expédié à l'adresse de livraison sélectionnée",
    "non può essere spedito all'indirizzo selezionato",
    "kan niet worden verzonden naar je geselecteerde bezorglocatie",
    "kan inte levereras till din valda leveransadress",
    "nie można wysłać na wybrany adres dostawy",
)

FREE_DELIVERY_MARKERS = (
    "free",
    "gratis",
    "gratuit",
    "kostenlos",
    "bezplat",
    "fri frakt",
)

ZERO_WIDTH_TRANSLATION = str.maketrans("", "", "\u200b\u200c\u200d\ufeff")
DELIVERY_PREFIX_PATTERNS = (
    r"^deliver(?:y|ing)?\s+to\s+",
    r"^ship(?:ping)?\s+to\s+",
    r"^liefer(?:n|ung)?\s+(?:nach|an)\s+",
    r"^env(?:i|í)ar\s+a\s+",
    r"^entregar\s+a\s+",
    r"^livr(?:er|aison)\s+(?:à|a)\s+",
    r"^consegna\s+a\s+",
    r"^bezorgen\s+in\s+",
    r"^leverera\s+till\s+",
    r"^dostarcz\s+do\s+",
)


@dataclass(slots=True)
class OfferRecord:
    marketplace: str
    domain: str
    url: str
    asin: str
    title: str = ""
    price: float | None = None
    price_ex_vat: float | None = None
    price_incl_vat: float | None = None
    vat_amount: float | None = None
    vat_rate: float | None = None
    currency: str | None = None
    shipping: float | None = None
    total: float | None = None
    comparison_price: float | None = None
    comparison_total: float | None = None
    comparison_basis: str | None = None
    store_slug: str = ""
    seller_summary: str = ""
    sold_by_amazon: bool = False
    image: str = ""
    delivery_address: dict[str, str] | None = None
    delivery_date_text: str = ""
    deliverable: bool | None = None
    address_match: bool | None = None
    eligible_for_best: bool = True
    exclusion_reasons: list[str] = field(default_factory=list)
    status: str = "ok"
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_offer_url(asin: str, marketplace: str) -> str:
    domain = get_marketplace(marketplace).domain
    return f"https://{domain}/dp/{asin}?{urlencode({'_encoding': 'UTF8', 'psc': '1'})}"


def _text(node) -> str:
    return _clean_text(node.get_text(" ", strip=True)) if node is not None else ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(ZERO_WIDTH_TRANSLATION).replace("\xa0", " ")).strip()


def _strip_delivery_prefix(value: str) -> str:
    cleaned = _clean_text(value)
    for pattern in DELIVERY_PREFIX_PATTERNS:
        updated = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        if updated != cleaned:
            return _clean_text(updated)
    return cleaned


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


def _extract_vat_prices(soup: BeautifulSoup, fallback_price: float | None) -> tuple[float | None, float | None]:
    ex_vat_node = soup.select_one("#price_vat_excl .a-offscreen, #price_vat_excl")
    price_ex_vat = parse_float_from_text(_text(ex_vat_node)) if ex_vat_node is not None else None
    price_incl_vat = None

    price_vat_excl = soup.select_one("#price_vat_excl")
    if price_vat_excl is not None:
        for sibling in price_vat_excl.find_next_siblings():
            sibling_text = _text(sibling)
            normalized = normalize_text(sibling_text)
            if "incl vat" not in normalized:
                continue
            price_node = sibling.select_one(".a-offscreen")
            price_incl_vat = parse_float_from_text(_text(price_node) or sibling_text)
            if price_incl_vat is not None:
                break

    if price_incl_vat is None and price_ex_vat is not None and fallback_price is not None:
        price_incl_vat = fallback_price if fallback_price >= price_ex_vat else None
    if price_incl_vat is None and price_ex_vat is None:
        price_incl_vat = fallback_price
    return price_ex_vat, price_incl_vat


def _calculate_vat(price_ex_vat: float | None, price_incl_vat: float | None) -> tuple[float | None, float | None]:
    if price_ex_vat is None or price_incl_vat is None or price_ex_vat <= 0 or price_incl_vat < price_ex_vat:
        return None, None
    vat_amount = round(price_incl_vat - price_ex_vat, 2)
    vat_rate = round((vat_amount / price_ex_vat) * 100, 2)
    return vat_amount, vat_rate


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


def _has_non_deliverable_marker(soup: BeautifulSoup) -> bool:
    body = normalize_text(soup.get_text(" ", strip=True))
    return any(normalize_text(marker) in body for marker in NON_DELIVERABLE_MARKERS)


def _extract_delivery_info(soup: BeautifulSoup) -> tuple[float, str, bool | None]:
    delivery = soup.select_one(
        "#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE, "
        "#deliveryBlockMessage, "
        "#deliveryBlock_feature_div"
    )
    price_text = ""
    date_text = ""
    deliverable: bool | None = False if _has_non_deliverable_marker(soup) else None
    if delivery is not None:
        priced = delivery.select_one("[data-csa-c-delivery-price]")
        if priced is not None:
            price_text = priced.get("data-csa-c-delivery-price", "") or _text(priced)
            date_text = _clean_text(priced.get("data-csa-c-delivery-time", "") or "")
        else:
            price_text = _text(delivery)
        if deliverable is not False:
            deliverable = True
    normalized_price_text = normalize_text(price_text)
    if not price_text or any(marker in normalized_price_text for marker in FREE_DELIVERY_MARKERS):
        return 0.0, date_text, deliverable
    return parse_float_from_text(price_text) or 0.0, date_text, deliverable


def _address_from_lines(line1: str, line2: str, raw: str | None = None) -> dict[str, str] | None:
    line1 = _clean_text(line1)
    line2 = _strip_delivery_prefix(line2)
    raw = _clean_text(raw or " ".join(part for part in (line1, line2) if part))
    if not line1 and not line2 and not raw:
        return None
    location_line = line2 or raw
    postal_match = re.search(r"\b\d{4,6}\b", location_line)
    postal_code = postal_match.group(0) if postal_match else ""
    location = _clean_text(re.sub(r"\b\d{4,6}\b", "", location_line).strip(" -,\u2013\u2014"))
    normalized_key = normalize_text(" ".join(part for part in (location, postal_code) if part) or location_line)
    return {
        "line1": line1,
        "line2": line2 or location_line,
        "raw": raw,
        "location": location,
        "postal_code": postal_code,
        "normalized_key": normalized_key,
    }


def _split_contextual_address(value: str) -> tuple[str, str]:
    cleaned = _clean_text(value)
    for separator in (" - ", " – ", " — "):
        if separator in cleaned:
            line1, line2 = cleaned.rsplit(separator, 1)
            return line1, line2
    return "", cleaned


def extract_delivery_address_from_html(html: str) -> dict[str, str] | None:
    soup = BeautifulSoup(html, "html.parser")
    return _extract_delivery_address(soup)


def _extract_delivery_address(soup: BeautifulSoup) -> dict[str, str] | None:
    contextual = _text(soup.select_one("#contextualIngressPtLabel_deliveryShortLine"))
    if contextual:
        line1, line2 = _split_contextual_address(contextual)
        return _address_from_lines(line1, line2, contextual)

    contextual_link = soup.select_one("#contextualIngressPtLink[aria-label]")
    if contextual_link is not None:
        value = contextual_link.get("aria-label", "")
        line1, line2 = _split_contextual_address(value)
        return _address_from_lines(line1, line2, value)

    header_line1 = _text(soup.select_one("#glow-ingress-line1"))
    header_line2 = _text(soup.select_one("#glow-ingress-line2"))
    if header_line1 or header_line2:
        return _address_from_lines(header_line1, header_line2)
    return None


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
    price_ex_vat, price_incl_vat = _extract_vat_prices(soup, price)
    if price is None:
        price = price_incl_vat or price_ex_vat
    vat_amount, vat_rate = _calculate_vat(price_ex_vat, price_incl_vat)
    currency = detect_currency(price_text) or market.currency
    shipping, delivery_date_text, deliverable = _extract_delivery_info(soup)
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
        price_ex_vat=price_ex_vat,
        price_incl_vat=price_incl_vat,
        vat_amount=vat_amount,
        vat_rate=vat_rate,
        currency=currency,
        shipping=shipping if price is not None else None,
        total=round(price + shipping, 2) if price is not None else None,
        store_slug=_extract_store_slug(soup),
        seller_summary=seller_summary,
        sold_by_amazon=_sold_by_amazon(soup, marketplace, seller_summary),
        image=_extract_image(soup),
        delivery_address=_extract_delivery_address(soup),
        delivery_date_text=delivery_date_text,
        deliverable=deliverable,
        eligible_for_best=status == "ok",
        status=status,
        failure_reason=failure_reason,
    )
