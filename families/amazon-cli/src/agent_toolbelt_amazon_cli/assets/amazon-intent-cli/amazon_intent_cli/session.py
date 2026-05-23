from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

try:
    from playwright.sync_api import sync_playwright
except Exception:  # noqa: BLE001
    sync_playwright = None

from .amazon import AmazonHttpClient, is_probably_blocked_html, is_probably_sign_in_html
from .marketplaces import Marketplace, get_marketplace
from .models import BrowserSession
from .offers import build_offer_url, parse_offer_html


DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
DEFAULT_PORTAL = "retail"
SUPPORTED_PORTALS = {"retail", "business"}
CART_CONFIRMATION_MARKERS = (
    "added to basket",
    "added to cart",
    "in den einkaufswagen",
    "añadido a la cesta",
    "anadido a la cesta",
    "ajoute au panier",
    "aggiunto al carrello",
    "toegevoegd aan winkelwagen",
    "dodano do koszyka",
    "lagts till i kundvagnen",
)
CART_REMOVAL_MARKERS = (
    "removed from basket",
    "removed from cart",
    "eliminado de la cesta",
    "eliminado del carrito",
    "retirado de la cesta",
    "supprime du panier",
    "entfernt",
    "rimosso dal carrello",
    "verwijderd uit winkelwagen",
    "usunieto z koszyka",
    "borttagen fran kundvagnen",
)
QUANTITY_SELECTORS = (
    "[data-a-selector='value']",
    '[data-a-selector="value"]',
    "input[name='quantity']",
    "select[name='quantity']",
    ".a-dropdown-prompt",
)
CART_DECREMENT_SELECTORS = (
    "[data-a-selector='decrement'] button",
    '[data-a-selector="decrement"] button',
    "[data-a-selector='decrement']",
    '[data-a-selector="decrement"]',
    "[data-action*='quantity-decrease'] button",
    "[data-action*='quantity-decrease']",
    "button[aria-label*='Decrease']",
    "button[aria-label*='Reducir']",
    "button[aria-label*='Disminuir']",
    "button[aria-label*='minus']",
)
CART_REMOVE_SELECTORS = (
    "[data-action*='delete'] button",
    "[data-action*='delete']",
    "[data-action*='remove'] button",
    "[data-action*='remove']",
    "button[aria-label*='Delete']",
    "button[aria-label*='Remove']",
    "button[aria-label*='Eliminar']",
    "button[aria-label*='trash']",
    "input[name*='delete']",
    "input[value*='Delete']",
    "input[value*='Eliminar']",
)
LOGIN_ACCOUNT_SELECTORS = (
    "#nav-link-accountList",
    "#nav-link-yourAccount",
)
LOGIN_WELCOME_WORDS = (
    "hello",
    "hola",
    "hallo",
    "bonjour",
    "ciao",
    "olá",
    "ola",
    "hej",
    "witaj",
    "welkom",
)
SIGNED_OUT_ACCOUNT_MARKERS = (
    "sign in",
    "signin",
    "log in",
    "iniciar sesion",
    "inicia sesion",
    "identifiez vous",
    "se connecter",
    "anmelden",
    "einloggen",
    "accedi",
    "inloggen",
    "zaloguj",
)
ACCOUNT_OWNER_MARKERS = (
    "account for",
    "cuenta para",
    "compte de",
    "konto fur",
    "konto fuer",
    "konto for",
)


class BrowserSessionError(RuntimeError):
    """Raised when browser-backed session bootstrap fails."""


def make_session_key(marketplace: str, portal: str = DEFAULT_PORTAL) -> str:
    normalized_marketplace = marketplace.strip().lower()
    normalized_portal = portal.strip().lower()
    if normalized_portal not in SUPPORTED_PORTALS:
        supported = ", ".join(sorted(SUPPORTED_PORTALS))
        raise ValueError(f"Unsupported portal `{portal}`. Supported portals: {supported}.")
    return f"{normalized_marketplace}:{normalized_portal}"


def _session_key_filename(session_key: str) -> str:
    return session_key.replace(":", "__") + ".json"


def _local_app_data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "amazon-intent-cli"


def _resolve_browser_executable(browser_executable: str | None) -> str:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
    candidates = [
        browser_executable,
        os.environ.get("AMAZON_CLI_BROWSER"),
        local_app_data / "imput" / "Helium" / "Application" / "chrome.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise BrowserSessionError(
        "No browser executable found. Pass --browser-executable or set AMAZON_CLI_BROWSER."
    )


def _default_user_agent() -> str:
    return DEFAULT_BROWSER_USER_AGENT


def _default_login_url(marketplace: Marketplace, portal: str) -> str:
    return f"https://{marketplace.domain}/"


def _monotonic_ms(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


def _normalize_ascii_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(ascii_only.casefold().split())


class BrowserSessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or (_local_app_data_dir() / "browser-sessions"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, marketplace: str, portal: str = DEFAULT_PORTAL) -> Path:
        return self.root / _session_key_filename(make_session_key(marketplace, portal))

    def _legacy_path(self, marketplace: str) -> Path:
        return self.root / f"{marketplace}.json"

    def save(self, session: BrowserSession) -> None:
        portal = session.portal or DEFAULT_PORTAL
        session.session_key = session.session_key or make_session_key(session.marketplace, portal)
        self._path(session.marketplace, portal).write_text(
            json.dumps(session.to_dict(), indent=2),
            encoding="utf-8",
        )

    def load(self, marketplace: str, portal: str = DEFAULT_PORTAL) -> BrowserSession | None:
        path = self._path(marketplace, portal)
        if not path.exists():
            path = self._legacy_path(marketplace)
        if not path.exists():
            return None
        session = BrowserSession.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if session.portal != portal or not session.session_key:
            session.portal = portal
            session.session_key = make_session_key(marketplace, portal)
        return session


class BrowserSessionBootstrapper:
    def __init__(
        self,
        store: BrowserSessionStore | None = None,
        *,
        profile_root: Path | None = None,
        playwright_factory=None,
        login_confirmation=None,
    ) -> None:
        self.store = store or BrowserSessionStore()
        self.profile_root = Path(profile_root or (_local_app_data_dir() / "browser-profiles"))
        self.profile_root.mkdir(parents=True, exist_ok=True)
        self.playwright_factory = playwright_factory or self._default_playwright_factory
        self.login_confirmation = login_confirmation or self._default_login_confirmation

    def _default_playwright_factory(self):
        if sync_playwright is None:
            raise BrowserSessionError(
                "Playwright is not installed. Install the `playwright` package to enable browser session bootstrap."
            )
        return sync_playwright()

    def _default_login_confirmation(self, target_url: str) -> None:
        try:
            input(f"Complete Amazon login in the opened browser for {target_url}, then press Enter to continue...")
        except EOFError as exc:
            raise BrowserSessionError(
                "Interactive session login requires an interactive terminal. "
                "Run `amazon-cli session login --marketplace <code> --portal <retail|business>` "
                "from PowerShell or another terminal where you can press Enter after logging in."
            ) from exc

    def login(
        self,
        marketplace: str,
        browser_executable: str | None,
        *,
        portal: str = DEFAULT_PORTAL,
        headless: bool = False,
        url: str | None = None,
        login_timeout_sec: int = 300,
        manual_confirm: bool = False,
    ) -> dict:
        session_key = make_session_key(marketplace, portal)
        resolved_executable = _resolve_browser_executable(browser_executable)
        market = get_marketplace(marketplace)
        target_url = url or _default_login_url(market, portal)
        profile_dir = self.profile_root / session_key.replace(":", "__")
        profile_dir.mkdir(parents=True, exist_ok=True)

        session, final_url, detected_marker, wait_strategy = self._capture_managed_session(
            market,
            resolved_executable,
            profile_dir,
            portal=portal,
            session_key=session_key,
            headless=headless,
            target_url=target_url,
            login_timeout_sec=login_timeout_sec,
            manual_confirm=manual_confirm,
        )

        self.store.save(session)
        usable = self._validate_session(market, session, target_url)
        return {
            "command": "session.bootstrap",
            "marketplace": market.code,
            "portal": portal,
            "session_key": session_key,
            "browser_executable": resolved_executable,
            "headless": headless,
            "url": target_url,
            "session_saved": True,
            "usable": usable,
            "final_url": final_url,
            "profile_dir": str(profile_dir),
            "session_source": "managed_profile",
            "login_timeout_sec": login_timeout_sec,
            "manual_confirm": manual_confirm,
            "wait_strategy": wait_strategy,
            "detected_marker": detected_marker,
        }

    def bootstrap(
        self,
        marketplace: str,
        browser_executable: str | None,
        *,
        headless: bool = False,
        url: str | None = None,
        capture_html: bool = False,
        user_data_dir: str | None = None,
        profile_directory: str | None = None,
        isolated: bool = False,
        portal: str = DEFAULT_PORTAL,
        login_timeout_sec: int = 300,
        manual_confirm: bool = False,
    ) -> dict:
        if capture_html:
            payload = self.capture_page(
                marketplace,
                url or f"https://{get_marketplace(marketplace).domain}/",
                portal=portal,
                browser_executable=browser_executable,
                headless=headless,
            )
            payload.update(
                {
                    "command": "session.bootstrap",
                    "marketplace": get_marketplace(marketplace).code,
                    "portal": portal,
                    "session_saved": False,
                    "usable": bool(payload.get("page_html")),
                }
            )
            return payload

        return self.login(
            marketplace,
            browser_executable,
            portal=portal,
            headless=headless,
            url=url,
            login_timeout_sec=login_timeout_sec,
            manual_confirm=manual_confirm,
        )

    def capture_page(
        self,
        marketplace: str,
        url: str,
        *,
        portal: str = DEFAULT_PORTAL,
        browser_executable: str | None = None,
        headless: bool = True,
    ) -> dict:
        session_key = make_session_key(marketplace, portal)
        resolved_executable = _resolve_browser_executable(browser_executable)
        market = get_marketplace(marketplace)
        session = self.store.load(market.code, portal=portal)
        page_html, final_url = self._capture_html_with_session(
            market,
            session,
            target_url=url,
            browser_executable=resolved_executable,
            headless=headless,
        )
        return {
            "marketplace": market.code,
            "portal": portal,
            "session_key": session_key,
            "browser_executable": resolved_executable,
            "headless": headless,
            "url": url,
            "final_url": final_url,
            "page_html": page_html,
            "session_source": session.session_source if session is not None else "anonymous",
        }

    def add_to_cart(
        self,
        marketplace: str,
        asin: str,
        *,
        portal: str = DEFAULT_PORTAL,
        quantity: int = 1,
    ) -> dict:
        if quantity < 1 or quantity > 99:
            raise ValueError("--quantity must be between 1 and 99")

        session_key = make_session_key(marketplace, portal)
        market = get_marketplace(marketplace)
        session = self.store.load(market.code, portal=portal)
        if session is None or session.session_source != "managed_profile":
            raise BrowserSessionError(
                f"Managed {portal} session is missing. "
                f"Run `amazon-cli session login --marketplace {market.code} --portal {portal}`."
            )

        resolved_executable = _resolve_browser_executable(session.browser_executable)
        profile_dir = Path(session.profile_dir or (self.profile_root / session_key.replace(":", "__")))
        profile_dir.mkdir(parents=True, exist_ok=True)
        url = build_offer_url(asin, market.code)
        return self._add_to_cart_with_managed_profile(
            market,
            session,
            target_url=url,
            browser_executable=resolved_executable,
            profile_dir=profile_dir,
            portal=portal,
            session_key=session_key,
            quantity=quantity,
        )

    def remove_from_cart(
        self,
        marketplace: str,
        asin: str,
        *,
        portal: str = DEFAULT_PORTAL,
        quantity: int = 1,
    ) -> dict:
        if quantity < 1 or quantity > 99:
            raise ValueError("--quantity must be between 1 and 99")

        session_key = make_session_key(marketplace, portal)
        market = get_marketplace(marketplace)
        session = self.store.load(market.code, portal=portal)
        if session is None or session.session_source != "managed_profile":
            raise BrowserSessionError(
                f"Managed {portal} session is missing. "
                f"Run `amazon-cli session login --marketplace {market.code} --portal {portal}`."
            )

        resolved_executable = _resolve_browser_executable(session.browser_executable)
        profile_dir = Path(session.profile_dir or (self.profile_root / session_key.replace(":", "__")))
        profile_dir.mkdir(parents=True, exist_ok=True)
        url = f"https://{market.domain}/cart"
        return self._remove_from_cart_with_managed_profile(
            market,
            session,
            target_url=url,
            browser_executable=resolved_executable,
            profile_dir=profile_dir,
            portal=portal,
            session_key=session_key,
            asin=asin,
            quantity=quantity,
        )

    def list_cart(
        self,
        marketplace: str,
        *,
        portal: str = DEFAULT_PORTAL,
    ) -> dict:
        session_key = make_session_key(marketplace, portal)
        market = get_marketplace(marketplace)
        session = self.store.load(market.code, portal=portal)
        if session is None or session.session_source != "managed_profile":
            raise BrowserSessionError(
                f"Managed {portal} session is missing. "
                f"Run `amazon-cli session login --marketplace {market.code} --portal {portal}`."
            )

        resolved_executable = _resolve_browser_executable(session.browser_executable)
        profile_dir = Path(session.profile_dir or (self.profile_root / session_key.replace(":", "__")))
        profile_dir.mkdir(parents=True, exist_ok=True)
        url = f"https://{market.domain}/-/en/gp/cart/view.html"
        return self._list_cart_with_managed_profile(
            market,
            session,
            target_url=url,
            browser_executable=resolved_executable,
            profile_dir=profile_dir,
            portal=portal,
            session_key=session_key,
        )

    def _capture_managed_session(
        self,
        marketplace: Marketplace,
        browser_executable: str,
        profile_dir: Path,
        *,
        portal: str,
        session_key: str,
        headless: bool,
        target_url: str,
        login_timeout_sec: int,
        manual_confirm: bool,
    ) -> tuple[BrowserSession, str, str, str]:
        detected_marker = ""
        wait_strategy = "manual_confirm" if manual_confirm else "targeted_login_detection"
        with self.playwright_factory() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                executable_path=browser_executable,
                headless=headless,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            page = None
            try:
                pages = getattr(context, "pages", [])
                page = pages[0] if pages else context.new_page()
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                except Exception as exc:  # noqa: BLE001
                    raise BrowserSessionError(f"Failed to open {target_url}: {exc}") from exc

                self._dismiss_cookie_banner(page)
                if manual_confirm:
                    self.login_confirmation(target_url)
                    detected_marker = "manual_confirm"
                else:
                    detected_marker = self._wait_for_login_detection(page, timeout_sec=login_timeout_sec)
                    if not detected_marker:
                        raise BrowserSessionError(
                            "login_not_detected: Amazon login did not reach an authenticated header "
                            f"within {login_timeout_sec} seconds. Re-run with --manual-confirm if this "
                            "marketplace uses an unusual login flow."
                        )

                try:
                    user_agent = page.evaluate("() => navigator.userAgent")
                except Exception:  # noqa: BLE001
                    user_agent = _default_user_agent()

                try:
                    final_url = page.url
                except Exception:  # noqa: BLE001
                    final_url = target_url

                cookies = list(context.cookies([target_url, f"https://{marketplace.domain}/"]))
            finally:
                self._close_visible_page_then_context(context, page)

        if not cookies:
            raise BrowserSessionError("No cookies were captured from the managed browser session.")

        return (
            BrowserSession(
                marketplace=marketplace.code,
                browser_executable=browser_executable,
                user_agent=str(user_agent or _default_user_agent()),
                cookies=cookies,
                session_source="managed_profile",
                portal=portal,
                session_key=session_key,
                profile_dir=str(profile_dir),
                final_url=final_url,
            ),
            final_url,
            detected_marker,
            wait_strategy,
        )

    def _capture_isolated_session(
        self,
        marketplace: Marketplace,
        browser_executable: str,
        profile_dir: Path,
        *,
        headless: bool,
        target_url: str,
        capture_html: bool,
    ) -> tuple[BrowserSession, str | None, str]:
        with self.playwright_factory() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                executable_path=browser_executable,
                headless=headless,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            page = None
            try:
                pages = getattr(context, "pages", [])
                page = pages[0] if pages else context.new_page()
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                except Exception as exc:  # noqa: BLE001
                    raise BrowserSessionError(f"Failed to open {target_url}: {exc}") from exc

                if hasattr(page, "wait_for_load_state"):
                    try:
                        page.wait_for_load_state("networkidle", timeout=10_000)
                    except Exception:  # noqa: BLE001
                        pass
                self._dismiss_cookie_banner(page)
                if hasattr(page, "wait_for_timeout"):
                    try:
                        page.wait_for_timeout(8_000)
                    except Exception:  # noqa: BLE001
                        pass

                try:
                    user_agent = page.evaluate("() => navigator.userAgent")
                except Exception:  # noqa: BLE001
                    user_agent = _default_user_agent()

                page_html = None
                if capture_html and hasattr(page, "content"):
                    try:
                        page_html = page.content()
                    except Exception:  # noqa: BLE001
                        page_html = None

                try:
                    final_url = page.url
                except Exception:  # noqa: BLE001
                    final_url = target_url

                cookies = list(context.cookies([target_url, f"https://{marketplace.domain}/"]))
            finally:
                self._close_visible_page_then_context(context, page)

        if not cookies:
            raise BrowserSessionError("No cookies were captured from the browser session.")

        return (
            BrowserSession(
                marketplace=marketplace.code,
                browser_executable=browser_executable,
                user_agent=str(user_agent or _default_user_agent()),
                cookies=cookies,
                session_source="isolated",
            ),
            page_html,
            final_url,
        )

    def _capture_html_with_session(
        self,
        marketplace: Marketplace,
        session: BrowserSession | None,
        *,
        target_url: str,
        browser_executable: str,
        headless: bool,
    ) -> tuple[str | None, str]:
        with self.playwright_factory() as playwright:
            browser = playwright.chromium.launch(
                executable_path=browser_executable,
                headless=headless,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            page = None
            try:
                context = browser.new_context(
                    user_agent=session.user_agent if session is not None else _default_user_agent()
                )
                if session is not None:
                    context.add_cookies(session.cookies)
                page = context.new_page()
                page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:  # noqa: BLE001
                    pass
                self._dismiss_cookie_banner(page)
                try:
                    page.wait_for_timeout(2_000)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    page_html = page.content()
                except Exception:  # noqa: BLE001
                    page_html = None
                try:
                    final_url = page.url
                except Exception:  # noqa: BLE001
                    final_url = target_url
                return page_html, final_url
            except Exception as exc:  # noqa: BLE001
                raise BrowserSessionError(f"Failed to render {target_url} with a browser session: {exc}") from exc
            finally:
                self._close_visible_page_then_context(browser, page)

    def _add_to_cart_with_managed_profile(
        self,
        marketplace: Marketplace,
        session: BrowserSession,
        *,
        target_url: str,
        browser_executable: str,
        profile_dir: Path,
        portal: str,
        session_key: str,
        quantity: int,
    ) -> dict:
        warnings: list[str] = []
        title = ""
        final_url = target_url
        clicked = False
        confirmation = False
        detected_marker: str | None = None
        quantity_select_method = "not_needed"
        started = time.perf_counter()
        phase_timing_ms = {
            "navigate": 0,
            "dismiss_cookie_banner": 0,
            "safety_parse": 0,
            "quantity_select": 0,
            "add_button_wait": 0,
            "add_click": 0,
            "confirmation_wait": 0,
            "browser_close": 0,
        }

        def record_phase(name: str, phase_started: float) -> None:
            phase_timing_ms[name] += _monotonic_ms(phase_started)

        with self.playwright_factory() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                executable_path=browser_executable,
                headless=False,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            page = None
            try:
                if hasattr(context, "add_cookies"):
                    try:
                        context.add_cookies(session.cookies)
                    except Exception:  # noqa: BLE001
                        warnings.append("session_cookie_seed_failed")
                pages = getattr(context, "pages", [])
                page = pages[0] if pages else context.new_page()
                phase_started = time.perf_counter()
                page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                record_phase("navigate", phase_started)
                phase_started = time.perf_counter()
                self._dismiss_cookie_banner(page)
                record_phase("dismiss_cookie_banner", phase_started)

                phase_started = time.perf_counter()
                initial_html = self._page_content(page)
                page_failure = self._cart_page_failure(initial_html, marketplace.code, target_url)
                title = page_failure.get("title", "")
                record_phase("safety_parse", phase_started)
                if page_failure["status"] == "failed":
                    warnings.extend(page_failure["warnings"])
                    return self._cart_receipt(
                        status="failed",
                        asin=page_failure.get("asin", ""),
                        marketplace=marketplace.code,
                        portal=portal,
                        quantity=quantity,
                        title=title,
                        url=target_url,
                        final_url=self._page_url(page, target_url),
                        cart_confirmation_detected=False,
                        warnings=warnings,
                        session_key=session_key,
                        action_timing_ms=_monotonic_ms(started),
                        wait_strategy="targeted",
                        detected_marker=detected_marker,
                        phase_timing_ms=phase_timing_ms,
                        quantity_select_method=quantity_select_method,
                    )

                phase_started = time.perf_counter()
                if quantity > 1:
                    quantity_select_method = self._select_quantity(page, quantity)
                if quantity_select_method == "failed":
                    record_phase("quantity_select", phase_started)
                    warnings.append("quantity_selector_missing")
                    return self._cart_receipt(
                        status="failed",
                        asin=page_failure.get("asin", ""),
                        marketplace=marketplace.code,
                        portal=portal,
                        quantity=quantity,
                        title=title,
                        url=target_url,
                        final_url=self._page_url(page, target_url),
                        cart_confirmation_detected=False,
                        warnings=warnings,
                        session_key=session_key,
                        action_timing_ms=_monotonic_ms(started),
                        wait_strategy="targeted",
                        detected_marker=detected_marker,
                        phase_timing_ms=phase_timing_ms,
                        quantity_select_method=quantity_select_method,
                    )
                record_phase("quantity_select", phase_started)

                phase_started = time.perf_counter()
                add_button = self._visible_locator(page, "#add-to-cart-button")
                if add_button is None:
                    add_button = self._wait_for_locator(page, "#add-to-cart-button", timeout_sec=10)
                record_phase("add_button_wait", phase_started)
                if add_button is None:
                    warnings.append("add_to_cart_button_missing")
                    return self._cart_receipt(
                        status="failed",
                        asin=page_failure.get("asin", ""),
                        marketplace=marketplace.code,
                        portal=portal,
                        quantity=quantity,
                        title=title,
                        url=target_url,
                        final_url=self._page_url(page, target_url),
                        cart_confirmation_detected=False,
                        warnings=warnings,
                        session_key=session_key,
                        action_timing_ms=_monotonic_ms(started),
                        wait_strategy="targeted",
                        detected_marker=detected_marker,
                        phase_timing_ms=phase_timing_ms,
                        quantity_select_method=quantity_select_method,
                    )

                phase_started = time.perf_counter()
                add_button.first.click(timeout=10_000)
                clicked = True
                record_phase("add_click", phase_started)
                phase_started = time.perf_counter()
                detected_marker = self._wait_for_cart_confirmation(page, fallback_url=target_url, timeout_sec=8)
                record_phase("confirmation_wait", phase_started)
                final_url = self._page_url(page, target_url)
                confirmation = detected_marker is not None
            except Exception as exc:  # noqa: BLE001
                warnings.append(str(exc))
                return self._cart_receipt(
                    status="failed",
                    asin=page_failure.get("asin", "") if "page_failure" in locals() else "",
                    marketplace=marketplace.code,
                    portal=portal,
                    quantity=quantity,
                    title=title,
                    url=target_url,
                    final_url=final_url,
                    cart_confirmation_detected=False,
                    warnings=warnings,
                    session_key=session_key,
                    action_timing_ms=_monotonic_ms(started),
                    wait_strategy="targeted",
                    detected_marker=detected_marker,
                    phase_timing_ms=phase_timing_ms,
                    quantity_select_method=quantity_select_method,
                )
            finally:
                phase_started = time.perf_counter()
                self._close_visible_page_then_context(context, page)
                record_phase("browser_close", phase_started)

        return self._cart_receipt(
            status="added" if clicked and confirmation else "add_clicked_unconfirmed",
            asin=page_failure.get("asin", ""),
            marketplace=marketplace.code,
            portal=portal,
            quantity=quantity,
            title=title,
            url=target_url,
            final_url=final_url,
            cart_confirmation_detected=confirmation,
            warnings=warnings,
            session_key=session_key,
            action_timing_ms=_monotonic_ms(started),
            wait_strategy="targeted",
            detected_marker=detected_marker,
            phase_timing_ms=phase_timing_ms,
            quantity_select_method=quantity_select_method,
        )

    def _list_cart_with_managed_profile(
        self,
        marketplace: Marketplace,
        session: BrowserSession,
        *,
        target_url: str,
        browser_executable: str,
        profile_dir: Path,
        portal: str,
        session_key: str,
    ) -> dict:
        warnings: list[str] = []
        items: list[dict] = []
        final_url = target_url
        started = time.perf_counter()

        with self.playwright_factory() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                executable_path=browser_executable,
                headless=False,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            page = None
            try:
                if hasattr(context, "add_cookies"):
                    try:
                        context.add_cookies(session.cookies)
                    except Exception:  # noqa: BLE001
                        warnings.append("session_cookie_seed_failed")
                pages = getattr(context, "pages", [])
                page = pages[0] if pages else context.new_page()
                page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                self._dismiss_cookie_banner(page)

                initial_html = self._page_content(page)
                early_failure = self._cart_remove_page_failure(initial_html)
                if early_failure is not None:
                    warnings.append(early_failure)
                    return self._cart_list_receipt(
                        status="failed",
                        marketplace=marketplace.code,
                        portal=portal,
                        url=target_url,
                        final_url=self._page_url(page, target_url),
                        session_key=session_key,
                        items=[],
                        warnings=warnings,
                        action_timing_ms=_monotonic_ms(started),
                        wait_strategy="targeted",
                    )

                items = self._cart_page_items(page, marketplace)
                final_url = self._page_url(page, target_url)
            except Exception as exc:  # noqa: BLE001
                warnings.append(str(exc))
                return self._cart_list_receipt(
                    status="failed",
                    marketplace=marketplace.code,
                    portal=portal,
                    url=target_url,
                    final_url=final_url,
                    session_key=session_key,
                    items=items,
                    warnings=warnings,
                    action_timing_ms=_monotonic_ms(started),
                    wait_strategy="targeted",
                )
            finally:
                self._close_visible_page_then_context(context, page)

        return self._cart_list_receipt(
            status="ok",
            marketplace=marketplace.code,
            portal=portal,
            url=target_url,
            final_url=final_url,
            session_key=session_key,
            items=items,
            warnings=warnings,
            action_timing_ms=_monotonic_ms(started),
            wait_strategy="targeted",
        )

    def _remove_from_cart_with_managed_profile(
        self,
        marketplace: Marketplace,
        session: BrowserSession,
        *,
        target_url: str,
        browser_executable: str,
        profile_dir: Path,
        portal: str,
        session_key: str,
        asin: str,
        quantity: int,
    ) -> dict:
        warnings: list[str] = []
        title = ""
        final_url = target_url
        quantity_before: int | None = None
        quantity_after: int | None = None
        quantity_removed = 0
        detected_marker: str | None = None
        started = time.perf_counter()

        with self.playwright_factory() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                executable_path=browser_executable,
                headless=False,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            page = None
            try:
                if hasattr(context, "add_cookies"):
                    try:
                        context.add_cookies(session.cookies)
                    except Exception:  # noqa: BLE001
                        warnings.append("session_cookie_seed_failed")
                pages = getattr(context, "pages", [])
                page = pages[0] if pages else context.new_page()
                page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                self._dismiss_cookie_banner(page)

                initial_html = self._page_content(page)
                early_failure = self._cart_remove_page_failure(initial_html)
                if early_failure is not None:
                    warnings.append(early_failure)
                    return self._cart_remove_receipt(
                        status="failed",
                        asin=asin,
                        marketplace=marketplace.code,
                        portal=portal,
                        quantity_requested=quantity,
                        quantity_removed=0,
                        quantity_before=None,
                        quantity_after=None,
                        title=title,
                        url=target_url,
                        final_url=self._page_url(page, target_url),
                        cart_removal_detected=False,
                        warnings=warnings,
                        session_key=session_key,
                        action_timing_ms=_monotonic_ms(started),
                        wait_strategy="targeted",
                        detected_marker=detected_marker,
                    )

                row = self._wait_for_cart_row(page, asin, timeout_sec=8)
                if row is None:
                    warnings.append("cart_item_not_found")
                    return self._cart_remove_receipt(
                        status="failed",
                        asin=asin,
                        marketplace=marketplace.code,
                        portal=portal,
                        quantity_requested=quantity,
                        quantity_removed=0,
                        quantity_before=None,
                        quantity_after=None,
                        title=title,
                        url=target_url,
                        final_url=self._page_url(page, target_url),
                        cart_removal_detected=False,
                        warnings=warnings,
                        session_key=session_key,
                        action_timing_ms=_monotonic_ms(started),
                        wait_strategy="targeted",
                        detected_marker=detected_marker,
                    )

                title = self._cart_row_title(row, asin)
                quantity_before = self._cart_row_quantity(row)
                if quantity_before is None:
                    warnings.append("cart_item_quantity_unknown")
                    return self._cart_remove_receipt(
                        status="failed",
                        asin=asin,
                        marketplace=marketplace.code,
                        portal=portal,
                        quantity_requested=quantity,
                        quantity_removed=0,
                        quantity_before=None,
                        quantity_after=None,
                        title=title,
                        url=target_url,
                        final_url=self._page_url(page, target_url),
                        cart_removal_detected=False,
                        warnings=warnings,
                        session_key=session_key,
                        action_timing_ms=_monotonic_ms(started),
                        wait_strategy="targeted",
                        detected_marker=detected_marker,
                    )

                current_quantity = quantity_before
                while quantity_removed < quantity and current_quantity > 0:
                    removing_last_unit = current_quantity <= 1
                    control = self._cart_row_remove_control(row, removing_last_unit=removing_last_unit)
                    if control is None:
                        warnings.append("cart_remove_control_missing")
                        break

                    control.first.click(timeout=10_000)
                    quantity_removed += 1
                    expected_quantity = current_quantity - 1
                    detected_marker = self._wait_for_cart_quantity_or_removal(
                        page,
                        asin,
                        expected_quantity=expected_quantity,
                        timeout_sec=2,
                    )
                    if not detected_marker:
                        detected_marker = self._reload_cart_and_detect(
                            page,
                            target_url,
                            asin,
                            expected_quantity=expected_quantity,
                        )
                    if not detected_marker:
                        warnings.append("cart_remove_confirmation_missing")
                        break

                    row = self._cart_row_locator(page, asin)
                    current_quantity = (
                        0
                        if expected_quantity <= 0 or row is None
                        else self._cart_row_quantity(row) or expected_quantity
                    )

                quantity_after = current_quantity
                final_url = self._page_url(page, target_url)
            except Exception as exc:  # noqa: BLE001
                warnings.append(str(exc))
                return self._cart_remove_receipt(
                    status="failed",
                    asin=asin,
                    marketplace=marketplace.code,
                    portal=portal,
                    quantity_requested=quantity,
                    quantity_removed=quantity_removed,
                    quantity_before=quantity_before,
                    quantity_after=quantity_after,
                    title=title,
                    url=target_url,
                    final_url=final_url,
                    cart_removal_detected=False,
                    warnings=warnings,
                    session_key=session_key,
                    action_timing_ms=_monotonic_ms(started),
                    wait_strategy="targeted",
                    detected_marker=detected_marker,
                )
            finally:
                self._close_visible_page_then_context(context, page)

        if quantity_removed == 0:
            status = "failed"
        elif quantity_after == 0:
            status = "removed"
        elif quantity_removed < quantity:
            status = "partial"
        else:
            status = "quantity_updated"

        return self._cart_remove_receipt(
            status=status,
            asin=asin,
            marketplace=marketplace.code,
            portal=portal,
            quantity_requested=quantity,
            quantity_removed=quantity_removed,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            title=title,
            url=target_url,
            final_url=final_url,
            cart_removal_detected=quantity_removed > 0 and detected_marker is not None,
            warnings=warnings,
            session_key=session_key,
            action_timing_ms=_monotonic_ms(started),
            wait_strategy="targeted",
            detected_marker=detected_marker,
        )

    def _page_content(self, page) -> str:
        if not hasattr(page, "content"):
            return ""
        try:
            return page.content()
        except Exception:  # noqa: BLE001
            return ""

    def _page_url(self, page, fallback: str) -> str:
        try:
            return str(page.url or fallback)
        except Exception:  # noqa: BLE001
            return fallback

    def _close_visible_page_then_context(self, context, page=None) -> None:
        if page is not None and hasattr(page, "close"):
            try:
                page.close(run_before_unload=False)
            except TypeError:
                page.close()
            except Exception:  # noqa: BLE001
                pass
        context.close()

    def _wait_for_value(self, detector, *, timeout_sec: float, interval_sec: float = 0.2):
        deadline = time.perf_counter() + max(0, timeout_sec)
        while True:
            try:
                value = detector()
            except Exception:  # noqa: BLE001
                value = None
            if value:
                return value
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return None
            time.sleep(min(interval_sec, remaining))

    def _wait_for_locator(self, page, selector: str, *, timeout_sec: float):
        if not hasattr(page, "locator"):
            return None

        def detect():
            return self._visible_locator(page, selector)

        return self._wait_for_value(detect, timeout_sec=timeout_sec)

    def _visible_locator(self, page, selector: str):
        if not hasattr(page, "locator"):
            return None
        try:
            locator = page.locator(selector)
            if locator.count() < 1:
                return None
            target = getattr(locator, "first", locator)
            if hasattr(target, "is_visible") and not target.is_visible(timeout=250):
                return None
            return locator
        except Exception:  # noqa: BLE001
            return None

    def _wait_for_login_detection(self, page, *, timeout_sec: float) -> str | None:
        return self._wait_for_value(lambda: self._login_detected_marker(page), timeout_sec=timeout_sec)

    def _login_detected_marker(self, page) -> str | None:
        html = self._page_content(page)
        normalized = _normalize_ascii_text(html)
        has_account_link = "/gp/css/homepage" in normalized or "/gp/your-account" in normalized

        for selector in LOGIN_ACCOUNT_SELECTORS:
            if self._account_selector_authenticated(html, selector):
                return f"selector:{selector}"
            if hasattr(page, "locator"):
                try:
                    locator = page.locator(selector)
                    if locator.count() > 0 and self._locator_account_authenticated(locator, html):
                        return f"selector:{selector}"
                except Exception:  # noqa: BLE001
                    pass

        if has_account_link and not self._looks_like_sign_in_only(html):
            return "account_link"
        if (
            self._has_welcome_text(html)
            and not self._looks_like_sign_in_only(html)
            and not self._has_signed_out_account_marker(html)
        ):
            return "welcome_text"
        return None

    def _account_selector_authenticated(self, html: str, selector: str) -> bool:
        if not self._html_has_id_selector(html, selector):
            return False
        element_id = re.escape(selector[1:])
        match = re.search(
            rf"<(?P<tag>[a-z0-9]+)[^>]*\bid\s*=\s*['\"]{element_id}['\"][^>]*>.*?</(?P=tag)>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippet = match.group(0) if match else html
        return self._account_text_authenticated(snippet)

    def _locator_account_authenticated(self, locator, html: str) -> bool:
        target = getattr(locator, "first", locator)
        text = ""
        if hasattr(target, "inner_text"):
            try:
                text = target.inner_text(timeout=500)
            except Exception:  # noqa: BLE001
                text = ""
        return self._account_text_authenticated(text or html)

    def _account_text_authenticated(self, text: str) -> bool:
        normalized = _normalize_ascii_text(re.sub(r"<[^>]+>", " ", text))
        if any(marker in normalized for marker in SIGNED_OUT_ACCOUNT_MARKERS):
            return False
        if any(word in normalized for word in LOGIN_WELCOME_WORDS):
            return True
        if any(marker in normalized for marker in ACCOUNT_OWNER_MARKERS):
            return True
        return "/gp/css/homepage" in text.casefold() or "/gp/your-account" in text.casefold()

    def _has_signed_out_account_marker(self, html: str) -> bool:
        normalized = _normalize_ascii_text(re.sub(r"<[^>]+>", " ", html))
        return any(marker in normalized for marker in SIGNED_OUT_ACCOUNT_MARKERS)

    def _html_has_id_selector(self, html: str, selector: str) -> bool:
        if not selector.startswith("#"):
            return False
        element_id = re.escape(selector[1:])
        return bool(re.search(rf"\bid\s*=\s*['\"]{element_id}['\"]", html, flags=re.IGNORECASE))

    def _has_welcome_text(self, html: str) -> bool:
        text = _normalize_ascii_text(re.sub(r"<[^>]+>", " ", html))
        return any(re.search(rf"\b{re.escape(word)}\b", text) for word in LOGIN_WELCOME_WORDS)

    def _looks_like_sign_in_only(self, html: str) -> bool:
        if not is_probably_sign_in_html(html):
            return False
        normalized = _normalize_ascii_text(html)
        return not any(word in normalized for word in LOGIN_WELCOME_WORDS)

    def _cart_page_failure(self, html: str, marketplace: str, target_url: str) -> dict:
        asin = target_url.rstrip("/").split("/dp/")[-1].split("?")[0] if "/dp/" in target_url else ""
        if is_probably_blocked_html(html):
            return {"status": "failed", "warnings": ["blocked"], "title": "", "asin": asin}
        if is_probably_sign_in_html(html):
            return {"status": "failed", "warnings": ["sign_in_required"], "title": "", "asin": asin}
        offer = parse_offer_html(html, marketplace=marketplace, asin=asin, url=target_url)
        warnings: list[str] = []
        if offer.deliverable is False:
            warnings.append("not_deliverable")
        if offer.status != "ok":
            warnings.append(f"offer_status_{offer.status}")
        if warnings:
            return {"status": "failed", "warnings": warnings, "title": offer.title, "asin": asin}
        return {"status": "ok", "warnings": [], "title": offer.title, "asin": asin}

    def _cart_remove_page_failure(self, html: str) -> str | None:
        if is_probably_blocked_html(html):
            return "blocked"
        if is_probably_sign_in_html(html):
            return "sign_in_required"
        return None

    def _cart_page_items(self, page, marketplace: Marketplace) -> list[dict]:
        items: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for row in self._cart_visible_rows(page):
            item = self._cart_row_item(row, marketplace)
            if not item["asin"] and not item["title"] and not item["row_text_excerpt"]:
                continue
            key = (
                item["asin"] or "",
                item["product_url"] or "",
                item["row_text_excerpt"][:160],
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
        return items

    def _cart_visible_rows(self, page) -> list:
        if not hasattr(page, "locator"):
            return []
        selectors = (
            "[data-asin], [data-itemid], [data-item-id], .sc-list-item, .sc-product",
            "[data-asin]",
            "[data-itemid]",
            "[data-item-id]",
            ".sc-list-item",
            ".sc-product",
        )
        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception:  # noqa: BLE001
                continue
            if count < 1:
                continue
            rows = []
            for index in range(min(count, 200)):
                try:
                    row = locator.nth(index) if hasattr(locator, "nth") else getattr(locator, "first", locator)
                except Exception:  # noqa: BLE001
                    continue
                rows.append(row)
                if not hasattr(locator, "nth"):
                    break
            return rows
        return []

    def _cart_row_item(self, row, marketplace: Marketplace) -> dict:
        row_text = self._cart_row_text_excerpt(row)
        product_url = self._cart_row_product_url(row, marketplace)
        asin = self._cart_row_asin(row, product_url, row_text)
        title = self._cart_row_product_title(row, asin, row_text)
        return {
            "asin": asin,
            "title": title,
            "quantity": self._cart_row_quantity(row),
            "price_text": self._cart_row_first_text(
                row,
                (
                    ".sc-product-price",
                    "[data-a-color='price']",
                    '[data-a-color="price"]',
                    ".a-price",
                    ".sc-price",
                    "[class*='price']",
                ),
            ),
            "seller": self._cart_row_first_text(
                row,
                (
                    "[class*='seller']",
                    "[data-feature-id*='seller']",
                    "[data-a-word-break*='seller']",
                ),
            ),
            "availability": self._cart_row_first_text(
                row,
                (
                    "[class*='availability']",
                    "[id*='availability']",
                    "[data-feature-id*='availability']",
                    "[class*='avail']",
                ),
            ),
            "image_url": self._cart_row_first_attribute(row, ("img[src]", "img"), "src"),
            "product_url": product_url,
            "row_text_excerpt": row_text,
        }

    def _cart_row_text_excerpt(self, row, *, max_chars: int = 500) -> str:
        try:
            text = row.inner_text(timeout=500)
        except Exception:  # noqa: BLE001
            return ""
        lines = [" ".join(line.split()) for line in str(text).splitlines()]
        excerpt = "\n".join(line for line in lines if line)
        return excerpt[:max_chars]

    def _cart_row_asin(self, row, product_url: str, row_text: str) -> str:
        for attribute in ("data-asin", "data-itemid", "data-item-id"):
            try:
                value = row.get_attribute(attribute, timeout=500)
            except Exception:  # noqa: BLE001
                value = None
            normalized = self._normalize_asin(value)
            if normalized:
                return normalized
        for value in (product_url, row_text):
            normalized = self._extract_asin_from_text(value)
            if normalized:
                return normalized
        return ""

    def _normalize_asin(self, value: str | None) -> str:
        value = str(value or "").strip().upper()
        return value if re.fullmatch(r"[A-Z0-9]{10}", value) else ""

    def _extract_asin_from_text(self, value: str) -> str:
        text = str(value or "")
        for pattern in (
            r"(?i)/(?:dp|gp/product|product|gp/aw/d)/([A-Z0-9]{10})(?:[/?#]|$)",
            r"\b([A-Z0-9]{10})\b",
        ):
            match = re.search(pattern, text)
            if match:
                normalized = self._normalize_asin(match.group(1))
                if normalized:
                    return normalized
        return ""

    def _cart_row_product_url(self, row, marketplace: Marketplace) -> str:
        href = self._cart_row_first_attribute(
            row,
            (
                "a[href*='/dp/']",
                "a[href*='/gp/product/']",
                "a[href*='/product/']",
                "a[href*='/gp/aw/d/']",
                "a[href*='ref=ox_sc_act_title']",
                "a[href]",
            ),
            "href",
        )
        if not href:
            return ""
        return urljoin(f"https://{marketplace.domain}/", href)

    def _cart_row_product_title(self, row, asin: str, row_text: str) -> str:
        selectors = []
        if asin:
            selectors.extend(
                [
                    f"a[href*='{asin}']",
                    f"a[href*='/dp/{asin}']",
                    f"a[href*='/gp/product/{asin}']",
                ]
            )
        selectors.extend(
            [
                "a[href*='/dp/']",
                "a[href*='/gp/product/']",
                "a[href*='ref=ox_sc_act_title']",
            ]
        )
        title = self._cart_row_first_text(row, tuple(selectors))
        if title:
            return title
        return row_text.splitlines()[0] if row_text else ""

    def _cart_row_first_text(self, row, selectors: tuple[str, ...]) -> str:
        for selector in selectors:
            try:
                locator = row.locator(selector)
                if locator.count() < 1:
                    continue
                target = getattr(locator, "first", locator)
                text = target.inner_text(timeout=500).strip()
                if text:
                    return " ".join(text.split())
            except Exception:  # noqa: BLE001
                continue
        return ""

    def _cart_row_first_attribute(self, row, selectors: tuple[str, ...], attribute: str) -> str:
        for selector in selectors:
            try:
                locator = row.locator(selector)
                if locator.count() < 1:
                    continue
                target = getattr(locator, "first", locator)
                value = target.get_attribute(attribute, timeout=500)
                if value:
                    return str(value).strip()
            except Exception:  # noqa: BLE001
                continue
        return ""

    def _wait_for_cart_row(self, page, asin: str, *, timeout_sec: float):
        return self._wait_for_value(lambda: self._cart_row_locator(page, asin), timeout_sec=timeout_sec)

    def _cart_row_locator(self, page, asin: str):
        if not hasattr(page, "locator"):
            return None
        selectors = (
            f"[data-asin='{asin}']",
            f'[data-asin="{asin}"]',
            f"[data-itemid='{asin}']",
            f'[data-itemid="{asin}"]',
            f"[data-item-id='{asin}']",
            f'[data-item-id="{asin}"]',
        )
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    return getattr(locator, "first", locator)
            except Exception:  # noqa: BLE001
                continue

        link_selectors = (
            f"a[href*='/dp/{asin}']",
            f"a[href*='/gp/product/{asin}']",
            f"a[href*='{asin}']",
        )
        for selector in link_selectors:
            try:
                link = page.locator(selector)
                if link.count() < 1:
                    continue
                row = link.first.locator(
                    "xpath=ancestor::*[@data-asin or contains(@class, 'sc-list-item') or contains(@class, 'sc-product')][1]"
                )
                if row.count() > 0:
                    return getattr(row, "first", row)
            except Exception:  # noqa: BLE001
                continue
        return None

    def _cart_row_title(self, row, asin: str) -> str:
        try:
            title_link = row.locator(f"a[href*='{asin}']")
            if title_link.count() > 0:
                text = title_link.first.inner_text(timeout=500).strip()
                if text:
                    return text
        except Exception:  # noqa: BLE001
            pass
        try:
            return row.inner_text(timeout=500).strip().splitlines()[0]
        except Exception:  # noqa: BLE001
            return ""

    def _cart_row_quantity(self, row) -> int | None:
        if row is None:
            return None
        for selector in QUANTITY_SELECTORS:
            try:
                locator = row.locator(selector)
                if locator.count() < 1:
                    continue
                target = getattr(locator, "first", locator)
                for attribute in ("value", "aria-valuenow", "data-quantity"):
                    try:
                        value = target.get_attribute(attribute, timeout=500)
                    except Exception:  # noqa: BLE001
                        value = None
                    quantity = self._parse_cart_quantity(value or "")
                    if quantity is not None:
                        return quantity
                try:
                    text = target.inner_text(timeout=500)
                except Exception:  # noqa: BLE001
                    text = ""
                quantity = self._parse_cart_quantity(text)
                if quantity is not None:
                    return quantity
            except Exception:  # noqa: BLE001
                continue
        try:
            return self._parse_cart_quantity(row.inner_text(timeout=500))
        except Exception:  # noqa: BLE001
            return None

    def _parse_cart_quantity(self, value: str) -> int | None:
        match = re.search(r"\b([1-9][0-9]?)\b", str(value))
        if not match:
            return None
        return int(match.group(1))

    def _cart_row_remove_control(self, row, *, removing_last_unit: bool):
        selector_groups = (
            (CART_DECREMENT_SELECTORS + CART_REMOVE_SELECTORS)
            if removing_last_unit
            else CART_DECREMENT_SELECTORS
        )
        for selector in selector_groups:
            try:
                locator = row.locator(selector)
                if locator.count() < 1:
                    continue
                target = getattr(locator, "first", locator)
                if hasattr(target, "is_visible") and not target.is_visible(timeout=250):
                    continue
                return locator
            except Exception:  # noqa: BLE001
                continue
        return None

    def _wait_for_cart_quantity_or_removal(
        self,
        page,
        asin: str,
        *,
        expected_quantity: int,
        timeout_sec: float,
    ) -> str | None:
        def detect() -> str | None:
            row = self._cart_row_locator(page, asin)
            if expected_quantity <= 0:
                if row is None:
                    return "row_removed"
                marker = self._cart_removal_marker(self._page_content(page))
                if marker:
                    return marker
                return None
            if row is None:
                return None
            quantity = self._cart_row_quantity(row)
            if quantity == expected_quantity:
                return f"quantity:{expected_quantity}"
            return None

        return self._wait_for_value(detect, timeout_sec=timeout_sec)

    def _reload_cart_and_detect(self, page, target_url: str, asin: str, *, expected_quantity: int) -> str | None:
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=20_000)
        except Exception:  # noqa: BLE001
            return None
        row = self._cart_row_locator(page, asin)
        if expected_quantity <= 0:
            if row is None:
                return "reload:row_removed"
            marker = self._cart_removal_marker(self._page_content(page))
            if marker:
                return marker
            return None
        if row is None:
            return None
        quantity = self._cart_row_quantity(row)
        if quantity == expected_quantity:
            return f"reload:quantity:{expected_quantity}"
        return None

    def _cart_removal_marker(self, html: str) -> str | None:
        normalized = _normalize_ascii_text(html)
        for marker in CART_REMOVAL_MARKERS:
            if marker in normalized:
                return f"text:{marker.replace(' ', '_')}"
        return None

    def _select_quantity(self, page, quantity: int) -> str:
        if quantity <= 1:
            return "not_needed"
        if 2 <= quantity <= 9 and self._select_quantity_with_aui_dropdown(page, quantity):
            return "aui_dropdown"
        if self._select_quantity_with_native_select(page, quantity):
            return "native_select"
        return "failed"

    def _select_quantity_with_aui_dropdown(self, page, quantity: int) -> bool:
        container = self._visible_locator(page, 'span[id$="predefinedQuantitiesDropdownContainer"]')
        if container is None:
            return False
        button = self._first_visible_child_locator(
            container,
            (
                "span.a-button-dropdown",
                "[data-action='a-dropdown-button']",
                ".a-dropdown-container .a-button",
            ),
        )
        if button is None:
            return False
        try:
            button.first.click(timeout=2_000)
        except Exception:  # noqa: BLE001
            return False

        option_selector = (
            'div.a-popover[aria-hidden="false"] '
            f'a.a-dropdown-link[data-value*=\'"stringVal":"{quantity}"\']'
        )
        option = self._wait_for_locator(page, option_selector, timeout_sec=2)
        if option is None:
            option_selector = (
                'div.a-popover[style*="visibility: visible"] '
                f'a.a-dropdown-link[data-value*=\'"stringVal":"{quantity}"\']'
            )
            option = self._wait_for_locator(page, option_selector, timeout_sec=1)
        if option is None:
            return False
        try:
            option.first.click(timeout=2_000)
        except Exception:  # noqa: BLE001
            return False
        return self._quantity_selection_matches(page, container, quantity, timeout_sec=2)

    def _select_quantity_with_native_select(self, page, quantity: int) -> bool:
        for selector in ("select#quantity", "select[id$='predefinedQuantitiesDropdown']"):
            try:
                locator = page.locator(selector)
                if locator.count() < 1:
                    continue
                locator.first.select_option(str(quantity), timeout=5_000)
                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _first_visible_child_locator(self, root, selectors: tuple[str, ...]):
        for selector in selectors:
            try:
                locator = root.locator(selector)
                if locator.count() < 1:
                    continue
                target = getattr(locator, "first", locator)
                if hasattr(target, "is_visible") and not target.is_visible(timeout=250):
                    continue
                return locator
            except Exception:  # noqa: BLE001
                continue
        return None

    def _quantity_selection_matches(self, page, container, quantity: int, *, timeout_sec: float) -> bool:
        expected = str(quantity)

        def detect() -> bool:
            checks = (
                (container, ".a-dropdown-prompt"),
                (container, "select[id$='predefinedQuantitiesDropdown']"),
                (page, "select#quantity"),
                (page, "select[id$='predefinedQuantitiesDropdown']"),
            )
            for root, selector in checks:
                try:
                    locator = root.locator(selector)
                    if locator.count() < 1:
                        continue
                    target = getattr(locator, "first", locator)
                    try:
                        value = target.get_attribute("value", timeout=500)
                    except Exception:  # noqa: BLE001
                        value = None
                    if value is not None and value.strip() == expected:
                        return True
                    try:
                        text = target.inner_text(timeout=500)
                    except Exception:  # noqa: BLE001
                        text = ""
                    if text.strip() == expected:
                        return True
                except Exception:  # noqa: BLE001
                    continue
            return False

        return bool(self._wait_for_value(detect, timeout_sec=timeout_sec, interval_sec=0.1))

    def _wait_for_cart_confirmation(self, page, *, fallback_url: str, timeout_sec: float) -> str | None:
        return self._wait_for_value(
            lambda: self._cart_confirmation_marker(self._page_content(page), self._page_url(page, fallback_url)),
            timeout_sec=timeout_sec,
        )

    def _cart_confirmation_marker(self, html: str, final_url: str) -> str | None:
        final_url_lower = final_url.casefold()
        if "/cart/" in final_url_lower or "smart-wagon" in final_url_lower:
            return "url:cart"
        normalized_ascii = _normalize_ascii_text(html)
        for marker in CART_CONFIRMATION_MARKERS:
            if marker in normalized_ascii:
                return f"text:{marker.replace(' ', '_')}"
        return None

    def _cart_confirmation_detected(self, html: str, final_url: str) -> bool:
        return self._cart_confirmation_marker(html, final_url) is not None

    def _cart_receipt(
        self,
        *,
        status: str,
        asin: str,
        marketplace: str,
        portal: str,
        quantity: int,
        title: str,
        url: str,
        final_url: str,
        cart_confirmation_detected: bool,
        warnings: list[str],
        session_key: str,
        action_timing_ms: int | None = None,
        wait_strategy: str | None = None,
        detected_marker: str | None = None,
        phase_timing_ms: dict[str, int] | None = None,
        quantity_select_method: str = "not_needed",
    ) -> dict:
        return {
            "status": status,
            "asin": asin,
            "marketplace": marketplace,
            "portal": portal,
            "quantity": quantity,
            "title": title,
            "url": url,
            "final_url": final_url,
            "cart_confirmation_detected": cart_confirmation_detected,
            "warnings": warnings,
            "session_key": session_key,
            "session_source": "managed_profile",
            "action_timing_ms": action_timing_ms,
            "wait_strategy": wait_strategy,
            "detected_marker": detected_marker,
            "phase_timing_ms": phase_timing_ms or {},
            "quantity_select_method": quantity_select_method,
            "safety": {
                "checkout_performed": False,
                "buy_now_clicked": False,
            },
        }

    def _cart_list_receipt(
        self,
        *,
        status: str,
        marketplace: str,
        portal: str,
        url: str,
        final_url: str,
        session_key: str,
        items: list[dict],
        warnings: list[str],
        action_timing_ms: int | None = None,
        wait_strategy: str | None = None,
    ) -> dict:
        return {
            "marketplace": marketplace,
            "portal": portal,
            "url": url,
            "final_url": final_url,
            "session_key": session_key,
            "session_source": "managed_profile",
            "status": status,
            "items": items,
            "item_count": len(items),
            "warnings": warnings,
            "action_timing_ms": action_timing_ms,
            "wait_strategy": wait_strategy,
            "safety": {
                "checkout_performed": False,
                "buy_now_clicked": False,
                "cart_mutation_performed": False,
            },
        }

    def _cart_remove_receipt(
        self,
        *,
        status: str,
        asin: str,
        marketplace: str,
        portal: str,
        quantity_requested: int,
        quantity_removed: int,
        quantity_before: int | None,
        quantity_after: int | None,
        title: str,
        url: str,
        final_url: str,
        cart_removal_detected: bool,
        warnings: list[str],
        session_key: str,
        action_timing_ms: int | None = None,
        wait_strategy: str | None = None,
        detected_marker: str | None = None,
    ) -> dict:
        return {
            "status": status,
            "asin": asin,
            "marketplace": marketplace,
            "portal": portal,
            "quantity_requested": quantity_requested,
            "quantity_removed": quantity_removed,
            "quantity_before": quantity_before,
            "quantity_after": quantity_after,
            "title": title,
            "url": url,
            "final_url": final_url,
            "cart_removal_detected": cart_removal_detected,
            "warnings": warnings,
            "session_key": session_key,
            "session_source": "managed_profile",
            "action_timing_ms": action_timing_ms,
            "wait_strategy": wait_strategy,
            "detected_marker": detected_marker,
            "safety": {
                "checkout_performed": False,
                "buy_now_clicked": False,
            },
        }

    def _dismiss_cookie_banner(self, page) -> None:
        if not hasattr(page, "locator"):
            return
        for selector in ("#sp-cc-accept", "#sp-cc-rejectall-link"):
            try:
                locator = page.locator(selector)
                if locator.count():
                    locator.first.click(timeout=2_000)
                    return
            except Exception:  # noqa: BLE001
                continue

    def _validate_session(self, marketplace: Marketplace, session: BrowserSession, target_url: str) -> bool:
        client = AmazonHttpClient(marketplace, session=session)
        try:
            html = client.fetch_url(target_url)
        except Exception:  # noqa: BLE001
            return False
        return not is_probably_blocked_html(html)
