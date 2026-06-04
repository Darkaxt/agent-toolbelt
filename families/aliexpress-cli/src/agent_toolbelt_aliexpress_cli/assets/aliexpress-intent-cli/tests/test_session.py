import tempfile
import unittest
from pathlib import Path

from aliexpress_intent_cli.session import BrowserSessionBootstrapper, BrowserSessionStore


class FakePage:
    def __init__(self):
        self.urls = []

    def goto(self, url, **kwargs):
        self.urls.append(url)

        class Response:
            status = 200

        return Response()

    def content(self):
        return "<html><body>AliExpress</body></html>"


class FakeContext:
    def __init__(self):
        self.page = FakePage()
        self.closed = False

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class FakeBrowserFactory:
    def __init__(self):
        self.calls = []
        self.contexts = []

    def open_context(self, user_data_dir: Path, *, headless: bool = False):
        self.calls.append({"user_data_dir": user_data_dir, "headless": headless})
        context = FakeContext()
        self.contexts.append(context)
        return context


class AliExpressSessionTests(unittest.TestCase):
    def test_login_records_metadata_and_closes_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FakeBrowserFactory()
            session = BrowserSessionBootstrapper(
                store=BrowserSessionStore(Path(tmpdir)),
                browser_factory=factory,
            )

            payload = session.login(login_timeout_sec=1, manual_confirm=False)

            self.assertEqual(payload["status"], "ready")
            self.assertTrue((Path(tmpdir) / "session.json").is_file())
            self.assertFalse(factory.calls[0]["headless"])
            self.assertTrue(factory.contexts[0].closed)

    def test_fetch_uses_headless_managed_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "browser-profile").mkdir()
            factory = FakeBrowserFactory()
            session = BrowserSessionBootstrapper(
                store=BrowserSessionStore(root),
                browser_factory=factory,
            )

            result = session.fetch("https://www.aliexpress.com/wholesale?SearchText=bin")

            self.assertEqual(result.fetcher, "managed_session")
            self.assertTrue(factory.calls[0]["headless"])
            self.assertTrue(factory.contexts[0].closed)

    def test_logout_removes_managed_profile_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "session"
            (root / "browser-profile").mkdir(parents=True)
            session = BrowserSessionBootstrapper(store=BrowserSessionStore(root), browser_factory=FakeBrowserFactory())

            payload = session.logout()

            self.assertTrue(payload["removed"])
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
