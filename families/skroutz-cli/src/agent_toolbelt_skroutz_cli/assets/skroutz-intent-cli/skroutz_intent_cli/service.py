from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from .fetch import SkroutzFetcher
from .identifiers import inspect_identifier, require_product_identifier
from .parsing import parse_product, parse_reviews, parse_search
from .session import BrowserSessionBootstrapper


class SkroutzService:
    def __init__(self, *, fetcher: Any | None = None, session: Any | None = None):
        self.fetcher = fetcher or SkroutzFetcher()
        self.session = session or BrowserSessionBootstrapper()

    def inspect_identifier(self, identifier: str) -> dict[str, Any]:
        return inspect_identifier(identifier)

    def search(self, *, query: str, pages: int = 1) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        warnings: list[str] = []
        fetched_pages: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            url = f"https://www.skroutz.cy/search?keyphrase={quote_plus(query)}"
            if page > 1:
                url = f"{url}&page={page}"
            html = self.fetcher.fetch_html(url)
            parsed = parse_search(html, query=query, page=page)
            results.extend(parsed["results"])
            fetched_pages.append({"page": page, "result_count": parsed["result_count"], "url": url})
        return {
            "command": "search",
            "query": query,
            "pages": pages,
            "results": results,
            "result_count": len(results),
            "pagination": {"requested_pages": pages, "fetched_pages": fetched_pages, "partial": False},
            "warnings": warnings,
            "safety": {"single_threaded": True, "background_crawling": False},
        }

    def get(self, identifier: str) -> dict[str, Any]:
        product_id, url = require_product_identifier(identifier)
        html = self.fetcher.fetch_html(url)
        payload = parse_product(html, product_id=product_id, url=url)
        payload["safety"] = {"read_only": True}
        return payload

    def offers(self, identifier: str) -> dict[str, Any]:
        product = self.get(identifier)
        return {
            "command": "offers",
            "product_id": product["product_id"],
            "url": product["url"],
            "title": product["title"],
            "offers": product.get("offers", []),
            "offer_count": len(product.get("offers", [])),
            "price_summary": product.get("price_summary", {}),
            "warnings": product.get("warnings", []),
            "safety": {"read_only": True},
        }

    def reviews(self, identifier: str, *, limit: int | None = None) -> dict[str, Any]:
        product_id, url = require_product_identifier(identifier)
        html = self.fetcher.fetch_html(url)
        return {
            "command": "reviews",
            "product_id": product_id,
            "url": url,
            "reviews": parse_reviews(html, limit=limit),
            "limit": limit,
            "warnings": [],
            "safety": {"read_only": True},
        }

    def compare(self, identifiers: list[str]) -> dict[str, Any]:
        products = [self.get(identifier) for identifier in identifiers]
        products.sort(key=lambda product: product.get("price_summary", {}).get("min_price") or 999999999)
        return {
            "command": "compare",
            "products": products,
            "product_count": len(products),
            "warnings": [],
            "safety": {"read_only": True},
        }

    def login(self, *, login_timeout_sec: int = 300, manual_confirm: bool = False) -> dict[str, Any]:
        return self.session.login(login_timeout_sec=login_timeout_sec, manual_confirm=manual_confirm)

    def cart_list(self) -> dict[str, Any]:
        return self.session.list_cart()

    def cart_add(self, identifier: str, *, quantity: int) -> dict[str, Any]:
        product_id, _url = require_product_identifier(identifier)
        return self.session.add_to_cart(product_id, quantity=quantity)

    def cart_remove(self, identifier: str, *, quantity: int) -> dict[str, Any]:
        product_id, _url = require_product_identifier(identifier)
        return self.session.remove_from_cart(product_id, quantity=quantity)
