from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse


BASE_URL = "https://www.aliexpress.com"


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return " ".join(value.split())


def extract_json_object(text: str, start_index: int) -> dict[str, Any] | None:
    brace_index = text.find("{", start_index)
    if brace_index < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(brace_index, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[brace_index : index + 1])
                except json.JSONDecodeError:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def page_state(page_html: str) -> dict[str, Any]:
    for match in re.finditer(
        r"<script[^>]+(?:id|data-spm-anchor-id)=[\"'][^\"']*(?:__AER_DATA__|__INIT_STATE__|runParams)[^\"']*[\"'][^>]*>(.*?)</script>",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        text = html.unescape(match.group(1)).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = extract_json_object(text, 0)
        if isinstance(parsed, dict):
            return parsed
    for marker in ("window.runParams", "window.__INIT_STATE__", "window._d_data_", "data:"):
        index = page_html.find(marker)
        if index >= 0:
            parsed = extract_json_object(page_html, index)
            if parsed:
                return parsed
    return {}


def iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def first_value(value: Any, keys: set[str]) -> Any:
    for item in iter_dicts(value):
        for key in keys:
            if key in item and item[key] not in (None, ""):
                return item[key]
    return None


def first_value_ordered(value: Any, keys: tuple[str, ...]) -> Any:
    for key in keys:
        found = first_value(value, {key})
        if found not in (None, ""):
            return found
    return None


def _price_number(price_text: str | None) -> float | None:
    if not price_text:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)", price_text.replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _currency(price_text: str | None, default: str = "EUR") -> str | None:
    if not price_text:
        return None
    if "€" in price_text or "EUR" in price_text.upper():
        return "EUR"
    if "$" in price_text or "USD" in price_text.upper():
        return "USD"
    return default


PRICE_PATTERN = re.compile(
    r"(?P<prefix>[€$])\s*(?P<prefix_major>\d+)(?:\s*[.,]\s*(?P<prefix_minor>\d{1,2}))?"
    r"|(?P<suffix_major>\d+)(?:\s*[.,]\s*(?P<suffix_minor>\d{1,2}))?\s*(?P<suffix>€|EUR|USD)\b",
    flags=re.IGNORECASE,
)


def _normalize_price_match(match: re.Match[str]) -> str:
    if match.group("prefix"):
        amount = match.group("prefix_major")
        if match.group("prefix_minor"):
            amount += f".{match.group('prefix_minor')}"
        return f"{match.group('prefix')}{amount}"
    amount = match.group("suffix_major")
    if match.group("suffix_minor"):
        amount += f".{match.group('suffix_minor')}"
    return f"{amount} {match.group('suffix')}"


def first_price_text(text: str) -> str | None:
    match = PRICE_PATTERN.search(text)
    return _normalize_price_match(match) if match else None


def price_details(state: dict[str, Any]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in iter_dicts(state):
        for key in ("salePrice", "formattedPrice", "price", "priceText", "skuAmount", "skuActivityAmount"):
            value = item.get(key)
            if value in (None, "", [], {}):
                continue
            text = clean_text(str(value))
            if not text:
                continue
            entry_key = (key, text)
            if entry_key in seen:
                continue
            seen.add(entry_key)
            details.append(
                {
                    "source": key,
                    "price_text": text,
                    "amount": _price_number(text),
                    "currency": _currency(text),
                }
            )
            if len(details) >= 25:
                return details
    return details


def shipping_details(state: dict[str, Any]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in iter_dicts(state):
        for key in ("shippingText", "logistics", "delivery", "shipping", "freight", "logisticsText"):
            value = item.get(key)
            if value in (None, "", [], {}):
                continue
            text = clean_text(str(value))
            if not text or text in seen:
                continue
            seen.add(text)
            details.append({"source": key, "text": text, "free_delivery": "free" in text.lower()})
            if len(details) >= 25:
                return details
    return details


def _item_id_from_url(url: str) -> str | None:
    match = re.search(r"/item/(\d+)(?:\.html)?", url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("productId", "itemId"):
        if query.get(key):
            return query[key][0]
    return None


def normalize_product_url(value: str) -> str:
    if value.startswith("//"):
        value = "https:" + value
    if value.startswith("/"):
        value = urljoin(BASE_URL, value)
    return value.split("?", 1)[0]


def parse_search(page_html: str, *, query: str, page: int, url: str) -> dict[str, Any]:
    state = page_state(page_html)
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in iter_dicts(state):
        product_url = item.get("productDetailUrl") or item.get("productUrl") or item.get("itemUrl") or item.get("url")
        title = item.get("title") or item.get("productTitle") or item.get("subject")
        if not product_url or not title:
            continue
        product_url = normalize_product_url(str(product_url))
        item_id = str(item.get("productId") or item.get("itemId") or _item_id_from_url(product_url) or "")
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        price_text = str(item.get("salePrice") or item.get("price") or item.get("formattedPrice") or item.get("priceText") or "")
        shipping_text = str(item.get("shippingText") or item.get("logistics") or item.get("delivery") or "")
        product_link = product_url
        results.append(
            {
                "item_id": item_id,
                "url": product_link,
                "product_link": product_link,
                "title": clean_text(str(title)),
                "price_text": clean_text(price_text) or None,
                "currency": _currency(price_text),
                "shipping_text": clean_text(shipping_text) or None,
                "free_delivery": "free" in shipping_text.lower() if shipping_text else None,
                "rating": item.get("averageStar") or item.get("rating"),
                "orders_text": clean_text(str(item.get("tradeDesc") or item.get("orders") or "")) or None,
                "seller": clean_text(str(item.get("storeName") or item.get("seller") or "")) or None,
                "image_url": item.get("imageUrl") or item.get("image") or item.get("productImage"),
                "badges": [clean_text(str(value)) for value in item.get("badges", [])] if isinstance(item.get("badges"), list) else [],
                "snippet": clean_text(str(title)),
            }
        )
    if not results:
        pattern = re.compile(r'<a[^>]+href=["\'](?P<href>[^"\']*/item/(?P<id>\d+)[^"\']*)["\'][^>]*>(?P<title>.*?)</a>', re.IGNORECASE | re.DOTALL)
        for match in pattern.finditer(page_html):
            item_id = match.group("id")
            if item_id in seen:
                continue
            seen.add(item_id)
            href = normalize_product_url(html.unescape(match.group("href")))
            card_text = clean_text(match.group("title"))
            after_text = clean_text(page_html[match.start() : match.end() + 1400])
            text = card_text or after_text
            price_text = first_price_text(card_text) or first_price_text(after_text)
            shipping_match = re.search(r"(free shipping|free delivery|shipping[^.]{0,80})", text, flags=re.IGNORECASE)
            results.append(
                {
                    "item_id": item_id,
                    "url": href,
                    "product_link": href,
                    "title": clean_text(match.group("title")),
                    "price_text": price_text,
                    "currency": _currency(price_text),
                    "shipping_text": clean_text(shipping_match.group(1)) if shipping_match else None,
                    "free_delivery": bool(shipping_match and "free" in shipping_match.group(1).lower()),
                    "rating": None,
                    "orders_text": None,
                    "seller": None,
                    "image_url": None,
                    "badges": [],
                    "snippet": text[:300],
                }
            )
    body_text = clean_text(page_html).lower()
    return {
        "command": "search",
        "query": query,
        "page": page,
        "url": url,
        "results": results,
        "result_count": len(results),
        "no_results": not results and ("no results" in body_text or "nothing found" in body_text),
    }


def parse_specs(page_html: str) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    patterns = [
        r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>",
        r"<li[^>]+class=[\"'][^\"']*(?:spec|property)[^\"']*[\"'][^>]*>(.*?)</li>",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, page_html, flags=re.IGNORECASE | re.DOTALL):
            if len(match.groups()) == 2:
                name = clean_text(match.group(1))
                value = clean_text(match.group(2))
            else:
                text = clean_text(match.group(1))
                if ":" not in text:
                    continue
                name, value = [part.strip() for part in text.split(":", 1)]
            if name and value:
                specs.append({"name": name, "value": value})
    return specs


SITE_CHROME_SPEC_NAMES = {
    "alibaba group",
    "browse by category",
    "help",
    "yardım",
    "birden fazla dili destekleyen aliexpress siteleri",
}


def _looks_like_site_chrome_specs(specs: list[dict[str, str]]) -> bool:
    if not specs:
        return False
    matched = 0
    for spec in specs:
        if spec.get("name", "").strip().lower() in SITE_CHROME_SPEC_NAMES:
            matched += 1
    return matched >= 2 or matched == len(specs)


def parse_variants(state: dict[str, Any]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for item in iter_dicts(state):
        sku_id = item.get("skuId") or item.get("skuIdStr")
        if not sku_id:
            continue
        label = item.get("skuPropIds") or item.get("skuAttr") or item.get("name")
        price_text = str(item.get("skuActivityAmount") or item.get("skuAmount") or item.get("price") or "")
        variants.append(
            {
                "sku_id": str(sku_id),
                "label": clean_text(str(label)) if label else None,
                "price_text": clean_text(price_text) or None,
                "available": item.get("availQuantity", 1) not in (0, "0"),
            }
        )
    return variants[:50]


def parse_product(page_html: str, *, item_id: str, url: str) -> dict[str, Any]:
    state = page_state(page_html)
    title = clean_text(str(first_value_ordered(state, ("subject", "title", "productTitle")) or ""))
    if not title:
        title = clean_text(re.search(r"<h1[^>]*>(.*?)</h1>", page_html, flags=re.IGNORECASE | re.DOTALL).group(1)) if re.search(r"<h1[^>]*>(.*?)</h1>", page_html, flags=re.IGNORECASE | re.DOTALL) else ""
    if not title:
        title = clean_text(re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.IGNORECASE | re.DOTALL).group(1)) if re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.IGNORECASE | re.DOTALL) else ""
    description = clean_text(str(first_value_ordered(state, ("description", "productDescription", "detailDesc")) or ""))
    if not description:
        meta_description = re.search(
            r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"'](.*?)[\"']",
            page_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if meta_description:
            description = clean_text(meta_description.group(1))
    price_text = clean_text(str(first_value_ordered(state, ("salePrice", "formattedPrice", "price", "priceText")) or ""))
    shipping_text = clean_text(str(first_value_ordered(state, ("shippingText", "logistics", "delivery", "shipping")) or ""))
    all_price_details = price_details(state)
    all_shipping_details = shipping_details(state)
    free_delivery = (
        "free" in shipping_text.lower()
        if shipping_text
        else any(bool(detail.get("free_delivery")) for detail in all_shipping_details)
    )
    images_raw = first_value(state, {"imagePathList", "images", "imageUrl"})
    if isinstance(images_raw, str):
        images = [images_raw]
    elif isinstance(images_raw, list):
        images = [str(image) for image in images_raw if image]
    else:
        images = []
    variants = parse_variants(state)
    specs = parse_specs(page_html)
    sparse_product_page = not state and not title and not description and not price_text and not images and not variants
    warnings = ["product_state_missing"] if sparse_product_page else []
    if sparse_product_page and _looks_like_site_chrome_specs(specs):
        specs = []
    return {
        "command": "get",
        "item_id": item_id,
        "url": url,
        "product_link": url,
        "title": title,
        "description": description or None,
        "specs": specs,
        "variants": variants,
        "availability": clean_text(str(first_value(state, {"availability", "stockStatus"}) or "")) or None,
        "shipping_summary": {
            "shipping_text": shipping_text or None,
            "free_delivery": free_delivery,
            "ship_to": None,
            "details": all_shipping_details,
        },
        "seller": {
            "store_name": clean_text(str(first_value_ordered(state, ("storeName", "sellerName")) or "")) or None,
            "store_url": first_value(state, {"storeUrl"}),
        },
        "ratings": {
            "rating": first_value_ordered(state, ("averageStar", "rating")),
            "review_count": first_value_ordered(state, ("reviewCount", "totalReviewCount")),
            "orders_text": clean_text(str(first_value_ordered(state, ("tradeCount", "orders", "tradeDesc")) or "")) or None,
        },
        "images": images,
        "price_summary": {
            "price_text": price_text or None,
            "min_price": _price_number(price_text),
            "max_price": None,
            "currency": _currency(price_text),
            "shipping_text": shipping_text or None,
            "free_delivery": free_delivery,
            "details": all_price_details,
        },
        "source_diagnostics": {
            "embedded_state_found": bool(state),
            "spec_count": len(specs),
            "variant_count": len(variants),
            "sparse_product_page": sparse_product_page,
        },
        "warnings": warnings,
    }


def parse_reviews(page_html: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for item in iter_dicts(page_state(page_html)):
        body = item.get("feedback") or item.get("reviewContent") or item.get("content")
        if isinstance(body, (dict, list)):
            continue
        if not body:
            continue
        reviews.append(
            {
                "rating": item.get("starRating") or item.get("rating"),
                "title": clean_text(str(item.get("title") or "")) or None,
                "body": clean_text(str(body)),
                "author": clean_text(str(item.get("buyerName") or item.get("author") or "")) or None,
                "date": clean_text(str(item.get("feedbackDate") or item.get("date") or "")) or None,
                "useful_votes": item.get("usefulCount"),
                "evidence": clean_text(str(body))[:500],
            }
        )
        if limit is not None and len(reviews) >= limit:
            break
    if not reviews:
        for match in re.finditer(r"<[^>]+class=[\"'][^\"']*(?:review|feedback)[^\"']*[\"'][^>]*>(?P<body>.*?)</(?:article|div|li)>", page_html, flags=re.IGNORECASE | re.DOTALL):
            text = clean_text(match.group("body"))
            if len(text) < 12:
                continue
            reviews.append({"rating": None, "title": None, "body": text, "author": None, "date": None, "useful_votes": None, "evidence": text[:500]})
            if limit is not None and len(reviews) >= limit:
                break
    return reviews


def search_url(query: str, *, page: int, ship_to: str, currency: str, locale: str, sort: str | None = None, min_price: float | None = None, max_price: float | None = None) -> str:
    url = f"{BASE_URL}/wholesale?SearchText={quote_plus(query)}&shipTo={quote_plus(ship_to)}&currency={quote_plus(currency)}&locale={quote_plus(locale)}"
    if page > 1:
        url += f"&page={page}"
    sort_map = {
        "orders": "total_tranpro_desc",
        "newest": "newest",
        "price-asc": "price_asc",
        "price-desc": "price_desc",
    }
    if sort and sort != "relevance":
        url += f"&SortType={sort_map.get(sort, sort)}"
    if min_price is not None:
        url += f"&minPrice={min_price:g}"
    if max_price is not None:
        url += f"&maxPrice={max_price:g}"
    return url
