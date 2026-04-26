from __future__ import annotations

import argparse
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


SKILLS_SEARCH_URL = "https://skills.sh/api/search"
GITHUB_API_URL = "https://api.github.com"
GITHUB_RAW_URL = "https://raw.githubusercontent.com"
MAX_QUERY_LIMIT = 100
MAX_BODY_EXCERPT = 1200
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "before",
    "build",
    "create",
    "creating",
    "expand",
    "expanding",
    "for",
    "from",
    "helper",
    "in",
    "new",
    "of",
    "on",
    "or",
    "skill",
    "skills",
    "the",
    "to",
    "use",
    "using",
    "with",
    "workflow",
}
OFFICIAL_SOURCES = {
    "astral-sh",
    "google-gemini",
    "openai",
    "microsoft",
    "anthropics",
    "cloudflare",
    "stripe",
    "supabase",
    "vercel",
}


@dataclass
class SearchResult:
    candidates: list[dict[str, Any]]
    capped_queries: list[str]
    warnings: list[str]
    errors: list[str]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-toolbelt-skills-sh-scout")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    scout_parser = subparsers.add_parser("scout", help="Search skills.sh before creating or expanding a skill.")
    scout_parser.add_argument("--workflow", required=True)
    scout_parser.add_argument("--query", action="append", default=[])
    scout_parser.add_argument("--compare-local-skill")
    scout_parser.add_argument("--max-candidates", type=int, default=30)
    scout_parser.add_argument("--max-inspect", type=int, default=5)
    scout_parser.add_argument("--output")
    return parser


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9_.@/+ -]+", " ", value).casefold()).strip()


def tokenize(value: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", normalize_text(value))
    return [token for token in tokens if len(token) >= 2 and token not in STOP_WORDS]


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def build_queries(workflow: str, explicit_queries: list[str] | None = None) -> list[str]:
    queries = [query for query in (explicit_queries or []) if query.strip()]
    normalized = normalize_text(workflow)
    if normalized:
        queries.append(normalized)

    terms = tokenize(workflow)
    for index, term in enumerate(terms):
        queries.append(term)
        if index + 1 < len(terms):
            queries.append(f"{term} {terms[index + 1]}")

    return dedupe_preserve_order(queries)[:20]


def default_http_get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "agent-toolbelt-skills-sh-scout/0.1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def default_http_get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "agent-toolbelt-skills-sh-scout/0.1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def skills_search_url(query: str) -> str:
    return f"{SKILLS_SEARCH_URL}?{urllib.parse.urlencode({'q': query, 'limit': MAX_QUERY_LIMIT})}"


def search_candidates(
    queries: list[str],
    *,
    http_get_json: Callable[[str], dict[str, Any]] = default_http_get_json,
) -> SearchResult:
    by_id: dict[str, dict[str, Any]] = {}
    capped_queries: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    for query in queries:
        try:
            payload = http_get_json(skills_search_url(query))
        except Exception as exc:  # noqa: BLE001 - preserve structured failure instead of raising.
            errors.append(f"skills.sh search failed for query {query!r}: {exc}")
            continue

        skills = payload.get("skills") if isinstance(payload.get("skills"), list) else []
        count = payload.get("count")
        if count == MAX_QUERY_LIMIT or len(skills) >= MAX_QUERY_LIMIT:
            capped_queries.append(query)

        for item in skills:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            candidate_id = str(item["id"])
            existing = by_id.setdefault(
                candidate_id,
                {
                    "id": candidate_id,
                    "skill_id": str(item.get("skillId") or item.get("name") or ""),
                    "name": str(item.get("name") or item.get("skillId") or ""),
                    "source": str(item.get("source") or ""),
                    "installs": int(item.get("installs") or 0),
                    "matched_queries": [],
                    "detail_url": f"https://skills.sh/{candidate_id}",
                },
            )
            existing["installs"] = max(existing["installs"], int(item.get("installs") or 0))
            if query not in existing["matched_queries"]:
                existing["matched_queries"].append(query)

    return SearchResult(
        candidates=sorted(by_id.values(), key=lambda item: (-int(item.get("installs") or 0), item["id"])),
        capped_queries=capped_queries,
        warnings=warnings,
        errors=errors,
    )


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"(?s)^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text)
    if not match:
        return {}, text
    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    return frontmatter, match.group(2)


def choose_skill_path(tree_items: list[dict[str, Any]], candidate: dict[str, Any]) -> str | None:
    skill_names = {
        normalize_text(str(candidate.get("skill_id") or "")),
        normalize_text(str(candidate.get("name") or "")),
        normalize_text(str(candidate.get("id") or "").rsplit("/", 1)[-1]),
    }
    paths = [
        str(item.get("path") or "")
        for item in tree_items
        if item.get("type") in {None, "blob"} and str(item.get("path") or "").endswith("SKILL.md")
    ]

    def score(path: str) -> tuple[int, int, str]:
        parts = [normalize_text(part) for part in path.split("/")]
        folder = parts[-2] if len(parts) >= 2 else ""
        exact = 1 if folder in skill_names else 0
        contains = 1 if any(name and name in normalize_text(path) for name in skill_names) else 0
        return (exact, contains, path)

    if not paths:
        return None
    best = max(paths, key=score)
    best_score = score(best)
    return best if best_score[0] or best_score[1] or len(paths) == 1 else None


def inspect_candidate_sources(
    candidates: list[dict[str, Any]],
    *,
    max_inspect: int,
    http_get_json: Callable[[str], dict[str, Any]] = default_http_get_json,
    http_get_text: Callable[[str], str] = default_http_get_text,
) -> list[dict[str, Any]]:
    inspected: list[dict[str, Any]] = []
    for candidate in candidates[: max(0, max_inspect)]:
        source = str(candidate.get("source") or "")
        if source.count("/") != 1:
            inspected.append({"id": candidate.get("id"), "ok": False, "warning": "candidate source is not a GitHub owner/repo"})
            continue
        try:
            repo_payload = http_get_json(f"{GITHUB_API_URL}/repos/{source}")
            branch = str(repo_payload.get("default_branch") or "main")
            tree_payload = http_get_json(f"{GITHUB_API_URL}/repos/{source}/git/trees/{urllib.parse.quote(branch, safe='')}?recursive=1")
            path = choose_skill_path(tree_payload.get("tree") if isinstance(tree_payload.get("tree"), list) else [], candidate)
            if not path:
                inspected.append({"id": candidate.get("id"), "ok": False, "warning": "no matching SKILL.md found"})
                continue
            raw_url = f"{GITHUB_RAW_URL}/{source}/{urllib.parse.quote(branch, safe='')}/{urllib.parse.quote(path, safe='/')}"
            text = http_get_text(raw_url)
            frontmatter, body = parse_frontmatter(text)
            inspected.append(
                {
                    "id": candidate.get("id"),
                    "ok": True,
                    "source": source,
                    "branch": branch,
                    "skill_path": path,
                    "frontmatter": frontmatter,
                    "description": frontmatter.get("description", ""),
                    "body_excerpt": normalize_excerpt(body),
                }
            )
        except Exception as exc:  # noqa: BLE001 - partial inspection should not fail search.
            inspected.append({"id": candidate.get("id"), "ok": False, "warning": f"source inspection failed: {exc}"})
    return inspected


def normalize_excerpt(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:MAX_BODY_EXCERPT]


def install_score(installs: int) -> int:
    if installs <= 0:
        return 0
    return min(10, int(math.log10(installs + 1) * 4))


def rank_candidates(
    workflow: str,
    candidates: list[dict[str, Any]],
    *,
    inspected_by_id: dict[str, dict[str, Any]] | None = None,
    compare_local_skill: str | None = None,
) -> list[dict[str, Any]]:
    inspected_by_id = inspected_by_id or {}
    workflow_terms = set(tokenize(workflow))
    if compare_local_skill:
        workflow_terms.update(tokenize(compare_local_skill))

    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        inspected = inspected_by_id.get(str(candidate.get("id")))
        text_parts = [
            str(candidate.get("id") or ""),
            str(candidate.get("name") or ""),
            str(candidate.get("skill_id") or ""),
            str(candidate.get("source") or ""),
        ]
        if inspected:
            text_parts.extend(
                [
                    str(inspected.get("description") or ""),
                    str(inspected.get("body_excerpt") or ""),
                ]
            )
            candidate["description"] = inspected.get("description") or candidate.get("description", "")
        elif candidate.get("description"):
            text_parts.append(str(candidate["description"]))

        candidate_terms = set(tokenize(" ".join(text_parts)))
        overlap = sorted(workflow_terms.intersection(candidate_terms))
        source_owner = str(candidate.get("source") or "").split("/", 1)[0].casefold()

        score = 0
        reasons: list[str] = []
        if overlap:
            score += len(overlap) * 8
            reasons.append(f"term overlap: {', '.join(overlap[:6])}")
        name_exact = normalize_text(str(candidate.get("name") or "")) in workflow_terms
        query_exact = any(normalize_text(str(candidate.get("name") or "")) == normalize_text(query) for query in candidate.get("matched_queries") or [])
        if name_exact:
            score += 18
            reasons.append("candidate name exactly matches workflow term")
        if query_exact:
            score += 12
            reasons.append("candidate name matched a query")
        if inspected and inspected.get("ok"):
            score += 8
            reasons.append("public SKILL.md inspected")
        if source_owner in OFFICIAL_SOURCES:
            score += 10
            reasons.append("source owner appears official")
        if workflow_terms and not overlap:
            score -= 20
            reasons.append("no meaningful workflow overlap")
        score += install_score(int(candidate.get("installs") or 0))

        if score >= 30 and (len(overlap) >= 2 or (overlap and (name_exact or query_exact))):
            classification = "direct"
        elif score >= 12 and overlap:
            classification = "partial"
        else:
            classification = "false_positive"

        enriched = dict(candidate)
        enriched.update(
            {
                "score": score,
                "score_reasons": reasons,
                "classification": classification,
            }
        )
        ranked.append(enriched)

    return sorted(
        ranked,
        key=lambda item: (
            {"direct": 0, "partial": 1, "false_positive": 2}[item["classification"]],
            -int(item["score"]),
            -int(item.get("installs") or 0),
            str(item["id"]),
        ),
    )


def choose_recommendation(ranked: list[dict[str, Any]], *, compare_local_skill: str | None = None) -> dict[str, Any]:
    direct = [item for item in ranked if item["classification"] == "direct"]
    partial = [item for item in ranked if item["classification"] == "partial"]
    if direct:
        best = direct[0]
        if compare_local_skill:
            category = "Use public skill as inspiration"
            summary = f"Direct public candidate found for comparison with {compare_local_skill}."
        else:
            category = "Install public skill"
            summary = "A direct public candidate appears to cover the requested workflow."
        return {
            "category": category,
            "candidate_id": best["id"],
            "summary": summary,
            "rationale": best.get("score_reasons", [])[:5],
        }
    if partial:
        best = partial[0]
        return {
            "category": "Use public skill as inspiration" if not compare_local_skill else "Improve existing local skill",
            "candidate_id": best["id"],
            "summary": "Only partial public matches were found; use them for feature inspiration rather than replacement.",
            "rationale": best.get("score_reasons", [])[:5],
        }
    return {
        "category": "Create new skill",
        "candidate_id": None,
        "summary": "No meaningful public alternative was found.",
        "rationale": [],
    }


def build_scout_report(
    *,
    workflow: str,
    explicit_queries: list[str] | None = None,
    compare_local_skill: str | None = None,
    max_candidates: int = 30,
    max_inspect: int = 5,
    http_get_json: Callable[[str], dict[str, Any]] = default_http_get_json,
    http_get_text: Callable[[str], str] = default_http_get_text,
) -> dict[str, Any]:
    queries = build_queries(workflow, explicit_queries)
    search_result = search_candidates(queries, http_get_json=http_get_json)
    preliminary_ranked = rank_candidates(
        workflow,
        search_result.candidates,
        inspected_by_id={},
        compare_local_skill=compare_local_skill,
    )
    inspected = inspect_candidate_sources(
        preliminary_ranked,
        max_inspect=max_inspect,
        http_get_json=http_get_json,
        http_get_text=http_get_text,
    )
    inspected_by_id = {str(item.get("id")): item for item in inspected if item.get("ok")}
    ranked = rank_candidates(
        workflow,
        search_result.candidates,
        inspected_by_id=inspected_by_id,
        compare_local_skill=compare_local_skill,
    )[: max(1, max_candidates)]
    warnings = list(search_result.warnings)
    warnings.extend(str(item["warning"]) for item in inspected if item.get("warning"))

    return {
        "ok": not search_result.errors,
        "operation": "scout",
        "workflow": workflow,
        "compare_local_skill": compare_local_skill,
        "queries": queries,
        "capped_queries": search_result.capped_queries,
        "candidate_count": len(search_result.candidates),
        "candidates": ranked,
        "inspected_candidates": inspected,
        "recommendation": choose_recommendation(ranked, compare_local_skill=compare_local_skill),
        "warnings": warnings,
        "errors": search_result.errors,
    }
