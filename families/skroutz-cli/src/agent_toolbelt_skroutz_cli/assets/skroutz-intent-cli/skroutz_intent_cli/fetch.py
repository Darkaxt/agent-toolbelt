from __future__ import annotations

import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class FetchError(RuntimeError):
    pass


def is_probably_blocked_html(html: str, *, status: int | None = None) -> bool:
    lowered = (html or "").lower()
    return bool(
        status in {403, 429}
        or "just a moment" in lowered
        or "cf-browser-verification" in lowered
        or "cloudflare" in lowered and "challenge" in lowered
    )


@dataclass
class FetchResult:
    url: str
    html: str
    status: int | None
    fetcher: str
    warnings: list[str]


class SkroutzFetcher:
    def __init__(self, *, curl_executable: str | None = None):
        self.curl_executable = curl_executable or shutil.which("curl.exe") or shutil.which("curl")

    def fetch_html(self, url: str, *, timeout_sec: int = 30) -> str:
        return self.fetch(url, timeout_sec=timeout_sec).html

    def fetch(self, url: str, *, timeout_sec: int = 30) -> FetchResult:
        warnings: list[str] = []
        try:
            result = self._fetch_urllib(url, timeout_sec=timeout_sec)
            if not is_probably_blocked_html(result.html, status=result.status):
                return result
            warnings.append("urllib fetch looked blocked; falling back to curl.")
        except Exception as exc:
            warnings.append(f"urllib fetch failed: {exc.__class__.__name__}")

        if not self.curl_executable:
            raise FetchError("Skroutz fetch failed and curl is not available.")

        result = self._fetch_curl(url, timeout_sec=timeout_sec)
        result.warnings[:0] = warnings
        if is_probably_blocked_html(result.html, status=result.status):
            result.warnings.append("Skroutz response appears blocked or challenged.")
        return result

    def _fetch_urllib(self, url: str, *, timeout_sec: int) -> FetchResult:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return FetchResult(url=url, html=raw.decode(charset, errors="replace"), status=response.status, fetcher="urllib", warnings=[])
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return FetchResult(url=url, html=raw.decode("utf-8", errors="replace"), status=exc.code, fetcher="urllib", warnings=[])

    def _fetch_curl(self, url: str, *, timeout_sec: int) -> FetchResult:
        command = [
            self.curl_executable or "curl",
            "-L",
            "-s",
            "-A",
            USER_AGENT,
            "--max-time",
            str(timeout_sec),
            "-w",
            "\n__HTTP_STATUS__:%{http_code}",
            url,
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_sec + 5, encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            raise FetchError((completed.stderr or completed.stdout or "curl failed").strip())
        stdout = completed.stdout
        marker = "\n__HTTP_STATUS__:"
        status = None
        if marker in stdout:
            html, status_text = stdout.rsplit(marker, 1)
            try:
                status = int(status_text.strip())
            except ValueError:
                status = None
        else:
            html = stdout
        return FetchResult(url=url, html=html, status=status, fetcher="curl", warnings=[])
