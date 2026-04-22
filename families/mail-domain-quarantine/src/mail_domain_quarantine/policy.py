from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class QuarantineDecision:
    action: str
    young_domains: list[str]
    reason: str


def decide_quarantine(
    *,
    domain_ages: Iterable[dict[str, Any]],
    trusted_domains: set[str],
    blocklisted_domains: Iterable[str] | None = None,
) -> QuarantineDecision:
    trusted = {domain.lower() for domain in trusted_domains}
    young_domains = sorted(
        {
            str(record.get("domain", "")).lower()
            for record in domain_ages
            if record.get("is_young") is True
            and str(record.get("domain", "")).lower() not in trusted
        }
    )
    listed_domains = sorted(
        {
            str(domain).lower()
            for domain in (blocklisted_domains or [])
            if str(domain).lower() and str(domain).lower() not in trusted
        }
    )
    if young_domains or listed_domains:
        reasons = []
        if young_domains:
            reasons.append(f"young untrusted domains: {', '.join(young_domains)}")
        if listed_domains:
            reasons.append(f"blocklisted domains: {', '.join(listed_domains)}")
        return QuarantineDecision(
            action="quarantine",
            young_domains=young_domains,
            reason="; ".join(reasons),
        )
    return QuarantineDecision(action="allow", young_domains=[], reason="no young untrusted domains")
