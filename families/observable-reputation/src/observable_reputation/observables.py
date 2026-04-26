from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

SUPPORTED_TYPES = {"domain", "url", "ip"}
AUTO_TYPE = "auto"


@dataclass(frozen=True)
class Observable:
    type: str
    value: str
    source: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    domain: str | None = None
    raw_value: str = ""
    normalization: dict[str, Any] = field(default_factory=dict)

    @property
    def cache_key(self) -> str:
        return f"{self.type}:{self.value}"

    @property
    def normalized_value(self) -> str:
        return self.value


def normalize_domain(value: str) -> str:
    normalized, _ = normalize_domain_details(value)
    return normalized


def normalize_domain_details(value: str) -> tuple[str, dict[str, Any]]:
    raw = str(value or "")
    text = raw.strip().strip(".").lower()
    warnings: list[str] = []
    if "://" in text:
        parsed = urlparse(text)
        text = parsed.hostname or ""
        warnings.append("url_host_extracted")
    if "@" in text:
        text = text.rsplit("@", 1)[1]
        warnings.append("email_domain_extracted")
    text = text.strip().strip(".").lower()
    if not text or "." not in text or any(char.isspace() for char in text):
        raise ValueError(f"Invalid domain observable: {value!r}")
    try:
        normalized = text.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError(f"Invalid domain observable: {value!r}") from exc
    return normalized, {"warnings": warnings}


def normalize_url(value: str) -> tuple[str, str]:
    normalized, domain, _ = normalize_url_details(value)
    return normalized, domain


def normalize_url_details(value: str) -> tuple[str, str, dict[str, Any]]:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid URL observable: {value!r}")

    host = normalize_url_host(parsed.hostname)
    warnings: list[str] = []
    if parsed.username or parsed.password:
        warnings.append("userinfo_removed")
    if parsed.fragment:
        warnings.append("fragment_removed")

    netloc_host = host
    try:
        if ipaddress.ip_address(host).version == 6:
            netloc_host = f"[{host}]"
    except ValueError:
        pass

    netloc = netloc_host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"

    normalized = urlunparse(
        (
            scheme,
            netloc,
            parsed.path or "",
            parsed.params or "",
            parsed.query or "",
            "",
        )
    )
    return normalized, host, {"warnings": warnings}


def normalize_url_host(value: str) -> str:
    text = str(value or "").strip().strip("[]")
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return normalize_domain(text)


def normalize_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError as exc:
        raise ValueError(f"Invalid IP observable: {value!r}") from exc


def normalize_observable(record: Any, *, auto_detect: bool = False) -> Observable:
    raw_value, observable_type, source, context = record_parts(record)
    detected_from: str | None = None

    if observable_type == AUTO_TYPE or (not observable_type and auto_detect):
        if not auto_detect:
            raise ValueError(f"Unsupported observable type: {observable_type!r}")
        observable_type, detected_from = detect_observable_type(raw_value)
    elif observable_type not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported observable type: {observable_type!r}")

    if observable_type == "domain":
        value, details = normalize_domain_details(raw_value)
        normalization = build_normalization(observable_type, detected_from, details)
        return Observable(
            type="domain",
            value=value,
            source=source,
            context=context,
            domain=value,
            raw_value=raw_value,
            normalization=normalization,
        )
    if observable_type == "url":
        value, domain, details = normalize_url_details(raw_value)
        normalization = build_normalization(observable_type, detected_from, details)
        return Observable(
            type="url",
            value=value,
            source=source,
            context=context,
            domain=domain,
            raw_value=raw_value,
            normalization=normalization,
        )
    value = normalize_ip(raw_value)
    normalization = build_normalization(observable_type, detected_from, {"warnings": []})
    return Observable(
        type="ip",
        value=value,
        source=source,
        context=context,
        raw_value=raw_value,
        normalization=normalization,
    )


def record_parts(record: Any) -> tuple[str, str, str, dict[str, Any]]:
    if isinstance(record, str):
        return record, AUTO_TYPE, "", {}
    if not isinstance(record, dict):
        return str(record), "", "", {}
    raw_value = str(record.get("value", "") or "")
    observable_type = str(record.get("type", "") or "").strip().lower()
    source = str(record.get("source", "") or "")
    context = dict(record.get("context") or {})
    return raw_value, observable_type, source, context


def detect_observable_type(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
        return "url", "url"
    try:
        normalize_ip(raw)
        return "ip", "ip"
    except ValueError:
        pass
    if "@" in raw and not any(char.isspace() for char in raw):
        candidate = raw.rsplit("@", 1)[1]
        normalize_domain(candidate)
        return "domain", "email-domain"
    normalize_domain(raw)
    return "domain", "domain"


def build_normalization(observable_type: str, detected_from: str | None, details: dict[str, Any]) -> dict[str, Any]:
    warnings = list(details.get("warnings") or [])
    return {
        "input_type": observable_type,
        "detected_from": detected_from or observable_type,
        "auto_detected": detected_from is not None,
        "warnings": warnings,
    }


def normalize_records(records: list[Any], *, auto_detect: bool = False) -> tuple[list[Observable], list[dict[str, Any]]]:
    normalized: list[Observable] = []
    rejected: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        raw_value, observable_type, source, _ = record_parts(record)
        try:
            normalized.append(normalize_observable(record, auto_detect=auto_detect))
        except ValueError as exc:
            rejected.append(
                {
                    "index": index,
                    "type": observable_type or None,
                    "raw_value": raw_value,
                    "source": source,
                    "error": str(exc),
                }
            )
    return normalized, rejected


def observable_to_dict(observable: Observable) -> dict[str, Any]:
    raw_value = observable.raw_value or observable.value
    return {
        "type": observable.type,
        "value": observable.value,
        "raw_value": raw_value,
        "normalized_value": observable.normalized_value,
        "source": observable.source,
        "context": observable.context,
        "domain": observable.domain,
        "normalization": observable.normalization or build_normalization(observable.type, None, {"warnings": []}),
    }


def normalize_report(records: list[Any], *, auto_detect: bool = True) -> dict[str, Any]:
    normalized, rejected = normalize_records(records, auto_detect=auto_detect)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "observables": [observable_to_dict(item) for item in normalized],
        "rejected_observables": rejected,
    }
