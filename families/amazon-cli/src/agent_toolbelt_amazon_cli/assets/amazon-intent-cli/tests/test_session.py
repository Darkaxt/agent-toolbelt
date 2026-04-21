from pathlib import Path

import pytest

from amazon_intent_cli.amazon import AmazonHttpClient
from amazon_intent_cli.marketplaces import SUPPORTED_MARKETPLACES, get_marketplace
from amazon_intent_cli.models import BrowserSession
from amazon_intent_cli.session import (
    BrowserSessionError,
    BrowserSessionBootstrapper,
    BrowserSessionStore,
    _resolve_browser_executable,
    make_session_key,
)


def test_browser_session_store_round_trip(tmp_path: Path) -> None:
    store = BrowserSessionStore(tmp_path)
    session = BrowserSession(
        marketplace="de",
        browser_executable=r"C:\Chrome\chrome.exe",
        user_agent="Mozilla/5.0 Test",
        cookies=[
            {
                "name": "session-id",
                "value": "abc123",
                "domain": ".amazon.de",
                "path": "/",
                "secure": True,
                "httpOnly": False,
            }
        ],
        portal="retail",
        session_key="de:retail",
        session_source="managed_profile",
        profile_dir=str(tmp_path / "profiles" / "de__retail"),
    )

    store.save(session)
    loaded = store.load("de", portal="retail")

    assert loaded is not None
    assert loaded.marketplace == "de"
    assert loaded.portal == "retail"
    assert loaded.session_key == "de:retail"
    assert loaded.session_source == "managed_profile"
    assert loaded.profile_dir == str(tmp_path / "profiles" / "de__retail")
    assert loaded.cookies[0]["name"] == "session-id"


def test_browser_session_store_loads_legacy_marketplace_file(tmp_path: Path) -> None:
    store = BrowserSessionStore(tmp_path)
    legacy = BrowserSession(
        marketplace="de",
        browser_executable=r"C:\Chrome\chrome.exe",
        user_agent="Mozilla/5.0 Legacy",
        cookies=[{"name": "session-id", "value": "abc123", "domain": ".amazon.de", "path": "/"}],
    )
    (tmp_path / "de.json").write_text(legacy.to_json(), encoding="utf-8")

    loaded = store.load("de", portal="retail")

    assert loaded is not None
    assert loaded.marketplace == "de"
    assert loaded.portal == "retail"
    assert loaded.session_key == "de:retail"


def test_http_client_uses_browser_session_headers_and_cookies(tmp_path: Path) -> None:
    session = BrowserSession(
        marketplace="de",
        browser_executable=r"C:\Chrome\chrome.exe",
        user_agent="Mozilla/5.0 Session UA",
        cookies=[
            {
                "name": "session-id",
                "value": "abc123",
                "domain": ".amazon.de",
                "path": "/",
                "secure": True,
                "httpOnly": False,
            }
        ],
    )

    client = AmazonHttpClient(get_marketplace("de"), session=session)

    assert client._client.headers["User-Agent"] == "Mozilla/5.0 Session UA"
    assert client._client.cookies.get("session-id") == "abc123"


@pytest.mark.parametrize("marketplace", sorted(SUPPORTED_MARKETPLACES))
def test_make_session_key_accepts_business_for_configured_marketplaces(marketplace: str) -> None:
    assert make_session_key(marketplace, "business") == f"{marketplace}:business"


def test_make_session_key_rejects_unsupported_portal() -> None:
    try:
        make_session_key("de", "vendor")
    except ValueError as exc:
        assert "Unsupported portal" in str(exc)
    else:
        raise AssertionError("Expected unsupported portal to be rejected")


def test_resolve_browser_executable_prefers_localappdata_helium(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AMAZON_CLI_BROWSER", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    helium = tmp_path / "imput" / "Helium" / "Application" / "chrome.exe"
    helium.parent.mkdir(parents=True)
    helium.write_text("", encoding="utf-8")

    assert _resolve_browser_executable(None) == str(helium)


def test_default_login_confirmation_reports_non_interactive_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = BrowserSessionStore(tmp_path / "sessions")
    bootstrapper = BrowserSessionBootstrapper(store)

    def raise_eof(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    with pytest.raises(BrowserSessionError, match="interactive terminal"):
        bootstrapper._default_login_confirmation("https://www.amazon.es/")


def test_managed_login_saves_cookies_from_persistent_context(tmp_path: Path, monkeypatch) -> None:
    class FakePage:
        url = "https://www.amazon.de/"

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def evaluate(self, expression: str) -> str:
            return "Mozilla/5.0 Fake Browser"

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]
            self.closed = False

        def cookies(self, urls: list[str]) -> list[dict]:
            return [{"name": "session-id", "value": "abc123", "domain": ".amazon.de", "path": "/"}]

        def close(self) -> None:
            self.closed = True

    class FakeChromium:
        def __init__(self) -> None:
            self.launch_kwargs = None

        def launch_persistent_context(self, **kwargs):
            self.launch_kwargs = kwargs
            return FakeContext()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

    class FakeManager:
        def __init__(self) -> None:
            self.playwright = FakePlaywright()

        def __enter__(self):
            return self.playwright

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    store = BrowserSessionStore(tmp_path / "sessions")
    confirmations: list[str] = []
    bootstrapper = BrowserSessionBootstrapper(
        store,
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
        login_confirmation=lambda url: confirmations.append(url),
    )
    monkeypatch.setattr(
        bootstrapper,
        "_validate_session",
        lambda marketplace, session, target_url: True,
    )

    payload = bootstrapper.login(
        "de",
        r"C:\Chrome\chrome.exe",
        portal="retail",
        url="https://www.amazon.de/",
    )
    session = store.load("de", portal="retail")

    assert payload["session_saved"] is True
    assert payload["usable"] is True
    assert payload["session_source"] == "managed_profile"
    assert payload["session_key"] == "de:retail"
    assert payload["portal"] == "retail"
    assert payload["profile_dir"].endswith("de__retail")
    assert confirmations == ["https://www.amazon.de/"]
    assert session is not None
    assert session.user_agent == "Mozilla/5.0 Fake Browser"
    assert session.session_source == "managed_profile"
    assert session.session_key == "de:retail"
    assert session.profile_dir is not None and session.profile_dir.endswith("de__retail")
    assert session.cookies[0]["name"] == "session-id"


def test_managed_business_login_defaults_to_standard_amazon_de_url(tmp_path: Path, monkeypatch) -> None:
    class FakePage:
        url = ""

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def evaluate(self, expression: str) -> str:
            return "Mozilla/5.0 Fake Browser"

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

        def cookies(self, urls: list[str]) -> list[dict]:
            return [{"name": "session-id", "value": "business123", "domain": ".amazon.de", "path": "/"}]

        def close(self) -> None:
            return None

    class FakeChromium:
        def __init__(self) -> None:
            self.launch_kwargs = None

        def launch_persistent_context(self, **kwargs):
            self.launch_kwargs = kwargs
            return FakeContext()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

    class FakeManager:
        def __init__(self) -> None:
            self.playwright = FakePlaywright()

        def __enter__(self):
            return self.playwright

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    store = BrowserSessionStore(tmp_path / "sessions")
    confirmations: list[str] = []
    bootstrapper = BrowserSessionBootstrapper(
        store,
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
        login_confirmation=lambda url: confirmations.append(url),
    )
    monkeypatch.setattr(
        bootstrapper,
        "_validate_session",
        lambda marketplace, session, target_url: True,
    )

    payload = bootstrapper.login("de", r"C:\Chrome\chrome.exe", portal="business")
    session = store.load("de", portal="business")

    assert payload["url"] == "https://www.amazon.de/"
    assert payload["session_key"] == "de:business"
    assert payload["portal"] == "business"
    assert payload["profile_dir"].endswith("de__business")
    assert confirmations == ["https://www.amazon.de/"]
    assert session is not None
    assert session.portal == "business"
    assert session.session_key == "de:business"
    assert session.profile_dir is not None and session.profile_dir.endswith("de__business")


def test_managed_business_login_defaults_to_standard_amazon_fr_url(tmp_path: Path, monkeypatch) -> None:
    class FakePage:
        url = ""

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def evaluate(self, expression: str) -> str:
            return "Mozilla/5.0 Fake Browser"

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

        def cookies(self, urls: list[str]) -> list[dict]:
            return [{"name": "session-id", "value": "business-fr", "domain": ".amazon.fr", "path": "/"}]

        def close(self) -> None:
            return None

    class FakeChromium:
        def launch_persistent_context(self, **kwargs):
            return FakeContext()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

    class FakeManager:
        def __init__(self) -> None:
            self.playwright = FakePlaywright()

        def __enter__(self):
            return self.playwright

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    store = BrowserSessionStore(tmp_path / "sessions")
    confirmations: list[str] = []
    bootstrapper = BrowserSessionBootstrapper(
        store,
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
        login_confirmation=lambda url: confirmations.append(url),
    )
    monkeypatch.setattr(
        bootstrapper,
        "_validate_session",
        lambda marketplace, session, target_url: True,
    )

    payload = bootstrapper.login("fr", r"C:\Chrome\chrome.exe", portal="business")
    session = store.load("fr", portal="business")

    assert payload["url"] == "https://www.amazon.fr/"
    assert payload["session_key"] == "fr:business"
    assert payload["profile_dir"].endswith("fr__business")
    assert confirmations == ["https://www.amazon.fr/"]
    assert session is not None
    assert session.portal == "business"
    assert session.session_key == "fr:business"
    assert session.profile_dir is not None and session.profile_dir.endswith("fr__business")
