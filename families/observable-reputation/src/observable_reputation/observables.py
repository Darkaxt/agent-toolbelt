from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunparse


SUPPORTED_TYPES = {"domain", "url", "ip"}


@dataclass(frozen=True)
class Observable:
    type: str
    value: str
    source: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    domain: str | None = None

    @property
    def cache_key(self) -> str:
        return f"{self.type}:{self.value}"


def normalize_domain(value: str) -> str:
    text = value.strip().strip(".").lower()
    if "://" in text:
        parsed = urlparse(text)
        text = parsed.hostname or ""
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    if not text or "." not in text or " " in text:
        raise ValueError(f"Invalid domain observable: {value!r}")
    try:
        return text.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"Invalid domain observable: {value!r}") from exc


def normalize_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid URL observable: {value!r}")
    domain = normalize_domain(parsed.hostname)
    netloc = domain
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username or parsed.password:
        userinfo = parsed.username or ""
        if parsed.password:
            userinfo = f"{userinfo}:{parsed.password}"
        netloc = f"{userinfo}@{netloc}"
    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "",
            parsed.params or "",
            parsed.query or "",
            parsed.fragment or "",
        )
    )
    return normalized, domain


def normalize_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError as exc:
        raise ValueError(f"Invalid IP observable: {value!r}") from exc


def normalize_observable(record: dict[str, Any]) -> Observable:
    observable_type = str(record.get("type", "")).strip().lower()
    if observable_type not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported observable type: {observable_type!r}")

    raw_value = str(record.get("value", "") or "")
    source = str(record.get("source", "") or "")
    context = dict(record.get("context") or {})
    if observable_type == "domain":
        value = normalize_domain(raw_value)
        return Observable(type="domain", value=value, source=source, context=context, domain=value)
    if observable_type == "url":
        value, domain = normalize_url(raw_value)
        return Observable(type="url", value=value, source=source, context=context, domain=domain)
    return Observable(type="ip", value=normalize_ip(raw_value), source=source, context=context)
