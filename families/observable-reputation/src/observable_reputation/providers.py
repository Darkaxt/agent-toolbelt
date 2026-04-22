from __future__ import annotations

import base64
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Protocol

from .observables import Observable


VERDICT_SCORES = {
    "malicious": 100,
    "suspicious": 50,
    "clean": 0,
    "unknown": 0,
    "skipped": 0,
    "error": 0,
}


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    verdict: str
    score: int = 0
    evidence: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HttpTransport(Protocol):
    def get_json(self, url: str, *, headers: dict[str, str] | None = None, params: dict[str, str] | None = None) -> Any:
        ...

    def post_form_json(self, url: str, data: dict[str, str], *, headers: dict[str, str] | None = None) -> Any:
        ...

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        ...


class UrllibHttp:
    def get_json(self, url: str, *, headers: dict[str, str] | None = None, params: dict[str, str] | None = None) -> Any:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_form_json(self, url: str, data: dict[str, str], *, headers: dict[str, str] | None = None) -> Any:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(url, data=encoded, headers=headers or {})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")


def skipped(provider: str, reason: str) -> ProviderResult:
    return ProviderResult(provider=provider, verdict="skipped", evidence=[{"reason": reason}])


def errored(provider: str, exc: Exception) -> ProviderResult:
    return ProviderResult(provider=provider, verdict="error", errors=[str(exc)])


class SpamhausProvider:
    name = "spamhaus"

    def __init__(self, dqs_key: str | None = None, resolver: Callable[[str], list[str]] | None = None):
        self.dqs_key = dqs_key
        self.resolver = resolver or self._resolve_a

    def check(self, observable: Observable) -> ProviderResult:
        if observable.type != "domain":
            return skipped(self.name, "unsupported observable type")
        if not self.dqs_key:
            return skipped(self.name, "missing SPAMHAUS_DQS_KEY")
        evidence = []
        try:
            for zone in ("dbl", "zrd"):
                query = f"{observable.value}.{self.dqs_key}.{zone}.dq.spamhaus.net"
                answers = self.resolver(query)
                if answers:
                    evidence.append({"zone": zone, "query": query, "answers": answers})
        except Exception as exc:
            return errored(self.name, exc)
        if any(item["zone"] == "dbl" for item in evidence):
            return ProviderResult(provider=self.name, verdict="malicious", score=100, evidence=evidence)
        if any(item["zone"] == "zrd" for item in evidence):
            return ProviderResult(provider=self.name, verdict="suspicious", score=50, evidence=evidence)
        return ProviderResult(provider=self.name, verdict="clean", evidence=[{"zones_checked": ["dbl", "zrd"]}])

    @staticmethod
    def _resolve_a(query: str) -> list[str]:
        try:
            return list(socket.gethostbyname_ex(query)[2])
        except socket.gaierror:
            return []


class UrlhausProvider:
    name = "urlhaus"

    def __init__(self, auth_key: str | None = None, http: HttpTransport | None = None):
        self.auth_key = auth_key
        self.http = http or UrllibHttp()

    def check(self, observable: Observable) -> ProviderResult:
        if observable.type not in {"url", "domain"}:
            return skipped(self.name, "unsupported observable type")
        if not self.auth_key:
            return skipped(self.name, "missing URLHAUS_AUTH_KEY")
        headers = {"Auth-Key": self.auth_key}
        try:
            if observable.type == "url":
                payload = self.http.post_form_json("https://urlhaus-api.abuse.ch/v1/url/", {"url": observable.value}, headers=headers)
            else:
                payload = self.http.post_form_json("https://urlhaus-api.abuse.ch/v1/host/", {"host": observable.value}, headers=headers)
        except Exception as exc:
            return errored(self.name, exc)
        if str(payload.get("query_status")) == "ok":
            if payload.get("url_status") in {"online", "offline"}:
                return ProviderResult(provider=self.name, verdict="malicious", score=100, evidence=[payload])
            if payload.get("urls"):
                return ProviderResult(provider=self.name, verdict="malicious", score=100, evidence=[payload])
            return ProviderResult(provider=self.name, verdict="suspicious", score=50, evidence=[payload])
        return ProviderResult(provider=self.name, verdict="clean", evidence=[{"query_status": payload.get("query_status")}])


class OpenPhishProvider:
    name = "openphish"
    feed_url = "https://openphish.com/feed.txt"

    def __init__(self, feed_text: str | None = None, http: HttpTransport | None = None):
        self.feed_text = feed_text
        self.http = http or UrllibHttp()

    def check(self, observable: Observable) -> ProviderResult:
        if observable.type != "url":
            return skipped(self.name, "unsupported observable type")
        try:
            feed = self._feed()
        except Exception as exc:
            return errored(self.name, exc)
        if observable.value in feed:
            return ProviderResult(provider=self.name, verdict="malicious", score=100, evidence=[{"feed": self.feed_url}])
        return ProviderResult(provider=self.name, verdict="clean", evidence=[{"feed": self.feed_url}])

    def _feed(self) -> set[str]:
        if self.feed_text is None:
            self.feed_text = self.http.get_text(self.feed_url)
        return {line.strip() for line in self.feed_text.splitlines() if line.strip()}


class UrlscanProvider:
    name = "urlscan"

    def __init__(self, api_key: str | None = None, http: HttpTransport | None = None):
        self.api_key = api_key
        self.http = http or UrllibHttp()

    def check(self, observable: Observable) -> ProviderResult:
        if observable.type not in {"domain", "url"}:
            return skipped(self.name, "unsupported observable type")
        if not self.api_key:
            return skipped(self.name, "missing URLSCAN_API_KEY")
        query = f"domain:{observable.value}" if observable.type == "domain" else f'page.url:"{observable.value}"'
        try:
            payload = self.http.get_json(
                "https://urlscan.io/api/v1/search/",
                headers={"API-Key": self.api_key},
                params={"q": query},
            )
        except Exception as exc:
            return errored(self.name, exc)
        for result in payload.get("results") or []:
            verdict = ((result.get("verdicts") or {}).get("overall") or {})
            if verdict.get("malicious") or int(verdict.get("score") or 0) > 0:
                return ProviderResult(provider=self.name, verdict="suspicious", score=50, evidence=[result])
        return ProviderResult(provider=self.name, verdict="clean", evidence=[{"result_count": len(payload.get("results") or [])}])


class VirusTotalProvider:
    name = "virustotal"

    def __init__(self, api_key: str | None = None, http: HttpTransport | None = None):
        self.api_key = api_key
        self.http = http or UrllibHttp()

    def check(self, observable: Observable) -> ProviderResult:
        if observable.type not in {"domain", "url", "ip"}:
            return skipped(self.name, "unsupported observable type")
        if not self.api_key:
            return skipped(self.name, "missing VIRUSTOTAL_API_KEY")
        try:
            payload = self.http.get_json(self._url(observable), headers={"x-apikey": self.api_key})
        except Exception as exc:
            return errored(self.name, exc)
        stats = (((payload.get("data") or {}).get("attributes") or {}).get("last_analysis_stats") or {})
        malicious = int(stats.get("malicious") or 0)
        if malicious >= 2:
            return ProviderResult(provider=self.name, verdict="malicious", score=100, evidence=[{"last_analysis_stats": stats}])
        if malicious == 1:
            return ProviderResult(provider=self.name, verdict="suspicious", score=50, evidence=[{"last_analysis_stats": stats}])
        return ProviderResult(provider=self.name, verdict="clean", evidence=[{"last_analysis_stats": stats}])

    @staticmethod
    def _url(observable: Observable) -> str:
        if observable.type == "domain":
            return f"https://www.virustotal.com/api/v3/domains/{observable.value}"
        if observable.type == "ip":
            return f"https://www.virustotal.com/api/v3/ip_addresses/{observable.value}"
        encoded = base64.urlsafe_b64encode(observable.value.encode("utf-8")).decode("ascii").rstrip("=")
        return f"https://www.virustotal.com/api/v3/urls/{encoded}"


class AbuseIpdbProvider:
    name = "abuseipdb"

    def __init__(self, api_key: str | None = None, http: HttpTransport | None = None):
        self.api_key = api_key
        self.http = http or UrllibHttp()

    def check(self, observable: Observable) -> ProviderResult:
        if observable.type != "ip":
            return skipped(self.name, "unsupported observable type")
        if not self.api_key:
            return skipped(self.name, "missing ABUSEIPDB_API_KEY")
        try:
            payload = self.http.get_json(
                "https://api.abuseipdb.com/api/v2/check",
                headers={"Key": self.api_key, "Accept": "application/json"},
                params={"ipAddress": observable.value, "maxAgeInDays": "90"},
            )
        except Exception as exc:
            return errored(self.name, exc)
        score = int((payload.get("data") or {}).get("abuseConfidenceScore") or 0)
        if score >= 90:
            return ProviderResult(provider=self.name, verdict="malicious", score=100, evidence=[payload])
        if score >= 25:
            return ProviderResult(provider=self.name, verdict="suspicious", score=50, evidence=[payload])
        return ProviderResult(provider=self.name, verdict="clean", evidence=[payload])


def default_providers(*, no_network: bool = False) -> list[Any]:
    if no_network:
        return []
    return [
        SpamhausProvider(dqs_key=os.environ.get("SPAMHAUS_DQS_KEY")),
        UrlhausProvider(auth_key=os.environ.get("URLHAUS_AUTH_KEY")),
        OpenPhishProvider(),
        UrlscanProvider(api_key=os.environ.get("URLSCAN_API_KEY")),
        VirusTotalProvider(api_key=os.environ.get("VIRUSTOTAL_API_KEY")),
        AbuseIpdbProvider(api_key=os.environ.get("ABUSEIPDB_API_KEY")),
    ]


def provider_status() -> list[dict[str, Any]]:
    return [
        {"provider": "spamhaus", "env_var": "SPAMHAUS_DQS_KEY", "configured": bool(os.environ.get("SPAMHAUS_DQS_KEY"))},
        {"provider": "urlhaus", "env_var": "URLHAUS_AUTH_KEY", "configured": bool(os.environ.get("URLHAUS_AUTH_KEY"))},
        {"provider": "openphish", "env_var": None, "configured": True},
        {"provider": "urlscan", "env_var": "URLSCAN_API_KEY", "configured": bool(os.environ.get("URLSCAN_API_KEY"))},
        {"provider": "virustotal", "env_var": "VIRUSTOTAL_API_KEY", "configured": bool(os.environ.get("VIRUSTOTAL_API_KEY"))},
        {"provider": "abuseipdb", "env_var": "ABUSEIPDB_API_KEY", "configured": bool(os.environ.get("ABUSEIPDB_API_KEY"))},
    ]
