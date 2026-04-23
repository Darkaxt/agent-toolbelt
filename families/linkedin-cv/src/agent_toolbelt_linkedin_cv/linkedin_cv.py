from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
import os
import re
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse

from agent_toolbelt_core.common import windows_local_tools_dir
from bs4 import BeautifulSoup

try:  # pragma: no cover - exercised in live use, not unit tests.
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - keeps parser/tests importable without browsers.
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


HOME_ENV = "LINKEDIN_CV_HOME"
DEFAULT_TIMEOUT_SEC = 300
REQUEST_REPLAY_MAX_WORKERS = 10
LOGIN_URL = "https://www.linkedin.com/login"
OWN_PROFILE_URL = "https://www.linkedin.com/in/me/"
PROFILE_HOSTS = {"linkedin.com", "www.linkedin.com"}
PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,120}$")
DISALLOWED_PATH_PREFIXES = (
    "/feed",
    "/search",
    "/mynetwork",
    "/jobs",
    "/company",
    "/school",
    "/sales",
    "/recruiter",
    "/messaging",
    "/notifications",
    "/groups",
    "/learning",
    "/pulse",
)
READ_ONLY_EXPANSION_SELECTORS = (
    "button[aria-expanded='false']:has-text('Show more')",
    "button[aria-expanded='false']:has-text('See more')",
    "button[aria-expanded='false']:has-text('Mostrar mas')",
    "button[aria-expanded='false']:has-text('Mostrar más')",
    "button[aria-expanded='false']:has-text('Ver mas')",
    "button[aria-expanded='false']:has-text('Ver más')",
    "button[aria-expanded='false']:has-text('Mehr anzeigen')",
    "button[aria-expanded='false']:has-text('Voir plus')",
)
AUTH_MARKER_SELECTORS = (
    "a[href*='/in/'][data-test-global-nav-link='me']",
    "img.global-nav__me-photo",
    "button.global-nav__primary-link-me-menu-trigger",
    "a[href*='/mynetwork/']",
)
SECTION_ALIASES = {
    "about": {"about", "acerca de", "sobre", "info", "zusammenfassung", "a propos", "a propos"},
    "experience": {"experience", "experiencia", "experiencia laboral", "berufserfahrung", "experiences", "expérience"},
    "education": {"education", "educacion", "educación", "ausbildung", "formation"},
    "licenses_certifications": {
        "licenses & certifications",
        "licenses and certifications",
        "licencias y certificaciones",
        "certifications",
        "certificaciones",
        "zertifikate",
        "certificats",
    },
    "skills": {"skills", "aptitudes", "habilidades", "kenntnisse", "competences", "compétences"},
    "projects": {"projects", "proyectos", "projekte", "projets"},
    "publications": {"publications", "publicaciones", "veröffentlichungen"},
    "languages": {"languages", "idiomas", "sprachen", "langues"},
    "recommendations": {"recommendations", "recomendaciones", "empfehlungen", "recommandations"},
}
LIST_SECTIONS = {
    "experience",
    "education",
    "licenses_certifications",
    "skills",
    "projects",
    "publications",
    "languages",
    "recommendations",
}
SECTION_KEYS = tuple(SECTION_ALIASES.keys())
SHOW_ALL_TEXTS = (
    "Show all",
    "See all",
    "Mostrar mas",
    "Mostrar más",
    "Ver mas",
    "Ver más",
    "Mehr anzeigen",
    "Voir tout",
    "Voir plus",
)
DETAIL_ROUTE_FRAGMENTS = {
    "about": "summary",
    "experience": "experience",
    "education": "education",
    "licenses_certifications": "certifications",
    "skills": "skills",
    "projects": "projects",
    "publications": "publications",
    "languages": "languages",
    "recommendations": "recommendations",
}
STRUCTURED_RECORD_SECTIONS = {"education", "experience", "licenses_certifications", "projects"}
EDUCATION_SCREEN_ID = "com.linkedin.sdui.flagshipnav.profile.ProfileEducationDetails"
EXPERIENCE_SCREEN_ID = "com.linkedin.sdui.flagshipnav.profile.ProfileExperienceDetails"
CERTIFICATIONS_SCREEN_ID = "com.linkedin.sdui.flagshipnav.profile.ProfileCertificationDetails"
PROJECTS_SCREEN_ID = "com.linkedin.sdui.flagshipnav.profile.ProfileProjectDetails"
SKILLS_SCREEN_ID = "com.linkedin.sdui.flagshipnav.profile.ProfileSkillDetails"
LANGUAGES_SCREEN_ID = "com.linkedin.sdui.flagshipnav.profile.ProfileLanguageDetails"
REQUESTED_ARGUMENTS_TYPE = "proto.sdui.actions.requests.RequestedArguments"
REQUEST_METADATA_TYPE = "proto.sdui.common.RequestMetadata"
NETWORK_TEXT_KEYS = (
    "title",
    "name",
    "headline",
    "companyName",
    "company",
    "organizationName",
    "organization",
    "schoolName",
    "school",
    "degreeName",
    "fieldOfStudy",
    "issuerName",
    "issuer",
    "description",
    "summary",
    "text",
    "occupation",
    "localizedName",
)
SECTION_COUNT_RE = re.compile(r"^(?P<label>.+?)\s*\((?P<count>\d+)\)\s*$")
EDUCATION_RSC_PAGER_ID = "com.linkedin.sdui.pagers.profile.details.education"
EXPERIENCE_RSC_PAGER_ID = "com.linkedin.sdui.pagers.profile.details.experience"
CERTIFICATIONS_RSC_PAGER_ID = "com.linkedin.sdui.pagers.profile.details.certifications"
PROJECTS_RSC_PAGER_ID = "com.linkedin.sdui.pagers.profile.details.projects"
SKILLS_RSC_PAGER_ID = "com.linkedin.sdui.pagers.profile.details.skills"
LANGUAGES_RSC_PAGER_ID = "com.linkedin.sdui.pagers.profile.details.languages"
SKILLS_RSC_PATH = "/flagship-web/rsc-action/actions/pagination"
EDUCATION_PAGINATION_URL = f"https://www.linkedin.com{SKILLS_RSC_PATH}?sduiid={EDUCATION_RSC_PAGER_ID}"
EXPERIENCE_PAGINATION_URL = f"https://www.linkedin.com{SKILLS_RSC_PATH}?sduiid={EXPERIENCE_RSC_PAGER_ID}"
CERTIFICATIONS_PAGINATION_URL = f"https://www.linkedin.com{SKILLS_RSC_PATH}?sduiid={CERTIFICATIONS_RSC_PAGER_ID}"
PROJECTS_PAGINATION_URL = f"https://www.linkedin.com{SKILLS_RSC_PATH}?sduiid={PROJECTS_RSC_PAGER_ID}"
SKILLS_PAGINATION_URL = f"https://www.linkedin.com{SKILLS_RSC_PATH}?sduiid={SKILLS_RSC_PAGER_ID}"
LANGUAGES_PAGINATION_URL = f"https://www.linkedin.com{SKILLS_RSC_PATH}?sduiid={LANGUAGES_RSC_PAGER_ID}"
SKILLS_RSC_BLOCK_RE = re.compile(
    r'componentKey":"com\.linkedin\.sdui\.profile\.skill\([^"]+\)".*?(?=componentKey":"com\.linkedin\.sdui\.profile\.skill\(|$)',
    re.DOTALL,
)
SKILLS_RSC_BOLD_TITLE_RE = re.compile(
    r'"fontWeight":"bold".{0,4000}?"children":\["((?:[^"\\]|\\.)+)"\]',
    re.DOTALL,
)
SKILLS_RSC_ARIA_LABEL_RE = re.compile(r'aria-label":"Edit ((?:[^"\\]|\\.)+?) skill"')
SKILLS_RSC_PAGINATION_REQUEST_RE = re.compile(
    r'"((?:[^"\\]|\\.)*proto\.sdui\.actions\.requests\.PaginationRequest(?:[^"\\]|\\.)*)"',
    re.DOTALL,
)
COMO_POINTER_RE = re.compile(r"^\$L[0-9A-Za-z]+$")
SKILLS_RSC_PAGER_CHILD_RE = re.compile(
    rf'(?m)^[0-9a-z]+:\[.*?"observabilityIdentifier":"{re.escape(SKILLS_RSC_PAGER_ID)}".*?"children":"(\$L[0-9A-Za-z]+)".*$'
)
SKILLS_RSC_LAZY_CHILD_RE = re.compile(r'"children":\["\$undefined","(\$L[0-9A-Za-z]+)"')
LANGUAGES_RSC_ENTRY_RE = re.compile(
    r'\["\$","p",null,\{.*?"children":\["((?:[^"\\]|\\.)+)"\]\}\],\["\$","p",null,\{.*?"children":\["((?:[^"\\]|\\.)+)"\]\}\]',
    re.DOTALL,
)
RSC_CHILDREN_TEXT_RE = re.compile(r'"children":\["((?:[^"\\]|\\.)+)"\]')
EXPERIENCE_EDIT_LABEL_RE = re.compile(r'aria-label":"Edit ((?:[^"\\]|\\.)+?) at ((?:[^"\\]|\\.)+?)"')
LICENSE_EDIT_LABEL_RE = re.compile(r'aria-label":"Edit ((?:[^"\\]|\\.)+?) certification"')
PROJECT_EDIT_LABEL_RE = re.compile(r'aria-label":"Edit project ((?:[^"\\]|\\.)+?)"')
EDUCATION_EDIT_FORM_URL_RE = re.compile(r"/details/education/edit/forms/\d+/")
EXPERIENCE_EDIT_FORM_URL_RE = re.compile(r"/details/experience/edit/forms/\d+/")
CERTIFICATIONS_EDIT_FORM_URL_RE = re.compile(r"/details/certifications/edit/forms/\d+/")
PROJECTS_EDIT_FORM_URL_RE = re.compile(r"/details/projects/edit/forms/\d+/")
COMPANY_URL_RE = re.compile(r"https://www\.linkedin\.com/company/\d+/")
SCHOOL_URL_RE = re.compile(r"https://www\.linkedin\.com/school/\d+/")
EXTERNAL_URL_RE = re.compile(r"https?://[^\"'\\\s]+")
ROLE_LOCATION_MARKERS = ("remote", "hybrid", "on-site", "onsite")
EMPLOYMENT_TYPE_MARKERS = (
    "full-time",
    "part-time",
    "contract",
    "freelance",
    "self-employed",
    "internship",
    "apprenticeship",
    "temporary",
    "seasonal",
)
MONTH_ABBREVIATIONS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
STRUCTURED_RECORD_FIELDS: dict[str, tuple[str, ...]] = {
    "education": (
        "school",
        "school_url",
        "degree",
        "field_of_study",
        "date_range",
        "start_date_text",
        "end_date_text",
        "grade",
        "activities",
        "description",
        "raw_lines",
    ),
    "projects": (
        "name",
        "date_range",
        "start_date_text",
        "end_date_text",
        "is_current",
        "associated_with",
        "project_url",
        "description",
        "raw_lines",
    ),
    "experience": (
        "title",
        "company",
        "company_url",
        "employment_type",
        "date_range",
        "start_date_text",
        "end_date_text",
        "is_current",
        "duration",
        "location",
        "description",
        "raw_lines",
    ),
    "licenses_certifications": (
        "name",
        "issuer",
        "issue_date_text",
        "expiration_date_text",
        "credential_id",
        "credential_url",
        "description",
        "raw_lines",
    ),
}
FORM_STATE_STRING_RE_TEMPLATE = (
    r'"\$type"\s*:\s*"proto\.sdui\.StateKey"\s*,\s*"value"\s*:\s*"[^"]*__SUFFIX__"'
    r'.*?"value"\s*:\s*\{\s*"\$case"\s*:\s*"stringValue"\s*,\s*"stringValue"\s*:\s*"(.*?)"\s*\}'
)
FORM_STATE_DATE_RE_TEMPLATE = (
    r'"\$type"\s*:\s*"proto\.sdui\.StateKey"\s*,\s*"value"\s*:\s*"[^"]*__SUFFIX__"'
    r'.*?"value"\s*:\s*\{\s*"\$case"\s*:\s*"dateValue"\s*,\s*"dateValue"\s*:\s*\{\s*"\$type"\s*:\s*"proto\.sdui\.common\.Date"\s*,\s*"day"\s*:\s*(\d+)\s*,\s*"month"\s*:\s*(\d+)\s*,\s*"year"\s*:\s*(\d+)\s*\}\s*\}'
)
RSC_LABEL_ENTRY_RE = re.compile(r"(?ms)^([0-9a-z]+):(.*?)(?=^[0-9a-z]+:|\Z)")
EXPERIENCE_EMPLOYMENT_OPTION_RE = re.compile(r'\{"label"\s*:\s*"([^"]+)"\s*,\s*"value"\s*:\s*"([^"]*)"\}')
EMBEDDED_RSC_LABEL_RE = re.compile(r'(?<![\w$])(?:[0-9a-z]+):(?:T[0-9A-Za-z]+,|I\[|\[|")')
DEFAULT_HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def make_result(
    *,
    ok: bool,
    operation: str,
    result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    stderr: str = "",
    exit_code: int = 0,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "operation": operation,
        "result": result or {},
        "warnings": warnings or [],
        "stderr": stderr,
        "exit_code": exit_code,
    }


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def resolve_app_home(explicit_home: str | None = None) -> Path:
    if explicit_home:
        return Path(explicit_home).expanduser().resolve()
    env_value = os.getenv(HOME_ENV)
    if env_value:
        return Path(env_value).expanduser().resolve()
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "agent-toolbelt" / "linkedin-cv"
    tools_dir = windows_local_tools_dir()
    if tools_dir is not None:
        return tools_dir.parent / "agent-toolbelt" / "linkedin-cv"
    return Path.home() / ".local" / "share" / "agent-toolbelt" / "linkedin-cv"


def sanitize_profile_name(profile_name: str) -> str:
    stripped = profile_name.strip()
    if not stripped or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", stripped):
        raise ValueError("Profile names may contain only letters, numbers, dots, dashes, and underscores.")
    return stripped


def profile_storage_dir(app_home: str | Path | None, profile_name: str) -> Path:
    return resolve_app_home(str(app_home) if app_home is not None else None) / "profiles" / sanitize_profile_name(profile_name)


def snapshot_storage_dir(app_home: str | Path | None) -> Path:
    return resolve_app_home(str(app_home) if app_home is not None else None) / "snapshots"


def session_state_path(app_home: str | Path | None, profile_name: str) -> Path:
    return resolve_app_home(str(app_home) if app_home is not None else None) / "sessions" / f"{sanitize_profile_name(profile_name)}.json"


def _load_session_state(state_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _cookie_matches_url(cookie: dict[str, Any], url: str) -> bool:
    if not isinstance(cookie, dict):
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    domain = str(cookie.get("domain") or "").lower().lstrip(".")
    if not domain or (host != domain and not host.endswith(f".{domain}")):
        return False
    cookie_path = str(cookie.get("path") or "/") or "/"
    request_path = parsed.path or "/"
    normalized_cookie_path = cookie_path if cookie_path.endswith("/") else f"{cookie_path}/"
    if request_path != cookie_path and not request_path.startswith(normalized_cookie_path):
        return False
    expires = cookie.get("expires")
    if isinstance(expires, (int, float)) and expires > 0 and expires < time.time():
        return False
    return True


def _build_cookie_header(session_state: dict[str, Any], url: str) -> str:
    pairs: list[str] = []
    for cookie in session_state.get("cookies", []):
        if not _cookie_matches_url(cookie, url):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if not name:
            continue
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _extract_csrf_token(session_state: dict[str, Any]) -> str:
    for cookie in session_state.get("cookies", []):
        if not isinstance(cookie, dict):
            continue
        if str(cookie.get("name") or "") != "JSESSIONID":
            continue
        return unquote(str(cookie.get("value") or "")).strip('"')
    return ""


def build_profile_url(*, profile_id: str | None = None, url: str | None = None) -> str:
    if url:
        return validate_profile_url(url)
    if not profile_id:
        raise ValueError("Provide --profile-id or --url.")
    slug = profile_id.strip().strip("/")
    if not PROFILE_ID_RE.fullmatch(slug):
        raise ValueError("LinkedIn profile IDs must be a single /in/<profile-id> slug.")
    return f"https://www.linkedin.com/in/{slug}/"


def validate_profile_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("LinkedIn profile URL must use https.")
    host = parsed.netloc.lower()
    if host not in PROFILE_HOSTS:
        raise ValueError("Only linkedin.com profile URLs are supported.")
    path = re.sub(r"/+", "/", parsed.path or "/")
    lower_path = path.lower().rstrip("/")
    for prefix in DISALLOWED_PATH_PREFIXES:
        if lower_path == prefix or lower_path.startswith(prefix + "/"):
            raise ValueError("Only one explicit LinkedIn /in/<profile-id> page is supported; crawling surfaces are blocked.")
    match = re.fullmatch(r"/in/([^/]+)/?", path)
    if not match:
        raise ValueError("Only individual LinkedIn /in/<profile-id> URLs are supported.")
    slug = match.group(1)
    if not PROFILE_ID_RE.fullmatch(slug):
        raise ValueError("LinkedIn profile URL contains an unsupported profile ID.")
    return f"https://www.linkedin.com/in/{slug}/"


def profile_id_from_url(profile_url: str) -> str:
    match = re.fullmatch(r"https://www\.linkedin\.com/in/([^/]+)/", profile_url)
    return match.group(1) if match else "unknown"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _norm_key(text: str) -> str:
    normalized = _norm(text).lower()
    normalized = normalized.replace("&", "and")
    return normalized.strip(":-")


def _all_text(node) -> str:
    return _norm(" ".join(node.stripped_strings))


def _visible_texts(node) -> list[str]:
    texts: list[str] = []
    for element in node.find_all(["h1", "h2", "h3", "li", "span", "div", "p"], recursive=True):
        text = _all_text(element)
        if not text:
            continue
        lowered = text.lower()
        if lowered in {"show more", "see more", "mostrar mas", "mostrar más", "ver mas", "ver más"}:
            continue
        if text not in texts:
            texts.append(text)
    return texts


def _headline_block_noise(text: str) -> bool:
    lowered = _norm_key(text)
    exact_noisy_phrases = {
        "resources",
        "account",
        "manage",
        "settings and privacy",
        "settings privacy",
        "help",
        "language",
        "sign out",
        "premium features",
        "posts and activity",
        "job posting account",
    }
    if lowered in exact_noisy_phrases:
        return True
    prefix_noisy_phrases = (
        "notifications",
        "view profile",
        "0 notifications",
    )
    return any(lowered.startswith(phrase) for phrase in prefix_noisy_phrases)


def _looks_like_headline(text: str, *, name: str) -> bool:
    normalized = _norm(text)
    if not normalized or normalized == name:
        return False
    if len(normalized) < 20:
        return False
    if _headline_block_noise(normalized):
        return False
    if _norm_key(normalized) in set().union(*SECTION_ALIASES.values()):
        return False
    return True


def _looks_like_location(text: str) -> bool:
    normalized = _norm(text)
    if not normalized or len(normalized) < 6:
        return False
    if _headline_block_noise(normalized):
        return False
    if "·" in normalized:
        return False
    return "," in normalized


def _detect_visibility_status(soup: BeautifulSoup) -> str:
    text = _all_text(soup).lower()
    if soup.select("form[action*='login'], form[action*='uas/login'], input[name='session_key']"):
        return "sign_in_required"
    if "checkpoint" in text or "security verification" in text or soup.select("form[action*='checkpoint']"):
        return "checkpoint_required"
    if "unusual activity" in text or "temporarily restricted" in text:
        return "blocked"
    if "profile is not available" in text or "this profile is not available" in text:
        return "unavailable"
    return "ok"


def _detect_visibility_status_from_url(url: str) -> str:
    parsed = urlparse(url or "")
    path = (parsed.path or "").lower()
    if "/checkpoint" in path:
        return "checkpoint_required"
    if "/login" in path or "/uas/login" in path:
        return "sign_in_required"
    return "ok"


def _extract_canonical_profile_url(soup: BeautifulSoup, *, profile_url: str, capture_type: str, name: str) -> str:
    if capture_type != "own_profile" or not profile_url.endswith("/in/me/"):
        return profile_url
    candidates: list[tuple[str, str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href.startswith("https://www.linkedin.com/in/"):
            continue
        try:
            candidate = validate_profile_url(href)
        except ValueError:
            continue
        anchor_text = _all_text(anchor)
        aria_label = _norm(anchor.get("aria-label", ""))
        candidates.append((candidate, anchor_text, aria_label))
        if name and (name in anchor_text or name in aria_label):
            return candidate
    if candidates:
        return candidates[0][0]
    return profile_url


def _extract_name(soup: BeautifulSoup) -> str:
    for selector in ("main h1", "h1", ".text-heading-xlarge"):
        node = soup.select_one(selector)
        if node:
            text = _all_text(node)
            if text:
                return text
    title = soup.find("title")
    if title:
        return _norm(title.get_text().split("|")[0])
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href.startswith("https://www.linkedin.com/in/"):
            continue
        aria_label = _norm(anchor.get("aria-label", ""))
        if aria_label:
            return aria_label
        texts = _visible_texts(anchor)
        if texts:
            return texts[0]
    return ""


def _extract_headline_near_name(soup: BeautifulSoup, name: str) -> str:
    if not name:
        return ""
    for node in soup.find_all(["h1", "h2", "p", "span", "div"]):
        if _all_text(node) != name:
            continue
        containers = [node.parent]
        if node.parent is not None:
            containers.append(node.parent.parent)
        seen: set[int] = set()
        for container in containers:
            if container is None or id(container) in seen:
                continue
            seen.add(id(container))
            texts = _visible_texts(container)
            if name in texts:
                texts = texts[texts.index(name) + 1 :]
            for text in texts:
                if _looks_like_headline(text, name=name):
                    return text
    return ""


def _extract_headline(soup: BeautifulSoup, name: str) -> str:
    adjacent = _extract_headline_near_name(soup, name)
    if adjacent:
        return adjacent
    selectors = (
        ".text-body-medium.break-words",
        ".top-card-layout h2",
        ".pv-text-details__left-panel div.text-body-medium",
        ".pv-top-card-profile-picture__container ~ div p",
    )
    for selector in selectors:
        for node in soup.select(selector):
            text = _all_text(node)
            if _looks_like_headline(text, name=name):
                return text
    return ""


def _extract_location_near_name(soup: BeautifulSoup, *, name: str, headline: str) -> str:
    if not name:
        return ""
    for node in soup.find_all(["h1", "h2", "p", "span", "div"]):
        if _all_text(node) != name:
            continue
        containers = [node.parent]
        if node.parent is not None:
            containers.append(node.parent.parent)
        if node.parent is not None and node.parent.parent is not None:
            containers.append(node.parent.parent.parent)
        seen: set[int] = set()
        for container in containers:
            if container is None or id(container) in seen:
                continue
            seen.add(id(container))
            texts = _visible_texts(container)
            for text in texts:
                if text in {name, headline}:
                    continue
                if _looks_like_location(text):
                    return text
    return ""


def _extract_location(soup: BeautifulSoup, *, name: str = "", headline: str = "") -> str:
    adjacent = _extract_location_near_name(soup, name=name, headline=headline)
    if adjacent:
        return adjacent
    for selector in (
        ".top-card__subline-item",
        ".text-body-small.inline.t-black--light.break-words",
        "span.text-body-small",
        ".pv-text-details__left-panel .text-body-small",
    ):
        node = soup.select_one(selector)
        if node:
            text = _all_text(node)
            if _looks_like_location(text):
                return text
    return ""


def _section_key_for_heading(text: str) -> str | None:
    heading = re.sub(r"\s*\(\d+\)\s*$", "", _norm(text or ""))
    heading = _norm_key(heading)
    for key, aliases in SECTION_ALIASES.items():
        if heading in aliases:
            return key
    return None


def _extract_section_count_from_html(html: str, *, section_key: str) -> int | None:
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.find_all(["h2", "h3", "div", "span"]):
        text = _all_text(node)
        if not text:
            continue
        match = SECTION_COUNT_RE.match(text)
        if not match:
            continue
        if _section_key_for_heading(match.group("label")) != section_key:
            continue
        try:
            return int(match.group("count"))
        except ValueError:
            return None
    return None


def _extract_sections(soup: BeautifulSoup) -> dict[str, str | list[str]]:
    extracted: dict[str, str | list[str]] = {key: ([] if key in LIST_SECTIONS else "") for key in SECTION_ALIASES}
    scores: dict[str, int] = {key: -1 for key in SECTION_ALIASES}
    for section in soup.find_all(["section", "li", "div"]):
        heading_node = section.find(["h2", "h3"])
        if not heading_node:
            continue
        section_key = _section_key_for_heading(_all_text(heading_node))
        if section_key is None:
            continue
        texts = _visible_texts(section)
        heading_text = _all_text(heading_node)
        texts = [text for text in texts if _norm_key(text) != _norm_key(heading_text)]
        candidate: str | list[str]
        if section_key in LIST_SECTIONS:
            candidate = _dedupe_texts(texts)
        else:
            candidate = _norm(" ".join(texts))
        candidate_score = _section_score(candidate)
        if candidate_score <= scores[section_key]:
            continue
        extracted[section_key] = candidate
        scores[section_key] = candidate_score
    return extracted


def _extract_text_without_expand_controls(node: Any) -> str:
    fragment = BeautifulSoup(str(node), "html.parser")
    for selector in (
        "[data-testid='expandable-text-button']",
        "button[aria-hidden='true']",
    ):
        for element in fragment.select(selector):
            element.decompose()
    return _norm(" ".join(fragment.stripped_strings))


def _extract_about_from_container(container: Any) -> str:
    best_text = ""
    for node in container.select("[data-testid='expandable-text-box']"):
        text = _extract_text_without_expand_controls(node)
        if len(text) > len(best_text):
            best_text = text
    if best_text:
        return best_text
    for paragraph in container.find_all(["p", "span", "div"], recursive=True):
        text = _extract_text_without_expand_controls(paragraph)
        if not text:
            continue
        lowered = _norm_key(text)
        if lowered in {"about", "edit", "edit about", "top skills"}:
            continue
        if len(text) > len(best_text):
            best_text = text
    return best_text


def _extract_about_section(soup: BeautifulSoup) -> str:
    best_text = ""
    for heading in soup.find_all(["h2", "h3"]):
        if _section_key_for_heading(_all_text(heading)) != "about":
            continue
        current = heading.parent
        depth = 0
        while current is not None and getattr(current, "name", None) in {"section", "li", "div"} and depth < 6:
            text = _extract_about_from_container(current)
            if len(text) > len(best_text):
                best_text = text
            current = current.parent
            depth += 1
    return best_text


def parse_profile_html(html: str, *, profile_url: str, capture_type: str) -> dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")
    status = _detect_visibility_status(soup)
    name = _extract_name(soup)
    canonical_profile_url = _extract_canonical_profile_url(
        soup,
        profile_url=profile_url,
        capture_type=capture_type,
        name=name,
    )
    headline = _extract_headline(soup, name)
    sections = _extract_sections(soup)
    about_text = _extract_about_section(soup)
    if _has_section_content(about_text):
        sections["about"] = about_text
    profile_id = profile_id_from_url(canonical_profile_url)
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "capture_type": capture_type,
        "profile_id": profile_id,
        "profile_url": canonical_profile_url,
        "captured_at": utc_now(),
        "visibility": {"status": status},
        "status": status,
        "name": name,
        "headline": headline,
        "location": _extract_location(soup, name=name, headline=headline),
        "about": sections["about"],
        "experience": sections["experience"],
        "education": sections["education"],
        "licenses_certifications": sections["licenses_certifications"],
        "skills": sections["skills"],
        "projects": sections["projects"],
        "publications": sections["publications"],
        "languages": sections["languages"],
        "recommendations": sections["recommendations"],
    }
    return snapshot


def _empty_section_value(section_key: str) -> str | list[str]:
    return [] if section_key in LIST_SECTIONS else ""


def _normalize_record_list(section_key: str, value: Any) -> list[dict[str, Any]]:
    fields = STRUCTURED_RECORD_FIELDS.get(section_key, ())
    if not fields:
        return []
    if isinstance(value, dict):
        items = [value]
    elif isinstance(value, list):
        items = [item for item in value if isinstance(item, dict)]
    else:
        return []
    normalized_records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        normalized: dict[str, Any] = {}
        for field in fields:
            raw = item.get(field)
            if field == "raw_lines":
                if isinstance(raw, list):
                    normalized[field] = _dedupe_texts([str(entry) for entry in raw if _norm(str(entry))])
                else:
                    normalized[field] = []
            elif field == "description":
                if isinstance(raw, str):
                    normalized[field] = "\n".join(_norm(part) for part in raw.splitlines() if _norm(part))
                else:
                    normalized[field] = _norm(str(raw or ""))
            elif field == "is_current":
                normalized[field] = bool(raw)
            else:
                normalized[field] = _norm(str(raw or ""))
        if not any(_norm(str(normalized.get(field, ""))) for field in fields if field not in {"raw_lines", "is_current"}):
            continue
        record_key = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
        if record_key in seen:
            continue
        seen.add(record_key)
        normalized_records.append(normalized)
    return normalized_records


def _section_value_text(value: Any) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        for nested in value.values():
            text = _section_value_text(nested)
            if text:
                parts.append(text)
        return _norm(" ".join(parts))
    if isinstance(value, list):
        parts = [_section_value_text(item) for item in value]
        return _norm(" ".join(part for part in parts if part))
    return _norm(str(value or ""))


def _has_section_content(value: str | list[str] | None) -> bool:
    if isinstance(value, list):
        return any(_section_value_text(item) for item in value)
    if isinstance(value, dict):
        return bool(_section_value_text(value))
    return bool(_norm(str(value or "")))


def _section_score(value: str | list[str] | None) -> int:
    if isinstance(value, list):
        texts = [_section_value_text(item) for item in value]
        return len([text for text in texts if text]) * 100 + sum(len(text) for text in texts if text)
    if isinstance(value, dict):
        return len(_section_value_text(value))
    return len(_norm(str(value or "")))


def _dedupe_texts(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        normalized = _norm(value)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _coerce_section_value(section_key: str, value: Any) -> str | list[str]:
    if section_key in STRUCTURED_RECORD_SECTIONS:
        records = _normalize_record_list(section_key, value)
        if records:
            return records
        if isinstance(value, list):
            return _dedupe_texts([str(item) for item in value if _norm(str(item))])
        if isinstance(value, str):
            normalized = _norm(value)
            return [normalized] if normalized else []
        if value is None:
            return []
        return _dedupe_texts([str(value)])
    if section_key in LIST_SECTIONS:
        if isinstance(value, list):
            return _dedupe_texts([str(item) for item in value])
        if isinstance(value, str):
            normalized = _norm(value)
            return [normalized] if normalized else []
        if value is None:
            return []
        return _dedupe_texts([str(value)])
    if isinstance(value, list):
        return _norm(" ".join(str(item) for item in value if _norm(str(item))))
    return _norm(str(value or ""))


def _payload_item_to_text(value: Any) -> str:
    if isinstance(value, str):
        return _norm(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _norm(str(value))
    if isinstance(value, list):
        return _norm(" ".join(filter(None, (_payload_item_to_text(item) for item in value))))
    if isinstance(value, dict):
        parts: list[str] = []
        for key in NETWORK_TEXT_KEYS:
            raw = value.get(key)
            text = _payload_item_to_text(raw)
            if text and text not in parts:
                parts.append(text)
        if not parts:
            for raw in value.values():
                text = _payload_item_to_text(raw)
                if text and text not in parts:
                    parts.append(text)
        return _norm(" - ".join(parts[:3]))
    return ""


def _coerce_payload_section(section_key: str, value: Any) -> str | list[str]:
    if section_key in LIST_SECTIONS:
        if isinstance(value, list):
            return _dedupe_texts([_payload_item_to_text(item) for item in value])
        text = _payload_item_to_text(value)
        return [text] if text else []
    return _payload_item_to_text(value)


def _normalize_network_sections(payload: Any) -> dict[str, str | list[str]]:
    extracted: dict[str, str | list[str]] = {key: _empty_section_value(key) for key in SECTION_KEYS}

    def visit(node: Any):
        if isinstance(node, dict):
            for key, value in node.items():
                mapped_key = _section_key_for_heading(str(key))
                if mapped_key is not None:
                    candidate = _coerce_payload_section(mapped_key, value)
                    if _has_section_content(candidate) and _section_score(candidate) > _section_score(extracted[mapped_key]):
                        extracted[mapped_key] = candidate
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return extracted


def merge_profile_snapshots(
    inline_snapshot: dict[str, Any],
    *,
    detail_snapshots: list[dict[str, Any]] | None = None,
    network_sections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(inline_snapshot)
    merged["capture_depth"] = "deep"
    section_sources: dict[str, str] = {}
    for section_key in SECTION_KEYS:
        current_value = _coerce_section_value(section_key, merged.get(section_key, _empty_section_value(section_key)))
        merged[section_key] = current_value
        section_sources[section_key] = "inline_dom" if _has_section_content(current_value) else "missing"

    for detail_snapshot in detail_snapshots or []:
        for field in ("name", "headline", "location"):
            if not merged.get(field) and detail_snapshot.get(field):
                merged[field] = detail_snapshot[field]
        for section_key in SECTION_KEYS:
            candidate = _coerce_section_value(section_key, detail_snapshot.get(section_key, _empty_section_value(section_key)))
            if not _has_section_content(candidate):
                continue
            merged[section_key] = candidate
            section_sources[section_key] = "detail_dom"

    for section_key, raw_candidate in (network_sections or {}).items():
        if section_key not in SECTION_KEYS:
            continue
        candidate = _coerce_section_value(section_key, raw_candidate)
        if not _has_section_content(candidate):
            continue
        if section_sources[section_key] == "detail_dom" and not (
            section_key in STRUCTURED_RECORD_SECTIONS
            and isinstance(candidate, list)
            and candidate
            and isinstance(candidate[0], dict)
            and not (isinstance(merged[section_key], list) and merged[section_key] and isinstance(merged[section_key][0], dict))
        ):
            continue
        if section_sources[section_key] == "missing" or _section_score(candidate) > _section_score(merged[section_key]):
            merged[section_key] = candidate
            section_sources[section_key] = "network"

    merged["section_sources"] = section_sources
    return merged


DETAIL_ROUTE_STOP_MARKERS = {
    "ad options",
    "about",
    "accessibility",
    "talent solutions",
    "community guidelines",
    "careers",
    "marketing solutions",
    "privacy and terms",
    "ad choices",
    "advertising",
    "sales solutions",
    "mobile",
    "small business",
    "safety center",
    "profile language",
    "questions?",
}
LANGUAGE_PROFICIENCY_MARKERS = (
    "proficiency",
    "fluency",
    "native",
    "bilingual",
    "elementary",
    "limited",
    "professional",
    "working",
)
DETAIL_ROUTE_WAIT_SELECTORS = {
    "experience": ("a[href*='/details/experience/edit/forms/']",),
    "education": ("a[href*='/details/education/edit/forms/']",),
    "licenses_certifications": ("a[href*='/details/certifications/edit/forms/']",),
    "skills": ("a[href*='/details/skills/edit/forms/']",),
    "projects": ("a[href*='/details/projects/']",),
    "languages": ("a[href*='/details/languages/edit/forms/']",),
    "recommendations": ("main",),
}


def _detail_route_anchor_items(soup: BeautifulSoup, section_key: str) -> list[str]:
    fragment = DETAIL_ROUTE_FRAGMENTS.get(section_key)
    if not fragment:
        return []
    edit_pattern = re.compile(rf"/details/{re.escape(fragment)}/edit/forms/", re.IGNORECASE)
    items: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not edit_pattern.search(href):
            continue
        text = _all_text(anchor)
        if text:
            items.append(text)
            continue
        aria_label = _norm(anchor.get("aria-label", ""))
        if section_key == "skills" and aria_label.lower().startswith("edit ") and aria_label.lower().endswith(" skill"):
            items.append(aria_label[5:-6])
    return _dedupe_texts(items)


def _detail_route_body_lines(soup: BeautifulSoup, section_key: str) -> list[str]:
    body = soup.body or soup
    lines = [_norm(line) for line in body.get_text("\n").splitlines()]
    lines = [line for line in lines if line]
    start_index = None
    for index, line in enumerate(lines):
        if _section_key_for_heading(line) == section_key:
            start_index = index + 1
            break
    if start_index is None:
        return []
    collected: list[str] = []
    for line in lines[start_index:]:
        normalized_key = _section_key_for_heading(line)
        normalized_line = _norm_key(line)
        if normalized_line in DETAIL_ROUTE_STOP_MARKERS:
            break
        if normalized_key is not None and normalized_key != section_key:
            break
        collected.append(line)
    return collected


def extract_detail_route_section(html: str, *, section_key: str) -> str | list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    anchor_items = _detail_route_anchor_items(soup, section_key)
    if section_key in LIST_SECTIONS:
        if anchor_items:
            return anchor_items
        if section_key == "skills":
            return []
        lines = _detail_route_body_lines(soup, section_key)
        if section_key == "languages":
            items: list[str] = []
            index = 0
            while index < len(lines):
                current = lines[index]
                next_line = lines[index + 1] if index + 1 < len(lines) else ""
                if next_line and any(marker in next_line.lower() for marker in LANGUAGE_PROFICIENCY_MARKERS):
                    items.append(f"{current} - {next_line}")
                    index += 2
                    continue
                if current != "… more":
                    items.append(current)
                index += 1
            return _dedupe_texts(items)
        if section_key == "recommendations":
            filtered = [line for line in lines if line not in {"Received", "Given"}]
            return _dedupe_texts(filtered)
        filtered = [line for line in _detail_route_body_lines(soup, section_key) if line != "… more"]
        return _dedupe_texts(filtered)
    if anchor_items:
        return _norm(" ".join(anchor_items))
    return _norm(" ".join(_detail_route_body_lines(soup, section_key)))


def _wait_for_detail_route_content(page: Any, section_key: str) -> str:
    for selector in DETAIL_ROUTE_WAIT_SELECTORS.get(section_key, ("main",)):
        try:
            if page.locator(selector).first().is_visible(timeout=5000):
                return selector
        except Exception:
            continue
    return ""


def _capture_ready_detail_html(page: Any, section_key: str, *, timeout_sec: int = 6) -> str:
    deadline = time.monotonic() + timeout_sec
    last_html = _safe_page_content(page)
    unchanged_polls = 0
    while time.monotonic() < deadline:
        if _has_section_content(extract_detail_route_section(last_html, section_key=section_key)):
            return last_html
        time.sleep(0.5)
        current_html = _safe_page_content(page)
        if current_html == last_html:
            unchanged_polls += 1
            if unchanged_polls >= 2:
                return current_html
        else:
            unchanged_polls = 0
        last_html = current_html
    return last_html


def _safe_page_content(page: Any, *, timeout_sec: float = 5.0, poll_interval: float = 0.2) -> str:
    deadline = time.monotonic() + timeout_sec
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return page.content()
        except Exception as exc:
            last_exc = exc
            message = _norm_key(str(exc))
            if not any(marker in message for marker in ("page is navigating", "changing the content", "unable to retrieve content")):
                raise
            time.sleep(poll_interval)
    if last_exc is not None:
        raise last_exc
    return page.content()


def _capture_ready_main_html(page: Any, *, profile_url: str, capture_type: str, timeout_sec: int = 6) -> str:
    deadline = time.monotonic() + timeout_sec
    richness_deadline = time.monotonic() + min(3.0, max(timeout_sec / 2, 1.0))
    last_html = _safe_page_content(page)
    unchanged_polls = 0
    while time.monotonic() < deadline:
        inline_snapshot = parse_profile_html(last_html, profile_url=profile_url, capture_type=capture_type)
        visible_section_hits = sum(
            1
            for section_key in ("experience", "education", "licenses_certifications", "skills", "projects", "languages")
            if _has_section_content(inline_snapshot.get(section_key))
        )
        section_count_hits = sum(
            1
            for section_key in ("experience", "education", "licenses_certifications", "skills", "projects", "languages")
            if _extract_section_count_from_html(last_html, section_key=section_key) is not None
        )
        route_count = len(_extract_detail_route_urls_from_html(last_html))
        if _has_section_content(inline_snapshot.get("about")):
            return last_html
        if time.monotonic() >= richness_deadline and (
            visible_section_hits >= 2 or (section_count_hits >= 2 and route_count >= 2)
        ):
            return last_html
        time.sleep(0.5)
        current_html = _safe_page_content(page)
        if current_html == last_html:
            unchanged_polls += 1
            if unchanged_polls >= 2:
                return current_html
        else:
            unchanged_polls = 0
        last_html = current_html
    return last_html


def _default_playwright_factory():
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed. Install the linkedin-cv package dependencies.")
    return sync_playwright()


def _expand_read_only_sections(page: Any) -> list[str]:
    clicked: list[str] = []
    for selector in READ_ONLY_EXPANSION_SELECTORS:
        try:
            locator = page.locator(selector).first()
            if locator.is_visible(timeout=250):
                locator.click(timeout=1000)
                clicked.append(selector)
        except Exception:
            continue
    return clicked


def _launch_context(playwright: Any, profile_dir: Path, *, headless: bool = False):
    profile_dir.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(profile_dir),
        headless=headless,
        viewport={"width": 1440, "height": 1200},
    )


def _launch_capture_context(playwright: Any, *, state_path: Path):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        storage_state=str(state_path),
        viewport={"width": 1440, "height": 1200},
    )
    return browser, context


def _save_snapshot(snapshot: dict[str, Any], *, app_home: str | Path | None, capture_type: str) -> Path:
    root = snapshot_storage_dir(app_home) / capture_type
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(
        f"{snapshot.get('profile_url')}:{snapshot.get('captured_at')}".encode("utf-8")
    ).hexdigest()[:10]
    path = root / f"{snapshot.get('profile_id', 'profile')}-{digest}.json"
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _save_raw_html(html: str, *, app_home: str | Path | None, profile_id: str) -> Path:
    root = snapshot_storage_dir(app_home) / "raw-html"
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{profile_id}:{utc_now()}".encode("utf-8")).hexdigest()[:10]
    path = root / f"{profile_id}-{digest}.html"
    path.write_text(html, encoding="utf-8")
    return path


def _save_raw_network_payloads(
    records: list[dict[str, Any]],
    *,
    app_home: str | Path | None,
    profile_id: str,
) -> Path:
    root = snapshot_storage_dir(app_home) / "raw-network"
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{profile_id}:{utc_now()}".encode("utf-8")).hexdigest()[:10]
    path = root / f"{profile_id}-{digest}.json"
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _sanitize_record_url(url: str) -> str:
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return url
    filtered_query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "parentSpanId"]
    return urlunparse(parsed._replace(query=urlencode(filtered_query)))


def _resolve_profile_relative_url(base_url: str, candidate: str) -> str:
    normalized_candidate = _norm(candidate)
    if not normalized_candidate:
        return ""
    if normalized_candidate.startswith(("http://", "https://")):
        return normalized_candidate
    parsed_base = urlparse(base_url or "")
    if normalized_candidate.startswith("/details/") and parsed_base.path.startswith("/in/"):
        path_parts = [part for part in parsed_base.path.split("/") if part]
        if len(path_parts) >= 2:
            profile_root = f"/{path_parts[0]}/{path_parts[1]}"
            return urlunparse(parsed_base._replace(path=profile_root + normalized_candidate))
    return urljoin(base_url, normalized_candidate)


def _request_with_session(
    *,
    state_path: Path,
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    referer: str | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> tuple[int, str, str]:
    session_state = _load_session_state(state_path)
    headers = {
        "user-agent": DEFAULT_HTTP_USER_AGENT,
        "accept-language": "en-US,en;q=0.9",
        "cookie": _build_cookie_header(session_state, url),
    }
    data = None
    if payload is None:
        headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    else:
        headers["accept"] = "text/x-component"
        headers["content-type"] = "application/json"
        headers["origin"] = "https://www.linkedin.com"
        headers["referer"] = referer or url
        csrf_token = _extract_csrf_token(session_state)
        if csrf_token:
            headers["csrf-token"] = csrf_token
        data = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(url, data=data, headers={key: value for key, value in headers.items() if value}, method=method)
    try:
        with urllib_request.urlopen(request, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8", errors="replace")
            return int(getattr(response, "status", 200)), str(response.geturl()), body
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), str(exc.geturl()), body


def _get_response_content_type(response: Any) -> str:
    headers = getattr(response, "headers", {}) or {}
    if isinstance(headers, dict):
        return str(headers.get("content-type", ""))
    return ""


def _is_skills_rsc_pagination_response(url: str, body: str) -> bool:
    parsed = urlparse(url or "")
    if parsed.path != SKILLS_RSC_PATH:
        return False
    lowered_url = (url or "").lower()
    lowered_body = (body or "").lower()
    return SKILLS_RSC_PAGER_ID in lowered_url or SKILLS_RSC_PAGER_ID in lowered_body


def _decode_quoted_fragment(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return value


def _extract_skills_from_rsc_text(body: str) -> list[str]:
    skills: list[str] = []
    for block in SKILLS_RSC_BLOCK_RE.findall(body or ""):
        match = SKILLS_RSC_BOLD_TITLE_RE.search(block)
        if match:
            skill = _norm(_decode_quoted_fragment(match.group(1)))
            if skill and skill not in skills:
                skills.append(skill)
            continue
        aria_match = SKILLS_RSC_ARIA_LABEL_RE.search(block)
        if aria_match:
            skill = _norm(_decode_quoted_fragment(aria_match.group(1)))
            if skill and skill not in skills:
                skills.append(skill)
    return skills


def _extract_languages_from_rsc_text(body: str) -> list[str]:
    languages: list[str] = []
    for segment in (body or "").split('"viewName":"languages-edit-button"'):
        matches = LANGUAGES_RSC_ENTRY_RE.findall(segment[-2500:])
        if not matches:
            continue
        language_name, proficiency = matches[-1]
        normalized_name = _norm(_decode_quoted_fragment(language_name))
        normalized_proficiency = _norm(_decode_quoted_fragment(proficiency))
        if not normalized_name or not normalized_proficiency:
            continue
        if not any(marker in normalized_proficiency.lower() for marker in LANGUAGE_PROFICIENCY_MARKERS):
            continue
        entry = f"{normalized_name} - {normalized_proficiency}"
        if entry not in languages:
            languages.append(entry)
    return languages


def _looks_like_role_location(text: str) -> bool:
    normalized = _norm(text)
    lowered = _norm_key(text)
    return _looks_like_location(normalized) or lowered in ROLE_LOCATION_MARKERS


def _looks_like_skill_summary(text: str) -> bool:
    lowered = _norm_key(text)
    return lowered.startswith("skills for ") or lowered == "skills" or lowered == "skills:" or " skill" in lowered


def _looks_like_employment_meta(text: str) -> bool:
    lowered = _norm_key(text)
    return any(marker in lowered for marker in EMPLOYMENT_TYPE_MARKERS)


def _looks_like_date_range_text(text: str) -> bool:
    normalized = _norm(text)
    lowered = _norm_key(text)
    if lowered.startswith(("issued ", "expires ", "credential id", "credential url")):
        return False
    if re.search(r"\b\d{4}\b", normalized) and any(separator in normalized for separator in (" - ", " – ", " — ")):
        return True
    return bool(re.search(r"\b\d{4}\b", normalized) and "present" in lowered)


def _split_date_range_and_duration(text: str) -> tuple[str, str]:
    normalized = _norm(text)
    parts = [part.strip() for part in normalized.split("·") if _norm(part)]
    if not parts:
        return "", ""
    date_range = parts[0]
    duration = parts[1] if len(parts) > 1 else ""
    return _norm(date_range), _norm(duration)


def _split_date_range_bounds(text: str) -> tuple[str, str]:
    normalized = _norm(text)
    parts = [part.strip() for part in re.split(r"\s[-–—]\s", normalized, maxsplit=1) if _norm(part)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return normalized, ""


def _split_education_degree_and_field(text: str) -> tuple[str, str]:
    normalized = _norm(text)
    if not normalized:
        return "", ""
    if "," not in normalized:
        return normalized, ""
    if "degree," in _norm_key(normalized):
        degree, field = normalized.split(",", 1)
        return _norm(degree), _norm(field)
    degree, field = normalized.rsplit(",", 1)
    return _norm(degree), _norm(field)


def _is_current_date_text(text: str) -> bool:
    lowered = _norm_key(text)
    return any(marker in lowered for marker in ("present", "actualidad", "current"))


def _extract_rsc_text_lines(chunk: str) -> list[str]:
    lines: list[str] = []
    for raw in RSC_CHILDREN_TEXT_RE.findall(chunk or ""):
        decoded = _decode_quoted_fragment(raw)
        for piece in str(decoded).splitlines():
            normalized = _norm(piece)
            if not normalized:
                continue
            lowered = _norm_key(normalized)
            if lowered in {
                "edit experience",
                "edit certification",
                "edit certifications",
                "navigate back to profile main screen",
            }:
                continue
            if normalized not in lines:
                lines.append(normalized)
    return lines


def _entry_chunks_from_matches(body: str, matches: list[re.Match[str]], *, lookbehind_chars: int = 2500) -> list[tuple[re.Match[str], str]]:
    chunks: list[tuple[re.Match[str], str]] = []
    for index, match in enumerate(matches):
        start = max(0, match.start() - lookbehind_chars)
        if index:
            start = max(start, matches[index - 1].end())
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        chunks.append((match, body[start:end]))
    return chunks


def _extract_rsc_entity_item_blocks(body: str) -> list[str]:
    blocks: list[str] = []
    source = body or ""
    marker = '["{\\"key\\":\\"'
    index = 0
    while True:
        start = source.find(marker, index)
        if start < 0:
            break
        end = _consume_edit_form_rsc_bracketed(source, start)
        if end <= start:
            break
        blocks.append(source[start:end])
        index = end
    return blocks


def _normalize_location_line(line: str) -> str:
    segments = [_norm(part) for part in str(line or "").split("·") if _norm(part)]
    if len(segments) >= 2 and _norm_key(segments[-1]) in ROLE_LOCATION_MARKERS:
        return segments[0]
    return _norm(line)


def _extract_credential_url_from_chunk(chunk: str) -> str:
    urls = [_norm(url) for url in EXTERNAL_URL_RE.findall(chunk or "") if _norm(url)]
    for url in urls:
        if "/safety/go/?url=" in url:
            return url
    for url in urls:
        lowered = url.lower()
        if "linkedin.com/company/" in lowered or "linkedin.com/school/" in lowered or "linkedin.com/in/" in lowered:
            continue
        return url
    return ""


def _extract_description_and_raw_lines(lines: list[str], *, consumed: set[str]) -> tuple[str, list[str]]:
    description_lines: list[str] = []
    raw_lines: list[str] = []
    for line in lines:
        if line in consumed or _looks_like_skill_summary(line):
            continue
        if len(line) >= 35 or line.endswith("."):
            description_lines.append(line)
            consumed.add(line)
            continue
        raw_lines.append(line)
    return "\n".join(description_lines), _dedupe_texts(raw_lines)


def _extract_education_entry_bundles_from_rsc_text(body: str) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    matches: list[re.Match[str]] = []
    for match in EDUCATION_EDIT_FORM_URL_RE.finditer(body or ""):
        url = match.group(0)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        matches.append(match)
    source = body or ""
    for index, url_match in enumerate(matches):
        context_start = max(0, url_match.start() - 1200)
        if index:
            context_start = max(context_start, matches[index - 1].end())
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        prefix = source[context_start:url_match.start()]
        suffix = source[url_match.end():content_end]
        lines = _extract_rsc_text_lines(suffix)
        if not lines:
            continue
        school_url_matches = SCHOOL_URL_RE.findall(prefix)
        if not school_url_matches:
            school_url_matches = SCHOOL_URL_RE.findall(suffix)
        school_url = school_url_matches[-1] if school_url_matches else ""
        school = lines[0] if lines else ""
        degree = ""
        field_of_study = ""
        date_range = ""
        raw_lines: list[str] = []
        for line in lines[1:]:
            if not degree and not _looks_like_date_range_text(line):
                degree, field_of_study = _split_education_degree_and_field(line)
                continue
            if not date_range and _looks_like_date_range_text(line):
                date_range = line
                continue
            if line not in raw_lines:
                raw_lines.append(line)
        start_date_text, end_date_text = _split_date_range_bounds(date_range)
        bundles.append(
            {
                "edit_form_url": _norm(url_match.group(0)),
                "record": {
                    "school": school,
                    "school_url": school_url,
                    "degree": degree,
                    "field_of_study": field_of_study,
                    "date_range": _norm(date_range),
                    "start_date_text": start_date_text,
                    "end_date_text": end_date_text,
                    "grade": "",
                    "activities": "",
                    "description": "",
                    "raw_lines": _dedupe_texts(raw_lines),
                },
            }
        )
    if bundles:
        return bundles
    seen_schools: set[str] = set()
    for block in _extract_rsc_entity_item_blocks(body):
        lines = [line for line in _extract_rsc_text_lines(block) if line != "Education"]
        if not lines:
            continue
        school = lines[0]
        school_key = _norm_key(school)
        if not school or school_key in seen_schools:
            continue
        seen_schools.add(school_key)
        school_urls = COMPANY_URL_RE.findall(block)
        school_urls = SCHOOL_URL_RE.findall(block) or school_urls
        school_url = school_urls[-1] if school_urls else ""
        degree = ""
        field_of_study = ""
        date_range = ""
        raw_lines: list[str] = []
        for line in lines[1:]:
            if not degree and not _looks_like_date_range_text(line):
                degree, field_of_study = _split_education_degree_and_field(line)
                continue
            if not date_range and _looks_like_date_range_text(line):
                date_range = line
                continue
            if line not in raw_lines:
                raw_lines.append(line)
        start_date_text, end_date_text = _split_date_range_bounds(date_range)
        bundles.append(
            {
                "edit_form_url": "",
                "record": {
                    "school": school,
                    "school_url": school_url,
                    "degree": degree,
                    "field_of_study": field_of_study,
                    "date_range": _norm(date_range),
                    "start_date_text": start_date_text,
                    "end_date_text": end_date_text,
                    "grade": "",
                    "activities": "",
                    "description": "",
                    "raw_lines": _dedupe_texts(raw_lines),
                },
            }
        )
    return bundles


def _extract_project_entry_bundles_from_rsc_text(body: str) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    matches: list[re.Match[str]] = []
    source = body or ""
    for match in PROJECTS_EDIT_FORM_URL_RE.finditer(source):
        url = match.group(0)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        matches.append(match)
    for index, url_match in enumerate(matches):
        chunk_start = max(0, url_match.start() - 12000)
        if index:
            chunk_start = max(chunk_start, matches[index - 1].end())
        suffix = source[chunk_start:url_match.start()]
        label_matches = list(PROJECT_EDIT_LABEL_RE.finditer(suffix))
        name = ""
        if label_matches:
            name = _norm(_decode_quoted_fragment(label_matches[-1].group(1)))
        lines = [
            line
            for line in _extract_rsc_text_lines(suffix)
            if line != "Projects"
            and line != "Skills:"
            and not line.startswith("$")
            and not _norm_key(line).startswith("edit project ")
        ]
        if not lines:
            continue
        date_range = ""
        associated_with = ""
        raw_lines: list[str] = []
        if not name:
            meaningful_lines = [
                line
                for line in lines
                if not _looks_like_date_range_text(line) and not _norm_key(line).startswith("associated with ")
            ]
            name = meaningful_lines[-1] if meaningful_lines else ""
        for line in reversed(lines):
            if not associated_with and _norm_key(line).startswith("associated with "):
                associated_with = _norm(line[len("Associated with ") :])
                continue
            if not date_range and _looks_like_date_range_text(line):
                date_range = line
                continue
        consumed = {item for item in (name, date_range) if item}
        if associated_with:
            consumed.add(f"Associated with {associated_with}")
        for line in lines:
            if line in consumed:
                continue
            if line not in raw_lines:
                raw_lines.append(line)
        if not name:
            continue
        start_date_text, end_date_text = _split_date_range_bounds(date_range)
        bundles.append(
            {
                "edit_form_url": _norm(url_match.group(0)),
                "record": {
                    "name": name,
                    "date_range": _norm(date_range),
                    "start_date_text": start_date_text,
                    "end_date_text": end_date_text,
                    "is_current": _is_current_date_text(end_date_text or date_range),
                    "associated_with": associated_with,
                    "project_url": "",
                    "description": "",
                    "raw_lines": _dedupe_texts(raw_lines),
                },
            }
        )
    if bundles:
        return bundles
    seen_names: set[str] = set()
    for block in _extract_rsc_entity_item_blocks(source):
        lines = [
            line
            for line in _extract_rsc_text_lines(block)
            if line != "Projects"
            and line != "Skills:"
            and not line.startswith("$")
            and not _norm_key(line).startswith("associated skills")
        ]
        if not lines:
            continue
        index = 0
        while index < len(lines):
            name = lines[index]
            if not name or _looks_like_date_range_text(name):
                index += 1
                continue
            if index + 1 >= len(lines) or not _looks_like_date_range_text(lines[index + 1]):
                index += 1
                continue
            date_range = lines[index + 1]
            index += 2
            associated_with = ""
            raw_lines: list[str] = []
            while index < len(lines):
                line = lines[index]
                lowered = _norm_key(line)
                if index + 1 < len(lines) and _looks_like_date_range_text(lines[index + 1]):
                    break
                if not associated_with and lowered.startswith("associated with "):
                    associated_with = _norm(line[len("Associated with ") :])
                elif line not in raw_lines:
                    raw_lines.append(line)
                index += 1
            name_key = _norm_key(name)
            if not name or name_key in seen_names:
                continue
            seen_names.add(name_key)
            start_date_text, end_date_text = _split_date_range_bounds(date_range)
            bundles.append(
                {
                    "edit_form_url": "",
                    "record": {
                        "name": name,
                        "date_range": _norm(date_range),
                        "start_date_text": start_date_text,
                        "end_date_text": end_date_text,
                        "is_current": _is_current_date_text(end_date_text or date_range),
                        "associated_with": associated_with,
                        "project_url": "",
                        "description": "",
                        "raw_lines": _dedupe_texts(raw_lines),
                    },
                }
            )
    return bundles


def _merge_project_bundle_with_edit_form(
    *,
    bundle: dict[str, Any],
    state_path: Path,
    referer: str,
    timeout_sec: int,
) -> dict[str, Any]:
    record = dict(bundle.get("record", {}))
    edit_form_url = _resolve_profile_relative_url(referer, _norm(str(bundle.get("edit_form_url", ""))))
    if not edit_form_url:
        return record
    edit_status, edit_final_url, edit_html = _request_with_session(
        state_path=state_path,
        url=edit_form_url,
        referer=referer,
        timeout_sec=timeout_sec,
    )
    edit_url_status = _detect_visibility_status_from_url(edit_final_url or edit_form_url)
    if edit_status >= 400 or edit_url_status != "ok":
        return record
    edit_visibility_status = _detect_visibility_status(BeautifulSoup(edit_html or "", "html.parser"))
    if edit_visibility_status != "ok":
        return record
    return _merge_project_record(record, edit_html)


def _parse_edit_form_rehydration(html: str) -> dict[str, Any]:
    assignment_value = _extract_json_assignment_value(html or "", "window.__como_rehydration__")
    entries = [part for part in assignment_value if isinstance(part, str)] if isinstance(assignment_value, list) else []
    stream = "".join(entries)
    labels: dict[str, str] = {}
    index = 0
    length = len(stream)
    while index < length:
        match = re.match(r"([0-9a-z]+):", stream[index:])
        if not match:
            index += 1
            continue
        label = match.group(1)
        payload_start = index + len(label) + 1
        payload, next_index = _consume_edit_form_rsc_payload(stream, payload_start)
        if next_index <= payload_start:
            index += 1
            continue
        labels.setdefault(label, payload.rstrip("\n"))
        index = next_index
    return {
        "entries": entries,
        "labels": labels,
        "raw_text": stream,
    }


def _consume_edit_form_rsc_payload(stream: str, start: int) -> tuple[str, int]:
    if start >= len(stream):
        return "", start
    if stream.startswith("T", start):
        length_match = re.match(r"T([0-9A-Fa-f]+),", stream[start:])
        if length_match:
            text_length = int(length_match.group(1), 16)
            payload_start = start + len(length_match.group(0))
            text_payload, payload_end = _slice_rehydration_text_by_encoded_length(stream, payload_start, text_length)
            return f"T{length_match.group(1)},{text_payload}", payload_end
    if stream[start] == '"':
        end = _consume_edit_form_rsc_string(stream, start)
        return stream[start:end], end
    prefixed_bracket_match = re.match(r"[A-Za-z$]+(?=[\[{])", stream[start:])
    bracket_start = start
    if prefixed_bracket_match:
        bracket_start = start + len(prefixed_bracket_match.group(0))
    if bracket_start < len(stream) and stream[bracket_start] in "[{":
        end = _consume_edit_form_rsc_bracketed(stream, bracket_start)
        if end > bracket_start:
            return stream[start:end], end
    primitive_match = re.match(r"(?:\$undefined|null|true|false|-?\d+(?:\.\d+)?)", stream[start:])
    if primitive_match:
        end = start + len(primitive_match.group(0))
        return stream[start:end], end
    newline_index = stream.find("\n", start)
    if newline_index == -1:
        return stream[start:], len(stream)
    return stream[start:newline_index], newline_index


def _consume_edit_form_rsc_string(stream: str, start: int) -> int:
    escaped = False
    index = start + 1
    while index < len(stream):
        char = stream[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char == '"':
            return index + 1
        index += 1
    return len(stream)


def _consume_edit_form_rsc_bracketed(stream: str, start: int) -> int:
    closing = {"]": "[", "}": "{"}
    stack = [stream[start]]
    escaped = False
    in_string = False
    index = start + 1
    while index < len(stream):
        char = stream[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            index += 1
            continue
        if char in "[{":
            stack.append(char)
            index += 1
            continue
        if char in "]}" and stack and closing.get(char) == stack[-1]:
            stack.pop()
            index += 1
            if not stack:
                return index
            continue
        index += 1
    return len(stream)


def _slice_rehydration_text_by_encoded_length(stream: str, start: int, target_length: int) -> tuple[str, int]:
    consumed = 0
    index = start
    while index < len(stream) and consumed < target_length:
        char = stream[index]
        encoded_length = len(char.encode("utf-8"))
        if consumed + encoded_length > target_length:
            break
        consumed += encoded_length
        index += 1
    return stream[start:index], index


def _normalize_rehydrated_text(text: str) -> str:
    def flush_paragraph(lines: list[str], blocks: list[str]) -> None:
        if not lines:
            return
        normalized_lines: list[str] = []
        for index, line in enumerate(lines):
            if not normalized_lines:
                normalized_lines.append(line)
                continue
            previous = normalized_lines[-1]
            previous_tail = previous.rsplit(" ", 1)[-1]
            current_head_match = re.match(r"[a-z]+", line)
            current_head = current_head_match.group(0) if current_head_match else ""
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if previous and previous[-1].isalnum() and line[0].islower():
                if len(previous_tail) <= 4 or len(current_head) <= 2:
                    normalized_lines[-1] = previous + line
                    continue
                if len(line) <= 4 and next_line and next_line[0].islower():
                    normalized_lines.append(line)
                    continue
                normalized_lines[-1] = previous + " " + line
                continue
            normalized_lines.append(line)
        blocks.append("\n".join(normalized_lines))

    normalized_blocks: list[str] = []
    paragraph_lines: list[str] = []
    for raw_line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            flush_paragraph(paragraph_lines, normalized_blocks)
            paragraph_lines = []
            continue
        if re.match(r"^(?:[-*•]\s+|\d+[.)]\s+)", stripped):
            flush_paragraph(paragraph_lines, normalized_blocks)
            paragraph_lines = []
            normalized_blocks.append(stripped)
            continue
        paragraph_lines.append(stripped)
    flush_paragraph(paragraph_lines, normalized_blocks)
    return "\n\n".join(part for part in normalized_blocks if part)


def _edit_form_resolve_text(parsed: dict[str, Any], value: str) -> str:
    normalized = "\n".join(_norm(part) for part in str(value or "").splitlines() if _norm(part))
    if not normalized or normalized == "$undefined":
        return ""
    if not normalized.startswith("$"):
        return _normalize_rehydrated_text(normalized)
    payload = str(parsed.get("labels", {}).get(normalized[1:], "") or "")
    if not payload:
        return ""
    if payload.startswith("T"):
        _prefix, separator, text = payload.partition(",")
        if not separator:
            return ""
        embedded_match = EMBEDDED_RSC_LABEL_RE.search(text)
        if embedded_match:
            text = text[: embedded_match.start()]
        return _normalize_rehydrated_text(text)
    if payload.startswith('"'):
        try:
            decoded = json.loads(payload)
        except Exception:
            return ""
        return _normalize_rehydrated_text(decoded) if isinstance(decoded, str) else ""
    return ""


def _looks_like_rsc_artifact_text(text: str) -> bool:
    lowered = _norm_key(text)
    if not lowered:
        return False
    return any(
        marker in lowered
        for marker in (
            "browser_local_storage",
            "browser_session_storage",
            "enforcementmode",
            "iswildcard",
            "qualtricssurveyhistory",
        )
    )


def _edit_form_string_state(parsed: dict[str, Any], suffix: str) -> str:
    rsc_text = str(parsed.get("raw_text", "") or "")
    pattern = re.compile(FORM_STATE_STRING_RE_TEMPLATE.replace("__SUFFIX__", re.escape(suffix)), re.DOTALL)
    match = pattern.search(rsc_text)
    if not match:
        return ""
    return _norm(_decode_quoted_fragment(match.group(1)))


def _edit_form_date_state(parsed: dict[str, Any], suffix: str) -> dict[str, int] | None:
    rsc_text = str(parsed.get("raw_text", "") or "")
    pattern = re.compile(FORM_STATE_DATE_RE_TEMPLATE.replace("__SUFFIX__", re.escape(suffix)), re.DOTALL)
    match = pattern.search(rsc_text)
    if not match:
        return None
    return {
        "day": int(match.group(1)),
        "month": int(match.group(2)),
        "year": int(match.group(3)),
    }


def _format_linkedin_date_value(value: dict[str, int] | None) -> str:
    if not isinstance(value, dict):
        return ""
    year = int(value.get("year", 0) or 0)
    month = int(value.get("month", 0) or 0)
    if year <= 0:
        return "Present"
    if 1 <= month < len(MONTH_ABBREVIATIONS):
        return f"{MONTH_ABBREVIATIONS[month]} {year}"
    return str(year)


def _extract_employment_type_labels(rsc_text: str) -> dict[str, str]:
    window = rsc_text or ""
    labels: dict[str, str] = {}
    for label, value in EXPERIENCE_EMPLOYMENT_OPTION_RE.findall(window):
        normalized_label = _norm(_decode_quoted_fragment(label))
        normalized_value = _norm(_decode_quoted_fragment(value))
        if not normalized_label or not normalized_value:
            continue
        normalized_key = _norm_key(normalized_label)
        if normalized_key not in EMPLOYMENT_TYPE_MARKERS:
            continue
        labels.setdefault(normalized_value, normalized_label)
    return labels


def _merge_education_record(base_record: dict[str, Any], edit_form_html: str) -> dict[str, Any]:
    parsed = _parse_edit_form_rehydration(edit_form_html)
    if not parsed.get("entries"):
        return base_record
    school = _edit_form_string_state(parsed, "dataAwareAddEducationFormComponentschoolName") or _norm(str(base_record.get("school", "")))
    degree = _edit_form_string_state(parsed, "dataAwareAddEducationFormComponentdegree") or _norm(str(base_record.get("degree", "")))
    field_of_study = _edit_form_string_state(parsed, "dataAwareAddEducationFormComponentfieldOfStudy") or _norm(str(base_record.get("field_of_study", "")))
    description = _edit_form_resolve_text(parsed, _edit_form_string_state(parsed, "dataAwareAddEducationFormComponentdescription"))
    if not description:
        description = _norm(str(base_record.get("description", "")))
    activities = _edit_form_resolve_text(parsed, _edit_form_string_state(parsed, "dataAwareAddEducationFormComponentactivities"))
    if not activities:
        activities = _norm(str(base_record.get("activities", "")))
    grade = _edit_form_string_state(parsed, "dataAwareAddEducationFormComponentgrade") or _norm(str(base_record.get("grade", "")))
    start_date_value = _edit_form_date_state(parsed, "dataAwareAddEducationFormComponentstartDate")
    end_date_value = _edit_form_date_state(parsed, "dataAwareAddEducationFormComponentendDate")
    start_date_text = _format_linkedin_date_value(start_date_value) or _norm(str(base_record.get("start_date_text", "")))
    end_date_text = _format_linkedin_date_value(end_date_value) or _norm(str(base_record.get("end_date_text", "")))
    date_parts = [part for part in (start_date_text, end_date_text) if _norm(part)]
    date_range = " - ".join(date_parts) if len(date_parts) == 2 else (date_parts[0] if date_parts else _norm(str(base_record.get("date_range", ""))))
    raw_lines = _dedupe_texts([str(item) for item in base_record.get("raw_lines", []) if _norm(str(item))])
    if description or activities or grade:
        raw_lines = []
    return {
        **base_record,
        "school": school,
        "degree": degree,
        "field_of_study": field_of_study,
        "date_range": date_range,
        "start_date_text": start_date_text,
        "end_date_text": end_date_text,
        "grade": grade,
        "activities": activities,
        "description": description,
        "raw_lines": raw_lines,
    }


def _merge_project_record(base_record: dict[str, Any], edit_form_html: str) -> dict[str, Any]:
    parsed = _parse_edit_form_rehydration(edit_form_html)
    if not parsed.get("entries"):
        return base_record
    name = _edit_form_string_state(parsed, "ProjectFormname") or _norm(str(base_record.get("name", "")))
    description = _edit_form_resolve_text(parsed, _edit_form_string_state(parsed, "ProjectFormdescription"))
    if _looks_like_rsc_artifact_text(description):
        description = ""
    if not description:
        description = _norm(str(base_record.get("description", "")))
    project_url = _edit_form_string_state(parsed, "ProjectFormlegacyProjectUrl") or _norm(str(base_record.get("project_url", "")))
    currently_working = _norm_key(_edit_form_string_state(parsed, "ProjectFormcurrentlyWorking"))
    start_date_value = _edit_form_date_state(parsed, "ProjectFormstartDate")
    end_date_value = _edit_form_date_state(parsed, "ProjectFormendDate")
    start_date_text = _format_linkedin_date_value(start_date_value) or _norm(str(base_record.get("start_date_text", "")))
    end_date_text = _format_linkedin_date_value(end_date_value) or _norm(str(base_record.get("end_date_text", "")))
    is_current = currently_working in {"checked", "true", "selected"} or _is_current_date_text(end_date_text)
    if is_current:
        end_date_text = "Present"
    date_parts = [part for part in (start_date_text, end_date_text) if _norm(part)]
    date_range = " - ".join(date_parts) if len(date_parts) == 2 else (date_parts[0] if date_parts else _norm(str(base_record.get("date_range", ""))))
    raw_lines = _dedupe_texts([str(item) for item in base_record.get("raw_lines", []) if _norm(str(item))])
    if description or project_url:
        raw_lines = []
    return {
        **base_record,
        "name": name,
        "date_range": date_range,
        "start_date_text": start_date_text,
        "end_date_text": end_date_text,
        "is_current": is_current,
        "project_url": project_url,
        "description": description,
        "raw_lines": raw_lines,
    }


def _merge_experience_record(base_record: dict[str, Any], edit_form_html: str) -> dict[str, Any]:
    parsed = _parse_edit_form_rehydration(edit_form_html)
    if not parsed.get("entries"):
        return base_record
    employment_labels = _extract_employment_type_labels(str(parsed.get("raw_text", "") or ""))

    title = _edit_form_string_state(parsed, "ProfilePositionFormtitle") or _norm(str(base_record.get("title", "")))
    company = _edit_form_string_state(parsed, "ProfilePositionFormcompanyName") or _norm(str(base_record.get("company", "")))
    employment_type_value = _edit_form_string_state(parsed, "ProfilePositionFormemploymentType")
    employment_type = employment_labels.get(employment_type_value, employment_type_value) or _norm(str(base_record.get("employment_type", "")))
    location = _edit_form_string_state(parsed, "ProfilePositionFormlocation") or _norm(str(base_record.get("location", "")))
    location_type = _edit_form_string_state(parsed, "ProfilePositionFormlocationType")
    if location_type.endswith("_REMOTE"):
        location = "Remote"

    description_token = _edit_form_string_state(parsed, "ProfilePositionFormdescription")
    initial_description_token = _edit_form_string_state(parsed, "ProfilePositionForminitialDescription")
    description = _edit_form_resolve_text(parsed, description_token)
    if not description:
        description = _edit_form_resolve_text(parsed, initial_description_token)
    if not description:
        description = _norm(str(base_record.get("description", "")))

    start_date_value = _edit_form_date_state(parsed, "ProfilePositionFormstartDate")
    end_date_value = _edit_form_date_state(parsed, "ProfilePositionFormendDate")
    start_date_text = _format_linkedin_date_value(start_date_value) or _norm(str(base_record.get("start_date_text", "")))
    end_date_text = _format_linkedin_date_value(end_date_value) or _norm(str(base_record.get("end_date_text", "")))
    date_parts = [part for part in (start_date_text, end_date_text) if _norm(part)]
    date_range = " - ".join(date_parts) if len(date_parts) == 2 else (date_parts[0] if date_parts else _norm(str(base_record.get("date_range", ""))))
    is_current = _is_current_date_text(end_date_text) or bool(base_record.get("is_current"))

    return {
        **base_record,
        "title": title,
        "company": company,
        "employment_type": employment_type,
        "date_range": date_range,
        "start_date_text": start_date_text,
        "end_date_text": end_date_text,
        "is_current": is_current,
        "location": location,
        "description": description,
    }


def _extract_experience_entry_bundles_from_rsc_text(body: str) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    matches: list[re.Match[str]] = []
    for match in EXPERIENCE_EDIT_FORM_URL_RE.finditer(body or ""):
        url = match.group(0)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        matches.append(match)
    for url_match, chunk in _entry_chunks_from_matches(body or "", matches, lookbehind_chars=5000):
        label_match = EXPERIENCE_EDIT_LABEL_RE.search(chunk)
        if not label_match:
            continue
        title = _norm(_decode_quoted_fragment(label_match.group(1)))
        company = _norm(_decode_quoted_fragment(label_match.group(2)))
        pair = (title.lower(), company.lower())
        if not title or not company or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        lines = _extract_rsc_text_lines(chunk)
        company_urls = COMPANY_URL_RE.findall(chunk)
        company_url = company_urls[-1] if company_urls else ""
        consumed: set[str] = {title, company, f"{title} at {company}"}
        title_index = lines.index(title) if title in lines else len(lines)
        company_index = -1
        for index, line in enumerate(lines[:title_index]):
            if _norm_key(company) in _norm_key(line):
                company_index = index

        employment_type = ""
        employment_candidates = lines[company_index:title_index] if company_index >= 0 else lines[:title_index]
        for line in reversed(employment_candidates):
            lowered = _norm_key(line)
            if line in consumed or _looks_like_date_range_text(line) or _looks_like_role_location(line):
                continue
            if "·" not in line:
                continue
            segments = [_norm(part) for part in line.split("·") if _norm(part)]
            candidate = next((segment for segment in segments if _norm_key(segment) in EMPLOYMENT_TYPE_MARKERS), "")
            if not candidate and segments:
                candidate = segments[0]
            if not candidate or any(char.isdigit() for char in candidate):
                continue
            if lowered == _norm_key(company):
                continue
            if candidate.lower() in EMPLOYMENT_TYPE_MARKERS or _looks_like_employment_meta(line):
                employment_type = candidate
                consumed.add(line)
                break

        date_line = next((line for line in lines if _looks_like_date_range_text(line)), "")
        date_index = lines.index(date_line) if date_line in lines else -1
        date_range, duration = _split_date_range_and_duration(date_line)
        start_date_text, end_date_text = _split_date_range_bounds(date_range)
        if date_line:
            consumed.add(date_line)

        location = ""
        if date_index > 0:
            for line in lines[:date_index]:
                if _looks_like_role_location(line):
                    consumed.add(line)
        search_lines = lines[date_index + 1 :] if date_index >= 0 else lines
        for line in search_lines:
            if line in consumed:
                continue
            if _looks_like_role_location(line):
                location = line
                consumed.add(line)
                break
        if not location:
            for line in lines:
                if line in consumed:
                    continue
                if _looks_like_role_location(line):
                    location = line
                    consumed.add(line)
                    break

        trimmed_lines: list[str] = []
        for index, line in enumerate(lines):
            if line in consumed:
                trimmed_lines.append(line)
                continue
            if _looks_like_date_range_text(line) and line != date_line:
                break
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if next_line and (_looks_like_date_range_text(next_line) or _looks_like_employment_meta(next_line)):
                break
            trimmed_lines.append(line)

        description, raw_lines = _extract_description_and_raw_lines(trimmed_lines, consumed=consumed)
        bundles.append(
            {
                "edit_form_url": _norm(url_match.group(0)),
                "record": {
                    "title": title,
                    "company": company,
                    "company_url": company_url,
                    "employment_type": employment_type,
                    "date_range": date_range,
                    "start_date_text": start_date_text,
                    "end_date_text": end_date_text,
                    "is_current": _is_current_date_text(end_date_text),
                    "duration": duration,
                    "location": location,
                    "description": description,
                    "raw_lines": raw_lines,
                },
            }
        )
    if bundles:
        return bundles
    seen_pairs.clear()
    for block in _extract_rsc_entity_item_blocks(body):
        lines = [line for line in _extract_rsc_text_lines(block) if line != "Experience" and not _looks_like_skill_summary(line)]
        if not lines:
            continue
        company_url_matches = COMPANY_URL_RE.findall(block)
        company_url = company_url_matches[-1] if company_url_matches else ""

        def append_record(*, title: str, company: str, employment_type: str, date_line: str, location_line: str = "") -> None:
            pair = (_norm_key(title), _norm_key(company))
            if not title or not company or pair in seen_pairs:
                return
            seen_pairs.add(pair)
            date_range, duration = _split_date_range_and_duration(date_line)
            start_date_text, end_date_text = _split_date_range_bounds(date_range)
            location = _normalize_location_line(location_line) if location_line else ""
            bundles.append(
                {
                    "edit_form_url": "",
                    "record": {
                        "title": _norm(title),
                        "company": _norm(company),
                        "company_url": company_url,
                        "employment_type": _norm(employment_type),
                        "date_range": date_range,
                        "start_date_text": start_date_text,
                        "end_date_text": end_date_text,
                        "is_current": _is_current_date_text(end_date_text),
                        "duration": duration,
                        "location": location,
                        "description": "",
                        "raw_lines": [],
                    },
                }
            )

        if (
            len(lines) >= 4
            and _looks_like_employment_meta(lines[1])
            and not _looks_like_date_range_text(lines[0])
            and _looks_like_date_range_text(lines[3])
        ):
            company = lines[0]
            segments = [_norm(part) for part in lines[1].split("·") if _norm(part)]
            employment_type = next((segment for segment in segments if _norm_key(segment) in EMPLOYMENT_TYPE_MARKERS), "")
            index = 2
            while index < len(lines):
                title = lines[index]
                if index + 1 >= len(lines) or not _looks_like_date_range_text(lines[index + 1]):
                    index += 1
                    continue
                date_line = lines[index + 1]
                location_line = ""
                if index + 2 < len(lines) and _looks_like_role_location(lines[index + 2]):
                    location_line = lines[index + 2]
                    index += 3
                else:
                    index += 2
                append_record(
                    title=title,
                    company=company,
                    employment_type=employment_type,
                    date_line=date_line,
                    location_line=location_line,
                )
            continue

        title = lines[0]
        company = ""
        employment_type = ""
        date_line = ""
        location_line = ""
        if len(lines) >= 2 and not _looks_like_date_range_text(lines[1]):
            segments = [_norm(part) for part in lines[1].split("·") if _norm(part)]
            if segments:
                company = segments[0]
                employment_type = next((segment for segment in segments[1:] if _norm_key(segment) in EMPLOYMENT_TYPE_MARKERS), "")
        if len(lines) >= 3 and _looks_like_date_range_text(lines[2]):
            date_line = lines[2]
        if len(lines) >= 4 and not _looks_like_date_range_text(lines[3]):
            location_line = lines[3]
        append_record(
            title=title,
            company=company,
            employment_type=employment_type,
            date_line=date_line,
            location_line=location_line,
        )
    return bundles


def _extract_experience_records_from_rsc_text(body: str) -> list[dict[str, Any]]:
    return _normalize_record_list(
        "experience",
        [bundle.get("record", {}) for bundle in _extract_experience_entry_bundles_from_rsc_text(body)],
    )


def _extract_education_records_from_rsc_text(body: str) -> list[dict[str, Any]]:
    return _normalize_record_list(
        "education",
        [bundle.get("record", {}) for bundle in _extract_education_entry_bundles_from_rsc_text(body)],
    )


def _extract_project_records_from_rsc_text(body: str) -> list[dict[str, Any]]:
    return _normalize_record_list(
        "projects",
        [bundle.get("record", {}) for bundle in _extract_project_entry_bundles_from_rsc_text(body)],
    )


def _extract_license_records_from_rsc_text(body: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    matches: list[re.Match[str]] = []
    for match in CERTIFICATIONS_EDIT_FORM_URL_RE.finditer(body or ""):
        url = match.group(0)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        matches.append(match)
    for _url_match, chunk in _entry_chunks_from_matches(body or "", matches, lookbehind_chars=1500):
        label_match = LICENSE_EDIT_LABEL_RE.search(chunk)
        if not label_match:
            continue
        name = _norm(_decode_quoted_fragment(label_match.group(1)))
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        lines = _extract_rsc_text_lines(chunk)
        consumed: set[str] = {name}

        issuer = ""
        issue_date_text = ""
        expiration_date_text = ""
        credential_id = ""
        credential_url = ""
        for line in lines:
            lowered = _norm_key(line)
            if line in consumed:
                continue
            if lowered.startswith("issued "):
                issue_date_text = _norm(line[7:])
                consumed.add(line)
                continue
            if lowered.startswith("expires "):
                expiration_date_text = _norm(line[8:])
                consumed.add(line)
                continue
            if lowered.startswith("credential id "):
                credential_id = _norm(line[14:])
                consumed.add(line)
                continue
            if lowered.startswith("credential url "):
                credential_url = _norm(line[15:])
                consumed.add(line)
                continue
            if not issuer and not _looks_like_skill_summary(line):
                issuer = line
                consumed.add(line)
                continue
        if not credential_url:
            credential_url = _extract_credential_url_from_chunk(chunk)
        description, raw_lines = _extract_description_and_raw_lines(lines, consumed=consumed)
        records.append(
            {
                "name": name,
                "issuer": issuer,
                "issue_date_text": issue_date_text,
                "expiration_date_text": expiration_date_text,
                "credential_id": credential_id,
                "credential_url": credential_url,
                "description": description,
                "raw_lines": raw_lines,
            }
        )
    if records:
        return _normalize_record_list("licenses_certifications", records)
    seen_names.clear()
    for block in _extract_rsc_entity_item_blocks(body):
        lines = [line for line in _extract_rsc_text_lines(block) if line not in {"Licenses & certifications", "Show credential"}]
        if not lines:
            continue
        credential_urls = [url for url in EXTERNAL_URL_RE.findall(block or "") if "/safety/go/?url=" in url]
        credential_index = 0
        index = 0
        while index < len(lines):
            name = lines[index]
            if not name or _norm_key(name) in seen_names:
                index += 1
                continue
            seen_names.add(_norm_key(name))
            index += 1
            issuer = ""
            if index < len(lines):
                lowered = _norm_key(lines[index])
                if not lowered.startswith(("issued ", "expires ", "credential id ", "credential url ")):
                    issuer = lines[index]
                    index += 1
            issue_date_text = ""
            expiration_date_text = ""
            credential_id = ""
            raw_lines: list[str] = []
            while index < len(lines):
                line = lines[index]
                lowered = _norm_key(line)
                if lowered.startswith("issued "):
                    issued_text = _norm(line[7:])
                    if "·" in issued_text:
                        parts = [_norm(part) for part in issued_text.split("·") if _norm(part)]
                        issue_date_text = parts[0] if parts else ""
                        for part in parts[1:]:
                            if _norm_key(part).startswith("expires "):
                                expiration_date_text = _norm(part[8:])
                    else:
                        issue_date_text = issued_text
                    index += 1
                    continue
                if lowered.startswith("expires "):
                    expiration_date_text = _norm(line[8:])
                    index += 1
                    continue
                if lowered.startswith("credential id "):
                    credential_id = _norm(line[14:])
                    index += 1
                    continue
                if lowered.startswith("credential url "):
                    index += 1
                    continue
                if issuer or issue_date_text or expiration_date_text or credential_id:
                    break
                if index + 1 < len(lines):
                    next_lowered = _norm_key(lines[index + 1])
                    if not lowered.startswith(("issued ", "expires ", "credential id ", "credential url ")) and (
                        next_lowered.startswith(("issued ", "expires ", "credential id ", "credential url ")) or lines[index + 1] == "Show credential"
                    ):
                        break
                if line not in raw_lines:
                    raw_lines.append(line)
                index += 1
            credential_url = credential_urls[credential_index] if credential_index < len(credential_urls) else ""
            credential_index += 1 if credential_url else 0
            records.append(
                {
                    "name": name,
                    "issuer": issuer,
                    "issue_date_text": issue_date_text,
                    "expiration_date_text": expiration_date_text,
                    "credential_id": credential_id,
                    "credential_url": credential_url,
                    "description": "",
                    "raw_lines": _dedupe_texts(raw_lines),
                }
            )
    return _normalize_record_list("licenses_certifications", records)


def _extract_json_assignment_object(text: str, marker: str) -> str | None:
    marker_index = text.find(marker)
    if marker_index < 0:
        return None
    assign_index = text.find("=", marker_index)
    if assign_index < 0:
        return None
    start_index = text.find("{", assign_index)
    if start_index < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]
    return None


def _extract_json_assignment_value(text: str, marker: str) -> Any | None:
    marker_index = text.find(marker)
    if marker_index < 0:
        return None
    assign_index = text.find("=", marker_index)
    if assign_index < 0:
        return None
    start_index = assign_index + 1
    while start_index < len(text) and text[start_index].isspace():
        start_index += 1
    if start_index >= len(text) or text[start_index] not in {"{", "["}:
        return None
    open_char = text[start_index]
    close_char = "}" if open_char == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for index in range(start_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == open_char:
            depth += 1
            continue
        if char == close_char:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start_index : index + 1])
                except Exception:
                    return None
    return None


def _iter_nested_nodes(value: Any):
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from _iter_nested_nodes(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_nested_nodes(nested)


def _build_como_pointer_map(value: Any) -> dict[str, Any]:
    pointer_map: dict[str, Any] = {}
    for node in _iter_nested_nodes(value):
        if not isinstance(node, dict):
            continue
        for key, nested in node.items():
            if isinstance(key, str) and COMO_POINTER_RE.fullmatch(key):
                pointer_map.setdefault(key, nested)
    return pointer_map


def _find_skills_pagination_request(node: Any, *, pointer_map: dict[str, Any]) -> dict[str, Any] | None:
    queue: deque[Any] = deque([node])
    seen_nodes: set[int] = set()
    seen_pointers: set[str] = set()
    while queue:
        current = queue.popleft()
        if isinstance(current, str) and current in pointer_map:
            if current in seen_pointers:
                continue
            seen_pointers.add(current)
            queue.append(pointer_map[current])
            continue
        if isinstance(current, (dict, list)):
            marker = id(current)
            if marker in seen_nodes:
                continue
            seen_nodes.add(marker)
        if isinstance(current, dict):
            next_page_request = current.get("nextPageRequest")
            if isinstance(next_page_request, dict) and next_page_request.get("pagerId") == SKILLS_RSC_PAGER_ID:
                return next_page_request
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current)
    return None


def _extract_balanced_json_object(text: str, start_index: int) -> str | None:
    if start_index < 0 or start_index >= len(text) or text[start_index] != "{":
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]
    return None


def _find_rsc_line(text: str, label: str) -> str | None:
    raw_label = label[2:] if label.startswith("$L") else label
    match = re.search(rf"(?m)^{re.escape(raw_label)}:(.*)$", text)
    return match.group(1) if match else None


def _extract_initial_pagination_request_from_rsc_blob(text: str, *, pager_id: str) -> dict[str, Any] | None:
    assignment_value = _extract_json_assignment_value(text or "", "window.__como_rehydration__")
    if isinstance(assignment_value, list):
        rsc_text = "\n".join(part for part in assignment_value if isinstance(part, str))
    else:
        rsc_text = text or ""
    pager_match = re.search(
        rf'(?m)^[0-9a-z]+:\[.*?"observabilityIdentifier":"{re.escape(pager_id)}".*?"children":"(\$L[0-9A-Za-z]+)".*$',
        rsc_text,
    )
    if not pager_match:
        return None
    current_label = pager_match.group(1)
    next_page_marker = '"nextPageRequest":'
    for _ in range(8):
        line = _find_rsc_line(rsc_text, current_label)
        if not line:
            return None
        marker_index = line.find(next_page_marker)
        if marker_index >= 0:
            object_start = line.find("{", marker_index)
            payload_text = _extract_balanced_json_object(line, object_start)
            if not payload_text:
                return None
            try:
                payload = json.loads(payload_text)
            except Exception:
                return None
            if isinstance(payload, dict) and payload.get("pagerId") == pager_id:
                return payload
            return None
        next_labels = [label for label in re.findall(r'"(\$L[0-9A-Za-z]+)"', line) if label != current_label]
        if not next_labels:
            return None
        current_label = next_labels[-1]
    return None


def _extract_skills_initial_pagination_request_from_html(html: str) -> dict[str, Any] | None:
    if pagination_request := _extract_initial_pagination_request_from_rsc_blob(html, pager_id=SKILLS_RSC_PAGER_ID):
        return pagination_request
    assignment_value = _extract_json_assignment_value(html or "", "window.__como_rehydration__")
    if isinstance(assignment_value, list):
        return None
    if not isinstance(assignment_value, dict):
        requests = _extract_skills_pagination_requests_from_rsc_text(html)
        return requests[0] if requests else None
    assignment = json.dumps(assignment_value, ensure_ascii=False)
    if assignment:
        try:
            como_data = json.loads(assignment)
        except Exception:
            como_data = None
        if como_data is not None:
            pointer_map = _build_como_pointer_map(como_data)
            for node in _iter_nested_nodes(como_data):
                if not isinstance(node, dict):
                    continue
                if node.get("observabilityIdentifier") != SKILLS_RSC_PAGER_ID:
                    continue
                pagination_request = _find_skills_pagination_request(node, pointer_map=pointer_map)
                if isinstance(pagination_request, dict):
                    return pagination_request
            pagination_request = _find_skills_pagination_request(como_data, pointer_map=pointer_map)
            if isinstance(pagination_request, dict):
                return pagination_request
    requests = _extract_skills_pagination_requests_from_rsc_text(html)
    return requests[0] if requests else None


def _extract_languages_initial_pagination_request_from_html(html: str) -> dict[str, Any] | None:
    return _extract_initial_pagination_request_from_rsc_blob(html, pager_id=LANGUAGES_RSC_PAGER_ID)


def _extract_education_initial_pagination_request_from_html(html: str) -> dict[str, Any] | None:
    return _extract_initial_pagination_request_from_rsc_blob(html, pager_id=EDUCATION_RSC_PAGER_ID)


def _extract_projects_initial_pagination_request_from_html(html: str) -> dict[str, Any] | None:
    return _extract_initial_pagination_request_from_rsc_blob(html, pager_id=PROJECTS_RSC_PAGER_ID)


def _extract_experience_initial_pagination_request_from_html(html: str) -> dict[str, Any] | None:
    return _extract_initial_pagination_request_from_rsc_blob(html, pager_id=EXPERIENCE_RSC_PAGER_ID)


def _extract_certifications_initial_pagination_request_from_html(html: str) -> dict[str, Any] | None:
    return _extract_initial_pagination_request_from_rsc_blob(html, pager_id=CERTIFICATIONS_RSC_PAGER_ID)


def _extract_request_payload(response: Any) -> dict[str, Any] | None:
    request = getattr(response, "request", None)
    if callable(request):
        try:
            request = request()
        except Exception:
            request = None
    if request is None:
        return None
    post_data_json = getattr(request, "post_data_json", None)
    if callable(post_data_json):
        try:
            payload = post_data_json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return payload
    post_data = getattr(request, "post_data", None)
    if callable(post_data):
        try:
            raw_payload = post_data()
        except Exception:
            raw_payload = None
        if raw_payload:
            try:
                payload = json.loads(raw_payload)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                return payload
    return None


def _extract_pagination_requests_from_rsc_text(body: str, *, pager_id: str) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for match in SKILLS_RSC_PAGINATION_REQUEST_RE.findall(body or ""):
        decoded = _decode_quoted_fragment(match)
        try:
            payload = json.loads(decoded)
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("pagerId") == pager_id:
            requests.append(payload)
    return requests


def _extract_skills_pagination_requests_from_rsc_text(body: str) -> list[dict[str, Any]]:
    return _extract_pagination_requests_from_rsc_text(body, pager_id=SKILLS_RSC_PAGER_ID)


def _extract_languages_pagination_requests_from_rsc_text(body: str) -> list[dict[str, Any]]:
    return _extract_pagination_requests_from_rsc_text(body, pager_id=LANGUAGES_RSC_PAGER_ID)


def _extract_education_pagination_requests_from_rsc_text(body: str) -> list[dict[str, Any]]:
    return _extract_pagination_requests_from_rsc_text(body, pager_id=EDUCATION_RSC_PAGER_ID)


def _extract_projects_pagination_requests_from_rsc_text(body: str) -> list[dict[str, Any]]:
    return _extract_pagination_requests_from_rsc_text(body, pager_id=PROJECTS_RSC_PAGER_ID)


def _extract_experience_pagination_requests_from_rsc_text(body: str) -> list[dict[str, Any]]:
    return _extract_pagination_requests_from_rsc_text(body, pager_id=EXPERIENCE_RSC_PAGER_ID)


def _extract_certifications_pagination_requests_from_rsc_text(body: str) -> list[dict[str, Any]]:
    return _extract_pagination_requests_from_rsc_text(body, pager_id=CERTIFICATIONS_RSC_PAGER_ID)


def _extract_skills_pagination_start(payload: dict[str, Any] | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    requested_arguments = payload.get("requestedArguments", {})
    if not isinstance(requested_arguments, dict):
        return None
    requested_payload = requested_arguments.get("payload", {})
    if not isinstance(requested_payload, dict):
        return None
    start = requested_payload.get("start")
    return start if isinstance(start, int) else None


def _extract_skills_request_start(request_payload: dict[str, Any] | None) -> int | None:
    if not isinstance(request_payload, dict):
        return None
    pagination_request = request_payload.get("paginationRequest")
    if isinstance(pagination_request, dict):
        return _extract_skills_pagination_start(pagination_request)
    return None


def _build_request_payload_from_pagination_request(
    pagination_request: dict[str, Any] | None,
    *,
    pager_id: str,
    screen_id: str,
) -> dict[str, Any] | None:
    if not isinstance(pagination_request, dict):
        return None
    if pagination_request.get("pagerId") != pager_id:
        return None
    requested_arguments = copy.deepcopy(pagination_request.get("requestedArguments"))
    if not isinstance(requested_arguments, dict):
        return None
    client_arguments = copy.deepcopy(requested_arguments)
    client_arguments.setdefault("$type", REQUESTED_ARGUMENTS_TYPE)
    client_arguments.setdefault("requestedStateKeys", [])
    client_arguments.setdefault("requestMetadata", {"$type": REQUEST_METADATA_TYPE})
    client_arguments["states"] = []
    client_arguments["screenId"] = screen_id
    return {
        "pagerId": pagination_request.get("pagerId", pager_id),
        "clientArguments": client_arguments,
        "paginationRequest": copy.deepcopy(pagination_request),
    }


def _build_skills_request_payload_from_pagination_request(pagination_request: dict[str, Any] | None) -> dict[str, Any] | None:
    return _build_request_payload_from_pagination_request(
        pagination_request,
        pager_id=SKILLS_RSC_PAGER_ID,
        screen_id=SKILLS_SCREEN_ID,
    )


def _build_languages_request_payload_from_pagination_request(pagination_request: dict[str, Any] | None) -> dict[str, Any] | None:
    return _build_request_payload_from_pagination_request(
        pagination_request,
        pager_id=LANGUAGES_RSC_PAGER_ID,
        screen_id=LANGUAGES_SCREEN_ID,
    )


def _build_education_request_payload_from_pagination_request(pagination_request: dict[str, Any] | None) -> dict[str, Any] | None:
    return _build_request_payload_from_pagination_request(
        pagination_request,
        pager_id=EDUCATION_RSC_PAGER_ID,
        screen_id=EDUCATION_SCREEN_ID,
    )


def _build_projects_request_payload_from_pagination_request(pagination_request: dict[str, Any] | None) -> dict[str, Any] | None:
    return _build_request_payload_from_pagination_request(
        pagination_request,
        pager_id=PROJECTS_RSC_PAGER_ID,
        screen_id=PROJECTS_SCREEN_ID,
    )


def _build_experience_request_payload_from_pagination_request(pagination_request: dict[str, Any] | None) -> dict[str, Any] | None:
    return _build_request_payload_from_pagination_request(
        pagination_request,
        pager_id=EXPERIENCE_RSC_PAGER_ID,
        screen_id=EXPERIENCE_SCREEN_ID,
    )


def _build_certifications_request_payload_from_pagination_request(pagination_request: dict[str, Any] | None) -> dict[str, Any] | None:
    return _build_request_payload_from_pagination_request(
        pagination_request,
        pager_id=CERTIFICATIONS_RSC_PAGER_ID,
        screen_id=CERTIFICATIONS_SCREEN_ID,
    )


def _build_skills_follow_up_requests_from_text(text: str, *, request_url: str) -> list[dict[str, Any]]:
    follow_ups: list[dict[str, Any]] = []
    for pagination_request in _extract_skills_pagination_requests_from_rsc_text(text):
        payload = _build_skills_request_payload_from_pagination_request(pagination_request)
        start = _extract_skills_pagination_start(pagination_request)
        if not isinstance(payload, dict) or not isinstance(start, int):
            continue
        follow_ups.append(
            {
                "url": request_url or SKILLS_PAGINATION_URL,
                "payload": payload,
                "start": start,
            }
        )
    return follow_ups


def _select_next_pagination_request_from_text(
    text: str,
    *,
    pager_id: str,
    attempted_starts: set[int],
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for pagination_request in _extract_pagination_requests_from_rsc_text(text, pager_id=pager_id):
        start = _extract_skills_pagination_start(pagination_request)
        if not isinstance(start, int) or start in attempted_starts:
            continue
        candidates.append(pagination_request)
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: int(_extract_skills_pagination_start(candidate) or 0))


def _select_next_skills_pagination_request_from_text(
    text: str,
    *,
    attempted_starts: set[int],
) -> dict[str, Any] | None:
    return _select_next_pagination_request_from_text(
        text,
        pager_id=SKILLS_RSC_PAGER_ID,
        attempted_starts=attempted_starts,
    )


def _select_next_languages_pagination_request_from_text(
    text: str,
    *,
    attempted_starts: set[int],
) -> dict[str, Any] | None:
    return _select_next_pagination_request_from_text(
        text,
        pager_id=LANGUAGES_RSC_PAGER_ID,
        attempted_starts=attempted_starts,
    )


def _select_next_education_pagination_request_from_text(
    text: str,
    *,
    attempted_starts: set[int],
) -> dict[str, Any] | None:
    return _select_next_pagination_request_from_text(
        text,
        pager_id=EDUCATION_RSC_PAGER_ID,
        attempted_starts=attempted_starts,
    )


def _select_next_projects_pagination_request_from_text(
    text: str,
    *,
    attempted_starts: set[int],
) -> dict[str, Any] | None:
    return _select_next_pagination_request_from_text(
        text,
        pager_id=PROJECTS_RSC_PAGER_ID,
        attempted_starts=attempted_starts,
    )


def _select_next_experience_pagination_request_from_text(
    text: str,
    *,
    attempted_starts: set[int],
) -> dict[str, Any] | None:
    return _select_next_pagination_request_from_text(
        text,
        pager_id=EXPERIENCE_RSC_PAGER_ID,
        attempted_starts=attempted_starts,
    )


def _select_next_certifications_pagination_request_from_text(
    text: str,
    *,
    attempted_starts: set[int],
) -> dict[str, Any] | None:
    return _select_next_pagination_request_from_text(
        text,
        pager_id=CERTIFICATIONS_RSC_PAGER_ID,
        attempted_starts=attempted_starts,
    )


def _select_skills_follow_up_request(
    records: list[dict[str, Any]],
    *,
    seed_text: str,
    attempted_starts: set[int],
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    seen_starts: set[int] = set()

    def add_candidates(text: str, *, request_url: str) -> None:
        for follow_up in _build_skills_follow_up_requests_from_text(text, request_url=request_url):
            start = follow_up.get("start")
            if not isinstance(start, int):
                continue
            if start in attempted_starts or start in seen_starts:
                continue
            seen_starts.add(start)
            candidates.append(follow_up)

    add_candidates(seed_text, request_url=SKILLS_PAGINATION_URL)
    for record in records:
        add_candidates(
            str(record.get("body", "")),
            request_url=str(record.get("request_url") or record.get("url") or SKILLS_PAGINATION_URL),
        )
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: int(candidate["start"]))


def _trigger_skills_follow_up_request(page: Any, *, url: str, payload: dict[str, Any]) -> tuple[bool, str]:
    try:
        result = page.evaluate(
            """
            async ({ url, payload }) => {
                const getCookieValue = (name) => {
                    const prefix = `${name}=`;
                    for (const chunk of document.cookie.split("; ")) {
                        if (chunk.startsWith(prefix)) {
                            return chunk.slice(prefix.length);
                        }
                    }
                    return "";
                };
                const csrf = decodeURIComponent(getCookieValue("JSESSIONID") || "").replace(/^"|"$/g, "");
                const headers = {
                    "content-type": "application/json",
                    "accept": "text/x-component",
                };
                if (csrf) {
                    headers["csrf-token"] = csrf;
                }
                const response = await fetch(url, {
                    method: "POST",
                    credentials: "include",
                    headers,
                    body: JSON.stringify(payload),
                });
                const body = await response.text();
                return { ok: response.ok, body };
            }
            """,
            {"url": url, "payload": payload},
        )
    except Exception:
        return False, ""
    if isinstance(result, dict):
        return bool(result.get("ok")), str(result.get("body") or "")
    return bool(result is None or result), ""


def _wait_for_network_growth(
    records: list[dict[str, Any]],
    *,
    previous_count: int,
    deadline: float,
    max_wait_sec: float = 1.5,
) -> None:
    wait_deadline = min(deadline, time.monotonic() + max_wait_sec)
    while time.monotonic() < wait_deadline:
        if len(records) > previous_count:
            return
        time.sleep(0.05)


def _record_serialized_text(record: dict[str, Any]) -> str:
    if "payload" in record:
        return json.dumps(record.get("payload", {}), ensure_ascii=False).lower()
    return _norm(str(record.get("body", ""))).lower()


def _collect_json_network_responses(page: Any) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def handle_response(response: Any):
        url = getattr(response, "url", "") or ""
        host = urlparse(url).netloc.lower()
        if host not in PROFILE_HOSTS:
            return
        content_type = _get_response_content_type(response).lower()
        try:
            response_text = response.text()
        except Exception:
            return
        if _is_skills_rsc_pagination_response(url, response_text):
            captured.append(
                {
                    "kind": "skills_rsc",
                    "url": _sanitize_record_url(url),
                    "request_url": url,
                    "body": response_text,
                    "request_payload": _extract_request_payload(response),
                }
            )
            return
        if "json" not in content_type and "/voyager/api/" not in url and "graphql" not in url.lower():
            return
        try:
            payload = json.loads(response_text)
        except Exception:
            return
        captured.append({"kind": "json", "url": _sanitize_record_url(url), "payload": payload})

    try:
        page.on("response", handle_response)
    except Exception:
        pass
    return captured


def _session_login_hint(profile_name: str) -> str:
    return f"Run `uv run agent-toolbelt-linkedin-cv session login --profile {sanitize_profile_name(profile_name)}`."


def _missing_session_result(
    *,
    operation: str,
    profile_name: str,
    profile_url: str,
    managed_profile: Path,
) -> dict[str, Any]:
    hint = _session_login_hint(profile_name)
    return make_result(
        ok=False,
        operation=operation,
        result={
            "status": "missing_session",
            "profile_url": profile_url,
            "managed_profile": str(managed_profile),
            "login_hint": hint,
        },
        stderr=f"Managed LinkedIn session is missing. {hint}",
        exit_code=3,
    )


def _invalid_session_result(
    *,
    operation: str,
    profile_name: str,
    profile_url: str,
    managed_profile: Path,
    visibility_status: str,
) -> dict[str, Any]:
    hint = _session_login_hint(profile_name)
    return make_result(
        ok=False,
        operation=operation,
        result={
            "status": "session_invalid",
            "profile_url": profile_url,
            "managed_profile": str(managed_profile),
            "visibility": {"status": visibility_status},
            "login_hint": hint,
        },
        stderr=f"Managed LinkedIn session is expired or unusable ({visibility_status}). {hint}",
        exit_code=3,
    )


def _profile_tokens(*, profile_id: str, profile_url: str, name: str) -> list[str]:
    tokens = [profile_id.lower(), profile_url.lower()]
    normalized_name = _norm(name).lower()
    if normalized_name:
        tokens.append(normalized_name)
    return [token for token in tokens if token and token != "unknown"]


def _record_looks_relevant(record: dict[str, Any], *, profile_id: str, profile_url: str, name: str) -> bool:
    serialized = _record_serialized_text(record)
    url = str(record.get("url", "")).lower()
    section_hit = any(alias in serialized or alias in url for aliases in SECTION_ALIASES.values() for alias in aliases)
    if not section_hit:
        return False
    if record.get("kind") in {"skills_rsc", "languages_rsc", "education_rsc", "projects_rsc", "experience_rsc", "licenses_rsc"}:
        return True
    return any(token in serialized or token in url for token in _profile_tokens(profile_id=profile_id, profile_url=profile_url, name=name)) or "/identity/profiles/" in url


def _extract_network_sections_for_profile(
    records: list[dict[str, Any]],
    *,
    profile_id: str,
    profile_url: str,
    name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    combined: dict[str, Any] = {key: _empty_section_value(key) for key in SECTION_KEYS}
    relevant_records: list[dict[str, Any]] = []
    used_urls: list[str] = []
    for record in records:
        if not _record_looks_relevant(record, profile_id=profile_id, profile_url=profile_url, name=name):
            continue
        if record.get("kind") == "skills_rsc":
            extracted_skills = _extract_skills_from_rsc_text(str(record.get("body", "")))
            relevant_record = {
                "kind": "skills_rsc",
                "url": record["url"],
                "body": str(record.get("body", "")),
            }
            if not extracted_skills:
                continue
            relevant_records.append(relevant_record)
            if record["url"] not in used_urls:
                used_urls.append(record["url"])
            existing_skills = combined["skills"] if isinstance(combined["skills"], list) else []
            combined["skills"] = _dedupe_texts(existing_skills + extracted_skills)
            continue
        if record.get("kind") == "languages_rsc":
            extracted_languages = _extract_languages_from_rsc_text(str(record.get("body", "")))
            relevant_record = {
                "kind": "languages_rsc",
                "url": record["url"],
                "body": str(record.get("body", "")),
            }
            if not extracted_languages:
                continue
            relevant_records.append(relevant_record)
            if record["url"] not in used_urls:
                used_urls.append(record["url"])
            existing_languages = combined["languages"] if isinstance(combined["languages"], list) else []
            combined["languages"] = _dedupe_texts(existing_languages + extracted_languages)
            continue
        if record.get("kind") == "education_rsc":
            extracted_education = _extract_education_records_from_rsc_text(str(record.get("body", "")))
            relevant_record = {
                "kind": "education_rsc",
                "url": record["url"],
                "body": str(record.get("body", "")),
            }
            if not extracted_education:
                continue
            relevant_records.append(relevant_record)
            if record["url"] not in used_urls:
                used_urls.append(record["url"])
            combined["education"] = extracted_education
            continue
        if record.get("kind") == "projects_rsc":
            extracted_projects = _extract_project_records_from_rsc_text(str(record.get("body", "")))
            relevant_record = {
                "kind": "projects_rsc",
                "url": record["url"],
                "body": str(record.get("body", "")),
            }
            if not extracted_projects:
                continue
            relevant_records.append(relevant_record)
            if record["url"] not in used_urls:
                used_urls.append(record["url"])
            combined["projects"] = extracted_projects
            continue
        if record.get("kind") == "experience_rsc":
            extracted_experience = _extract_experience_records_from_rsc_text(str(record.get("body", "")))
            relevant_record = {
                "kind": "experience_rsc",
                "url": record["url"],
                "body": str(record.get("body", "")),
            }
            if not extracted_experience:
                continue
            relevant_records.append(relevant_record)
            if record["url"] not in used_urls:
                used_urls.append(record["url"])
            combined["experience"] = extracted_experience
            continue
        if record.get("kind") == "licenses_rsc":
            extracted_licenses = _extract_license_records_from_rsc_text(str(record.get("body", "")))
            relevant_record = {
                "kind": "licenses_rsc",
                "url": record["url"],
                "body": str(record.get("body", "")),
            }
            if not extracted_licenses:
                continue
            relevant_records.append(relevant_record)
            if record["url"] not in used_urls:
                used_urls.append(record["url"])
            combined["licenses_certifications"] = extracted_licenses
            continue
        else:
            extracted = _normalize_network_sections(record.get("payload", {}))
            relevant_record = {
                "kind": str(record.get("kind", "json")),
                "url": record["url"],
                "payload": record.get("payload", {}),
            }
        if not any(_has_section_content(value) for value in extracted.values()):
            continue
        relevant_records.append(relevant_record)
        if record["url"] not in used_urls:
            used_urls.append(record["url"])
        for section_key in SECTION_KEYS:
            if _section_score(extracted[section_key]) > _section_score(combined[section_key]):
                combined[section_key] = extracted[section_key]
    return combined, relevant_records, used_urls


def _warm_profile_page(page: Any) -> list[str]:
    markers: list[str] = []
    for step in range(1, 4):
        try:
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {step} / 3);")
            markers.append(f"scroll_step_{step}")
            for section_key, fragment in DETAIL_ROUTE_FRAGMENTS.items():
                try:
                    if page.locator(f"a[href*='/details/{fragment}/']").first().is_visible(timeout=750):
                        markers.append(f"route_visible:{section_key}")
                except Exception:
                    continue
        except Exception:
            break
    return _dedupe_texts(markers)


def _extract_skills_from_records(
    records: list[dict[str, Any]],
    *,
    profile_id: str,
    profile_url: str,
    name: str,
) -> list[str]:
    collected: list[str] = []
    for record in records:
        if record.get("kind") != "skills_rsc":
            continue
        if not _record_looks_relevant(record, profile_id=profile_id, profile_url=profile_url, name=name):
            continue
        for skill in _extract_skills_from_rsc_text(str(record.get("body", ""))):
            if skill not in collected:
                collected.append(skill)
    return collected


def _extract_languages_from_records(
    records: list[dict[str, Any]],
    *,
    profile_id: str,
    profile_url: str,
    name: str,
) -> list[str]:
    collected: list[str] = []
    for record in records:
        if record.get("kind") != "languages_rsc":
            continue
        if not _record_looks_relevant(record, profile_id=profile_id, profile_url=profile_url, name=name):
            continue
        for language in _extract_languages_from_rsc_text(str(record.get("body", ""))):
            if language not in collected:
                collected.append(language)
    return collected


def _extract_experience_from_records(
    records: list[dict[str, Any]],
    *,
    profile_id: str,
    profile_url: str,
    name: str,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") != "experience_rsc":
            continue
        if not _record_looks_relevant(record, profile_id=profile_id, profile_url=profile_url, name=name):
            continue
        for experience in _extract_experience_records_from_rsc_text(str(record.get("body", ""))):
            if experience not in collected:
                collected.append(experience)
    return collected


def _extract_education_from_records(
    records: list[dict[str, Any]],
    *,
    profile_id: str,
    profile_url: str,
    name: str,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") != "education_rsc":
            continue
        if not _record_looks_relevant(record, profile_id=profile_id, profile_url=profile_url, name=name):
            continue
        for education_record in _extract_education_records_from_rsc_text(str(record.get("body", ""))):
            if education_record not in collected:
                collected.append(education_record)
    return collected


def _extract_projects_from_records(
    records: list[dict[str, Any]],
    *,
    profile_id: str,
    profile_url: str,
    name: str,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") != "projects_rsc":
            continue
        if not _record_looks_relevant(record, profile_id=profile_id, profile_url=profile_url, name=name):
            continue
        for project_record in _extract_project_records_from_rsc_text(str(record.get("body", ""))):
            if project_record not in collected:
                collected.append(project_record)
    return collected


def _extract_licenses_from_records(
    records: list[dict[str, Any]],
    *,
    profile_id: str,
    profile_url: str,
    name: str,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") != "licenses_rsc":
            continue
        if not _record_looks_relevant(record, profile_id=profile_id, profile_url=profile_url, name=name):
            continue
        for license_record in _extract_license_records_from_rsc_text(str(record.get("body", ""))):
            if license_record not in collected:
                collected.append(license_record)
    return collected


def _capture_skills_route(
    *,
    state_path: Path,
    route_url: str,
    timeout_sec: int,
    expected_count: int | None = None,
) -> tuple[list[str], str | None, list[dict[str, Any]]]:
    status_code, final_url, route_html = _request_with_session(
        state_path=state_path,
        url=route_url,
        timeout_sec=timeout_sec,
    )
    if status_code >= 400:
        return [], "request_replay_failed", []
    url_status = _detect_visibility_status_from_url(final_url or route_url)
    if url_status != "ok":
        return [], "access_denied", []
    visibility_status = _detect_visibility_status(BeautifulSoup(route_html or "", "html.parser"))
    if visibility_status != "ok":
        return [], "access_denied", []

    initial_request = _extract_skills_initial_pagination_request_from_html(route_html)
    if not isinstance(initial_request, dict):
        return [], "no_request_shape", []

    target_count = min(200, expected_count or 200)
    attempted_starts: set[int] = set()
    skills: list[str] = []
    records: list[dict[str, Any]] = []
    current_request = initial_request
    referer = final_url or route_url

    while isinstance(current_request, dict) and len(skills) < target_count:
        start = _extract_skills_pagination_start(current_request)
        if not isinstance(start, int) or start in attempted_starts:
            break
        payload = _build_skills_request_payload_from_pagination_request(current_request)
        if not isinstance(payload, dict):
            return skills, "request_replay_failed" if skills else "no_request_shape", records
        attempted_starts.add(start)
        status_code, _response_url, response_text = _request_with_session(
            state_path=state_path,
            url=SKILLS_PAGINATION_URL,
            method="POST",
            payload=payload,
            referer=referer,
            timeout_sec=timeout_sec,
        )
        if status_code >= 400:
            return skills, "request_replay_failed", records
        records.append(
            {
                "kind": "skills_rsc",
                "url": _sanitize_record_url(SKILLS_PAGINATION_URL),
                "request_url": SKILLS_PAGINATION_URL,
                "body": response_text,
                "request_payload": payload,
            }
        )
        skills = _dedupe_texts(skills + _extract_skills_from_rsc_text(response_text))
        current_request = _select_next_skills_pagination_request_from_text(
            response_text,
            attempted_starts=attempted_starts,
        )

    if expected_count is not None and len(skills) < expected_count:
        return skills, "pagination_stopped_early", records
    if not skills:
        return [], "no_request_shape", records
    return skills, None, records


def _capture_languages_route(
    *,
    state_path: Path,
    route_url: str,
    timeout_sec: int,
) -> tuple[list[str], str | None, list[dict[str, Any]]]:
    status_code, final_url, route_html = _request_with_session(
        state_path=state_path,
        url=route_url,
        timeout_sec=timeout_sec,
    )
    if status_code >= 400:
        return [], "request_replay_failed", []
    url_status = _detect_visibility_status_from_url(final_url or route_url)
    if url_status != "ok":
        return [], "access_denied", []
    visibility_status = _detect_visibility_status(BeautifulSoup(route_html or "", "html.parser"))
    if visibility_status != "ok":
        return [], "access_denied", []

    initial_request = _extract_languages_initial_pagination_request_from_html(route_html)
    if not isinstance(initial_request, dict):
        return [], "no_request_shape", []

    attempted_starts: set[int] = set()
    languages: list[str] = []
    records: list[dict[str, Any]] = []
    current_request = initial_request
    referer = final_url or route_url

    while isinstance(current_request, dict):
        start = _extract_skills_pagination_start(current_request)
        if not isinstance(start, int) or start in attempted_starts:
            break
        payload = _build_languages_request_payload_from_pagination_request(current_request)
        if not isinstance(payload, dict):
            return languages, "request_replay_failed" if languages else "no_request_shape", records
        attempted_starts.add(start)
        status_code, _response_url, response_text = _request_with_session(
            state_path=state_path,
            url=LANGUAGES_PAGINATION_URL,
            method="POST",
            payload=payload,
            referer=referer,
            timeout_sec=timeout_sec,
        )
        if status_code >= 400:
            return languages, "request_replay_failed", records
        records.append(
            {
                "kind": "languages_rsc",
                "url": _sanitize_record_url(LANGUAGES_PAGINATION_URL),
                "request_url": LANGUAGES_PAGINATION_URL,
                "body": response_text,
                "request_payload": payload,
            }
        )
        updated_languages = _dedupe_texts(languages + _extract_languages_from_rsc_text(response_text))
        if len(updated_languages) <= len(languages):
            break
        languages = updated_languages
        current_request = _select_next_languages_pagination_request_from_text(
            response_text,
            attempted_starts=attempted_starts,
        )

    if not languages:
        return [], "no_request_shape", records
    return languages, None, records


def _capture_education_route(
    *,
    state_path: Path,
    route_url: str,
    timeout_sec: int,
) -> tuple[list[dict[str, Any]], str | None, list[dict[str, Any]]]:
    status_code, final_url, route_html = _request_with_session(
        state_path=state_path,
        url=route_url,
        timeout_sec=timeout_sec,
    )
    if status_code >= 400:
        return [], "request_replay_failed", []
    url_status = _detect_visibility_status_from_url(final_url or route_url)
    if url_status != "ok":
        return [], "access_denied", []
    visibility_status = _detect_visibility_status(BeautifulSoup(route_html or "", "html.parser"))
    if visibility_status != "ok":
        return [], "access_denied", []
    initial_request = _extract_education_initial_pagination_request_from_html(route_html)
    if not isinstance(initial_request, dict):
        return [], "no_request_shape", []

    attempted_starts: set[int] = set()
    attempted_edit_urls: set[str] = set()
    education: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    current_request = initial_request
    referer = final_url or route_url

    while isinstance(current_request, dict):
        start = _extract_skills_pagination_start(current_request)
        if not isinstance(start, int) or start in attempted_starts:
            break
        payload = _build_education_request_payload_from_pagination_request(current_request)
        if not isinstance(payload, dict):
            return education, "request_replay_failed" if education else "no_request_shape", records
        attempted_starts.add(start)
        status_code, _response_url, response_text = _request_with_session(
            state_path=state_path,
            url=EDUCATION_PAGINATION_URL,
            method="POST",
            payload=payload,
            referer=referer,
            timeout_sec=timeout_sec,
        )
        if status_code >= 400:
            return education, "request_replay_failed", records
        records.append(
            {
                "kind": "education_rsc",
                "url": _sanitize_record_url(EDUCATION_PAGINATION_URL),
                "request_url": EDUCATION_PAGINATION_URL,
                "body": response_text,
                "request_payload": payload,
            }
        )
        page_records: list[dict[str, Any]] = []
        for bundle in _extract_education_entry_bundles_from_rsc_text(response_text):
            record = dict(bundle.get("record", {}))
            edit_form_url = _resolve_profile_relative_url(referer, _norm(str(bundle.get("edit_form_url", ""))))
            if edit_form_url and edit_form_url not in attempted_edit_urls:
                attempted_edit_urls.add(edit_form_url)
                edit_status, edit_final_url, edit_html = _request_with_session(
                    state_path=state_path,
                    url=edit_form_url,
                    referer=referer,
                    timeout_sec=timeout_sec,
                )
                edit_url_status = _detect_visibility_status_from_url(edit_final_url or edit_form_url)
                if edit_status < 400 and edit_url_status == "ok":
                    edit_visibility_status = _detect_visibility_status(BeautifulSoup(edit_html or "", "html.parser"))
                    if edit_visibility_status == "ok":
                        record = _merge_education_record(record, edit_html)
            page_records.append(record)
        updated_education = _coerce_section_value("education", education + page_records)
        if isinstance(updated_education, list):
            education = updated_education
        next_request = _select_next_education_pagination_request_from_text(
            response_text,
            attempted_starts=attempted_starts,
        )
        if next_request is None:
            break
        current_request = next_request

    return education, None if attempted_starts else "no_request_shape", records


def _capture_projects_route(
    *,
    state_path: Path,
    route_url: str,
    timeout_sec: int,
) -> tuple[list[dict[str, Any]], str | None, list[dict[str, Any]]]:
    status_code, final_url, route_html = _request_with_session(
        state_path=state_path,
        url=route_url,
        timeout_sec=timeout_sec,
    )
    if status_code >= 400:
        return [], "request_replay_failed", []
    url_status = _detect_visibility_status_from_url(final_url or route_url)
    if url_status != "ok":
        return [], "access_denied", []
    visibility_status = _detect_visibility_status(BeautifulSoup(route_html or "", "html.parser"))
    if visibility_status != "ok":
        return [], "access_denied", []
    initial_request = _extract_projects_initial_pagination_request_from_html(route_html)
    if not isinstance(initial_request, dict):
        return [], "no_request_shape", []

    attempted_starts: set[int] = set()
    attempted_edit_urls: set[str] = set()
    projects: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    current_request = initial_request
    referer = final_url or route_url

    while isinstance(current_request, dict):
        start = _extract_skills_pagination_start(current_request)
        if not isinstance(start, int) or start in attempted_starts:
            break
        payload = _build_projects_request_payload_from_pagination_request(current_request)
        if not isinstance(payload, dict):
            return projects, "request_replay_failed" if projects else "no_request_shape", records
        attempted_starts.add(start)
        status_code, _response_url, response_text = _request_with_session(
            state_path=state_path,
            url=PROJECTS_PAGINATION_URL,
            method="POST",
            payload=payload,
            referer=referer,
            timeout_sec=timeout_sec,
        )
        if status_code >= 400:
            return projects, "request_replay_failed", records
        records.append(
            {
                "kind": "projects_rsc",
                "url": _sanitize_record_url(PROJECTS_PAGINATION_URL),
                "request_url": PROJECTS_PAGINATION_URL,
                "body": response_text,
                "request_payload": payload,
            }
        )
        page_bundles = _extract_project_entry_bundles_from_rsc_text(response_text)
        fresh_bundles: list[dict[str, Any]] = []
        page_records: list[dict[str, Any]] = []
        for bundle in page_bundles:
            edit_form_url = _resolve_profile_relative_url(referer, _norm(str(bundle.get("edit_form_url", ""))))
            if not edit_form_url or edit_form_url in attempted_edit_urls:
                page_records.append(dict(bundle.get("record", {})))
                continue
            attempted_edit_urls.add(edit_form_url)
            fresh_bundles.append(bundle)
        if fresh_bundles:
            max_workers = min(REQUEST_REPLAY_MAX_WORKERS, len(fresh_bundles))
            if max_workers <= 1:
                page_records.extend(
                    _merge_project_bundle_with_edit_form(
                        bundle=bundle,
                        state_path=state_path,
                        referer=referer,
                        timeout_sec=timeout_sec,
                    )
                    for bundle in fresh_bundles
                )
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    page_records.extend(
                        executor.map(
                            lambda bundle: _merge_project_bundle_with_edit_form(
                                bundle=bundle,
                                state_path=state_path,
                                referer=referer,
                                timeout_sec=timeout_sec,
                            ),
                            fresh_bundles,
                        )
                    )
        updated_projects = _coerce_section_value("projects", projects + page_records)
        if isinstance(updated_projects, list):
            projects = updated_projects
        next_request = _select_next_projects_pagination_request_from_text(
            response_text,
            attempted_starts=attempted_starts,
        )
        if next_request is None:
            break
        current_request = next_request

    return projects, None if attempted_starts else "no_request_shape", records


def _capture_experience_route(
    *,
    state_path: Path,
    route_url: str,
    timeout_sec: int,
) -> tuple[list[dict[str, Any]], str | None, list[dict[str, Any]]]:
    status_code, final_url, route_html = _request_with_session(
        state_path=state_path,
        url=route_url,
        timeout_sec=timeout_sec,
    )
    if status_code >= 400:
        return [], "request_replay_failed", []
    url_status = _detect_visibility_status_from_url(final_url or route_url)
    if url_status != "ok":
        return [], "access_denied", []
    visibility_status = _detect_visibility_status(BeautifulSoup(route_html or "", "html.parser"))
    if visibility_status != "ok":
        return [], "access_denied", []
    initial_request = _extract_experience_initial_pagination_request_from_html(route_html)
    if not isinstance(initial_request, dict):
        return [], "no_request_shape", []

    attempted_starts: set[int] = set()
    attempted_edit_urls: set[str] = set()
    experience: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    current_request = initial_request
    referer = final_url or route_url

    while isinstance(current_request, dict):
        start = _extract_skills_pagination_start(current_request)
        if not isinstance(start, int) or start in attempted_starts:
            break
        payload = _build_experience_request_payload_from_pagination_request(current_request)
        if not isinstance(payload, dict):
            return experience, "request_replay_failed" if experience else "no_request_shape", records
        attempted_starts.add(start)
        status_code, _response_url, response_text = _request_with_session(
            state_path=state_path,
            url=EXPERIENCE_PAGINATION_URL,
            method="POST",
            payload=payload,
            referer=referer,
            timeout_sec=timeout_sec,
        )
        if status_code >= 400:
            return experience, "request_replay_failed", records
        records.append(
            {
                "kind": "experience_rsc",
                "url": _sanitize_record_url(EXPERIENCE_PAGINATION_URL),
                "request_url": EXPERIENCE_PAGINATION_URL,
                "body": response_text,
                "request_payload": payload,
            }
        )
        page_records: list[dict[str, Any]] = []
        for bundle in _extract_experience_entry_bundles_from_rsc_text(response_text):
            record = dict(bundle.get("record", {}))
            edit_form_url = _resolve_profile_relative_url(referer, _norm(str(bundle.get("edit_form_url", ""))))
            if edit_form_url and edit_form_url not in attempted_edit_urls:
                attempted_edit_urls.add(edit_form_url)
                edit_status, edit_final_url, edit_html = _request_with_session(
                    state_path=state_path,
                    url=edit_form_url,
                    referer=referer,
                    timeout_sec=timeout_sec,
                )
                edit_url_status = _detect_visibility_status_from_url(edit_final_url or edit_form_url)
                if edit_status < 400 and edit_url_status == "ok":
                    edit_visibility_status = _detect_visibility_status(BeautifulSoup(edit_html or "", "html.parser"))
                    if edit_visibility_status == "ok":
                        record = _merge_experience_record(record, edit_html)
            page_records.append(record)
        updated_experience = _coerce_section_value("experience", experience + page_records)
        if isinstance(updated_experience, list):
            experience = updated_experience
        next_request = _select_next_experience_pagination_request_from_text(
            response_text,
            attempted_starts=attempted_starts,
        )
        if next_request is None:
            break
        current_request = next_request

    return experience, None if attempted_starts else "no_request_shape", records


def _capture_licenses_route(
    *,
    state_path: Path,
    route_url: str,
    timeout_sec: int,
) -> tuple[list[dict[str, Any]], str | None, list[dict[str, Any]]]:
    status_code, final_url, route_html = _request_with_session(
        state_path=state_path,
        url=route_url,
        timeout_sec=timeout_sec,
    )
    if status_code >= 400:
        return [], "request_replay_failed", []
    url_status = _detect_visibility_status_from_url(final_url or route_url)
    if url_status != "ok":
        return [], "access_denied", []
    visibility_status = _detect_visibility_status(BeautifulSoup(route_html or "", "html.parser"))
    if visibility_status != "ok":
        return [], "access_denied", []
    initial_request = _extract_certifications_initial_pagination_request_from_html(route_html)
    if not isinstance(initial_request, dict):
        return [], "no_request_shape", []

    attempted_starts: set[int] = set()
    licenses: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    current_request = initial_request
    referer = final_url or route_url

    while isinstance(current_request, dict):
        start = _extract_skills_pagination_start(current_request)
        if not isinstance(start, int) or start in attempted_starts:
            break
        payload = _build_certifications_request_payload_from_pagination_request(current_request)
        if not isinstance(payload, dict):
            return licenses, "request_replay_failed" if licenses else "no_request_shape", records
        attempted_starts.add(start)
        status_code, _response_url, response_text = _request_with_session(
            state_path=state_path,
            url=CERTIFICATIONS_PAGINATION_URL,
            method="POST",
            payload=payload,
            referer=referer,
            timeout_sec=timeout_sec,
        )
        if status_code >= 400:
            return licenses, "request_replay_failed", records
        records.append(
            {
                "kind": "licenses_rsc",
                "url": _sanitize_record_url(CERTIFICATIONS_PAGINATION_URL),
                "request_url": CERTIFICATIONS_PAGINATION_URL,
                "body": response_text,
                "request_payload": payload,
            }
        )
        updated_licenses = _coerce_section_value("licenses_certifications", licenses + _extract_license_records_from_rsc_text(response_text))
        if isinstance(updated_licenses, list):
            licenses = updated_licenses
        next_request = _select_next_certifications_pagination_request_from_text(
            response_text,
            attempted_starts=attempted_starts,
        )
        if next_request is None:
            break
        current_request = next_request

    return licenses, None if attempted_starts else "no_request_shape", records


def _build_route_candidate_map(html: str, profile_url: str) -> dict[str, str]:
    route_candidates_map: dict[str, str] = {}
    for section_key, route_url in _extract_detail_route_urls_from_html(html):
        route_candidates_map.setdefault(section_key, route_url)
    supported_constructed_sections = {"skills", "education", "experience", "licenses_certifications"}
    if any(section_key not in route_candidates_map for section_key in supported_constructed_sections):
        for section_key, route_url in _build_constructed_detail_route_candidates(profile_url):
            if section_key not in supported_constructed_sections:
                continue
            route_candidates_map.setdefault(section_key, route_url)
    return route_candidates_map


def _initial_section_transport(snapshot: dict[str, Any]) -> dict[str, str]:
    transport: dict[str, str] = {}
    for section_key in SECTION_KEYS:
        current_value = _coerce_section_value(section_key, snapshot.get(section_key, _empty_section_value(section_key)))
        transport[section_key] = "initial_html" if _has_section_content(current_value) else "missing"
    return transport


def _maybe_block_unsupported_sections(
    *,
    route_candidates: dict[str, str],
    section_blockers: dict[str, str],
    supported_sections: set[str],
) -> dict[str, str]:
    for section_key in route_candidates:
        if section_key in supported_sections:
            continue
        section_blockers.setdefault(section_key, "no_request_shape")
    return section_blockers


def _relevant_records_for_save(
    captured_network: list[dict[str, Any]],
    *,
    profile_id: str,
    profile_url: str,
    name: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    _network_sections, relevant_records, used_urls = _extract_network_sections_for_profile(
        captured_network,
        profile_id=profile_id,
        profile_url=profile_url,
        name=name,
    )
    return relevant_records, used_urls


def _capture_with_session(
    *,
    profile_name: str,
    profile_url: str,
    capture_type: str,
    app_home: str | Path | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    save_raw: bool = False,
    playwright_factory=None,
) -> dict[str, Any]:
    operation = "profile.capture-own" if capture_type == "own_profile" else "profile.capture"
    start = time.perf_counter()
    profile_dir = profile_storage_dir(app_home, profile_name)
    state_path = session_state_path(app_home, profile_name)
    if not state_path.exists():
        return _missing_session_result(
            operation=operation,
            profile_name=profile_name,
            profile_url=profile_url,
            managed_profile=profile_dir,
        )

    raw_html_path: Path | None = None
    raw_network_path: Path | None = None
    browser = None
    context = None
    try:
        with (playwright_factory or _default_playwright_factory)() as playwright:
            browser, context = _launch_capture_context(playwright, state_path=state_path)
            page = context.new_page()
            captured_network: list[dict[str, Any]] = []
            page.goto(profile_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            initial_html = _capture_ready_main_html(page, profile_url=profile_url, capture_type=capture_type)
            initial_url = getattr(page, "url", profile_url) or profile_url
            try:
                parse_url = validate_profile_url(initial_url)
            except ValueError:
                parse_url = profile_url
            inline_snapshot = parse_profile_html(initial_html, profile_url=parse_url, capture_type=capture_type)
            visibility_status = inline_snapshot["visibility"]["status"]
            url_status = _detect_visibility_status_from_url(initial_url)
            if url_status != "ok":
                visibility_status = url_status
            if visibility_status in {"sign_in_required", "checkpoint_required"}:
                return _invalid_session_result(
                    operation=operation,
                    profile_name=profile_name,
                    profile_url=profile_url,
                    managed_profile=profile_dir,
                    visibility_status=visibility_status,
                )
            inline_snapshot["visibility"]["status"] = visibility_status
            inline_snapshot["status"] = visibility_status
            main_profile_url = inline_snapshot["profile_url"]

            route_candidates = _build_route_candidate_map(initial_html, main_profile_url)
            expected_skills_count = _extract_section_count_from_html(initial_html, section_key="skills")
            section_transport = _initial_section_transport(inline_snapshot)
            section_blockers: dict[str, str] = {}
            detail_routes_visited: list[str] = []
            dialogs_opened: list[str] = []
            warnings: list[str] = []
            lazy_load_markers_seen: list[str] = []

            network_sections: dict[str, Any] = {}
            skills_route = route_candidates.get("skills")
            if skills_route:
                skills, skills_blocker, skill_records = _capture_skills_route(
                    state_path=state_path,
                    route_url=skills_route,
                    timeout_sec=timeout_sec,
                    expected_count=expected_skills_count,
                )
                captured_network.extend(skill_records)
                detail_routes_visited.append(skills_route)
                if skills:
                    network_sections["skills"] = skills
                    section_transport["skills"] = "api_replay"
                elif not _has_section_content(inline_snapshot.get("skills")):
                    section_transport["skills"] = "missing"
                if skills_blocker:
                    section_blockers["skills"] = skills_blocker
                    warnings.append(f"skills:{skills_blocker}")
            elif expected_skills_count:
                inline_skills = _coerce_section_value("skills", inline_snapshot.get("skills"))
                inline_skill_count = len(inline_skills) if isinstance(inline_skills, list) else 0
                if inline_skill_count < expected_skills_count:
                    section_blockers["skills"] = "no_request_shape"
                    warnings.append("skills:no_request_shape")

            languages_route = route_candidates.get("languages")
            if languages_route:
                languages, languages_blocker, language_records = _capture_languages_route(
                    state_path=state_path,
                    route_url=languages_route,
                    timeout_sec=timeout_sec,
                )
                captured_network.extend(language_records)
                detail_routes_visited.append(languages_route)
                if languages:
                    network_sections["languages"] = languages
                    section_transport["languages"] = "api_replay"
                elif not _has_section_content(inline_snapshot.get("languages")):
                    section_transport["languages"] = "missing"
                if languages_blocker:
                    section_blockers["languages"] = languages_blocker
                    warnings.append(f"languages:{languages_blocker}")

            education_route = route_candidates.get("education")
            if education_route:
                education_records, education_blocker, education_rsc_records = _capture_education_route(
                    state_path=state_path,
                    route_url=education_route,
                    timeout_sec=timeout_sec,
                )
                captured_network.extend(education_rsc_records)
                detail_routes_visited.append(education_route)
                network_sections["education"] = education_records
                section_transport["education"] = "api_replay" if education_blocker is None else "missing"
                if education_blocker:
                    section_blockers["education"] = education_blocker
                    warnings.append(f"education:{education_blocker}")

            projects_route = route_candidates.get("projects")
            if projects_route:
                project_records, projects_blocker, projects_rsc_records = _capture_projects_route(
                    state_path=state_path,
                    route_url=projects_route,
                    timeout_sec=timeout_sec,
                )
                captured_network.extend(projects_rsc_records)
                detail_routes_visited.append(projects_route)
                network_sections["projects"] = project_records
                section_transport["projects"] = "api_replay" if projects_blocker is None else "missing"
                if projects_blocker:
                    section_blockers["projects"] = projects_blocker
                    warnings.append(f"projects:{projects_blocker}")

            experience_route = route_candidates.get("experience")
            if experience_route:
                experience_records, experience_blocker, experience_rsc_records = _capture_experience_route(
                    state_path=state_path,
                    route_url=experience_route,
                    timeout_sec=timeout_sec,
                )
                captured_network.extend(experience_rsc_records)
                detail_routes_visited.append(experience_route)
                network_sections["experience"] = experience_records
                section_transport["experience"] = "api_replay" if experience_blocker is None else "missing"
                if experience_blocker:
                    section_blockers["experience"] = experience_blocker
                    warnings.append(f"experience:{experience_blocker}")

            licenses_route = route_candidates.get("licenses_certifications")
            if licenses_route:
                license_records, licenses_blocker, licenses_rsc_records = _capture_licenses_route(
                    state_path=state_path,
                    route_url=licenses_route,
                    timeout_sec=timeout_sec,
                )
                captured_network.extend(licenses_rsc_records)
                detail_routes_visited.append(licenses_route)
                network_sections["licenses_certifications"] = license_records
                section_transport["licenses_certifications"] = "api_replay" if licenses_blocker is None else "missing"
                if licenses_blocker:
                    section_blockers["licenses_certifications"] = licenses_blocker
                    warnings.append(f"licenses_certifications:{licenses_blocker}")

            section_blockers = _maybe_block_unsupported_sections(
                route_candidates=route_candidates,
                section_blockers=section_blockers,
                supported_sections={"skills", "languages", "education", "projects", "experience", "licenses_certifications"},
            )
            for section_key, blocker in section_blockers.items():
                marker = f"{section_key}:{blocker}"
                if marker not in warnings:
                    warnings.append(marker)

            merged_snapshot = merge_profile_snapshots(
                inline_snapshot,
                network_sections=network_sections,
            )
            merged_snapshot["capture_depth"] = "deep"
            for section_key in STRUCTURED_RECORD_SECTIONS:
                if section_transport.get(section_key) == "api_replay":
                    merged_snapshot[section_key] = _normalize_record_list(section_key, network_sections.get(section_key, []))
                    merged_snapshot["section_sources"][section_key] = "network"
                else:
                    merged_snapshot[section_key] = []
                    merged_snapshot["section_sources"][section_key] = "missing"
            merged_snapshot["requested_profile_url"] = profile_url
            merged_snapshot["final_url"] = initial_url
            merged_snapshot["detail_routes_visited"] = detail_routes_visited
            merged_snapshot["dialogs_opened"] = dialogs_opened
            relevant_records, used_network_urls = _relevant_records_for_save(
                captured_network,
                profile_id=inline_snapshot["profile_id"],
                profile_url=main_profile_url,
                name=inline_snapshot["name"],
            )
            merged_snapshot["network_responses_used"] = used_network_urls
            merged_snapshot["lazy_load_markers_seen"] = lazy_load_markers_seen
            merged_snapshot["warnings"] = warnings
            merged_snapshot["section_transport"] = section_transport
            merged_snapshot["section_blockers"] = section_blockers

            if save_raw:
                raw_html_path = _save_raw_html(initial_html, app_home=app_home, profile_id=merged_snapshot["profile_id"])
                if relevant_records:
                    raw_network_path = _save_raw_network_payloads(
                        relevant_records,
                        app_home=app_home,
                        profile_id=merged_snapshot["profile_id"],
                    )
            snapshot_path = _save_snapshot(merged_snapshot, app_home=app_home, capture_type=capture_type)
            status = merged_snapshot["visibility"]["status"]
            return make_result(
                ok=status == "ok",
                operation=operation,
                result={
                    **merged_snapshot,
                    "snapshot_path": str(snapshot_path),
                    "raw_html_path": str(raw_html_path) if raw_html_path else None,
                    "raw_network_path": str(raw_network_path) if raw_network_path else None,
                    "expanded_selectors": [],
                    "action_timing_ms": round((time.perf_counter() - start) * 1000),
                    "managed_profile": str(profile_dir),
                    "session_state": str(state_path),
                },
                stderr="" if status == "ok" else f"LinkedIn profile capture failed with status: {status}",
                exit_code=0 if status == "ok" else 3,
            )
    except PlaywrightTimeoutError as exc:
        return make_result(
            ok=False,
            operation=operation,
            result={"status": "timeout", "profile_url": profile_url},
            stderr=f"Timed out capturing LinkedIn profile: {exc}",
            exit_code=124,
        )
    except Exception as exc:
        return make_result(
            ok=False,
            operation=operation,
            result={"status": "browser_error", "profile_url": profile_url},
            stderr=str(exc),
            exit_code=1,
        )
    finally:
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass


def _build_show_all_selectors() -> list[tuple[str, str]]:
    selectors: list[tuple[str, str]] = []
    for section_key, aliases in SECTION_ALIASES.items():
        fragment = DETAIL_ROUTE_FRAGMENTS.get(section_key)
        if fragment:
            selectors.append((section_key, f"a[href*='/details/{fragment}/']"))
        for alias in sorted(aliases):
            title = alias.title()
            for show_all_text in SHOW_ALL_TEXTS:
                selectors.append((section_key, f"section:has(h2:has-text('{title}')) a:has-text('{show_all_text}')"))
                selectors.append((section_key, f"section:has(h2:has-text('{title}')) button:has-text('{show_all_text}')"))
    return selectors


SHOW_ALL_ROUTE_SELECTORS = _build_show_all_selectors()


def _extract_detail_route_urls_from_html(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    routes: list[tuple[str, str]] = []
    seen: set[str] = set()
    fragment_to_section = {fragment: section_key for section_key, fragment in DETAIL_ROUTE_FRAGMENTS.items()}
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if href.startswith("/"):
            href = f"https://www.linkedin.com{href}"
        match = re.fullmatch(r"https://www\.linkedin\.com/in/[^/]+/details/([^/]+)/?", href)
        if not match:
            continue
        section_key = fragment_to_section.get(match.group(1).lower())
        if section_key is None or href in seen:
            continue
        seen.add(href)
        routes.append((section_key, href))
    return routes


def _build_constructed_detail_route_candidates(profile_url: str) -> list[tuple[str, str]]:
    if not re.fullmatch(r"https://www\.linkedin\.com/in/[^/]+/", profile_url):
        return []
    return [
        (section_key, f"{profile_url}details/{fragment}/")
        for section_key, fragment in DETAIL_ROUTE_FRAGMENTS.items()
    ]


def _capture_detail_sources(
    page: Any,
    *,
    main_profile_url: str,
    profile_name: str,
    timeout_sec: int,
    captured_network: list[dict[str, Any]],
    expected_skills_count: int | None = None,
    html_route_candidates: list[tuple[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    detail_snapshots: list[dict[str, Any]] = []
    detail_routes_visited: list[str] = []
    dialogs_opened: list[str] = []
    warnings: list[str] = []
    seen_sections: set[str] = set()
    profile_id = profile_id_from_url(main_profile_url)

    for section_key, route_url in html_route_candidates or []:
        if section_key in seen_sections:
            continue
        try:
            page.goto(route_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            url_status = _detect_visibility_status_from_url(getattr(page, "url", route_url) or route_url)
            if url_status != "ok":
                warnings.append(f"{section_key}:{url_status}")
                continue
            network_skills: list[str] = []
            if section_key == "skills":
                route_html, network_skills = _capture_skills_route(
                    page,
                    captured_network,
                    profile_id=profile_id,
                    profile_url=main_profile_url,
                    name=profile_name,
                    timeout_sec=timeout_sec,
                    expected_count=expected_skills_count,
                )
            else:
                _wait_for_detail_route_content(page, section_key)
                route_html = _capture_ready_detail_html(page, section_key=section_key)
            detail_snapshot = parse_profile_html(route_html, profile_url=main_profile_url, capture_type="own_profile")
            if not _has_section_content(detail_snapshot.get(section_key)):
                detail_snapshot[section_key] = extract_detail_route_section(route_html, section_key=section_key)
            section_has_network_fallback = section_key == "skills" and bool(network_skills)
            if _has_section_content(detail_snapshot.get(section_key)) or section_has_network_fallback:
                detail_routes_visited.append(route_url)
            if _has_section_content(detail_snapshot.get(section_key)):
                detail_snapshots.append(detail_snapshot)
                seen_sections.add(section_key)
            elif section_has_network_fallback:
                seen_sections.add(section_key)
            elif section_key == "skills":
                warnings.append("skills:capture_failed")
            page.goto(main_profile_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            _expand_read_only_sections(page)
        except Exception:
            continue

    for section_key, selector in SHOW_ALL_ROUTE_SELECTORS:
        if section_key in seen_sections:
            continue
        try:
            locator = page.locator(selector).first()
            if not locator.is_visible(timeout=250):
                continue
            before_url = getattr(page, "url", main_profile_url) or main_profile_url
            locator.click(timeout=1000)
            after_url = getattr(page, "url", before_url) or before_url
            url_status = _detect_visibility_status_from_url(after_url)
            if url_status != "ok":
                warnings.append(f"{section_key}:{url_status}")
                continue
            if after_url != before_url and "/details/" in after_url:
                network_skills = []
                if section_key == "skills":
                    route_html, network_skills = _capture_skills_route(
                        page,
                        captured_network,
                        profile_id=profile_id,
                        profile_url=main_profile_url,
                        name=profile_name,
                        timeout_sec=timeout_sec,
                        expected_count=expected_skills_count,
                    )
                else:
                    _wait_for_detail_route_content(page, section_key)
                    route_html = _capture_ready_detail_html(page, section_key=section_key)
                detail_snapshot = parse_profile_html(route_html, profile_url=main_profile_url, capture_type="own_profile")
                if not _has_section_content(detail_snapshot.get(section_key)):
                    detail_snapshot[section_key] = extract_detail_route_section(route_html, section_key=section_key)
                section_has_network_fallback = section_key == "skills" and bool(network_skills)
                if _has_section_content(detail_snapshot.get(section_key)) or section_has_network_fallback:
                    detail_routes_visited.append(after_url)
                if _has_section_content(detail_snapshot.get(section_key)):
                    detail_snapshots.append(detail_snapshot)
                    seen_sections.add(section_key)
                elif section_has_network_fallback:
                    seen_sections.add(section_key)
                elif section_key == "skills":
                    warnings.append("skills:capture_failed")
                page.goto(main_profile_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
                _expand_read_only_sections(page)
                continue
            dialog = page.locator("[role='dialog']").first()
            if dialog.is_visible(timeout=250):
                detail_snapshot = parse_profile_html(_safe_page_content(page), profile_url=main_profile_url, capture_type="own_profile")
                if _has_section_content(detail_snapshot.get(section_key)):
                    dialogs_opened.append(section_key)
                    detail_snapshots.append(detail_snapshot)
                    seen_sections.add(section_key)
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
        except Exception:
            continue

    return detail_snapshots, detail_routes_visited, dialogs_opened, warnings


def _capture_own_profile_deep(
    *,
    profile_name: str,
    app_home: str | Path | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    save_raw: bool = False,
    playwright_factory=None,
) -> dict[str, Any]:
    return _capture_with_session(
        profile_name=profile_name,
        profile_url=OWN_PROFILE_URL,
        capture_type="own_profile",
        app_home=app_home,
        timeout_sec=timeout_sec,
        save_raw=save_raw,
        playwright_factory=playwright_factory,
    )


def _capture_profile(
    *,
    profile_name: str,
    profile_url: str,
    capture_type: str,
    app_home: str | Path | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    save_raw: bool = False,
    playwright_factory=None,
) -> dict[str, Any]:
    return _capture_with_session(
        profile_name=profile_name,
        profile_url=profile_url,
        capture_type=capture_type,
        app_home=app_home,
        timeout_sec=timeout_sec,
        save_raw=save_raw,
        playwright_factory=playwright_factory,
    )


def capture_accessible_profile(
    *,
    profile_name: str,
    url: str | None = None,
    profile_id: str | None = None,
    confirm_accessible_profile_capture: bool = False,
    app_home: str | Path | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    save_raw: bool = False,
    playwright_factory=None,
) -> dict[str, Any]:
    if not confirm_accessible_profile_capture:
        return make_result(
            ok=False,
            operation="profile.capture",
            result={"status": "confirmation_required"},
            stderr="Accessible profile capture requires --confirm-accessible-profile-capture.",
            exit_code=2,
        )
    try:
        profile_url = build_profile_url(profile_id=profile_id, url=url)
    except ValueError as exc:
        return make_result(
            ok=False,
            operation="profile.capture",
            result={"status": "invalid_profile_url"},
            stderr=str(exc),
            exit_code=2,
        )
    return _capture_profile(
        profile_name=profile_name,
        profile_url=profile_url,
        capture_type="accessible_profile",
        app_home=app_home,
        timeout_sec=timeout_sec,
        save_raw=save_raw,
        playwright_factory=playwright_factory,
    )


def capture_own_profile(
    *,
    profile_name: str,
    app_home: str | Path | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    save_raw: bool = False,
    playwright_factory=None,
) -> dict[str, Any]:
    return _capture_own_profile_deep(
        profile_name=profile_name,
        app_home=app_home,
        timeout_sec=timeout_sec,
        save_raw=save_raw,
        playwright_factory=playwright_factory,
    )


def _detect_authenticated(page: Any) -> tuple[bool, str]:
    current_url = getattr(page, "url", "") or ""
    parsed = urlparse(current_url)
    path = re.sub(r"/+", "/", parsed.path or "/")
    normalized_path = path if path.endswith("/") else f"{path}/"
    if normalized_path.startswith("/feed/"):
        return True, "url:/feed/"
    if re.fullmatch(r"/in/[^/]+/?", path):
        return True, f"url:{normalized_path}"
    for selector in AUTH_MARKER_SELECTORS:
        try:
            if page.locator(selector).first().is_visible(timeout=250):
                return True, selector
        except Exception:
            continue
    return False, ""


def session_login(
    *,
    profile_name: str,
    app_home: str | Path | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    manual_confirm: bool = False,
    playwright_factory=None,
) -> dict[str, Any]:
    profile_dir = profile_storage_dir(app_home, profile_name)
    state_path = session_state_path(app_home, profile_name)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    context = None
    try:
        with (playwright_factory or _default_playwright_factory)() as playwright:
            context = _launch_context(playwright, profile_dir)
            page = context.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            marker = ""
            if manual_confirm:
                try:
                    input("Complete LinkedIn login in the browser, then press Enter to save the managed session.")
                except EOFError:
                    return make_result(
                        ok=False,
                        operation="session.login",
                        result={"status": "confirmation_unavailable"},
                        stderr="Manual confirmation requires an interactive terminal.",
                        exit_code=2,
                    )
                authenticated, marker = _detect_authenticated(page)
            else:
                deadline = time.monotonic() + timeout_sec
                authenticated = False
                while time.monotonic() < deadline:
                    authenticated, marker = _detect_authenticated(page)
                    if authenticated:
                        break
                    time.sleep(0.5)
                if not authenticated:
                    return make_result(
                        ok=False,
                        operation="session.login",
                        result={"status": "login_not_detected", "managed_profile": str(profile_dir)},
                        stderr="LinkedIn login was not detected before timeout. Retry or use --manual-confirm.",
                        exit_code=124,
                    )
            context.storage_state(path=str(state_path))
            context.close()
            return make_result(
                ok=True,
                operation="session.login",
                result={
                    "status": "ok",
                    "profile": sanitize_profile_name(profile_name),
                    "managed_profile": str(profile_dir),
                    "session_state": str(state_path),
                    "detected_marker": marker,
                    "action_timing_ms": round((time.perf_counter() - start) * 1000),
                },
            )
    except Exception as exc:
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        return make_result(
            ok=False,
            operation="session.login",
            result={"status": "browser_error"},
            stderr=str(exc),
            exit_code=1,
        )


def _load_snapshot(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _text_len(value: Any) -> int:
    return len(_section_value_text(value))


def _is_missing_or_thin_section(section_key: str, own_value: Any, target_value: Any) -> bool:
    if section_key in STRUCTURED_RECORD_SECTIONS:
        if not _has_section_content(own_value) and _has_section_content(target_value):
            return True
    return _text_len(own_value) < 40 and _text_len(target_value) >= 40


def compare_snapshots(*, own_snapshot: str, target_snapshot: str) -> dict[str, Any]:
    own = _load_snapshot(own_snapshot)
    target = _load_snapshot(target_snapshot)
    sections = ["headline", "about", "experience", "education", "licenses_certifications", "skills", "projects"]
    missing_or_thin = [
        section
        for section in sections
        if _is_missing_or_thin_section(section, own.get(section), target.get(section))
    ]
    own_skills = {str(skill).lower() for skill in own.get("skills") or []}
    target_skills = [str(skill) for skill in target.get("skills") or []]
    skills_gap = [skill for skill in target_skills if skill.lower() not in own_skills][:20]
    headline_gap = max(0, _text_len(target.get("headline")) - _text_len(own.get("headline")))
    improvement_areas: list[str] = []
    if headline_gap > 20:
        improvement_areas.append("Make the headline more specific about audience, domain, and measurable value.")
    if "about" in missing_or_thin:
        improvement_areas.append("Add or strengthen the About section with outcomes, scope, and proof points.")
    if skills_gap:
        improvement_areas.append("Review target-visible skills for legitimate skills you can add with evidence.")
    if "experience" in missing_or_thin:
        improvement_areas.append("Add quantified responsibility and impact bullets to experience entries.")
    return make_result(
        ok=True,
        operation="profile.compare",
        result={
            "own_snapshot": str(Path(own_snapshot)),
            "target_snapshot": str(Path(target_snapshot)),
            "missing_or_thin_sections": missing_or_thin,
            "skills_gap": skills_gap,
            "improvement_areas": improvement_areas,
            "copying_warning": "Do not copy another profile verbatim; use comparison output only to identify your own truthful improvements.",
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture and compare explicit LinkedIn CV profile snapshots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    session_parser = subparsers.add_parser("session", help="Manage LinkedIn browser sessions.")
    session_subparsers = session_parser.add_subparsers(dest="session_command", required=True)
    login = session_subparsers.add_parser("login", help="Open a managed browser for LinkedIn login.")
    login.add_argument("--profile", required=True, dest="profile_name")
    login.add_argument("--home", dest="app_home")
    login.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    login.add_argument("--manual-confirm", action="store_true")

    profile_parser = subparsers.add_parser("profile", help="Capture or compare LinkedIn profile snapshots.")
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command", required=True)

    capture_own = profile_subparsers.add_parser("capture-own", help="Capture the logged-in user's own profile.")
    capture_own.add_argument("--profile", required=True, dest="profile_name")
    capture_own.add_argument("--home", dest="app_home")
    capture_own.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    capture_own.add_argument("--save-raw", action="store_true")

    capture = profile_subparsers.add_parser("capture", help="Capture one explicit accessible LinkedIn profile.")
    capture.add_argument("--profile", required=True, dest="profile_name")
    target = capture.add_mutually_exclusive_group(required=True)
    target.add_argument("--url")
    target.add_argument("--profile-id")
    capture.add_argument("--confirm-accessible-profile-capture", action="store_true")
    capture.add_argument("--home", dest="app_home")
    capture.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    capture.add_argument("--save-raw", action="store_true")

    compare = profile_subparsers.add_parser("compare", help="Compare an own snapshot with an accessible target snapshot.")
    compare.add_argument("--own", required=True, dest="own_snapshot")
    compare.add_argument("--target", required=True, dest="target_snapshot")
    return parser


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "session" and args.session_command == "login":
        return session_login(
            profile_name=args.profile_name,
            app_home=args.app_home,
            timeout_sec=args.timeout_sec,
            manual_confirm=args.manual_confirm,
        )
    if args.command == "profile" and args.profile_command == "capture-own":
        return capture_own_profile(
            profile_name=args.profile_name,
            app_home=args.app_home,
            timeout_sec=args.timeout_sec,
            save_raw=args.save_raw,
        )
    if args.command == "profile" and args.profile_command == "capture":
        return capture_accessible_profile(
            profile_name=args.profile_name,
            url=args.url,
            profile_id=args.profile_id,
            confirm_accessible_profile_capture=args.confirm_accessible_profile_capture,
            app_home=args.app_home,
            timeout_sec=args.timeout_sec,
            save_raw=args.save_raw,
        )
    if args.command == "profile" and args.profile_command == "compare":
        return compare_snapshots(own_snapshot=args.own_snapshot, target_snapshot=args.target_snapshot)
    return make_result(ok=False, operation="unknown", stderr="Unsupported command.", exit_code=2)
