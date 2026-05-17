from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urljoin


BASE_URL = "https://www.skroutz.cy"


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return " ".join(value.split())


def _json_ld_blocks(page_html: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<body>.*?)</script>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw = clean_text(match.group("body"))
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
        elif isinstance(parsed, list):
            blocks.extend(item for item in parsed if isinstance(item, dict))
    return blocks


def _product_ld(page_html: str) -> dict[str, Any]:
    for block in _json_ld_blocks(page_html):
        if str(block.get("@type", "")).lower() == "product":
            return block
    return {}


def _first(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    return clean_text(match.group(1)) if match else default


def _price_text(text: str) -> str | None:
    match = re.search(
        r"(?:από\s*)?(\d[\d.]*\s*(?:[,.]\s*|\s+)\d{2}\s*€|\d[\d.]*\s*€)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    value = clean_text(match.group(1))
    if re.search(r"\d\s+\d{2}\s*€", value) and "," not in value and "." not in value:
        value = re.sub(r"(\d)\s+(\d{2}\s*€)", r"\1,\2", value)
    return value


def _price_number(price_text: str | None) -> float | None:
    if not price_text:
        return None
    normalized = price_text.replace("€", "").strip()
    if re.search(r"\d\s+\d{2}$", normalized) and "," not in normalized and "." not in normalized:
        normalized = re.sub(r"(\d)\s+(\d{2})$", r"\1,\2", normalized)
    normalized = normalized.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _int_from_text(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1).replace(".", ""))
    except ValueError:
        return None


def _rating_from_text(text: str) -> float | None:
    match = re.search(r"\b([1-5](?:[.,]\d)?)\b", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _product_links(page_html: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r'<a[^>]+href=["\'](?P<href>/s/(?P<id>\d+)/[^"\']+)["\'][^>]*>(?P<title>.*?)</a>', page_html, flags=re.IGNORECASE | re.DOTALL):
        href = match.group("href").split("?", 1)[0]
        if href in seen:
            continue
        seen.add(href)
        title = clean_text(match.group("title"))
        if not title:
            continue
        links.append((href, title))
    return links


def parse_search(page_html: str, *, query: str, page: int) -> dict[str, Any]:
    body_text = clean_text(page_html)
    results: list[dict[str, Any]] = []
    for block in _json_ld_blocks(page_html):
        if str(block.get("@type", "")).lower() != "itemlist":
            continue
        for element in block.get("itemListElement", []):
            if not isinstance(element, dict):
                continue
            product = element.get("item")
            if not isinstance(product, dict):
                continue
            url = str(product.get("url") or "")
            id_match = re.search(r"/s/(\d+)/", url)
            if not id_match:
                continue
            offers = product.get("offers") if isinstance(product.get("offers"), dict) else {}
            aggregate = product.get("aggregateRating") if isinstance(product.get("aggregateRating"), dict) else {}
            low_price = offers.get("lowPrice")
            price_text = f"{low_price} {offers.get('priceCurrency', 'EUR')}".strip() if low_price is not None else None
            images = product.get("image") if isinstance(product.get("image"), list) else []
            results.append(
                {
                    "product_id": id_match.group(1),
                    "url": url,
                    "title": clean_text(str(product.get("name") or "")),
                    "category": _first(r"<title>.*?-\s*(.*?)\s*\|", page_html),
                    "min_price_text": price_text,
                    "min_price": float(low_price) if isinstance(low_price, int | float) else _price_number(price_text),
                    "rating": float(aggregate["ratingValue"]) if str(aggregate.get("ratingValue") or "").replace(".", "", 1).isdigit() else None,
                    "review_count": int(aggregate["reviewCount"]) if str(aggregate.get("reviewCount") or "").isdigit() else None,
                    "shop_count": int(offers["offerCount"]) if str(offers.get("offerCount") or "").isdigit() else None,
                    "image_url": str(images[0]) if images else None,
                    "snippet": clean_text(str(product.get("name") or "")),
                }
            )
        if results:
            return {
                "command": "search",
                "query": query,
                "page": page,
                "results": results,
                "result_count": len(results),
                "no_results": False,
            }

    for href, title in _product_links(page_html):
        product_id = href.split("/")[2]
        around_index = page_html.find(href)
        excerpt_html = page_html[max(0, around_index - 600): around_index + 1600] if around_index >= 0 else page_html[:1600]
        excerpt_text = clean_text(excerpt_html)
        image_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', excerpt_html, flags=re.IGNORECASE)
        price_text = _price_text(excerpt_text)
        results.append(
            {
                "product_id": product_id,
                "url": urljoin(BASE_URL, href),
                "title": title,
                "category": _first(r"<title>(.*?)\|", page_html),
                "min_price_text": price_text,
                "min_price": _price_number(price_text),
                "rating": _rating_from_text(excerpt_text),
                "review_count": _int_from_text(r"(\d+)\s+(?:αξιολογήσεις|reviews)", excerpt_text),
                "shop_count": _int_from_text(r"σε\s+(\d+)\s+καταστήματα", excerpt_text),
                "image_url": html.unescape(image_match.group(1)) if image_match else None,
                "snippet": excerpt_text[:300],
            }
        )
    return {
        "command": "search",
        "query": query,
        "page": page,
        "results": results,
        "result_count": len(results),
        "no_results": not results and ("δεν βρέθηκαν" in body_text.lower() or "no results" in body_text.lower()),
    }


def parse_specs(page_html: str) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for match in re.finditer(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", page_html, flags=re.IGNORECASE | re.DOTALL):
        name = clean_text(match.group(1))
        value = clean_text(match.group(2))
        if name and value:
            specs.append({"name": name, "value": value})
    return specs


def parse_offers(page_html: str) -> list[dict[str, Any]]:
    offers: list[dict[str, Any]] = []
    offer_block_pattern = (
        r"<div[^>]+(?:"
        r"data-e2e=[\"']shop-offer[\"']|"
        r"data-testid=[\"'][^\"']*(?:shop|offer)[^\"']*[\"']|"
        r"class=[\"'][^\"']*(?:shop-offer|offer-card|shop-card|shop-listing)[^\"']*[\"']"
        r")[^>]*>(?P<body>.*?)</div>"
    )
    for match in re.finditer(offer_block_pattern, page_html, flags=re.IGNORECASE | re.DOTALL):
        offer_html = match.group("body")
        text = clean_text(offer_html)
        price_text = _price_text(text)
        if not price_text:
            continue
        store = _first(r"<a[^>]*>(.*?)</a>", offer_html) or _first(r"<strong[^>]*>(.*?)</strong>", offer_html)
        offers.append(
            {
                "store": store or None,
                "price_text": price_text,
                "price": _price_number(price_text),
                "delivery_text": text,
                "availability": "available" if re.search(r"available|διαθέσιμο|παράδοση", text, flags=re.IGNORECASE) else None,
                "store_rating": _rating_from_text(text),
                "row_text_excerpt": text[:300],
            }
        )
    if not offers:
        price_text = _price_text(clean_text(page_html))
        if price_text:
            offers.append(
                {
                    "store": None,
                    "price_text": price_text,
                    "price": _price_number(price_text),
                    "delivery_text": None,
                    "availability": None,
                    "store_rating": None,
                    "row_text_excerpt": clean_text(page_html)[:300],
                }
            )
    return offers


def parse_product(page_html: str, *, product_id: str, url: str) -> dict[str, Any]:
    product = _product_ld(page_html)
    title = clean_text(str(product.get("name") or "")) or _first(r"<h1[^>]*>(.*?)</h1>", page_html) or _first(r"<title>(.*?)\|", page_html)
    aggregate = product.get("aggregateRating") if isinstance(product.get("aggregateRating"), dict) else {}
    offers_ld = product.get("offers") if isinstance(product.get("offers"), dict) else {}
    price_text = _price_text(clean_text(page_html))
    if offers_ld.get("price") and not price_text:
        price_text = f"{offers_ld.get('price')} {offers_ld.get('priceCurrency', 'EUR')}".strip()
    images = product.get("image") if isinstance(product.get("image"), list) else ([product.get("image")] if product.get("image") else [])
    parsed_offers = parse_offers(page_html)
    return {
        "command": "get",
        "product_id": product_id,
        "url": url,
        "title": title,
        "category": _first(r"<nav[^>]*>(.*?)</nav>", page_html) or None,
        "description": clean_text(str(product.get("description") or "")) or None,
        "specs": parse_specs(page_html),
        "variants": [],
        "rating": float(aggregate["ratingValue"]) if str(aggregate.get("ratingValue") or "").replace(".", "", 1).isdigit() else _rating_from_text(clean_text(page_html)),
        "review_count": int(aggregate["reviewCount"]) if str(aggregate.get("reviewCount") or "").isdigit() else _int_from_text(r"(\d+)\s+(?:αξιολογήσεις|reviews)", clean_text(page_html)),
        "images": [str(image) for image in images if image],
        "shop_count": _int_from_text(r"σε\s+(\d+)\s+καταστήματα", clean_text(page_html)),
        "price_summary": {
            "min_price_text": price_text,
            "min_price": _price_number(price_text),
            "currency": "EUR" if price_text else None,
            "offer_count": len(parsed_offers),
        },
        "offers": parsed_offers,
        "warnings": [],
    }


def parse_reviews(page_html: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for match in re.finditer(r"<article[^>]+class=[\"'][^\"']*review[^\"']*[\"'][^>]*>(?P<body>.*?)</article>", page_html, flags=re.IGNORECASE | re.DOTALL):
        body = match.group("body")
        review = {
            "rating": _rating_from_text(clean_text(body)),
            "title": _first(r"<h[1-6][^>]*>(.*?)</h[1-6]>", body),
            "body": _first(r"<p[^>]*>(.*?)</p>", body),
            "author": _first(r"<span[^>]*>(.*?)</span>", body),
            "date": _first(r"<time[^>]*>(.*?)</time>", body),
            "useful_votes": _int_from_text(r"(\d+)\s+(?:useful|χρήσιμ)", clean_text(body)),
            "evidence": clean_text(body)[:500],
        }
        reviews.append(review)
        if limit is not None and len(reviews) >= limit:
            break
    return reviews


def parse_cart(page_html: str, *, url: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for match in re.finditer(r"<div[^>]+(?:cart-item|data-sku-id|cart_item)[^>]*>(?P<body>.*?)</div>", page_html, flags=re.IGNORECASE | re.DOTALL):
        row_html = match.group(0)
        row_text = clean_text(row_html)
        id_match = re.search(r'data-(?:sku-id|product-id)=["\'](\d+)["\']', row_html, flags=re.IGNORECASE)
        link_match = re.search(r'href=["\'](?P<href>/s/(?P<id>\d+)/[^"\']+)["\']', row_html, flags=re.IGNORECASE)
        product_id = id_match.group(1) if id_match else (link_match.group("id") if link_match else None)
        quantity_match = re.search(r'(?:name=["\']quantity["\'][^>]+value=["\']|quantity["\']?\s*[:=]\s*["\']?)(\d+)', row_html, flags=re.IGNORECASE)
        price_text = _price_text(row_text)
        items.append(
            {
                "product_id": product_id,
                "title": _first(r"<a[^>]*>(.*?)</a>", row_html),
                "quantity": int(quantity_match.group(1)) if quantity_match else None,
                "price_text": price_text,
                "seller": None,
                "availability": _first(r'class=["\'][^"\']*availability[^"\']*["\'][^>]*>(.*?)</', row_html) or None,
                "image_url": _first(r'<img[^>]+src=["\']([^"\']+)["\']', row_html) or None,
                "product_url": urljoin(BASE_URL, link_match.group("href")) if link_match else None,
                "row_text_excerpt": row_text[:400],
            }
        )
    return {
        "command": "cart.list",
        "url": url,
        "final_url": url,
        "status": "ok",
        "items": items,
        "item_count": len(items),
        "warnings": [],
    }
