from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .identifiers import normalize_product_url
from .parsing import parse_cart


class BrowserSessionError(RuntimeError):
    pass


def default_session_root() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "Tools" / "skroutz-intent-cli" / "sessions" / "cy"
    return Path.home() / ".cache" / "skroutz-intent-cli" / "sessions" / "cy"


class BrowserSessionStore:
    def __init__(self, root: Path | None = None):
        self.root = root or default_session_root()

    def profile_dir(self) -> Path:
        return self.root / "browser-profile"


class PlaywrightBrowserFactory:
    def open_context(self, user_data_dir: Path):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - exercised by live use only.
            raise BrowserSessionError("Playwright is required for Skroutz session/cart workflows.") from exc

        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(str(user_data_dir), headless=False)
        context._agent_toolbelt_playwright = playwright
        return context


class BrowserSessionBootstrapper:
    def __init__(self, *, store: BrowserSessionStore | None = None, browser_factory: Any | None = None):
        self.store = store or BrowserSessionStore()
        self.browser_factory = browser_factory or PlaywrightBrowserFactory()

    def require_session(self) -> None:
        if not self.store.profile_dir().is_dir():
            raise BrowserSessionError("Run `skroutz-cli session login` first to create a managed local Skroutz session.")

    def _open_context(self):
        self.require_session()
        return self.browser_factory.open_context(self.store.profile_dir())

    def login(self, *, login_timeout_sec: int = 300, manual_confirm: bool = False, url: str | None = None) -> dict[str, Any]:
        self.store.profile_dir().mkdir(parents=True, exist_ok=True)
        context = self.browser_factory.open_context(self.store.profile_dir())
        page = context.new_page()
        page.goto(url or "https://www.skroutz.cy/", wait_until="domcontentloaded", timeout=login_timeout_sec * 1000)
        return {
            "command": "session.login",
            "status": "ready",
            "session_key": "cy",
            "profile_dir": str(self.store.profile_dir()),
            "manual_confirm": manual_confirm,
            "safety": {"cart_mutations_require_confirmation": True, "checkout_allowed": False},
        }

    def list_cart(self) -> dict[str, Any]:
        context = self._open_context()
        page = context.new_page()
        url = "https://www.skroutz.cy/cart"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        payload = parse_cart(page.content(), url=url)
        payload.update(
            {
                "session_key": "cy",
                "action_timing_ms": {},
                "wait_strategy": "domcontentloaded",
                "safety": {"read_only": True, "checkout_allowed": False, "clicked_selectors": []},
            }
        )
        try:
            context.close()
        except Exception:
            pass
        return payload

    def add_to_cart(self, product_id: str, *, quantity: int) -> dict[str, Any]:
        context = self._open_context()
        page = context.new_page()
        page.goto(normalize_product_url(product_id), wait_until="domcontentloaded", timeout=30000)
        clicked_selector = "button[type='submit'][name*='cart'], button:has-text('Add'), button:has-text('Καλάθι')"
        page.locator(clicked_selector).first().click(timeout=10000)
        try:
            context.close()
        except Exception:
            pass
        return {
            "command": "cart.add",
            "status": "ok",
            "product_id": product_id,
            "quantity": quantity,
            "session_key": "cy",
            "warnings": [],
            "safety": {
                "checkout_allowed": False,
                "clicked_selectors": [clicked_selector],
                "forbidden_selectors": ["checkout", "buy", "payment"],
            },
        }

    def remove_from_cart(self, product_id: str, *, quantity: int) -> dict[str, Any]:
        context = self._open_context()
        page = context.new_page()
        page.goto("https://www.skroutz.cy/cart", wait_until="domcontentloaded", timeout=30000)
        clicked_selector = f"[data-sku-id='{product_id}'] button[name*='remove'], [data-product-id='{product_id}'] button[name*='remove']"
        page.locator(clicked_selector).first().click(timeout=10000)
        try:
            context.close()
        except Exception:
            pass
        return {
            "command": "cart.remove",
            "status": "ok",
            "product_id": product_id,
            "quantity": quantity,
            "session_key": "cy",
            "warnings": [],
            "safety": {
                "checkout_allowed": False,
                "clicked_selectors": [clicked_selector],
                "forbidden_selectors": ["checkout", "buy", "payment"],
            },
        }
