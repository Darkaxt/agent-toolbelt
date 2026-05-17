import tempfile
import unittest
from pathlib import Path

from skroutz_intent_cli.session import BrowserSessionBootstrapper, BrowserSessionError, BrowserSessionStore


class FakeLocator:
    def __init__(self, name, clicks):
        self.name = name
        self.clicks = clicks

    def first(self):
        return self

    def click(self, timeout=0):
        self.clicks.append(self.name)


class FakePage:
    def __init__(self):
        self.urls = []
        self.clicks = []

    def goto(self, url, wait_until=None, timeout=0):
        self.urls.append(url)

    def locator(self, selector):
        return FakeLocator(selector, self.clicks)

    def content(self):
        return '<div class="cart-item" data-sku-id="62956505"><a href="/s/62956505/item.html">Item</a></div>'


class FakeContext:
    def __init__(self, page):
        self.page = page

    def new_page(self):
        return self.page

    def close(self):
        pass


class FakeBrowserFactory:
    def __init__(self, page):
        self.page = page

    def open_context(self, user_data_dir):
        return FakeContext(self.page)


class SessionTests(unittest.TestCase):
    def test_store_tracks_profile_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = BrowserSessionStore(root=Path(temp_dir))

            profile = store.profile_dir()

            self.assertEqual(profile, Path(temp_dir) / "browser-profile")
            self.assertFalse((profile / "Cookies").exists())

    def test_require_session_fails_when_profile_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = BrowserSessionStore(root=Path(temp_dir))
            bootstrapper = BrowserSessionBootstrapper(store=store)

            with self.assertRaises(BrowserSessionError):
                bootstrapper.require_session()

    def test_cart_add_clicks_only_allowed_cart_controls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            page = FakePage()
            store = BrowserSessionStore(root=Path(temp_dir))
            store.profile_dir().mkdir(parents=True)
            bootstrapper = BrowserSessionBootstrapper(store=store, browser_factory=FakeBrowserFactory(page))

            payload = bootstrapper.add_to_cart("62956505", quantity=1)

            self.assertEqual(payload["command"], "cart.add")
            self.assertTrue(any("cart" in click or "add" in click for click in page.clicks))
            self.assertFalse(any("checkout" in click.lower() or "buy" in click.lower() or "payment" in click.lower() for click in page.clicks))

    def test_cart_list_reads_without_mutation_clicks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            page = FakePage()
            store = BrowserSessionStore(root=Path(temp_dir))
            store.profile_dir().mkdir(parents=True)
            bootstrapper = BrowserSessionBootstrapper(store=store, browser_factory=FakeBrowserFactory(page))

            payload = bootstrapper.list_cart()

            self.assertEqual(payload["command"], "cart.list")
            self.assertEqual(payload["item_count"], 1)
            self.assertEqual(page.clicks, [])


if __name__ == "__main__":
    unittest.main()
