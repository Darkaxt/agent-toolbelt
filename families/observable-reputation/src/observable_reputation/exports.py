from __future__ import annotations

import csv
import ipaddress
import json
import uuid
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

CSV_COLUMNS = [
    "type",
    "value",
    "raw_value",
    "domain",
    "source",
    "verdict",
    "score",
    "cached",
    "provider_verdicts",
    "evidence_count",
    "error_count",
    "explanation",
]

STIX_NAMESPACE = uuid.UUID("0e1d1b54-3e92-5b25-86df-9d624a8fd347")


def report_to_csv_text(report: dict[str, Any]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for observable in report.get("observables") or []:
        writer.writerow(csv_row(observable))
    return buffer.getvalue()


def write_csv_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_to_csv_text(report), encoding="utf-8")


def csv_row(observable: dict[str, Any]) -> dict[str, Any]:
    providers = observable.get("providers") or []
    return {
        "type": observable.get("type") or "",
        "value": observable.get("value") or "",
        "raw_value": observable.get("raw_value") or observable.get("value") or "",
        "domain": observable.get("domain") or "",
        "source": observable.get("source") or "",
        "verdict": observable.get("verdict") or "",
        "score": observable.get("score") or 0,
        "cached": bool(observable.get("cached")),
        "provider_verdicts": ";".join(
            f"{provider.get('provider')}:{provider.get('verdict')}" for provider in providers
        ),
        "evidence_count": len(observable.get("evidence") or []),
        "error_count": len(observable.get("errors") or []),
        "explanation": observable.get("explanation") or "",
    }


def report_to_stix_bundle(report: dict[str, Any]) -> dict[str, Any]:
    indicators = [indicator for item in report.get("observables") or [] if (indicator := stix_indicator(item))]
    bundle_seed = "|".join(indicator["id"] for indicator in indicators)
    return {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid5(STIX_NAMESPACE, bundle_seed)}",
        "objects": indicators,
    }


def write_stix_bundle(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_stix_bundle(report), indent=2, ensure_ascii=False), encoding="utf-8")


def stix_indicator(observable: dict[str, Any]) -> dict[str, Any] | None:
    verdict = str(observable.get("verdict") or "")
    if verdict not in {"malicious", "suspicious"}:
        return None
    pattern = stix_pattern(observable)
    if pattern is None:
        return None
    value = str(observable.get("value") or "")
    indicator_seed = f"{observable.get('type')}:{value}"
    indicator_id = f"indicator--{uuid.uuid5(STIX_NAMESPACE, indicator_seed)}"
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    provider_names = [
        provider.get("provider")
        for provider in observable.get("providers") or []
        if provider.get("provider")
    ]
    return {
        "type": "indicator",
        "spec_version": "2.1",
        "id": indicator_id,
        "created": timestamp,
        "modified": timestamp,
        "name": f"{verdict} {observable.get('type')} observable: {value}",
        "indicator_types": ["malicious-activity"] if verdict == "malicious" else ["anomalous-activity"],
        "pattern": pattern,
        "pattern_type": "stix",
        "valid_from": timestamp,
        "x_observable_reputation_score": int(observable.get("score") or 0),
        "x_observable_reputation_verdict": verdict,
        "x_observable_reputation_providers": provider_names,
        "x_observable_reputation_source": observable.get("source") or "",
        "x_observable_reputation_explanation": observable.get("explanation") or "",
    }


def stix_pattern(observable: dict[str, Any]) -> str | None:
    observable_type = observable.get("type")
    value = str(observable.get("value") or "")
    escaped = stix_quote(value)
    if observable_type == "domain":
        return f"[domain-name:value = '{escaped}']"
    if observable_type == "url":
        return f"[url:value = '{escaped}']"
    if observable_type == "ip":
        try:
            version = ipaddress.ip_address(value).version
        except ValueError:
            return None
        stix_type = "ipv4-addr" if version == 4 else "ipv6-addr"
        return f"[{stix_type}:value = '{escaped}']"
    return None


def stix_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
