from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


SKROUTZ_HOSTS = {"www.skroutz.cy", "skroutz.cy"}
PRODUCT_PATH_RE = re.compile(r"^/s/(?P<product_id>\d+)(?:/[^?#]*)?$")


def normalize_product_url(product_id: str, slug: str = "product") -> str:
    safe_slug = slug.strip("/") or "product"
    if not safe_slug.endswith(".html"):
        safe_slug = f"{safe_slug}.html"
    return f"https://www.skroutz.cy/s/{product_id}/{safe_slug}"


def inspect_identifier(identifier: str) -> dict[str, object]:
    raw = str(identifier).strip()
    warnings: list[str] = []
    if re.fullmatch(r"\d+", raw):
        return {
            "command": "inspect-identifier",
            "input": raw,
            "identifier_type": "product_id",
            "supported": True,
            "product_id": raw,
            "normalized_url": normalize_product_url(raw),
            "warnings": warnings,
        }

    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc.lower()
        if host not in SKROUTZ_HOSTS:
            return {
                "command": "inspect-identifier",
                "input": raw,
                "identifier_type": "unsupported_url",
                "supported": False,
                "product_id": None,
                "normalized_url": None,
                "warnings": ["Only skroutz.cy product URLs are supported."],
            }
        match = PRODUCT_PATH_RE.match(parsed.path)
        if not match:
            return {
                "command": "inspect-identifier",
                "input": raw,
                "identifier_type": "unsupported_skroutz_url",
                "supported": False,
                "product_id": None,
                "normalized_url": None,
                "warnings": ["The URL is a Skroutz URL but not a product URL."],
            }
        product_id = match.group("product_id")
        normalized = urlunparse(("https", "www.skroutz.cy", parsed.path, "", "", ""))
        return {
            "command": "inspect-identifier",
            "input": raw,
            "identifier_type": "product_url",
            "supported": True,
            "product_id": product_id,
            "normalized_url": normalized,
            "warnings": warnings,
        }

    return {
        "command": "inspect-identifier",
        "input": raw,
        "identifier_type": "unsupported",
        "supported": False,
        "product_id": None,
        "normalized_url": None,
        "warnings": ["Expected a Skroutz product URL or numeric product id."],
    }


def require_product_identifier(identifier: str) -> tuple[str, str]:
    inspected = inspect_identifier(identifier)
    if not inspected["supported"]:
        warnings = inspected.get("warnings") or []
        reason = warnings[0] if isinstance(warnings, list) and warnings else "Unsupported Skroutz identifier."
        raise ValueError(reason)
    return str(inspected["product_id"]), str(inspected["normalized_url"])
