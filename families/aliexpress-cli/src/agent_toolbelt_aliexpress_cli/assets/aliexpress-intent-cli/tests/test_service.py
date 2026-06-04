import unittest
from pathlib import Path

from aliexpress_intent_cli.fetch import FetchResult
from aliexpress_intent_cli.service import AliExpressService
from aliexpress_intent_cli.session import BrowserSessionError


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FakeFetcher:
    def __init__(self, html_name: str = "search_results.html"):
        self.html_name = html_name
        self.urls: list[str] = []

    def fetch(self, url: str, *, timeout_sec: int = 30):
        self.urls.append(url)
        return FetchResult(
            url=url,
            html=(FIXTURES / self.html_name).read_text(encoding="utf-8"),
            status=200,
            fetcher="fake_http",
            warnings=[],
        )


class FakeSession:
    def __init__(self, html_name: str = "search_results.html", exists: bool = True):
        self.html_name = html_name
        self.exists = exists
        self.urls: list[str] = []

    def fetch(self, url: str, *, timeout_sec: int = 30):
        if not self.exists:
            raise BrowserSessionError("missing session")
        self.urls.append(url)
        return FetchResult(
            url=url,
            html=(FIXTURES / self.html_name).read_text(encoding="utf-8"),
            status=200,
            fetcher="managed_session",
            warnings=[],
        )

    def login(self, **kwargs):
        return {"command": "session.login", "status": "ready"}

    def status(self):
        return {"command": "session.status", "status": "ready"}

    def logout(self):
        return {"command": "session.logout", "removed": True}


class AliExpressServiceTests(unittest.TestCase):
    def test_search_uses_http_fetcher_by_default(self):
        fetcher = FakeFetcher()
        session = FakeSession()
        service = AliExpressService(fetcher=fetcher, session=session)

        payload = service.search(query="30L trash bin", pages=1)

        self.assertEqual(payload["command"], "search")
        self.assertEqual(payload["result_count"], 2)
        self.assertEqual(len(fetcher.urls), 1)
        self.assertEqual(session.urls, [])
        self.assertFalse(payload["session_used"])
        self.assertIn("SearchText=30L+trash+bin", fetcher.urls[0])

    def test_search_can_use_managed_session_explicitly(self):
        fetcher = FakeFetcher()
        session = FakeSession()
        service = AliExpressService(fetcher=fetcher, session=session)

        payload = service.search(query="30L trash bin", pages=1, use_session=True)

        self.assertEqual(len(session.urls), 1)
        self.assertEqual(fetcher.urls, [])
        self.assertTrue(payload["session_used"])
        self.assertEqual(payload["pagination"]["fetched_pages"][0]["fetcher"], "managed_session")

    def test_get_extracts_detail_fields(self):
        service = AliExpressService(fetcher=FakeFetcher("item_detail.html"), session=FakeSession())

        payload = service.get("1005001111111111", ship_to="CY", currency="EUR")

        self.assertEqual(payload["command"], "get")
        self.assertEqual(payload["item_id"], "1005001111111111")
        self.assertTrue(payload["price_summary"]["free_delivery"])
        self.assertEqual(payload["source_diagnostics"]["fetcher"], "fake_http")

    def test_reviews_extract_comments(self):
        service = AliExpressService(fetcher=FakeFetcher("reviews.html"), session=FakeSession())

        payload = service.reviews("1005001111111111", limit=2)

        self.assertEqual(payload["command"], "reviews")
        self.assertEqual(len(payload["reviews"]), 2)

    def test_compare_sorts_by_price(self):
        service = AliExpressService(fetcher=FakeFetcher("item_detail.html"), session=FakeSession())

        payload = service.compare(["1005001111111111", "1005002222222222"])

        self.assertEqual(payload["product_count"], 2)
        self.assertEqual(payload["products"][0]["price_summary"]["min_price"], 24.99)

    def test_use_session_requires_managed_session(self):
        service = AliExpressService(fetcher=FakeFetcher(), session=FakeSession(exists=False))

        with self.assertRaises(BrowserSessionError):
            service.search(query="30L trash bin", use_session=True)


if __name__ == "__main__":
    unittest.main()
