from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .fetch import FetchResult


class BrowserSessionError(RuntimeError):
    pass


def default_session_root() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "Tools" / "aliexpress-intent-cli" / "sessions" / "default"
    return Path.home() / ".cache" / "aliexpress-intent-cli" / "sessions" / "default"


class BrowserSessionStore:
    def __init__(self, root: Path | None = None):
        self.root = root or default_session_root()

    def profile_dir(self) -> Path:
        return self.root / "browser-profile"

    def metadata_path(self) -> Path:
        return self.root / "session.json"

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path().write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def read_metadata(self) -> dict[str, Any]:
        path = self.metadata_path()
        if not path.is_file():
            return {}
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"metadata_error": "invalid_json"}
        return parsed if isinstance(parsed, dict) else {}


class PlaywrightBrowserFactory:
    def open_context(self, user_data_dir: Path, *, headless: bool = False):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - live dependency only.
            raise BrowserSessionError("Playwright is required for AliExpress managed login.") from exc
        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(str(user_data_dir), headless=headless)
        context._agent_toolbelt_playwright = playwright
        return context


class BrowserSessionBootstrapper:
    def __init__(self, *, store: BrowserSessionStore | None = None, browser_factory: Any | None = None):
        self.store = store or BrowserSessionStore()
        self.browser_factory = browser_factory or PlaywrightBrowserFactory()

    def login(self, *, login_timeout_sec: int = 300, manual_confirm: bool = False, url: str | None = None) -> dict[str, Any]:
        self.store.profile_dir().mkdir(parents=True, exist_ok=True)
        context = self.browser_factory.open_context(self.store.profile_dir(), headless=False)
        page = context.new_page()
        login_url = url or "https://www.aliexpress.com/"
        page.goto(login_url, wait_until="domcontentloaded", timeout=login_timeout_sec * 1000)
        if manual_confirm:
            input("Log in to AliExpress in the opened browser, then press Enter here to save the managed session...")
        metadata = {
            "session_key": "default",
            "profile_dir": str(self.store.profile_dir()),
            "login_url": login_url,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "manual_confirm": manual_confirm,
        }
        self.store.write_metadata(metadata)
        self._close_context(context)
        return {
            "command": "session.login",
            "status": "ready",
            "session_key": "default",
            "profile_dir": str(self.store.profile_dir()),
            "metadata_path": str(self.store.metadata_path()),
            "manual_confirm": manual_confirm,
            "safety": {"cart_operations_supported": False, "checkout_allowed": False},
        }

    def require_session(self) -> None:
        if not self.store.profile_dir().is_dir():
            raise BrowserSessionError("Run `aliexpress-cli session login` first to create a managed local AliExpress session.")

    def fetch(self, url: str, *, timeout_sec: int = 30) -> FetchResult:
        self.require_session()
        context = self.browser_factory.open_context(self.store.profile_dir(), headless=True)
        page = context.new_page()
        warnings: list[str] = []
        status = None
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            status = response.status if response is not None else None
            html = page.content()
        finally:
            self._close_context(context)
        if not html:
            warnings.append("empty_session_page")
        return FetchResult(url=url, html=html, status=status, fetcher="managed_session", warnings=warnings)

    def _close_context(self, context: Any) -> None:
        playwright = getattr(context, "_agent_toolbelt_playwright", None)
        try:
            context.close()
        except Exception:
            pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass

    def status(self) -> dict[str, Any]:
        profile_dir = self.store.profile_dir()
        metadata = self.store.read_metadata()
        return {
            "command": "session.status",
            "session_key": "default",
            "profile_dir": str(profile_dir),
            "metadata_path": str(self.store.metadata_path()),
            "exists": profile_dir.is_dir(),
            "status": "ready" if profile_dir.is_dir() else "missing",
            "metadata": metadata,
            "safety": {"cart_operations_supported": False, "checkout_allowed": False},
        }

    def logout(self) -> dict[str, Any]:
        root = self.store.root
        existed = root.exists()
        if existed:
            shutil.rmtree(root)
        return {
            "command": "session.logout",
            "session_key": "default",
            "removed": existed,
            "profile_dir": str(self.store.profile_dir()),
            "safety": {"cart_operations_supported": False, "checkout_allowed": False},
        }
