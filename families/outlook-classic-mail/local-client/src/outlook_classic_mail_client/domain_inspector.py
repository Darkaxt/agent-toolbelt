from __future__ import annotations

import email.utils
import ipaddress
import json
import math
import re
import sqlite3
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, unquote, urlparse

from . import blocklists


INTERNET_HEADERS_PROPERTY = "http://schemas.microsoft.com/mapi/proptag/0x007D001E"
DEFAULT_YOUNG_DAYS = 365
DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[2] / "state" / "domain_cache.sqlite"
DEFAULT_BLOCKLIST_CACHE_PATH = blocklists.DEFAULT_CACHE_PATH

COMMON_MULTI_LABEL_SUFFIXES = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "gov.uk",
    "com.au",
    "net.au",
    "org.au",
    "co.nz",
    "com.br",
    "com.mx",
    "com.tr",
    "co.jp",
}

IGNORED_FINAL_LABELS = {
    "avi",
    "bmp",
    "csv",
    "css",
    "dll",
    "doc",
    "docx",
    "eot",
    "exe",
    "gif",
    "htm",
    "html",
    "ico",
    "ics",
    "jpeg",
    "jpg",
    "js",
    "json",
    "m4a",
    "mov",
    "mp3",
    "mp4",
    "pdf",
    "png",
    "rar",
    "svg",
    "ttf",
    "txt",
    "wav",
    "webm",
    "webp",
    "woff",
    "woff2",
    "xls",
    "xlsx",
    "xml",
    "zip",
}

TRANSIENT_RDAP_ERROR_MARKERS = (
    "429",
    "too many requests",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "temporary failure",
    "connection reset",
    "502",
    "503",
    "504",
)

URL_RE = re.compile(r"https?://[^\s'\"<>)]+", re.IGNORECASE)
DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}\b",
    re.IGNORECASE,
)
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HEADER_DOMAIN_PATTERNS = {
    "reply-to": re.compile(r"^reply-to:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "return-path": re.compile(r"^return-path:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "list-unsubscribe": re.compile(r"^list-unsubscribe:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
}
HEADER_IP_PREFIXES = {
    "received:": "received",
    "received-spf:": "received-spf",
    "authentication-results:": "authentication-results",
}
RISKY_TLDS = {"biz", "cc", "click", "icu", "lol", "sbs", "top", "xyz"}
VOWELS = set("aeiou")


@dataclass(frozen=True)
class DomainReference:
    raw_value: str
    domain: str
    registrable_domain: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def safe_get(obj: Any, attribute: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attribute)
    except Exception:
        return default


def get_internet_headers(item: Any) -> str:
    accessor = safe_get(item, "PropertyAccessor")
    if accessor is None:
        return ""
    try:
        return accessor.GetProperty(INTERNET_HEADERS_PROPERTY) or ""
    except Exception:
        return ""


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().strip("<>[](){}.,;:'\"").lower()
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    if "://" in text:
        parsed = urlparse(text)
        text = parsed.hostname or ""
    text = text.strip(".")
    if not text or "." not in text or " " in text:
        return None
    try:
        return text.encode("idna").decode("ascii")
    except UnicodeError:
        return None


def registrable_domain(domain: str | None) -> str | None:
    normalized = normalize_domain(domain)
    if not normalized:
        return None
    labels = [label for label in normalized.split(".") if label]
    if len(labels) < 2:
        return None
    tld = labels[-1]
    if tld in IGNORED_FINAL_LABELS:
        return None
    if not re.fullmatch(r"(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})", tld):
        return None
    suffix = ".".join(labels[-2:])
    if suffix in COMMON_MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def parse_email_domains(value: str, source: str) -> Iterable[DomainReference]:
    for _, address in email.utils.getaddresses([value or ""]):
        domain = normalize_domain(address)
        reg_domain = registrable_domain(domain)
        if domain and reg_domain:
            yield DomainReference(
                raw_value=address,
                domain=domain,
                registrable_domain=reg_domain,
                source=source,
            )


def domains_from_urls(text: str, source: str) -> Iterable[DomainReference]:
    for match in URL_RE.finditer(text or ""):
        raw_url = match.group(0).rstrip(".,;")
        domain = normalize_domain(raw_url)
        reg_domain = registrable_domain(domain)
        if domain and reg_domain:
            yield DomainReference(
                raw_value=raw_url,
                domain=domain,
                registrable_domain=reg_domain,
                source=source,
            )


def domains_from_url_embeds(text: str, source: str) -> Iterable[DomainReference]:
    for match in URL_RE.finditer(text or ""):
        raw_url = match.group(0).rstrip(".,;")
        parsed = urlparse(raw_url)
        for _, value in parse_qsl(parsed.query, keep_blank_values=True):
            decoded = unquote(value)
            if not decoded:
                continue
            embedded_source = f"{source}-embedded"
            yield from domains_from_urls(decoded, embedded_source)
            yield from domains_from_bare_text(decoded, embedded_source)


def domains_from_bare_text(text: str, source: str) -> Iterable[DomainReference]:
    text_without_urls = URL_RE.sub(" ", text or "")
    for match in DOMAIN_RE.finditer(text_without_urls):
        raw_domain = match.group(0)
        domain = normalize_domain(raw_domain)
        reg_domain = registrable_domain(domain)
        if domain and reg_domain:
            yield DomainReference(
                raw_value=raw_domain,
                domain=domain,
                registrable_domain=reg_domain,
                source=source,
            )


def dedupe_references(references: Iterable[DomainReference]) -> list[DomainReference]:
    seen: set[tuple[str, str, str]] = set()
    output: list[DomainReference] = []
    for ref in references:
        key = (ref.registrable_domain, ref.source, ref.raw_value)
        if key in seen:
            continue
        seen.add(key)
        output.append(ref)
    return output


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value.lower())
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def max_consonant_run(value: str) -> int:
    longest = current = 0
    for char in value.lower():
        if char.isalpha() and char not in VOWELS:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def digit_ratio(value: str) -> float:
    compact = [char for char in value if char.isalnum()]
    if not compact:
        return 0.0
    return sum(1 for char in compact if char.isdigit()) / len(compact)


def random_like_token(value: str) -> bool:
    token = re.sub(r"[^a-z0-9]", "", value.lower())
    if len(token) < 8:
        return False
    entropy = shannon_entropy(token)
    vowels = sum(1 for char in token if char in VOWELS)
    return entropy >= 2.75 and (
        vowels <= max(1, len(token) // 5)
        or max_consonant_run(token) >= 5
        or digit_ratio(token) >= 0.35
    )


def subdomain_labels(domain: str, registrable: str) -> list[str]:
    labels = [label for label in (normalize_domain(domain) or "").split(".") if label]
    registrable_labels = [label for label in (normalize_domain(registrable) or "").split(".") if label]
    if not labels or not registrable_labels:
        return []
    if labels[-len(registrable_labels) :] != registrable_labels:
        return []
    return labels[: -len(registrable_labels)]


def sender_localpart(raw_value: str) -> str | None:
    _, address = email.utils.parseaddr(raw_value or "")
    if "@" not in address:
        return None
    localpart = address.rsplit("@", 1)[0]
    return localpart or None


def domain_structure_summaries(references: Iterable[DomainReference]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in references:
        key = (ref.domain, ref.source, ref.raw_value)
        if key in seen:
            continue
        seen.add(key)
        labels = [label for label in ref.domain.split(".") if label]
        subs = subdomain_labels(ref.domain, ref.registrable_domain)
        label_entropies = {label: round(shannon_entropy(label), 3) for label in labels}
        random_labels = [label for label in subs if random_like_token(label)]
        evidence_tags: list[str] = []
        if len(subs) >= 2:
            evidence_tags.append("deep_subdomain_chain")
        if random_labels:
            evidence_tags.append("random_like_label")
        registrable_labels = ref.registrable_domain.split(".")
        tld = registrable_labels[-1] if registrable_labels else ""
        if tld in RISKY_TLDS:
            evidence_tags.append("risky_tld")
        localpart = sender_localpart(ref.raw_value) if ref.source == "sender" else None
        if localpart and random_like_token(localpart):
            evidence_tags.append("random_like_sender_localpart")
        summaries.append(
            {
                "raw_value": ref.raw_value,
                "domain": ref.domain,
                "registrable_domain": ref.registrable_domain,
                "source": ref.source,
                "label_count": len(labels),
                "subdomain_labels": subs,
                "longest_label_length": max((len(label) for label in labels), default=0),
                "digit_ratio": round(digit_ratio(ref.domain), 3),
                "shannon_entropy": round(shannon_entropy(ref.domain.replace(".", "")), 3),
                "label_entropies": label_entropies,
                "suspicious_label_count": len(random_labels),
                "risky_tld": tld in RISKY_TLDS,
                "evidence_tags": evidence_tags,
            }
        )
    return summaries


def extract_domain_references(item: Any) -> list[DomainReference]:
    references: list[DomainReference] = []

    sender_email = str(safe_get(item, "SenderEmailAddress", "") or "")
    references.extend(parse_email_domains(sender_email, "sender"))

    headers = get_internet_headers(item)
    for source, pattern in HEADER_DOMAIN_PATTERNS.items():
        for match in pattern.finditer(headers):
            references.extend(parse_email_domains(match.group(1), source))
            references.extend(domains_from_urls(match.group(1), source))
            references.extend(domains_from_bare_text(match.group(1), source))

    auth_lines = "\n".join(
        line
        for line in headers.splitlines()
        if line.lower().startswith(("authentication-results:", "dkim-signature:", "received-spf:"))
    )
    references.extend(domains_from_bare_text(auth_lines, "authentication-results"))

    body = str(safe_get(item, "Body", "") or "")
    html_body = str(safe_get(item, "HTMLBody", "") or "")
    references.extend(domains_from_urls(body, "body-url"))
    references.extend(domains_from_url_embeds(body, "body-url"))
    references.extend(domains_from_bare_text(body, "body-domain"))
    references.extend(domains_from_urls(html_body, "html-url"))
    references.extend(domains_from_url_embeds(html_body, "html-url"))
    references.extend(domains_from_bare_text(html_body, "html-domain"))

    return dedupe_references(references)


def extract_ip_references(item: Any) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    headers = get_internet_headers(item)
    seen: set[tuple[str, str]] = set()
    for line in headers.splitlines():
        lower = line.lower()
        source = next((value for prefix, value in HEADER_IP_PREFIXES.items() if lower.startswith(prefix)), None)
        if source is None:
            continue
        for match in IPV4_RE.finditer(line):
            raw_ip = match.group(0)
            try:
                ip = str(ipaddress.ip_address(raw_ip))
            except ValueError:
                continue
            key = (ip, source)
            if key in seen:
                continue
            seen.add(key)
            references.append({"ip": ip, "source": source, "raw_value": raw_ip})
    return references


def parse_rdap_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def domain_age_summary(
    domain: str,
    rdap_record: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    young_days: int = DEFAULT_YOUNG_DAYS,
    blocklist_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    record = rdap_record or {}
    registration_date = record.get("registration_date")
    created_at = parse_rdap_datetime(registration_date)
    age_days = None
    is_young = None
    if created_at is not None:
        age_days = max((now - created_at).days, 0)
        is_young = age_days < young_days

    return {
        "domain": domain,
        "registration_date": registration_date,
        "expiration_date": record.get("expiration_date"),
        "last_changed_date": record.get("last_changed_date"),
        "registrar": record.get("registrar"),
        "status": record.get("status"),
        "rdap_url": record.get("rdap_url"),
        "rdap_error": record.get("error"),
        "age_days": age_days,
        "is_young": is_young,
        "blocklist_hits": blocklist_hits or [],
    }


class RdapCache:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_CACHE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rdap_cache (
                    domain TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )
                """
            )

    def get(self, domain: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM rdap_cache WHERE domain = ?",
                (domain,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        if not should_cache_rdap_payload(payload):
            with self._connect() as conn:
                conn.execute("DELETE FROM rdap_cache WHERE domain = ?", (domain,))
            return None
        return payload

    def set(self, domain: str, payload: dict[str, Any]) -> None:
        if not should_cache_rdap_payload(payload):
            return
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rdap_cache(domain, payload, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    payload = excluded.payload,
                    fetched_at = excluded.fetched_at
                """,
                (domain, json.dumps(payload, sort_keys=True), fetched_at),
            )

    def lookup(self, domain: str) -> dict[str, Any]:
        cached = self.get(domain)
        if cached is not None:
            return cached
        payload = fetch_rdap(domain)
        self.set(domain, payload)
        return payload


def should_cache_rdap_payload(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    error = str(payload.get("error") or "").lower()
    if not error:
        return True
    return not any(marker in error for marker in TRANSIENT_RDAP_ERROR_MARKERS)


def rdap_urls_for_domain(domain: str) -> list[str]:
    normalized = registrable_domain(domain) or normalize_domain(domain) or domain.lower()
    labels = normalized.split(".")
    tld = labels[-1] if labels else ""
    urls: list[str] = []
    if tld == "com":
        urls.append(f"https://rdap.verisign.com/com/v1/domain/{normalized.upper()}")
    elif tld == "net":
        urls.append(f"https://rdap.verisign.com/net/v1/domain/{normalized.upper()}")
    elif tld == "org":
        urls.append(f"https://rdap.publicinterestregistry.org/rdap/domain/{normalized}")
    elif tld == "biz":
        urls.append(f"https://rdap.nic.biz/domain/{normalized}")
    elif tld == "de":
        urls.append(f"https://rdap.denic.de/domain/{normalized}")
    elif tld == "uk":
        urls.append(f"https://rdap.nominet.uk/uk/domain/{normalized}")

    fallback = f"https://rdap.org/domain/{normalized}"
    if fallback not in urls:
        urls.append(fallback)
    return urls


def fetch_rdap(domain: str) -> dict[str, Any]:
    errors: list[str] = []
    for url in rdap_urls_for_domain(domain):
        payload = fetch_rdap_url(domain, url)
        if payload.get("error") is None:
            return payload
        errors.append(f"{url}: {payload.get('error')}")
        if should_cache_rdap_payload(payload):
            return payload
    return {
        "domain": domain,
        "rdap_url": rdap_urls_for_domain(domain)[-1],
        "registration_date": None,
        "expiration_date": None,
        "last_changed_date": None,
        "registrar": None,
        "status": None,
        "error": " | ".join(errors),
    }


def fetch_rdap_url(domain: str, url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/rdap+json, application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "domain": domain,
            "rdap_url": url,
            "registration_date": None,
            "expiration_date": None,
            "last_changed_date": None,
            "registrar": None,
            "status": None,
            "error": str(exc),
        }

    events = payload.get("events") or []
    registration_date = first_event_date(events, ("registration", "created"))
    expiration_date = first_event_date(events, ("expiration",))
    last_changed_date = first_event_date(events, ("last changed", "last update"))
    return {
        "domain": domain,
        "rdap_url": url,
        "registration_date": registration_date,
        "expiration_date": expiration_date,
        "last_changed_date": last_changed_date,
        "registrar": registrar_name(payload),
        "status": ", ".join(payload.get("status") or []),
        "error": None,
    }


def first_event_date(events: list[dict[str, Any]], actions: tuple[str, ...]) -> str | None:
    for event in events:
        action = str(event.get("eventAction", "")).lower()
        if any(token in action for token in actions):
            return event.get("eventDate")
    return None


def registrar_name(payload: dict[str, Any]) -> str | None:
    for entity in payload.get("entities") or []:
        if "registrar" not in (entity.get("roles") or []):
            continue
        vcard = entity.get("vcardArray") or []
        if len(vcard) < 2:
            continue
        for field in vcard[1]:
            if field and field[0] == "fn" and len(field) >= 4:
                return field[3]
    return None


def inspect_item_domains(
    item: Any,
    *,
    with_rdap: bool = False,
    cache_path: Path | None = None,
    young_days: int = DEFAULT_YOUNG_DAYS,
    with_blocklists: bool = False,
    blocklist_cache_path: Path | None = None,
    blocklist_profile: str = "threat",
    blocklist_cache: Any | None = None,
) -> dict[str, Any]:
    references = extract_domain_references(item)
    unique_domains = sorted({ref.registrable_domain for ref in references})
    cache = RdapCache(cache_path) if with_rdap else None
    resolved_blocklist_cache = None
    if with_blocklists:
        resolved_blocklist_cache = blocklist_cache or blocklists.BlocklistCache(blocklist_cache_path)
        resolved_blocklist_cache.refresh(profile=blocklist_profile)
    domain_ages = []
    for domain in unique_domains:
        record = cache.lookup(domain) if cache is not None else None
        hits = resolved_blocklist_cache.lookup(domain, profile=blocklist_profile) if resolved_blocklist_cache is not None else []
        domain_ages.append(domain_age_summary(domain, record, young_days=young_days, blocklist_hits=hits))
    return {
        "domain_references": [ref.to_dict() for ref in references],
        "ip_references": extract_ip_references(item),
        "domain_structure": domain_structure_summaries(references),
        "domain_ages": domain_ages,
    }
