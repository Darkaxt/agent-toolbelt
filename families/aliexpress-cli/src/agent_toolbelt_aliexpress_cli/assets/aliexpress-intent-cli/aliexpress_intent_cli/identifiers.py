from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


BASE_URL = "https://www.aliexpress.com"
ITEM_URL_RE = re.compile(r"/item/(?P<id>\d+)(?:\.html)?", re.IGNORECASE)
NUMERIC_ID_RE = re.compile(r"^\d{8,}$")


def normalize_item_url(identifier: str) -> str:
    item_id = extract_item_id(identifier)
    if item_id is None:
        raise ValueError(f"Unsupported AliExpress item identifier: {identifier}")
    return f"{BASE_URL}/item/{item_id}.html"


def is_supported_host(host: str) -> bool:
    return bool(host and (host == "aliexpress.com" or host.endswith(".aliexpress.com")))


def extract_item_id(identifier: str) -> str | None:
    value = identifier.strip()
    if NUMERIC_ID_RE.match(value):
        return value
    parsed = urlparse(value)
    if parsed.netloc:
        match = ITEM_URL_RE.search(parsed.path)
        return match.group("id") if match else None
    return None


def inspect_identifier(identifier: str) -> dict[str, Any]:
    value = identifier.strip()
    parsed = urlparse(value)
    item_id = extract_item_id(value)
    warnings: list[str] = []
    if parsed.netloc and not is_supported_host(parsed.netloc.lower()):
        identifier_type = "unsupported_url"
    elif NUMERIC_ID_RE.match(value):
        identifier_type = "item_id"
    elif parsed.netloc and item_id:
        identifier_type = "item_url"
    elif parsed.netloc:
        identifier_type = "browse_url" if is_supported_host(parsed.netloc.lower()) else "unsupported_url"
    else:
        identifier_type = "unknown"
    marketplace_host = parsed.netloc.lower() if parsed.netloc else "www.aliexpress.com"
    supported_host = not parsed.netloc or is_supported_host(marketplace_host)
    if parsed.netloc and not supported_host:
        warnings.append("unsupported_host")
    if item_id is None:
        warnings.append("item_id_not_found")
    return {
        "command": "inspect-identifier",
        "input": identifier,
        "identifier_type": identifier_type,
        "item_id": item_id,
        "url": normalize_item_url(item_id) if item_id else None,
        "marketplace": "aliexpress",
        "marketplace_host": marketplace_host,
        "supported": bool(item_id and supported_host),
        "warnings": warnings,
        "safety": {"network_access": False, "session_required": False},
    }


def require_item_identifier(identifier: str) -> tuple[str, str]:
    inspected = inspect_identifier(identifier)
    if not inspected["supported"] or not inspected["item_id"]:
        raise ValueError(f"Unsupported AliExpress item identifier: {identifier}")
    return inspected["item_id"], inspected["url"]


def validate_browse_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Browse URL must be an absolute AliExpress URL: {url}")
    if parsed.scheme not in {"http", "https"} or not is_supported_host(parsed.netloc.lower()):
        raise ValueError(f"Unsupported AliExpress browse URL: {url}")
    return value
