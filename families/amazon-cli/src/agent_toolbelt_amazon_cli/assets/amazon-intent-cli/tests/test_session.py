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


def test_login_detection_recognizes_spanish_business_account_header(tmp_path: Path) -> None:
    class FakePage:
        def content(self) -> str:
            return """
            <a href="https://www.amazon.es/gp/css/homepage.html?ref_=abn_bnav_youraccount_btn"
               id="nav-link-yourAccount">
                <span class="nav-line-1">Hola José</span>
                <span class="nav-line-2">
                  <span class="abnav-accountfor">Cuenta para José Miguel Soriano</span>
                </span>
            </a>
            """

    bootstrapper = BrowserSessionBootstrapper(BrowserSessionStore(tmp_path / "sessions"))

    assert bootstrapper._login_detected_marker(FakePage()) == "selector:#nav-link-yourAccount"


def test_login_detection_rejects_signed_out_account_header(tmp_path: Path) -> None:
    class FakePage:
        def content(self) -> str:
            return """
            <a id="nav-link-accountList" href="/ap/signin">
              <span class="nav-line-1">Hello, sign in</span>
              <span class="nav-line-2">Account & Lists</span>
            </a>
            """

    bootstrapper = BrowserSessionBootstrapper(BrowserSessionStore(tmp_path / "sessions"))

    assert bootstrapper._login_detected_marker(FakePage()) is None


def test_managed_login_saves_cookies_from_persistent_context(tmp_path: Path, monkeypatch) -> None:
    class FakePage:
        url = "https://www.amazon.de/"

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def evaluate(self, expression: str) -> str:
            return "Mozilla/5.0 Fake Browser"

        def content(self) -> str:
            return """
            <a id="nav-link-accountList" href="/gp/css/homepage.html">
              <span class="nav-line-1">Hello José</span>
            </a>
            """

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
    assert payload["wait_strategy"] == "targeted_login_detection"
    assert payload["detected_marker"] == "selector:#nav-link-accountList"
    assert confirmations == []
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

        def content(self) -> str:
            return """
            <a id="nav-link-yourAccount" href="https://www.amazon.de/gp/css/homepage.html">
              <span class="nav-line-1">Hallo José</span>
            </a>
            """

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
    assert payload["wait_strategy"] == "targeted_login_detection"
    assert payload["detected_marker"] == "selector:#nav-link-yourAccount"
    assert confirmations == []
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

        def content(self) -> str:
            return """
            <a id="nav-link-yourAccount" href="https://www.amazon.fr/gp/css/homepage.html">
              <span class="nav-line-1">Bonjour José</span>
            </a>
            """

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
    assert payload["detected_marker"] == "selector:#nav-link-yourAccount"
    assert confirmations == []
    assert session is not None
    assert session.portal == "business"
    assert session.session_key == "fr:business"
    assert session.profile_dir is not None and session.profile_dir.endswith("fr__business")


def test_managed_login_manual_confirm_preserves_explicit_enter_path(tmp_path: Path, monkeypatch) -> None:
    class FakePage:
        url = ""

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def evaluate(self, expression: str) -> str:
            return "Mozilla/5.0 Fake Browser"

        def content(self) -> str:
            return "<html><body>Please sign in</body></html>"

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

        def cookies(self, urls: list[str]) -> list[dict]:
            return [{"name": "session-id", "value": "manual", "domain": ".amazon.es", "path": "/"}]

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

    confirmations: list[str] = []
    store = BrowserSessionStore(tmp_path / "sessions")
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
        "es",
        r"C:\Chrome\chrome.exe",
        portal="business",
        manual_confirm=True,
    )

    assert confirmations == ["https://www.amazon.es/"]
    assert payload["wait_strategy"] == "manual_confirm"
    assert payload["detected_marker"] == "manual_confirm"
    assert store.load("es", portal="business") is not None


def test_managed_login_timeout_does_not_save_session(tmp_path: Path) -> None:
    class FakePage:
        url = ""

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def evaluate(self, expression: str) -> str:
            return "Mozilla/5.0 Fake Browser"

        def content(self) -> str:
            return """
            <form id="ap_signin_form">
              <input id="ap_email">
            </form>
            """

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]
            self.closed = False

        def cookies(self, urls: list[str]) -> list[dict]:
            return [{"name": "session-id", "value": "not-saved", "domain": ".amazon.es", "path": "/"}]

        def close(self) -> None:
            self.closed = True

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
    bootstrapper = BrowserSessionBootstrapper(
        store,
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )

    with pytest.raises(BrowserSessionError, match="login_not_detected"):
        bootstrapper.login(
            "es",
            r"C:\Chrome\chrome.exe",
            portal="business",
            login_timeout_sec=0,
        )

    assert store.load("es", portal="business") is None


def test_add_to_cart_uses_managed_profile_and_clicks_only_add_to_cart(tmp_path: Path) -> None:
    clicked_selectors: list[str] = []
    selected_options: list[tuple[str, str]] = []
    launch_kwargs: dict[str, object] = {}
    load_states: list[str] = []
    timeouts: list[int] = []

    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector
            self.first = self

        def count(self) -> int:
            if self.selector == "#add-to-cart-button":
                return 1
            if self.selector == "select#quantity":
                return 1
            return 0

        def click(self, timeout: int | None = None) -> None:
            clicked_selectors.append(self.selector)
            if self.selector == "#add-to-cart-button":
                self.page.added = True

        def select_option(self, value: str, timeout: int | None = None) -> None:
            selected_options.append((self.selector, value))

        def is_visible(self, timeout: int | None = None) -> bool:
            return self.count() > 0

    class FakePage:
        def __init__(self) -> None:
            self.url = ""
            self.added = False

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            load_states.append(state)

        def wait_for_timeout(self, timeout: int) -> None:
            timeouts.append(timeout)

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        def content(self) -> str:
            confirmation = "<h1>Added to Basket</h1>" if self.added else ""
            return f"""
            <html>
              <body>
                <span id="productTitle">Pilexil Forte Max</span>
                <input id="twister-plus-price-data-price" value="141.44">
                <div id="deliveryBlockMessage">Free delivery tomorrow</div>
                {confirmation}
              </body>
            </html>
            """

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

        def close(self) -> None:
            return None

    class FakeChromium:
        def launch_persistent_context(self, **kwargs):
            launch_kwargs.update(kwargs)
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
    profile_dir = tmp_path / "profiles" / "es__business"
    store.save(
        BrowserSession(
            marketplace="es",
            browser_executable=r"C:\Chrome\chrome.exe",
            user_agent="Mozilla/5.0 Managed",
            cookies=[{"name": "session-id", "value": "abc", "domain": ".amazon.es", "path": "/"}],
            portal="business",
            session_key="es:business",
            session_source="managed_profile",
            profile_dir=str(profile_dir),
        )
    )
    bootstrapper = BrowserSessionBootstrapper(
        store,
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )

    payload = bootstrapper.add_to_cart("es", "B0TEST1234", portal="business", quantity=2)

    assert launch_kwargs["user_data_dir"] == str(profile_dir)
    assert launch_kwargs["headless"] is False
    assert selected_options == [("select#quantity", "2")]
    assert clicked_selectors == ["#add-to-cart-button"]
    assert load_states == []
    assert timeouts == []
    assert payload["status"] == "added"
    assert payload["cart_confirmation_detected"] is True
    assert payload["wait_strategy"] == "targeted"
    assert payload["detected_marker"] == "text:added_to_basket"
    assert isinstance(payload["action_timing_ms"], int)
    assert payload["safety"] == {"checkout_performed": False, "buy_now_clicked": False}


def test_add_to_cart_clicks_immediately_when_button_is_visible(tmp_path: Path) -> None:
    clicked_selectors: list[str] = []
    selected_options: list[tuple[str, str]] = []

    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector
            self.first = self

        def count(self) -> int:
            if self.selector in {"#add-to-cart-button", "select#quantity"}:
                return 1
            return 0

        def click(self, timeout: int | None = None) -> None:
            clicked_selectors.append(self.selector)
            self.page.added = True
            self.page.url = "https://www.amazon.es/cart/smart-wagon?newItems=B0TEST1234"

        def select_option(self, value: str, timeout: int | None = None) -> None:
            selected_options.append((self.selector, value))

        def is_visible(self, timeout: int | None = None) -> bool:
            return self.count() > 0

    class FakePage:
        def __init__(self) -> None:
            self.url = ""
            self.added = False

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        def content(self) -> str:
            return """
            <html>
              <body>
                <span id="productTitle">Pilexil Forte Max</span>
                <input id="twister-plus-price-data-price" value="141.44">
                <div id="deliveryBlockMessage">Entrega mañana</div>
              </body>
            </html>
            """

        def close(self, run_before_unload: bool = False) -> None:
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

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
    store.save(
        BrowserSession(
            marketplace="es",
            browser_executable=r"C:\Chrome\chrome.exe",
            user_agent="Mozilla/5.0 Managed",
            cookies=[{"name": "session-id", "value": "abc", "domain": ".amazon.es", "path": "/"}],
            portal="business",
            session_key="es:business",
            session_source="managed_profile",
            profile_dir=str(tmp_path / "profiles" / "es__business"),
        )
    )
    bootstrapper = BrowserSessionBootstrapper(
        store,
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )

    def fail_slow_wait(*args, **kwargs):
        raise AssertionError("visible add button should not enter the slow polling wait")

    bootstrapper._wait_for_locator = fail_slow_wait  # type: ignore[method-assign]

    payload = bootstrapper.add_to_cart("es", "B0TEST1234", portal="business", quantity=2)

    assert selected_options == [("select#quantity", "2")]
    assert clicked_selectors == ["#add-to-cart-button"]
    assert payload["status"] == "added"
    expected_phase_keys = {
        "navigate",
        "dismiss_cookie_banner",
        "safety_parse",
        "quantity_select",
        "add_button_wait",
        "add_click",
        "confirmation_wait",
        "browser_close",
    }
    assert set(payload["phase_timing_ms"]) == expected_phase_keys
    assert all(isinstance(payload["phase_timing_ms"][key], int) for key in expected_phase_keys)


def _aui_quantity_bootstrapper(
    tmp_path: Path,
    *,
    aui_available: bool,
    aui_option_available: bool = True,
    native_available: bool = False,
):
    clicked_actions: list[str] = []
    native_selections: list[str] = []

    class FakeLocator:
        def __init__(self, page, kind: str, *, option_value: str | None = None) -> None:
            self.page = page
            self.kind = kind
            self.option_value = option_value
            self.first = self

        def count(self) -> int:
            if self.kind == "container":
                return 1 if aui_available else 0
            if self.kind in {"dropdown_button", "prompt", "aui_select"}:
                return 1 if aui_available else 0
            if self.kind == "popover_option":
                return 1 if self.page.popover_open and aui_option_available else 0
            if self.kind == "native_select":
                return 1 if native_available else 0
            if self.kind == "add_button":
                return 1
            return 0

        def is_visible(self, timeout: int | None = None) -> bool:
            return self.count() > 0

        def click(self, timeout: int | None = None) -> None:
            clicked_actions.append(self.kind)
            if self.kind == "dropdown_button":
                self.page.popover_open = True
            elif self.kind == "popover_option" and self.option_value is not None:
                self.page.quantity = self.option_value
                self.page.popover_open = False
            elif self.kind == "add_button":
                self.page.added = True
                self.page.url = "https://www.amazon.es/cart/smart-wagon?newItems=B0TEST1234"

        def select_option(self, value: str, timeout: int | None = None) -> None:
            native_selections.append(value)
            self.page.quantity = value

        def inner_text(self, timeout: int | None = None) -> str:
            if self.kind == "prompt":
                return self.page.quantity
            return ""

        def get_attribute(self, name: str, timeout: int | None = None) -> str | None:
            if self.kind in {"aui_select", "native_select"} and name == "value":
                return self.page.quantity
            return None

        def locator(self, selector: str):
            if selector in {"span.a-button-dropdown", "[data-action='a-dropdown-button']", ".a-dropdown-container .a-button"}:
                return FakeLocator(self.page, "dropdown_button")
            if selector in {".a-dropdown-prompt", "select[id$='predefinedQuantitiesDropdown']"}:
                return FakeLocator(self.page, "prompt" if selector == ".a-dropdown-prompt" else "aui_select")
            return FakeLocator(self.page, "missing")

    class FakePage:
        def __init__(self) -> None:
            self.url = ""
            self.quantity = "1"
            self.popover_open = False
            self.added = False

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def locator(self, selector: str) -> FakeLocator:
            if selector == 'span[id$="predefinedQuantitiesDropdownContainer"]':
                return FakeLocator(self, "container")
            if selector.startswith('div.a-popover[aria-hidden="false"] a.a-dropdown-link'):
                option_value = "2" if '"stringVal":"2"' in selector else None
                return FakeLocator(self, "popover_option", option_value=option_value)
            if selector == "#add-to-cart-button":
                return FakeLocator(self, "add_button")
            if selector in {"select#quantity", "select[id$='predefinedQuantitiesDropdown']"}:
                return FakeLocator(self, "native_select")
            return FakeLocator(self, "missing")

        def content(self) -> str:
            return """
            <html>
              <body>
                <span id="productTitle">Pilexil Forte Max</span>
                <input id="twister-plus-price-data-price" value="141.44">
                <div id="deliveryBlockMessage">Entrega mañana</div>
              </body>
            </html>
            """

        def close(self, run_before_unload: bool = False) -> None:
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

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
    store.save(
        BrowserSession(
            marketplace="es",
            browser_executable=r"C:\Chrome\chrome.exe",
            user_agent="Mozilla/5.0 Managed",
            cookies=[{"name": "session-id", "value": "abc", "domain": ".amazon.es", "path": "/"}],
            portal="business",
            session_key="es:business",
            session_source="managed_profile",
            profile_dir=str(tmp_path / "profiles" / "es__business"),
        )
    )
    bootstrapper = BrowserSessionBootstrapper(
        store,
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )
    return bootstrapper, clicked_actions, native_selections


def test_add_to_cart_uses_aui_quantity_dropdown_before_native_select(tmp_path: Path) -> None:
    bootstrapper, clicked_actions, native_selections = _aui_quantity_bootstrapper(
        tmp_path,
        aui_available=True,
        native_available=True,
    )

    payload = bootstrapper.add_to_cart("es", "B0TEST1234", portal="business", quantity=2)

    assert clicked_actions == ["dropdown_button", "popover_option", "add_button"]
    assert native_selections == []
    assert payload["status"] == "added"
    assert payload["quantity_select_method"] == "aui_dropdown"


def test_add_to_cart_falls_back_to_native_quantity_select_when_aui_absent(tmp_path: Path) -> None:
    bootstrapper, clicked_actions, native_selections = _aui_quantity_bootstrapper(
        tmp_path,
        aui_available=False,
        native_available=True,
    )

    payload = bootstrapper.add_to_cart("es", "B0TEST1234", portal="business", quantity=2)

    assert clicked_actions == ["add_button"]
    assert native_selections == ["2"]
    assert payload["status"] == "added"
    assert payload["quantity_select_method"] == "native_select"


def test_add_to_cart_falls_back_to_native_when_aui_option_missing(tmp_path: Path) -> None:
    bootstrapper, clicked_actions, native_selections = _aui_quantity_bootstrapper(
        tmp_path,
        aui_available=True,
        aui_option_available=False,
        native_available=True,
    )

    payload = bootstrapper.add_to_cart("es", "B0TEST1234", portal="business", quantity=2)

    assert clicked_actions == ["dropdown_button", "add_button"]
    assert native_selections == ["2"]
    assert payload["status"] == "added"
    assert payload["quantity_select_method"] == "native_select"


def test_add_to_cart_does_not_click_add_when_all_quantity_selection_fails(tmp_path: Path) -> None:
    bootstrapper, clicked_actions, native_selections = _aui_quantity_bootstrapper(
        tmp_path,
        aui_available=False,
        native_available=False,
    )

    payload = bootstrapper.add_to_cart("es", "B0TEST1234", portal="business", quantity=2)

    assert clicked_actions == []
    assert native_selections == []
    assert payload["status"] == "failed"
    assert payload["quantity_select_method"] == "failed"
    assert "quantity_selector_missing" in payload["warnings"]


def test_add_to_cart_does_not_click_when_offer_is_not_deliverable(tmp_path: Path) -> None:
    clicked_selectors: list[str] = []
    load_states: list[str] = []
    timeouts: list[int] = []

    class FakeLocator:
        def __init__(self, selector: str) -> None:
            self.selector = selector
            self.first = self

        def count(self) -> int:
            return 1 if self.selector == "#add-to-cart-button" else 0

        def click(self, timeout: int | None = None) -> None:
            clicked_selectors.append(self.selector)

    class FakePage:
        url = ""

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            load_states.append(state)

        def wait_for_timeout(self, timeout: int) -> None:
            timeouts.append(timeout)

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(selector)

        def content(self) -> str:
            return """
            <html>
              <body>
                <span id="productTitle">Pilexil Forte Max</span>
                <input id="twister-plus-price-data-price" value="141.44">
                <div id="deliveryBlockMessage">
                  This item cannot be shipped to your selected delivery location.
                </div>
              </body>
            </html>
            """

    class FakeContext:
        pages = [FakePage()]

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
    store.save(
        BrowserSession(
            marketplace="es",
            browser_executable=r"C:\Chrome\chrome.exe",
            user_agent="Mozilla/5.0 Managed",
            cookies=[{"name": "session-id", "value": "abc", "domain": ".amazon.es", "path": "/"}],
            portal="business",
            session_key="es:business",
            session_source="managed_profile",
            profile_dir=str(tmp_path / "profiles" / "es__business"),
        )
    )
    bootstrapper = BrowserSessionBootstrapper(
        store,
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )

    payload = bootstrapper.add_to_cart("es", "B0TEST1234", portal="business")

    assert clicked_selectors == []
    assert load_states == []
    assert timeouts == []
    assert payload["status"] == "failed"
    assert "not_deliverable" in payload["warnings"]
    assert payload["cart_confirmation_detected"] is False


def test_add_to_cart_confirmation_can_be_detected_from_cart_url(tmp_path: Path) -> None:
    clicked_selectors: list[str] = []

    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector
            self.first = self

        def count(self) -> int:
            return 1 if self.selector == "#add-to-cart-button" else 0

        def is_visible(self, timeout: int | None = None) -> bool:
            return self.count() > 0

        def click(self, timeout: int | None = None) -> None:
            clicked_selectors.append(self.selector)
            self.page.url = "https://www.amazon.es/cart/smart-wagon?newItems=B0TEST1234"

    class FakePage:
        def __init__(self) -> None:
            self.url = ""

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            raise AssertionError("cart add must not wait for networkidle")

        def wait_for_timeout(self, timeout: int) -> None:
            raise AssertionError("cart add must not use fixed sleeps")

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        def content(self) -> str:
            return """
            <html>
              <body>
                <span id="productTitle">Pilexil Forte Max</span>
                <input id="twister-plus-price-data-price" value="114.97">
                <div id="deliveryBlockMessage">Entrega mañana</div>
              </body>
            </html>
            """

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

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
    store.save(
        BrowserSession(
            marketplace="es",
            browser_executable=r"C:\Chrome\chrome.exe",
            user_agent="Mozilla/5.0 Managed",
            cookies=[{"name": "session-id", "value": "abc", "domain": ".amazon.es", "path": "/"}],
            portal="business",
            session_key="es:business",
            session_source="managed_profile",
            profile_dir=str(tmp_path / "profiles" / "es__business"),
        )
    )
    bootstrapper = BrowserSessionBootstrapper(
        store,
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )

    payload = bootstrapper.add_to_cart("es", "B0TEST1234", portal="business")

    assert clicked_selectors == ["#add-to-cart-button"]
    assert payload["status"] == "added"
    assert payload["cart_confirmation_detected"] is True
    assert payload["detected_marker"] == "url:cart"


def _managed_cart_session_store(tmp_path: Path) -> BrowserSessionStore:
    store = BrowserSessionStore(tmp_path / "sessions")
    store.save(
        BrowserSession(
            marketplace="es",
            browser_executable=r"C:\Chrome\chrome.exe",
            user_agent="Mozilla/5.0 Managed",
            cookies=[{"name": "session-id", "value": "abc", "domain": ".amazon.es", "path": "/"}],
            portal="business",
            session_key="es:business",
            session_source="managed_profile",
            profile_dir=str(tmp_path / "profiles" / "es__business"),
        )
    )
    return store


def _cart_remove_bootstrapper(tmp_path: Path, *, starting_quantity: int, asin: str = "B0TEST1234"):
    clicked_actions: list[str] = []
    load_states: list[str] = []
    timeouts: list[int] = []
    launch_kwargs: dict[str, object] = {}

    class FakeLocator:
        def __init__(self, page, kind: str) -> None:
            self.page = page
            self.kind = kind
            self.first = self

        def count(self) -> int:
            if self.kind == "row":
                return 1 if self.page.row_exists else 0
            if self.kind == "quantity":
                return 1 if self.page.row_exists else 0
            if self.kind == "minus":
                return 1 if self.page.row_exists and self.page.quantity > 1 else 0
            if self.kind == "trash":
                return 1 if self.page.row_exists and self.page.quantity <= 1 else 0
            return 0

        def is_visible(self, timeout: int | None = None) -> bool:
            return self.count() > 0

        def inner_text(self, timeout: int | None = None) -> str:
            if self.kind == "quantity":
                return str(self.page.quantity)
            if self.kind == "row":
                return f"Pilexil Forte Max {self.page.quantity}"
            return ""

        def get_attribute(self, name: str, timeout: int | None = None) -> str | None:
            if self.kind == "quantity" and name == "value":
                return str(self.page.quantity)
            return None

        def click(self, timeout: int | None = None) -> None:
            clicked_actions.append(self.kind)
            if self.kind == "minus":
                self.page.quantity -= 1
            elif self.kind == "trash":
                self.page.quantity = 0
                self.page.row_exists = False
                self.page.removed = True

        def locator(self, selector: str):
            lowered = selector.casefold()
            if "data-a-selector='value'" in lowered or "data-a-selector=\"value\"" in lowered:
                return FakeLocator(self.page, "quantity")
            if "decrement" in lowered or "quantity-decrease" in lowered or "minus" in lowered:
                return FakeLocator(self.page, "minus")
            if "delete" in lowered or "remove" in lowered or "trash" in lowered:
                return FakeLocator(self.page, "trash")
            return FakeLocator(self.page, "missing")

    class FakePage:
        def __init__(self) -> None:
            self.url = ""
            self.quantity = starting_quantity
            self.row_exists = True
            self.removed = False

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            load_states.append(state)

        def wait_for_timeout(self, timeout: int) -> None:
            timeouts.append(timeout)

        def locator(self, selector: str) -> FakeLocator:
            if asin in selector and "data-asin" in selector:
                return FakeLocator(self, "row")
            return FakeLocator(self, "missing")

        def content(self) -> str:
            if self.row_exists:
                return f"""
                <html>
                  <body>
                    <div data-asin="{asin}">
                      <a href="/dp/{asin}">Pilexil Forte Max</a>
                      <span data-a-selector="value">{self.quantity}</span>
                    </div>
                  </body>
                </html>
                """
            marker = "<div>Removed from basket</div>" if self.removed else ""
            return f"<html><body>{marker}</body></html>"

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

        def close(self) -> None:
            return None

    class FakeChromium:
        def launch_persistent_context(self, **kwargs):
            launch_kwargs.update(kwargs)
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

    bootstrapper = BrowserSessionBootstrapper(
        _managed_cart_session_store(tmp_path),
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )
    return bootstrapper, clicked_actions, load_states, timeouts, launch_kwargs


def test_remove_from_cart_decrements_quantity_with_item_scoped_minus(tmp_path: Path) -> None:
    bootstrapper, clicked_actions, load_states, timeouts, launch_kwargs = _cart_remove_bootstrapper(
        tmp_path,
        starting_quantity=3,
    )

    payload = bootstrapper.remove_from_cart("es", "B0TEST1234", portal="business", quantity=1)

    assert launch_kwargs["headless"] is False
    assert clicked_actions == ["minus"]
    assert load_states == []
    assert timeouts == []
    assert payload["status"] == "quantity_updated"
    assert payload["quantity_requested"] == 1
    assert payload["quantity_removed"] == 1
    assert payload["quantity_before"] == 3
    assert payload["quantity_after"] == 2
    assert payload["cart_removal_detected"] is True
    assert payload["detected_marker"] == "quantity:2"
    assert payload["safety"] == {"checkout_performed": False, "buy_now_clicked": False}


def test_remove_from_cart_uses_trash_when_quantity_is_one(tmp_path: Path) -> None:
    bootstrapper, clicked_actions, load_states, timeouts, _launch_kwargs = _cart_remove_bootstrapper(
        tmp_path,
        starting_quantity=1,
    )

    payload = bootstrapper.remove_from_cart("es", "B0TEST1234", portal="business", quantity=1)

    assert clicked_actions == ["trash"]
    assert load_states == []
    assert timeouts == []
    assert payload["status"] == "removed"
    assert payload["quantity_removed"] == 1
    assert payload["quantity_before"] == 1
    assert payload["quantity_after"] == 0
    assert payload["cart_removal_detected"] is True
    assert payload["detected_marker"] == "row_removed"


def test_remove_from_cart_decrements_then_uses_trash_for_last_unit(tmp_path: Path) -> None:
    bootstrapper, clicked_actions, _load_states, _timeouts, _launch_kwargs = _cart_remove_bootstrapper(
        tmp_path,
        starting_quantity=2,
    )

    payload = bootstrapper.remove_from_cart("es", "B0TEST1234", portal="business", quantity=2)

    assert clicked_actions == ["minus", "trash"]
    assert payload["status"] == "removed"
    assert payload["quantity_removed"] == 2
    assert payload["quantity_before"] == 2
    assert payload["quantity_after"] == 0
    assert payload["cart_removal_detected"] is True


def test_remove_from_cart_fails_without_mutation_when_asin_is_not_found(tmp_path: Path) -> None:
    bootstrapper, clicked_actions, load_states, timeouts, _launch_kwargs = _cart_remove_bootstrapper(
        tmp_path,
        starting_quantity=1,
        asin="B0OTHER123",
    )

    payload = bootstrapper.remove_from_cart("es", "B0TEST1234", portal="business", quantity=1)

    assert clicked_actions == []
    assert load_states == []
    assert timeouts == []
    assert payload["status"] == "failed"
    assert "cart_item_not_found" in payload["warnings"]
    assert payload["cart_removal_detected"] is False


def test_remove_from_cart_fails_without_mutation_on_sign_in_page(tmp_path: Path) -> None:
    clicked_actions: list[str] = []

    class FakeLocator:
        first = None

        def __init__(self) -> None:
            self.first = self

        def count(self) -> int:
            return 0

        def click(self, timeout: int | None = None) -> None:
            clicked_actions.append("unexpected")

    class FakePage:
        url = ""

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            raise AssertionError("cart remove must not wait for networkidle")

        def wait_for_timeout(self, timeout: int) -> None:
            raise AssertionError("cart remove must not use fixed sleeps")

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator()

        def content(self) -> str:
            return '<html><body><form id="ap_signin_form"></form></body></html>'

    class FakeContext:
        pages = [FakePage()]

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

    bootstrapper = BrowserSessionBootstrapper(
        _managed_cart_session_store(tmp_path),
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )

    payload = bootstrapper.remove_from_cart("es", "B0TEST1234", portal="business", quantity=1)

    assert clicked_actions == []
    assert payload["status"] == "failed"
    assert "sign_in_required" in payload["warnings"]


def test_remove_from_cart_reloads_cart_when_last_row_removal_is_delayed(tmp_path: Path) -> None:
    clicked_actions: list[str] = []
    navigations: list[str] = []

    class FakeLocator:
        def __init__(self, page, kind: str) -> None:
            self.page = page
            self.kind = kind
            self.first = self

        def count(self) -> int:
            if self.kind == "row":
                return 1 if self.page.row_exists else 0
            if self.kind == "quantity":
                return 1 if self.page.row_exists else 0
            if self.kind == "trash":
                return 1 if self.page.row_exists else 0
            return 0

        def is_visible(self, timeout: int | None = None) -> bool:
            return self.count() > 0

        def inner_text(self, timeout: int | None = None) -> str:
            return "1" if self.kind == "quantity" else "Pilexil Forte Max"

        def get_attribute(self, name: str, timeout: int | None = None) -> str | None:
            return "1" if self.kind == "quantity" and name == "value" else None

        def click(self, timeout: int | None = None) -> None:
            clicked_actions.append(self.kind)
            if self.kind == "trash":
                self.page.pending_removal = True

        def locator(self, selector: str):
            lowered = selector.casefold()
            if "data-a-selector='value'" in lowered or "data-a-selector=\"value\"" in lowered:
                return FakeLocator(self.page, "quantity")
            if "delete" in lowered or "remove" in lowered or "trash" in lowered or "decrement" in lowered:
                return FakeLocator(self.page, "trash")
            return FakeLocator(self.page, "missing")

    class FakePage:
        def __init__(self) -> None:
            self.url = ""
            self.row_exists = True
            self.pending_removal = False

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            navigations.append(url)
            self.url = url
            if self.pending_removal:
                self.row_exists = False

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            raise AssertionError("cart remove must not wait for networkidle")

        def wait_for_timeout(self, timeout: int) -> None:
            raise AssertionError("cart remove must not use fixed sleeps")

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, "row") if "B0TEST1234" in selector and "data-asin" in selector else FakeLocator(self, "missing")

        def content(self) -> str:
            if self.row_exists:
                return '<div data-asin="B0TEST1234"><span data-a-selector="value">1</span></div>'
            return "<html><body></body></html>"

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

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

    bootstrapper = BrowserSessionBootstrapper(
        _managed_cart_session_store(tmp_path),
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )

    payload = bootstrapper.remove_from_cart("es", "B0TEST1234", portal="business", quantity=1)

    assert clicked_actions == ["trash"]
    assert len(navigations) == 2
    assert payload["status"] == "removed"
    assert payload["quantity_after"] == 0
    assert payload["cart_removal_detected"] is True
    assert payload["detected_marker"] == "reload:row_removed"


def test_remove_from_cart_closes_visible_page_before_context_shutdown(tmp_path: Path) -> None:
    close_events: list[str] = []

    class FakeLocator:
        def __init__(self, page, kind: str) -> None:
            self.page = page
            self.kind = kind
            self.first = self

        def count(self) -> int:
            if self.kind in {"row", "quantity", "trash"}:
                return 1 if self.page.row_exists else 0
            return 0

        def is_visible(self, timeout: int | None = None) -> bool:
            return self.count() > 0

        def inner_text(self, timeout: int | None = None) -> str:
            return "1" if self.kind == "quantity" else "Pilexil Forte Max"

        def get_attribute(self, name: str, timeout: int | None = None) -> str | None:
            return "1" if self.kind == "quantity" and name == "value" else None

        def click(self, timeout: int | None = None) -> None:
            if self.kind == "trash":
                self.page.row_exists = False

        def locator(self, selector: str):
            lowered = selector.casefold()
            if "data-a-selector='value'" in lowered or "data-a-selector=\"value\"" in lowered:
                return FakeLocator(self.page, "quantity")
            if "delete" in lowered or "remove" in lowered or "trash" in lowered or "decrement" in lowered:
                return FakeLocator(self.page, "trash")
            return FakeLocator(self.page, "missing")

    class FakePage:
        def __init__(self) -> None:
            self.url = ""
            self.row_exists = True

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, "row") if "B0TEST1234" in selector and "data-asin" in selector else FakeLocator(self, "missing")

        def content(self) -> str:
            if self.row_exists:
                return '<div data-asin="B0TEST1234"><span data-a-selector="value">1</span></div>'
            return "<html><body></body></html>"

        def close(self, run_before_unload: bool = False) -> None:
            close_events.append("page")

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage()]

        def close(self) -> None:
            close_events.append("context")

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

    bootstrapper = BrowserSessionBootstrapper(
        _managed_cart_session_store(tmp_path),
        profile_root=tmp_path / "profiles",
        playwright_factory=lambda: FakeManager(),
    )

    payload = bootstrapper.remove_from_cart("es", "B0TEST1234", portal="business", quantity=1)

    assert payload["status"] == "removed"
    assert close_events == ["page", "context"]
