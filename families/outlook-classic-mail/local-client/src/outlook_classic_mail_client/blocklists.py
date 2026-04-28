from __future__ import annotations

import ipaddress
import json
import re
import sqlite3
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse


DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[2] / "state" / "blocklist_cache.sqlite"
DEFAULT_REFRESH_TTL = timedelta(hours=24)
IGNORED_FINAL_LABELS = {"gif", "html", "ico", "jpeg", "jpg", "js", "json", "pdf", "png", "svg", "txt", "webp", "xml", "zip"}


@dataclass(frozen=True)
class BlocklistSource:
    name: str
    category: str
    url: str
    profile: str = "threat"


THREAT_SOURCES = (
    BlocklistSource(
        name="hagezi-tif-medium",
        category="threat",
        url="https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/tif.medium-onlydomains.txt",
    ),
    BlocklistSource(
        name="hagezi-tif-mini",
        category="threat",
        url="https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/tif.mini-onlydomains.txt",
    ),
    BlocklistSource("blocklistproject-abuse", "abuse", "https://blocklistproject.github.io/Lists/alt-version/abuse-nl.txt"),
    BlocklistSource("blocklistproject-crypto", "crypto", "https://blocklistproject.github.io/Lists/alt-version/crypto-nl.txt"),
    BlocklistSource("blocklistproject-fraud", "fraud", "https://blocklistproject.github.io/Lists/alt-version/fraud-nl.txt"),
    BlocklistSource("blocklistproject-malware", "malware", "https://blocklistproject.github.io/Lists/alt-version/malware-nl.txt"),
    BlocklistSource("blocklistproject-phishing", "phishing", "https://blocklistproject.github.io/Lists/alt-version/phishing-nl.txt"),
    BlocklistSource(
        "blocklistproject-ransomware",
        "ransomware",
        "https://blocklistproject.github.io/Lists/alt-version/ransomware-nl.txt",
    ),
    BlocklistSource("blocklistproject-redirect", "redirect", "https://blocklistproject.github.io/Lists/alt-version/redirect-nl.txt"),
    BlocklistSource("blocklistproject-scam", "scam", "https://blocklistproject.github.io/Lists/alt-version/scam-nl.txt"),
)

DEBUG_ONLY_SOURCES = (
    BlocklistSource("oisd-big", "mixed", "https://big.oisd.nl/", profile="debug-all"),
    BlocklistSource("oisd-small", "ads", "https://small.oisd.nl/", profile="debug-all"),
    BlocklistSource("stevenblack-base", "mixed", "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts", profile="debug-all"),
    BlocklistSource("blocklistproject-ads", "ads", "https://blocklistproject.github.io/Lists/alt-version/ads-nl.txt", profile="debug-all"),
    BlocklistSource("blocklistproject-drugs", "drugs", "https://blocklistproject.github.io/Lists/alt-version/drugs-nl.txt", profile="debug-all"),
    BlocklistSource("blocklistproject-facebook", "facebook", "https://blocklistproject.github.io/Lists/alt-version/facebook-nl.txt", profile="debug-all"),
    BlocklistSource("blocklistproject-gambling", "gambling", "https://blocklistproject.github.io/Lists/alt-version/gambling-nl.txt", profile="debug-all"),
    BlocklistSource("blocklistproject-piracy", "piracy", "https://blocklistproject.github.io/Lists/alt-version/piracy-nl.txt", profile="debug-all"),
    BlocklistSource("blocklistproject-porn", "porn", "https://blocklistproject.github.io/Lists/alt-version/porn-nl.txt", profile="debug-all"),
    BlocklistSource("blocklistproject-tiktok", "tiktok", "https://blocklistproject.github.io/Lists/alt-version/tiktok-nl.txt", profile="debug-all"),
    BlocklistSource("blocklistproject-torrent", "torrent", "https://blocklistproject.github.io/Lists/alt-version/torrent-nl.txt", profile="debug-all"),
    BlocklistSource("blocklistproject-tracking", "tracking", "https://blocklistproject.github.io/Lists/alt-version/tracking-nl.txt", profile="debug-all"),
    BlocklistSource("blocklistproject-twitter", "twitter", "https://blocklistproject.github.io/Lists/alt-version/twitter-nl.txt", profile="debug-all"),
)

DEFAULT_SOURCES = THREAT_SOURCES + DEBUG_ONLY_SOURCES


def sources_for_profile(profile: str, sources: Iterable[BlocklistSource] = DEFAULT_SOURCES) -> list[BlocklistSource]:
    profile = normalize_profile(profile)
    source_list = list(sources)
    if profile == "debug-all":
        return source_list
    return [source for source in source_list if source.profile == "threat"]


def normalize_profile(profile: str | None) -> str:
    value = (profile or "threat").strip().lower()
    if value not in {"threat", "debug-all"}:
        raise ValueError(f"Unsupported blocklist profile: {profile}")
    return value


def default_fetcher(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "outlook-classic-mail-client/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_blocklist_domains(text: str) -> set[str]:
    domains: set[str] = set()
    for line in text.splitlines():
        domains.update(parse_blocklist_line(line))
    return domains


def parse_blocklist_line(line: str) -> set[str]:
    text = line.strip()
    if not text or text.startswith(("#", "!", "[", "//")):
        return set()
    if text.startswith(("server=/", "address=/")):
        return normalized_domain_set(text.split("/", 2)[1])
    if text.startswith("||"):
        token = re.split(r"[\^/$*]", text[2:], maxsplit=1)[0]
        return normalized_domain_set(token)
    if text.startswith("*."):
        return normalized_domain_set(text[2:])
    if text.startswith("."):
        return normalized_domain_set(text[1:])
    if "://" in text:
        return normalized_domain_set((urlparse(text).hostname or "").strip())

    tokens = text.split()
    if not tokens:
        return set()
    if looks_like_ip(tokens[0]):
        return normalized_domain_set(tokens[1]) if len(tokens) > 1 else set()
    return normalized_domain_set(tokens[0])


def normalized_domain_set(value: str) -> set[str]:
    domain = normalize_blocklist_domain(value)
    return {domain} if domain else set()


def normalize_blocklist_domain(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().strip("<>[](){}.,;:'\"").lower()
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    if "://" in text:
        text = urlparse(text).hostname or ""
    text = text.strip(".")
    if not text or "." not in text or " " in text:
        return None
    labels = text.split(".")
    if labels[-1] in IGNORED_FINAL_LABELS:
        return None
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}", text):
        return None
    try:
        return text.encode("idna").decode("ascii")
    except UnicodeError:
        return None


def looks_like_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


class BlocklistCache:
    def __init__(
        self,
        path: Path | None = None,
        *,
        sources: Iterable[BlocklistSource] = DEFAULT_SOURCES,
        fetcher: Callable[[str], str] = default_fetcher,
        refresh_ttl: timedelta = DEFAULT_REFRESH_TTL,
    ):
        self.path = path or DEFAULT_CACHE_PATH
        self.sources = tuple(sources)
        self.fetcher = fetcher
        self.refresh_ttl = refresh_ttl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS blocklist_sources (
                        name TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        profile TEXT NOT NULL,
                        url TEXT NOT NULL,
                        fetched_at TEXT,
                        status TEXT NOT NULL,
                        error TEXT,
                        domain_count INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS blocklist_domains (
                        domain TEXT NOT NULL,
                        source TEXT NOT NULL,
                        category TEXT NOT NULL,
                        profile TEXT NOT NULL,
                        fetched_at TEXT NOT NULL,
                        PRIMARY KEY(domain, source)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_blocklist_domains_domain ON blocklist_domains(domain)")

    def refresh(self, *, profile: str = "threat", force: bool = False, now: datetime | None = None) -> dict[str, int | str]:
        now = normalize_datetime(now)
        refreshed = skipped = failed = 0
        for source in sources_for_profile(profile, self.sources):
            if not force and not self.source_needs_refresh(source, now=now):
                skipped += 1
                continue
            try:
                domains = parse_blocklist_domains(self.fetcher(source.url))
            except Exception as exc:
                self.record_source_error(source, exc, now=now)
                failed += 1
                continue
            self.replace_source_domains(source, domains, now=now)
            refreshed += 1
        return {"profile": normalize_profile(profile), "refreshed": refreshed, "skipped": skipped, "failed": failed}

    def source_needs_refresh(self, source: BlocklistSource, *, now: datetime) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT fetched_at, status FROM blocklist_sources WHERE name = ?",
                (source.name,),
            ).fetchone()
        if row is None or row[0] is None or row[1] != "ok":
            return True
        fetched_at = datetime.fromisoformat(row[0])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return now - fetched_at >= self.refresh_ttl

    def replace_source_domains(self, source: BlocklistSource, domains: set[str], *, now: datetime) -> None:
        fetched_at = now.isoformat()
        with closing(self._connect()) as conn:
            with conn:
                conn.execute("DELETE FROM blocklist_domains WHERE source = ?", (source.name,))
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO blocklist_domains(domain, source, category, profile, fetched_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [(domain, source.name, source.category, source.profile, fetched_at) for domain in sorted(domains)],
                )
                conn.execute(
                    """
                    INSERT INTO blocklist_sources(name, category, profile, url, fetched_at, status, error, domain_count)
                    VALUES (?, ?, ?, ?, ?, 'ok', NULL, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        category = excluded.category,
                        profile = excluded.profile,
                        url = excluded.url,
                        fetched_at = excluded.fetched_at,
                        status = excluded.status,
                        error = excluded.error,
                        domain_count = excluded.domain_count
                    """,
                    (source.name, source.category, source.profile, source.url, fetched_at, len(domains)),
                )

    def record_source_error(self, source: BlocklistSource, exc: Exception, *, now: datetime) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO blocklist_sources(name, category, profile, url, fetched_at, status, error, domain_count)
                    VALUES (?, ?, ?, ?, ?, 'error', ?, 0)
                    ON CONFLICT(name) DO UPDATE SET
                        category = excluded.category,
                        profile = excluded.profile,
                        url = excluded.url,
                        fetched_at = excluded.fetched_at,
                        status = excluded.status,
                        error = excluded.error
                    """,
                    (source.name, source.category, source.profile, source.url, now.isoformat(), str(exc)),
                )

    def lookup(self, domain: str, *, profile: str = "threat") -> list[dict[str, str]]:
        candidates = lookup_candidates(domain)
        if not candidates:
            return []
        profiles = ("threat", "debug-all") if normalize_profile(profile) == "debug-all" else ("threat",)
        placeholders = ",".join("?" for _ in candidates)
        profile_placeholders = ",".join("?" for _ in profiles)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""
                SELECT domain, source, category, profile, fetched_at
                FROM blocklist_domains
                WHERE domain IN ({placeholders}) AND profile IN ({profile_placeholders})
                ORDER BY LENGTH(domain) DESC, source
                """,
                (*candidates, *profiles),
            ).fetchall()
        return [
            {
                "source": row[1],
                "category": row[2],
                "matched_domain": row[0],
                "profile": row[3],
                "fetched_at": row[4],
            }
            for row in rows
        ]

    def status(self, *, profile: str = "threat") -> list[dict[str, str | int | None]]:
        source_names = [source.name for source in sources_for_profile(profile, self.sources)]
        if not source_names:
            return []
        placeholders = ",".join("?" for _ in source_names)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""
                SELECT name, category, profile, url, fetched_at, status, error, domain_count
                FROM blocklist_sources
                WHERE name IN ({placeholders})
                ORDER BY name
                """,
                source_names,
            ).fetchall()
        by_name = {row[0]: row for row in rows}
        status_rows = []
        for source in sources_for_profile(profile, self.sources):
            row = by_name.get(source.name)
            status_rows.append(
                {
                    "source": source.name,
                    "category": source.category,
                    "profile": source.profile,
                    "url": source.url,
                    "fetched_at": row[4] if row else None,
                    "status": row[5] if row else "missing",
                    "error": row[6] if row else None,
                    "domains": int(row[7]) if row else 0,
                }
            )
        return status_rows


def lookup_candidates(domain: str) -> list[str]:
    normalized = normalize_blocklist_domain(domain)
    if not normalized:
        return []
    labels = normalized.split(".")
    return [".".join(labels[index:]) for index in range(0, max(len(labels) - 1, 0))]


def normalize_datetime(value: datetime | None) -> datetime:
    now = value or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now
