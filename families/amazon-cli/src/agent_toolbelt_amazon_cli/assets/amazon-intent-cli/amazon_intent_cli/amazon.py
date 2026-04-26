from __future__ import annotations

import re
import unicodedata
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse

import httpx
from bs4 import BeautifulSoup

from .marketplaces import Marketplace, get_marketplace
from .models import BrowserSession, ProductRecord, ReviewPage, SearchPage
from .normalization import normalize_specs


class AmazonBlockedError(RuntimeError):
    """Raised when Amazon returns a captcha or anti-automation page."""


def is_probably_blocked_html(html: str) -> bool:
    lowered = html.casefold()
    return any(
        token in lowered
        for token in (
            "validatecaptcha",
            "opfcaptcha",
            "api-services-support@amazon.com",
            "bm-verify=",
            "triggerinterstitialchallenge",
            "interstitialchallenge",
            "tut uns leid",
            "klicke auf die schaltfläche unten, um mit dem einkauf fortzufahren",
        )
    )


def is_probably_sign_in_html(html: str) -> bool:
    lowered = html.casefold()
    return "amazon sign in" in lowered or 'name="signin"' in lowered or 'id="ap_signin_form"' in lowered


def normalize_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_only.casefold()).strip()


def infer_brand(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        return ""
    token = cleaned.split()[0]
    return re.sub(r"[^A-Za-z0-9]+$", "", token)


def looks_like_non_brand_label(value: str) -> bool:
    normalized = normalize_text(value)
    return normalized in {
        "sponsored",
        "patrocinado",
        "gesponsert",
        "sponsorise",
        "sponsorise d",
        "sponsorise e",
        "sponsorisee",
        "sponsorisees",
        "amazon s choice",
        "amazon choice",
        "best seller",
        "bestseller",
    }


def strip_promotional_prefixes(value: str) -> str:
    cleaned = value.strip()
    patterns = (
        r"^(?:sponsored|sponsored ad)\s*[–-]\s*",
        r"^patrocinado\s*[–-]\s*",
        r"^gesponsert\s*[–-]\s*",
        r"^sponsorisé\s*[–-]\s*",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def parse_float_from_text(value: str) -> float | None:
    match = re.search(r"([0-9][0-9\s\.,]*)", value)
    if not match:
        return None
    candidate = re.sub(r"\s+", "", match.group(1).strip())
    separators = [index for index, char in enumerate(candidate) if char in ".,"]  # noqa: C401
    decimal_separator: str | None = None
    decimal_index: int | None = None
    if separators:
        decimal_index = separators[-1]
        digits_after_separator = len(candidate) - decimal_index - 1
        if 0 < digits_after_separator <= 2:
            decimal_separator = candidate[decimal_index]
        elif len(separators) == 1 and digits_after_separator != 3:
            decimal_separator = candidate[decimal_index]

    normalized_chars: list[str] = []
    for index, char in enumerate(candidate):
        if char.isdigit():
            normalized_chars.append(char)
            continue
        if decimal_separator is not None and decimal_index == index and char == decimal_separator:
            normalized_chars.append(".")
    candidate = "".join(normalized_chars)
    if not candidate or candidate == ".":
        return None
    try:
        return float(Decimal(candidate))
    except InvalidOperation:
        return None


def parse_review_count(value: str) -> int:
    shortened = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*([km])\b", value.casefold())
    if shortened:
        amount = parse_float_from_text(shortened.group(1))
        if amount is None:
            return 0
        multiplier = 1_000 if shortened.group(2) == "k" else 1_000_000
        return int(amount * multiplier)
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else 0


def parse_helpful_count(value: str) -> int:
    normalized = " ".join(value.split())
    if not normalized:
        return 0
    if normalized.casefold().startswith("one "):
        return 1
    return parse_review_count(normalized)


def detect_currency(value: str) -> str | None:
    if "€" in value:
        return "EUR"
    if "zł" in value:
        return "PLN"
    if "kr" in value:
        return "SEK"
    if "£" in value:
        return "GBP"
    return None


def compose_search_query(
    base: str,
    *,
    brand: str | None = None,
    model: str | None = None,
) -> str:
    parts: list[str] = []
    normalized_query = ""
    for part in (base, brand, model):
        cleaned = part.strip() if part else ""
        if not cleaned:
            continue
        normalized_part = normalize_text(cleaned)
        if parts and normalized_part and f" {normalized_part} " in f" {normalized_query} ":
            continue
        parts.append(cleaned)
        normalized_query = normalize_text(" ".join(parts))
    return " ".join(parts)


def format_search_price(value: float | None) -> str:
    if value is None:
        return ""
    decimal_value = Decimal(str(value))
    normalized = format(decimal_value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def find_spec_value(specs: dict[str, str], *labels: str) -> str:
    normalized_specs = {normalize_text(key): value for key, value in specs.items()}
    for label in labels:
        value = normalized_specs.get(normalize_text(label))
        if value:
            return value
    return ""


def extract_asin(identifier: str) -> str | None:
    candidate = identifier.strip()
    if re.fullmatch(r"[A-Z0-9]{10}", candidate, flags=re.IGNORECASE):
        return candidate.upper()
    match = re.search(r"/dp/([A-Z0-9]{10})", candidate, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def extract_page_number(url: str | None, default: int = 1) -> int:
    if not url:
        return default
    match = re.search(r"[?&]page(?:number)?=(\d+)", url, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return default


@dataclass(slots=True)
class AmazonHttpClient:
    marketplace: Marketplace
    session: BrowserSession | None = None
    timeout: float = 20.0
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        headers = {
            "User-Agent": (
                self.session.user_agent
                if self.session is not None
                else (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
                )
            ),
            "Accept-Language": self.marketplace.language,
        }
        cookies = httpx.Cookies()
        if self.session is not None:
            for cookie in self.session.cookies:
                name = cookie.get("name")
                value = cookie.get("value")
                if not name or value is None:
                    continue
                cookies.set(
                    name,
                    value,
                    domain=cookie.get("domain"),
                    path=cookie.get("path", "/"),
                )
        self._client = httpx.Client(
            headers=headers,
            cookies=cookies,
            follow_redirects=True,
            timeout=self.timeout,
        )

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
        params = {
            "k": compose_search_query(base, brand=brand, model=model),
        }
        if min_price is not None or max_price is not None:
            params["rnid"] = "12419339031"
            params["low-price"] = format_search_price(min_price)
            params["high-price"] = format_search_price(max_price)
        if page is not None and page > 1:
            params["page"] = str(page)
        return f"https://{self.marketplace.domain}/s?{urlencode(params)}"

    def build_reviews_url(self, identifier: str, *, page: int = 1) -> str:
        asin = extract_asin(identifier)
        if not asin:
            raise ValueError(f"Could not determine ASIN from identifier: {identifier}")
        params = {"ie": "UTF8"}
        if page > 1:
            params["pageNumber"] = str(page)
        return f"https://{self.marketplace.domain}/-/en/product-reviews/{asin}/ref=cm_cr_dp_d_show_all_btm?{urlencode(params)}"

    def fetch_search_page(
        self,
        base: str,
        *,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        page: int | None = None,
    ) -> str:
        url = self.build_search_url(
            base,
            brand=brand,
            model=model,
            min_price=min_price,
            max_price=max_price,
            page=page,
        )
        return self.fetch_url(url)

    def fetch_product_page(self, identifier: str) -> str:
        asin = extract_asin(identifier)
        if asin:
            url = f"https://{self.marketplace.domain}/dp/{asin}"
        else:
            url = identifier
        return self.fetch_url(url)

    def fetch_reviews_page(self, identifier: str, *, page: int = 1, url: str | None = None) -> str:
        target_url = url or self.build_reviews_url(identifier, page=page)
        return self.fetch_url(target_url)

    def fetch_reviews_ajax_page(self, next_page_state: dict[str, object], *, referer: str) -> tuple[str, str]:
        reviews_ajax_url = str(next_page_state["reviews_ajax_url"])
        reftag = str(next_page_state.get("reftag") or "cm_cr_arp_d_paging_btm")
        endpoint = reviews_ajax_url.rstrip("/") + f"/ref={reftag}"
        target_url = f"https://{self.marketplace.domain}{endpoint}"
        payload = {
            "sortBy": str(next_page_state.get("sortBy", "")),
            "reviewerType": str(next_page_state.get("reviewerType", "")),
            "formatType": str(next_page_state.get("formatType", "")),
            "mediaType": str(next_page_state.get("mediaType", "")),
            "filterByStar": str(next_page_state.get("filterByStar", "")),
            "filterByAge": str(next_page_state.get("filterByAge", "")),
            "pageNumber": str(next_page_state["pageNumber"]),
            "filterByLanguage": str(next_page_state.get("filterByLanguage", "")),
            "filterByKeyword": str(next_page_state.get("filterByKeyword", "")),
            "nextPageToken": str(next_page_state["nextPageToken"]),
            "shouldAppend": str(next_page_state.get("shouldAppend", "true")),
            "deviceType": str(next_page_state.get("deviceType", "desktop")),
            "canShowIntHeader": str(next_page_state.get("canShowIntHeader", "true")),
            "reviewsShown": "undefined",
            "reftag": reftag,
            "pageSize": str(next_page_state.get("pageSize", "10")),
            "asin": str(next_page_state["asin"]),
            "scope": str(next_page_state.get("scope", "reviewsAjax0")),
        }
        response = self._client.post(
            target_url,
            data=payload,
            headers={
                "Accept": "text/html,*/*",
                "X-Requested-With": "XMLHttpRequest",
                "anti-csrftoken-a2z": str(next_page_state["reviews_csrf_token"]),
                "Referer": referer,
            },
        )
        return response.text, str(response.url)

    def fetch_url(self, url: str) -> str:
        response = self._client.get(url)
        return response.text

    def fetch_url_details(self, url: str) -> tuple[str, str]:
        response = self._client.get(url)
        return response.text, str(response.url)


class AmazonParser:
    def __init__(self, marketplace: Marketplace) -> None:
        self.marketplace = marketplace

    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    def _assert_not_blocked(self, soup: BeautifulSoup) -> None:
        if is_probably_blocked_html(str(soup)):
            raise AmazonBlockedError("Amazon returned a blocked or captcha page.")

    def _absolute_href(self, href: str) -> str:
        if href.startswith("/"):
            return f"https://{self.marketplace.domain}{href}"
        return href

    def _extract_search_title(self, node) -> str:
        selectors = (
            '[data-cy="title-recipe"] a h2',
            '[data-cy="title-recipe"] a',
            "a.a-link-normal h2",
            "h2 a",
        )
        candidates: list[str] = []
        for selector in selectors:
            for candidate in node.select(selector):
                text = candidate.get("aria-label", "") if candidate.has_attr("aria-label") else ""
                if not text:
                    text = candidate.get_text(" ", strip=True)
                normalized = strip_promotional_prefixes(" ".join(text.split()))
                if normalized:
                    candidates.append(normalized)
        if candidates:
            return max(candidates, key=len)

        fallback_titles = [
            strip_promotional_prefixes(" ".join(candidate.get_text(" ", strip=True).split()))
            for candidate in node.select("h2 span, h2")
            if candidate.get_text(" ", strip=True)
        ]
        return max(fallback_titles, key=len, default="")

    def _extract_search_link(self, node) -> str:
        for selector in ('[data-cy="title-recipe"] a[href]', "h2 a[href]", 'a[href*="/dp/"]'):
            for candidate in node.select(selector):
                href = (candidate.get("href") or "").strip()
                if not href:
                    continue
                return self._absolute_href(href)
        return ""

    def _extract_search_brand(self, node, title: str) -> str:
        for selector in (
            '[data-cy="title-recipe"] .a-color-secondary h2',
            '[data-cy="title-recipe"] h2.a-size-mini',
            "h2.a-size-mini",
        ):
            candidate = node.select_one(selector)
            if candidate is None:
                continue
            text = candidate.get_text(" ", strip=True)
            if text and not looks_like_non_brand_label(text):
                inferred = infer_brand(text)
                if inferred and not looks_like_non_brand_label(inferred):
                    return inferred
        return infer_brand(title)

    def _extract_search_review_text(self, node) -> str:
        best_text = ""
        best_count = 0
        for candidate in node.select(
            '.s-underline-text, a[href*="customerReviews"], a[href*="#customerReviews"], [aria-label*="ratings" i], [aria-label*="reviews" i]'
        ):
            text = " ".join(candidate.get_text(" ", strip=True).split())
            if not text or any(symbol in text for symbol in ("€", "$", "£")):
                continue
            count = parse_review_count(text)
            if count > best_count:
                best_text = text
                best_count = count
        return best_text

    def parse_search_results(self, html: str) -> list[ProductRecord]:
        return self.parse_search_page(html).records

    def parse_search_page(self, html: str, source_url: str | None = None) -> SearchPage:
        soup = self._soup(html)
        self._assert_not_blocked(soup)

        records: list[ProductRecord] = []
        seen_asins: set[str] = set()
        for node in soup.select(
            '[data-component-type="s-search-result"], [data-component-type="sp-sponsored-result"], .s-result-item[data-asin]'
        ):
            asin = (node.get("data-asin") or "").strip()
            if not asin or asin in seen_asins:
                continue
            seen_asins.add(asin)

            title = self._extract_search_title(node)
            if not title:
                continue
            href = self._extract_search_link(node)
            brand = self._extract_search_brand(node, title)

            price_text = ""
            price_node = node.select_one(".a-price .a-offscreen, .a-offscreen")
            if price_node:
                price_text = price_node.get_text(" ", strip=True)

            rating_text = ""
            rating_node = node.select_one(".a-icon-alt")
            if rating_node:
                rating_text = rating_node.get_text(" ", strip=True)

            reviews_text = self._extract_search_review_text(node)

            component_type = node.get("data-component-type", "")
            combined_text = " ".join(node.get_text(" ", strip=True).split()).casefold()
            is_sponsored = component_type.startswith("sp-") or any(
                token in combined_text for token in ("sponsored", "gesponsert", "patrocinado", "sponsorisé")
            )

            records.append(
                ProductRecord(
                    asin=asin,
                    url=href,
                    title=title,
                    brand=brand,
                    marketplace=self.marketplace.code,
                    price=parse_float_from_text(price_text),
                    currency=detect_currency(price_text) or self.marketplace.currency,
                    prime=node.select_one(".a-icon-prime") is not None or " prime " in f" {combined_text} ",
                    seller_summary="",
                    review_count=parse_review_count(reviews_text),
                    rating=parse_float_from_text(rating_text),
                    brand_store_present=False,
                    is_sponsored=is_sponsored,
                )
            )
        pagination = self._extract_pagination(soup)
        return SearchPage(
            records=records,
            current_page=pagination["current_page"],
            available_pages=pagination["available_pages"],
            next_page_url=pagination["next_page_url"],
            source_url=source_url,
        )

    def _extract_pagination(self, soup: BeautifulSoup) -> dict[str, object]:
        container = soup.select_one(".s-pagination-strip")
        current_page = 1
        available_pages: list[int] = []
        next_page_url: str | None = None
        if container is None:
            return {
                "current_page": current_page,
                "available_pages": available_pages,
                "next_page_url": next_page_url,
            }

        for node in container.select(".s-pagination-item"):
            text = node.get_text(" ", strip=True)
            if text.isdigit():
                number = int(text)
                if number not in available_pages:
                    available_pages.append(number)
                classes = node.get("class", [])
                if "s-pagination-selected" in classes:
                    current_page = number

        next_link = container.select_one("a.s-pagination-next[href], a[aria-label*='next' i][href]")
        if next_link is not None:
            href = (next_link.get("href") or "").strip()
            if href:
                next_page_url = self._absolute_href(href)

        available_pages.sort()
        return {
            "current_page": current_page,
            "available_pages": available_pages,
            "next_page_url": next_page_url,
        }

    def _extract_review_histogram(self, soup: BeautifulSoup) -> dict[str, int]:
        histogram: dict[str, int] = {}
        table = soup.select_one("#histogramTable")
        if table is None:
            return histogram
        for row in table.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td, th")]
            if len(cells) < 2:
                continue
            star_match = re.search(r"([1-5])", cells[0])
            percent_match = re.search(r"([0-9]+)\s*%", cells[-1])
            if not star_match or not percent_match:
                continue
            histogram[star_match.group(1)] = int(percent_match.group(1))
        return histogram

    def _extract_review_topics(self, soup: BeautifulSoup) -> list[dict[str, object]]:
        labels = soup.select('[data-testid="aspect-label"]')
        summaries = soup.select('[data-testid="aspect-summary"]')
        icons = soup.select('[data-testid^="aspect-icon-"]')
        topics: list[dict[str, object]] = []
        for index, label_node in enumerate(labels):
            raw_label = label_node.get_text(" ", strip=True)
            count_match = re.search(r"^(.*?)(?:\s*\(([\d.,Kk]+)\))?$", raw_label)
            if not count_match:
                continue
            topic = count_match.group(1).strip()
            mentions = parse_review_count(count_match.group(2) or "")
            sentiment = "unknown"
            if index < len(icons):
                sentiment = icons[index].get("data-testid", "").removeprefix("aspect-icon-") or "unknown"
            summary = summaries[index].get_text(" ", strip=True) if index < len(summaries) else ""
            topics.append(
                {
                    "topic": topic,
                    "mentions": mentions,
                    "sentiment": sentiment,
                    "summary": summary,
                }
            )
        return topics

    def _extract_detail_review_text(self, card) -> str:
        for selector in (
            '[data-hook="review-body"] .cr-original-review-content',
            '[data-hook="review-body"] [data-hook="review-collapsed"]',
            '[data-hook="review-body"]',
        ):
            node = card.select_one(selector)
            if node is None:
                continue
            text = " ".join(node.get_text(" ", strip=True).split())
            text = re.sub(r"\bRead more\b$", "", text, flags=re.IGNORECASE).strip()
            if text:
                return text
        return ""

    def _extract_top_reviews(self, soup: BeautifulSoup, *, limit: int | None = 5) -> list[dict[str, object]]:
        reviews: list[dict[str, object]] = []
        seen_review_ids: set[str] = set()
        cards = soup.select('div[id^="customer_review-"], [data-hook="review"]')
        for card in cards:
            review_id = (card.get("id") or card.get("data-review-id") or "").removeprefix("customer_review-")
            if review_id and review_id in seen_review_ids:
                continue
            if review_id:
                seen_review_ids.add(review_id)
            author_node = card.select_one(".a-profile-name")
            title_node = card.select_one('[data-hook="review-title"] .cr-original-review-content, [data-hook="review-title"]')
            rating_node = card.select_one('[data-hook="review-star-rating"] .a-icon-alt, [data-hook="cmps-review-star-rating"] .a-icon-alt')
            date_node = card.select_one('[data-hook="review-date"]')
            format_node = card.select_one('[data-hook="format-strip-linkless"], [data-hook="format-strip"]')
            helpful_node = card.select_one('[data-hook="helpful-vote-statement"]')

            title_text = ""
            if title_node is not None:
                title_text = " ".join(title_node.get_text(" ", strip=True).split())
                rating_prefix = rating_node.get_text(" ", strip=True) if rating_node is not None else ""
                if rating_prefix and title_text.startswith(rating_prefix):
                    title_text = title_text[len(rating_prefix):].strip()

            reviews.append(
                {
                    "review_id": review_id,
                    "author": author_node.get_text(" ", strip=True) if author_node is not None else "",
                    "rating": parse_float_from_text(rating_node.get_text(" ", strip=True)) if rating_node is not None else None,
                    "title": title_text,
                    "date": date_node.get_text(" ", strip=True) if date_node is not None else "",
                    "format": format_node.get_text(" ", strip=True) if format_node is not None else "",
                    "verified_purchase": card.select_one('[data-hook="avp-badge"]') is not None,
                    "body": self._extract_detail_review_text(card),
                    "helpful_count": parse_helpful_count(helpful_node.get_text(" ", strip=True)) if helpful_node is not None else 0,
                }
            )
            if limit is not None and len(reviews) >= limit:
                break
        return reviews

    def _extract_review_insights(self, soup: BeautifulSoup) -> dict[str, object]:
        summary_node = soup.select_one('[data-testid="overall-summary"]')
        return {
            "summary": summary_node.get_text(" ", strip=True) if summary_node is not None else "",
            "histogram": self._extract_review_histogram(soup),
            "topics": self._extract_review_topics(soup),
        }

    def _extract_review_pagination(self, soup: BeautifulSoup, source_url: str | None = None) -> dict[str, object]:
        container = soup.select_one(".a-pagination")
        current_page = extract_page_number(source_url, default=1)
        available_pages: list[int] = []
        next_page_url: str | None = None
        if container is None:
            return {
                "current_page": current_page,
                "available_pages": available_pages,
                "next_page_url": next_page_url,
            }

        for node in container.select("li"):
            text = node.get_text(" ", strip=True)
            if text.isdigit():
                number = int(text)
                if number not in available_pages:
                    available_pages.append(number)
                classes = node.get("class", [])
                if "a-selected" in classes:
                    current_page = number

        next_link = container.select_one("li.a-last a[href], a[href][aria-label*='next' i]")
        if next_link is not None:
            href = (next_link.get("href") or "").strip()
            if href:
                next_page_url = self._absolute_href(href)

        available_pages.sort()
        return {
            "current_page": current_page,
            "available_pages": available_pages,
            "next_page_url": next_page_url,
        }

    def _extract_available_review_count(self, soup: BeautifulSoup) -> int:
        node = soup.select_one('[data-hook="cr-filter-info-review-rating-count"]')
        if node is None:
            return 0
        return parse_review_count(node.get_text(" ", strip=True))

    def _extract_review_show_more_state(self, soup: BeautifulSoup) -> dict[str, object]:
        button = soup.select_one('[data-hook="show-more-button"][data-reviews-state-param]')
        if button is None:
            return {}

        try:
            button_state = json.loads(button.get("data-reviews-state-param") or "{}")
        except json.JSONDecodeError:
            return {}

        next_page_state: dict[str, object] = dict(button_state)
        reftag = button.get("data-reftag")
        if reftag:
            next_page_state["reftag"] = reftag

        state_node = soup.select_one("#cr-state-object[data-state]")
        if state_node is not None:
            try:
                state = json.loads(state_node.get("data-state") or "{}")
            except json.JSONDecodeError:
                state = {}
            next_page_state.update(
                {
                    "reviews_ajax_url": state.get("reviewsAjaxUrl", ""),
                    "reviews_csrf_token": state.get("reviewsCsrfToken", ""),
                    "asin": state.get("asin", ""),
                    "reviewerType": state.get("reviewerType", ""),
                    "filterByStar": state.get("filterByStar", ""),
                    "filterByAge": state.get("filterByAge", ""),
                    "filterByLanguage": state.get("filterByLanguage", ""),
                    "filterByKeyword": state.get("filterByKeyword", ""),
                    "formatType": state.get("formatType", ""),
                    "sortBy": state.get("sortBy", ""),
                    "scope": "reviewsAjax0",
                    "pageSize": "10",
                }
            )

        return {key: value for key, value in next_page_state.items() if value is not None}

    def _ajax_review_soup(self, html: str) -> BeautifulSoup | None:
        if "&&&" not in html or not html.lstrip().startswith("["):
            return None

        fragments: list[str] = []
        for raw_chunk in html.split("&&&"):
            chunk = raw_chunk.strip()
            if not chunk:
                continue
            try:
                payload = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if len(payload) >= 3 and payload[0] in {"append", "update"} and isinstance(payload[2], str):
                fragments.append(payload[2])

        if not fragments:
            return None
        return self._soup("\n".join(fragments))

    def parse_review_page(
        self,
        html: str,
        source_url: str | None = None,
        final_url: str | None = None,
    ) -> ReviewPage:
        soup = self._ajax_review_soup(html) or self._soup(html)
        self._assert_not_blocked(soup)
        if is_probably_sign_in_html(str(soup)):
            return ReviewPage(
                reviews=[],
                current_page=extract_page_number(source_url, default=1),
                source_url=source_url,
                final_url=final_url or source_url,
                sign_in_required=True,
            )
        pagination = self._extract_review_pagination(soup, source_url=source_url)
        return ReviewPage(
            reviews=self._extract_top_reviews(soup, limit=None),
            current_page=pagination["current_page"],
            available_pages=pagination["available_pages"],
            next_page_url=pagination["next_page_url"],
            next_page_state=self._extract_review_show_more_state(soup),
            available_review_count=self._extract_available_review_count(soup),
            source_url=source_url,
            final_url=final_url or source_url,
            sign_in_required=False,
        )

    def parse_product_detail(self, html: str, source_url: str, asin: str | None = None) -> ProductRecord:
        soup = self._soup(html)
        self._assert_not_blocked(soup)

        title_node = soup.select_one("#productTitle")
        if title_node is not None:
            title = title_node.get_text(" ", strip=True)
        else:
            hidden_title = soup.select_one('input#productTitle[value]')
            title = (hidden_title.get("value") or "").strip() if hidden_title is not None else ""
        brand_link = soup.select_one("#bylineInfo")
        brand_text = brand_link.get_text(" ", strip=True) if brand_link else ""

        price_node = soup.select_one("#corePrice_feature_div .a-offscreen, .a-price .a-offscreen")
        if price_node is not None:
            price_text = price_node.get_text(" ", strip=True)
        else:
            hidden_price = soup.select_one('input#priceValue[value]')
            currency_symbol = soup.select_one('input#priceSymbol[value]')
            price_text = ""
            if hidden_price is not None:
                price_text = f"{currency_symbol.get('value', '')}{hidden_price.get('value', '')}"

        seller_node = soup.select_one("#merchantInfoFeature_feature_div, #sellerProfileTriggerId")
        seller_text = seller_node.get_text(" ", strip=True) if seller_node else ""

        review_node = soup.select_one("#acrCustomerReviewText")
        review_text = review_node.get_text(" ", strip=True) if review_node else ""

        rating_node = soup.select_one("#averageCustomerReviews .a-icon-alt, #acrPopover .a-icon-alt")
        rating_text = rating_node.get_text(" ", strip=True) if rating_node else ""

        specs: dict[str, str] = {}
        for row in soup.select("table tr"):
            header = row.select_one("th")
            value = row.select_one("td")
            if header and value:
                specs[header.get_text(" ", strip=True)] = value.get_text(" ", strip=True)

        if not brand_text:
            brand_text = find_spec_value(specs, "Brand Name", "Brand", "Marke", "Marque")
        brand = infer_brand(
            brand_text.replace("Besuche den", "").replace("Visit the", "").replace("Store", "").strip()
        ) or infer_brand(title)

        brand_store_present = any(
            token in normalize_text(anchor.get_text(" ", strip=True))
            for anchor in soup.select('#bylineInfo, a[href*="stores"], a[href*="/stores/"]')
            for token in ("store", "boutique", "tienda")
        )
        if not brand_store_present:
            body_text = normalize_text(soup.get_text(" ", strip=True))
            brand_store_present = any(
                token in body_text for token in ("visit the store", "besuche den store", "visita la tienda", "visiter la boutique")
            )

        resolved_asin = asin or extract_asin(source_url) or ""
        return ProductRecord(
            asin=resolved_asin,
            url=source_url,
            title=title,
            brand=brand,
            marketplace=self.marketplace.code,
            price=parse_float_from_text(price_text),
            currency=detect_currency(price_text) or self.marketplace.currency,
            prime="prime" in normalize_text(soup.get_text(" ", strip=True)),
            seller_summary=seller_text,
            review_count=parse_review_count(review_text),
            rating=parse_float_from_text(rating_text),
            brand_store_present=brand_store_present,
            is_sponsored=False,
            specs=specs,
            specs_normalized=normalize_specs(specs),
            review_insights=self._extract_review_insights(soup),
            top_reviews=self._extract_top_reviews(soup),
        )


class AmazonScraper:
    def __init__(self, marketplace_code: str, session: BrowserSession | None = None) -> None:
        self.marketplace = get_marketplace(marketplace_code)
        self.client = AmazonHttpClient(self.marketplace, session=session)
        self.parser = AmazonParser(self.marketplace)

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
        return self.client.build_search_url(
            base,
            brand=brand,
            model=model,
            min_price=min_price,
            max_price=max_price,
            page=page,
        )

    def build_reviews_url(self, identifier: str, *, page: int = 1) -> str:
        return self.client.build_reviews_url(identifier, page=page)

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
        source_url = url or self.build_search_url(
            base,
            brand=brand,
            model=model,
            min_price=min_price,
            max_price=max_price,
            page=page,
        )
        html = self.client.fetch_url(source_url)
        return self.parser.parse_search_page(html, source_url=source_url)

    def search(
        self,
        base: str,
        *,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> list[ProductRecord]:
        return self.search_page(
            base,
            brand=brand,
            model=model,
            min_price=min_price,
            max_price=max_price,
        ).records

    def get(self, identifier: str) -> ProductRecord:
        asin = extract_asin(identifier)
        html = self.client.fetch_product_page(identifier)
        source_url = identifier
        if asin and not identifier.startswith(("http://", "https://")):
            source_url = f"https://{self.marketplace.domain}/dp/{asin}"
        return self.parser.parse_product_detail(html, source_url=source_url, asin=asin)

    def review_page(self, identifier: str, *, page: int = 1, url: str | None = None) -> ReviewPage:
        source_url = url or self.build_reviews_url(identifier, page=page)
        html, final_url = self.client.fetch_url_details(source_url)
        return self.parser.parse_review_page(html, source_url=source_url, final_url=final_url)

    def review_ajax_page(self, next_page_state: dict[str, object], *, source_url: str | None = None) -> ReviewPage:
        referer = source_url or self.build_reviews_url(str(next_page_state["asin"]))
        html, final_url = self.client.fetch_reviews_ajax_page(next_page_state, referer=referer)
        return self.parser.parse_review_page(html, source_url=final_url, final_url=final_url)


def marketplace_from_identifier(identifier: str, fallback: str, *, strict_url: bool = False) -> str:
    if identifier.startswith("http://") or identifier.startswith("https://"):
        host = urlparse(identifier).netloc.casefold()
        if "amazon." not in host:
            if strict_url:
                raise ValueError(f"Unsupported product URL domain: {host}")
            return fallback
        for code, marketplace in {
            code: get_marketplace(code) for code in ("de", "es", "fr", "it", "nl", "pl", "se", "be", "ie", "uk")
        }.items():
            if marketplace.domain.casefold() == host:
                return code
        if strict_url:
            raise ValueError(f"Unsupported Amazon marketplace domain: {host}")
    return fallback


def inspect_identifier(identifier: str, marketplace: str) -> dict[str, object]:
    requested_marketplace = get_marketplace(marketplace)
    parsed = urlparse(identifier.strip())
    is_url = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    host = parsed.netloc.casefold() if is_url else ""
    asin = extract_asin(identifier)
    detected_marketplace: str | None = None
    warnings: list[str] = []

    if is_url and "amazon." in host:
        for code in ("de", "es", "fr", "it", "nl", "pl", "se", "be", "ie", "uk"):
            candidate = get_marketplace(code)
            if candidate.domain.casefold() == host:
                detected_marketplace = code
                break
        if detected_marketplace is None:
            warnings.append(f"Unsupported Amazon marketplace domain: {host}")
    elif is_url:
        asin = None
        warnings.append(f"Unsupported product URL domain: {host}")

    resolved_marketplace = get_marketplace(detected_marketplace or requested_marketplace.code)
    identifier_type = "amazon_url" if is_url and "amazon." in host else "url" if is_url else "asin" if asin else "text"
    if not asin and not warnings:
        warnings.append("Could not determine ASIN from identifier.")

    supported = bool(asin and not warnings)
    normalized_url = f"https://{resolved_marketplace.domain}/dp/{asin}" if supported else None
    return {
        "command": "inspect-identifier",
        "input": identifier,
        "identifier_type": identifier_type,
        "asin": asin,
        "requested_marketplace": requested_marketplace.code,
        "detected_marketplace": detected_marketplace,
        "marketplace": resolved_marketplace.code,
        "marketplace_domain": resolved_marketplace.domain,
        "normalized_url": normalized_url,
        "supported": supported,
        "warnings": warnings,
    }
