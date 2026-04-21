from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except Exception:  # noqa: BLE001
    sync_playwright = None

from .amazon import AmazonHttpClient, is_probably_blocked_html
from .marketplaces import Marketplace, get_marketplace
from .models import BrowserSession


DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
DEFAULT_PORTAL = "retail"
SUPPORTED_PORTALS = {"retail", "business"}


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
    ) -> dict:
        session_key = make_session_key(marketplace, portal)
        resolved_executable = _resolve_browser_executable(browser_executable)
        market = get_marketplace(marketplace)
        target_url = url or _default_login_url(market, portal)
        profile_dir = self.profile_root / session_key.replace(":", "__")
        profile_dir.mkdir(parents=True, exist_ok=True)

        session, final_url = self._capture_managed_session(
            market,
            resolved_executable,
            profile_dir,
            portal=portal,
            session_key=session_key,
            headless=headless,
            target_url=target_url,
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
    ) -> tuple[BrowserSession, str]:
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
                self.login_confirmation(target_url)

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
                context.close()

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
                context.close()

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
                browser.close()

    def _dismiss_cookie_banner(self, page) -> None:
        if not hasattr(page, "locator"):
            return
        for selector in ("#sp-cc-accept", "#sp-cc-rejectall-link"):
            try:
                locator = page.locator(selector)
                if locator.count():
                    locator.first.click(timeout=2_000)
                    if hasattr(page, "wait_for_load_state"):
                        try:
                            page.wait_for_load_state("networkidle", timeout=5_000)
                        except Exception:  # noqa: BLE001
                            pass
                    if hasattr(page, "wait_for_timeout"):
                        try:
                            page.wait_for_timeout(1_000)
                        except Exception:  # noqa: BLE001
                            pass
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
