from __future__ import annotations

import json


def render_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_text(payload: dict) -> str:
    lines: list[str] = []
    if "error" in payload:
        lines.append(f"Error: {payload['error']}")
        if "hint" in payload:
            lines.append(f"Hint: {payload['hint']}")
        return "\n".join(lines)
    if "query" in payload:
        lines.append(f"Query: {payload['query']}")
    if "marketplace" in payload:
        lines.append(f"Marketplace: {payload['marketplace']}")
    if "mode" in payload:
        lines.append(f"Mode: {payload['mode']}")
    if "pagination" in payload:
        pagination = payload["pagination"]
        if "pages_requested" in pagination:
            lines.append(
                "Pagination: "
                f"{pagination.get('pages_fetched', 0)}/{pagination.get('pages_requested', 0)} pages"
            )
        else:
            lines.append(f"Pagination: {pagination.get('pages_fetched', 0)} pages fetched")
    if "results" in payload:
        for item in payload["results"]:
            score = item.get("ranking_score", 0)
            reason = item.get("score_reason", "")
            summary = f"- {item['title']} ({item.get('match_tier', 'unranked')}, score={score}/100)"
            if reason:
                summary += f": {reason}"
            lines.append(summary)
    if "item" in payload:
        lines.append(payload["item"]["title"])
    if payload.get("command") == "reviews":
        summary = payload.get("review_insights", {}).get("summary")
        if summary:
            lines.append(f"Summary: {summary}")
        lines.append(f"Reviews source: {payload.get('reviews_source')}")
        if payload.get("session_status"):
            lines.append(f"Session status: {payload.get('session_status')}")
        if payload.get("session_hint"):
            lines.append(f"Session hint: {payload.get('session_hint')}")
        comments_summary = payload.get("comments_summary") or {}
        if comments_summary:
            available_count = comments_summary.get("available_review_count")
            extracted_count = comments_summary.get("extracted_review_count", 0)
            count_text = f"{extracted_count} extracted"
            if available_count:
                count_text += f" of {available_count} available"
            lines.append(
                "Comments: "
                f"{count_text}, "
                f"average rating {comments_summary.get('average_rating')}, "
                f"verified purchases {comments_summary.get('verified_purchase_count', 0)}"
            )
            countries = comments_summary.get("source_countries") or {}
            if countries:
                lines.append("Countries: " + ", ".join(f"{key}={value}" for key, value in countries.items()))
            positive_terms = comments_summary.get("positive_terms") or []
            if positive_terms:
                lines.append(
                    "Positive terms: "
                    + ", ".join(f"{item['term']}={item['count']}" for item in positive_terms)
                )
            critical_terms = comments_summary.get("critical_terms") or []
            if critical_terms:
                lines.append(
                    "Critical terms: "
                    + ", ".join(f"{item['term']}={item['count']}" for item in critical_terms)
                )
        if payload.get("session_source"):
            lines.append(f"Session source: {payload.get('session_source')}")
        if payload.get("final_url"):
            lines.append(f"Final URL: {payload.get('final_url')}")
        if payload.get("fallback_reason"):
            lines.append(f"Fallback reason: {payload.get('fallback_reason')}")
        for review in payload.get("reviews", []):
            author = review.get("author") or "Unknown"
            title = review.get("title") or ""
            body = review.get("body") or ""
            lines.append(f"- {author}: {title}")
            if body:
                lines.append(f"  {body}")
    if payload.get("command") == "offers":
        if payload.get("asin"):
            lines.append(f"ASIN: {payload['asin']}")
        best_offer = payload.get("best_offer")
        if best_offer:
            lines.append(
                "Best offer: "
                f"{best_offer['marketplace']} {best_offer.get('total') if payload.get('include_shipping') else best_offer.get('price')} "
                f"{best_offer.get('currency')}"
            )
        current_offer = payload.get("current_offer")
        if current_offer:
            lines.append(f"Current marketplace offer: {current_offer['marketplace']} status={current_offer.get('status')}")
        for offer in payload.get("offers", []):
            value = offer.get("total") if payload.get("include_shipping") else offer.get("price")
            lines.append(
                f"- {offer['marketplace']}: status={offer.get('status')}, "
                f"price={offer.get('price')}, shipping={offer.get('shipping')}, total={value}, "
                f"seller_amazon={offer.get('sold_by_amazon')}"
            )
    if "items" in payload and "results" not in payload:
        for item in payload["items"]:
            lines.append(f"- {item['asin']}")
    if "comparison_rows" in payload:
        lines.append("Comparison:")
        for row in payload["comparison_rows"]:
            values = ", ".join(f"{key}={value}" for key, value in row["values"].items())
            lines.append(f"- {row['label']}: {values}")
    if payload.get("command") == "compare" and "items" in payload:
        lines.append("Raw specs:")
        for item in payload["items"]:
            lines.append(f"- {item['marketplace']}:{item['asin']}")
            for label, value in item.get("specs_raw", {}).items():
                lines.append(f"  {label}: {value}")
    if payload.get("command") == "session.bootstrap":
        lines.append(
            f"Session bootstrap for {payload['marketplace']}: "
            f"usable={payload.get('usable')}, source={payload.get('session_source')}"
        )
    return "\n".join(lines)
