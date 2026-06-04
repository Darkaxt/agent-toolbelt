from __future__ import annotations

import json
from typing import Any


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_text(payload: dict[str, Any]) -> str:
    command = payload.get("command", "aliexpress")
    lines = [f"{command}"]
    if payload.get("query"):
        lines.append(f"query: {payload['query']}")
    for result in payload.get("results", [])[:10]:
        lines.append(f"- {result.get('title') or result.get('item_id')}: {result.get('price_text') or ''} {result.get('url') or ''}".strip())
    if payload.get("title"):
        lines.append(f"title: {payload['title']}")
    if payload.get("price_summary"):
        lines.append(f"price: {payload['price_summary']}")
    for warning in payload.get("warnings", []):
        lines.append(f"warning: {warning}")
    return "\n".join(lines)

