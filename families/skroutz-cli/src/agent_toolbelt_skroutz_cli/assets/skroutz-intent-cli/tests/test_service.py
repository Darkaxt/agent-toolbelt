import unittest

from skroutz_intent_cli.service import SkroutzService
from skroutz_intent_cli.session import BrowserSessionError


class FakeFetcher:
    def __init__(self):
        self.calls = []

    def fetch_html(self, url, *, timeout_sec=30):
        self.calls.append(url)
        if "search" in url:
            return '<a href="/s/62956505/apple.html">Apple iPhone</a><span>από 999,00 €</span>'
        return '<h1>Apple iPhone</h1><script type="application/ld+json">{"@type":"Product","name":"Apple iPhone","offers":{"price":"999.00","priceCurrency":"EUR"}}</script>'


class FakeSession:
    def __init__(self, available=True):
        self.available = available
        self.actions = []

    def require_session(self):
        if not self.available:
            raise BrowserSessionError("Run `skroutz-cli session login` first.")

    def login(self, **kwargs):
        return {"command": "session.login", "status": "ready", "session_key": "cy"}

    def list_cart(self):
        self.require_session()
        return {"command": "cart.list", "status": "ok", "items": [], "item_count": 0}

    def add_to_cart(self, product_id, *, quantity):
        self.require_session()
        self.actions.append(("add", product_id, quantity))
        return {"command": "cart.add", "status": "ok", "product_id": product_id, "quantity": quantity}

    def remove_from_cart(self, product_id, *, quantity):
        self.require_session()
        self.actions.append(("remove", product_id, quantity))
        return {"command": "cart.remove", "status": "ok", "product_id": product_id, "quantity": quantity}


class ServiceTests(unittest.TestCase):
    def test_search_is_bounded_and_single_threaded(self):
        fetcher = FakeFetcher()
        service = SkroutzService(fetcher=fetcher, session=FakeSession())

        payload = service.search(query="iphone", pages=2)

        self.assertEqual(payload["command"], "search")
        self.assertEqual(len(fetcher.calls), 2)
        self.assertIn("single_threaded", payload["safety"])

    def test_get_and_offers_return_structured_payloads(self):
        service = SkroutzService(fetcher=FakeFetcher(), session=FakeSession())

        detail = service.get("62956505")
        offers = service.offers("62956505")

        self.assertEqual(detail["command"], "get")
        self.assertEqual(detail["product_id"], "62956505")
        self.assertEqual(offers["command"], "offers")
        self.assertIn("offers", offers)

    def test_compare_uses_product_details(self):
        service = SkroutzService(fetcher=FakeFetcher(), session=FakeSession())

        payload = service.compare(["62956505", "62956506"])

        self.assertEqual(payload["command"], "compare")
        self.assertEqual(len(payload["products"]), 2)

    def test_cart_list_requires_managed_session_but_no_confirmation(self):
        service = SkroutzService(fetcher=FakeFetcher(), session=FakeSession(available=False))

        with self.assertRaises(BrowserSessionError):
            service.cart_list()

    def test_cart_add_remove_delegate_to_session_with_confirmed_actions(self):
        session = FakeSession()
        service = SkroutzService(fetcher=FakeFetcher(), session=session)

        add = service.cart_add("62956505", quantity=2)
        remove = service.cart_remove("62956505", quantity=1)

        self.assertEqual(add["command"], "cart.add")
        self.assertEqual(remove["command"], "cart.remove")
        self.assertEqual(session.actions, [("add", "62956505", 2), ("remove", "62956505", 1)])


if __name__ == "__main__":
    unittest.main()
