from __future__ import annotations

from typing import Any

from .fetch import AliExpressFetcher, FetchResult, is_probably_blocked_html
from .identifiers import inspect_identifier, require_item_identifier, validate_browse_url
from .parsing import parse_product, parse_reviews, parse_search, search_url
from .session import BrowserSessionBootstrapper


class AliExpressService:
    def __init__(self, *, fetcher: Any | None = None, session: Any | None = None):
        self.fetcher = fetcher or AliExpressFetcher()
        self.session = session or BrowserSessionBootstrapper()

    def inspect_identifier(self, identifier: str) -> dict[str, Any]:
        return inspect_identifier(identifier)

    def _fetch(self, url: str, *, use_session: bool = False) -> FetchResult:
        if use_session:
            return self.session.fetch(url)
        return self.fetcher.fetch(url)

    def _page_blocked(self, fetched: FetchResult) -> bool:
        return is_probably_blocked_html(fetched.html, status=fetched.status) or any(
            "blocked" in warning.lower() or "challenged" in warning.lower() or "login-gated" in warning.lower()
            for warning in fetched.warnings
        )

    def _extend_fetch_warnings(self, warnings: list[str], fetched: FetchResult, *, blocked: bool) -> None:
        warnings.extend(fetched.warnings)
        blocked_warning = "AliExpress response appears blocked, challenged, or login-gated."
        if blocked and blocked_warning not in warnings:
            warnings.append(blocked_warning)

    def search(
        self,
        *,
        query: str,
        pages: int = 1,
        sort: str = "relevance",
        min_price: float | None = None,
        max_price: float | None = None,
        ship_to: str = "CY",
        currency: str = "EUR",
        locale: str = "en_US",
        use_session: bool = False,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        warnings: list[str] = []
        fetched_pages: list[dict[str, Any]] = []
        blocked = False
        no_results = False
        for page in range(1, pages + 1):
            url = search_url(query, page=page, ship_to=ship_to, currency=currency, locale=locale, sort=sort, min_price=min_price, max_price=max_price)
            fetched = self._fetch(url, use_session=use_session)
            page_blocked = self._page_blocked(fetched)
            blocked = blocked or page_blocked
            self._extend_fetch_warnings(warnings, fetched, blocked=page_blocked)
            parsed = parse_search(fetched.html, query=query, page=page, url=fetched.url)
            no_results = no_results or bool(parsed.get("no_results"))
            results.extend(parsed["results"])
            fetched_pages.append(
                {
                    "page": page,
                    "url": url,
                    "result_count": parsed["result_count"],
                    "fetcher": fetched.fetcher,
                    "status": fetched.status,
                    "blocked": page_blocked,
                    "no_results": bool(parsed.get("no_results")),
                }
            )
        return {
            "command": "search",
            "query": query,
            "pages": pages,
            "filters": {"sort": sort, "min_price": min_price, "max_price": max_price, "ship_to": ship_to, "currency": currency, "locale": locale},
            "results": results,
            "result_count": len(results),
            "pagination": {"requested_pages": pages, "fetched_pages": fetched_pages, "partial": False},
            "blocked": blocked,
            "no_results": not blocked and not results and no_results,
            "warnings": warnings,
            "session_used": use_session,
            "safety": {"single_threaded": True, "background_crawling": False, "cart_operations_supported": False},
        }

    def browse(self, *, url: str, pages: int = 1, use_session: bool = False) -> dict[str, Any]:
        url = validate_browse_url(url)
        results: list[dict[str, Any]] = []
        warnings: list[str] = []
        fetched_pages: list[dict[str, Any]] = []
        blocked = False
        no_results = False
        for page in range(1, pages + 1):
            page_url = url if page == 1 else f"{url}{'&' if '?' in url else '?'}page={page}"
            fetched = self._fetch(page_url, use_session=use_session)
            page_blocked = self._page_blocked(fetched)
            blocked = blocked or page_blocked
            self._extend_fetch_warnings(warnings, fetched, blocked=page_blocked)
            parsed = parse_search(fetched.html, query=url, page=page, url=fetched.url)
            no_results = no_results or bool(parsed.get("no_results"))
            results.extend(parsed["results"])
            fetched_pages.append(
                {
                    "page": page,
                    "url": page_url,
                    "result_count": parsed["result_count"],
                    "fetcher": fetched.fetcher,
                    "status": fetched.status,
                    "blocked": page_blocked,
                    "no_results": bool(parsed.get("no_results")),
                }
            )
        return {
            "command": "browse",
            "url": url,
            "pages": pages,
            "results": results,
            "result_count": len(results),
            "pagination": {"requested_pages": pages, "fetched_pages": fetched_pages, "partial": False},
            "blocked": blocked,
            "no_results": not blocked and not results and no_results,
            "warnings": warnings,
            "session_used": use_session,
            "safety": {"single_threaded": True, "background_crawling": False, "cart_operations_supported": False},
        }

    def get(
        self,
        identifier: str,
        *,
        ship_to: str = "CY",
        currency: str = "EUR",
        locale: str = "en_US",
        use_session: bool = False,
    ) -> dict[str, Any]:
        item_id, url = require_item_identifier(identifier)
        detail_url = f"{url}?shipTo={ship_to}&currency={currency}&locale={locale}"
        fetched = self._fetch(detail_url, use_session=use_session)
        payload = parse_product(fetched.html, item_id=item_id, url=url)
        payload["request"] = {"ship_to": ship_to, "currency": currency, "locale": locale}
        payload["source_diagnostics"].update({"fetcher": fetched.fetcher, "status": fetched.status})
        payload["warnings"].extend(fetched.warnings)
        payload["session_used"] = use_session
        payload["safety"] = {"read_only": True, "cart_operations_supported": False}
        return payload

    def reviews(self, identifier: str, *, limit: int | None = None, use_session: bool = False) -> dict[str, Any]:
        item_id, url = require_item_identifier(identifier)
        fetched = self._fetch(url, use_session=use_session)
        return {
            "command": "reviews",
            "item_id": item_id,
            "url": url,
            "reviews": parse_reviews(fetched.html, limit=limit),
            "limit": limit,
            "warnings": fetched.warnings,
            "source_diagnostics": {"fetcher": fetched.fetcher, "status": fetched.status},
            "session_used": use_session,
            "safety": {"read_only": True, "cart_operations_supported": False},
        }

    def compare(self, identifiers: list[str]) -> dict[str, Any]:
        products = [self.get(identifier) for identifier in identifiers]
        products.sort(key=lambda product: product.get("price_summary", {}).get("min_price") or 999999999)
        return {
            "command": "compare",
            "products": products,
            "product_count": len(products),
            "warnings": [],
            "safety": {"read_only": True, "cart_operations_supported": False},
        }

    def login(self, *, login_timeout_sec: int = 300, manual_confirm: bool = False) -> dict[str, Any]:
        return self.session.login(login_timeout_sec=login_timeout_sec, manual_confirm=manual_confirm)

    def session_status(self) -> dict[str, Any]:
        return self.session.status()

    def session_logout(self) -> dict[str, Any]:
        return self.session.logout()
