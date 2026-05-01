from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


STOPWORDS = {
    "a",
    "about",
    "already",
    "an",
    "and",
    "are",
    "as",
    "be",
    "because",
    "but",
    "by",
    "can",
    "create",
    "do",
    "does",
    "for",
    "from",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "new",
    "not",
    "of",
    "on",
    "or",
    "our",
    "skill",
    "skills",
    "so",
    "that",
    "the",
    "this",
    "to",
    "use",
    "using",
    "we",
    "with",
    "workflow",
    "you",
}

GENERIC_MATCH_WORDS = {
    "agent",
    "attacks",
    "automation",
    "code",
    "codex",
    "command",
    "detecting",
    "development",
    "file",
    "github",
    "helper",
    "implementing",
    "investigating",
    "logs",
    "local",
    "mail",
    "pipeline",
    "python",
    "performing",
    "repo",
    "review",
    "run",
    "script",
    "test",
    "tool",
}

DURABLE_PATTERNS = [
    r"\balways\b",
    r"\bfrom now on\b",
    r"\bnext time\b",
    r"\bprefer\b",
    r"\bremember\b",
    r"\brecord\b",
    r"\bmake sure\b",
    r"\bdo not\b",
    r"\bdon't\b",
    r"\bmust\b",
    r"\bavoid\b",
    r"\bstop\b",
]

STRUCTURED_TEXT_HINTS = {
    "please implement this plan",
    "test plan",
    "implementation changes",
    "public interface",
    "key changes",
}

COMMAND_LEARNING_WORDS = {
    "failed",
    "fix",
    "fixed",
    "gotcha",
    "issue",
    "missing",
    "prefer",
    "remember",
    "resolved",
    "setup",
    "workaround",
}

COMMON_COMMAND_FAMILIES = {
    "git branch",
    "git diff",
    "git show",
    "git status",
    "powershell",
    "python",
    "rg",
    "where",
}

PROPOSAL_ACTIONS = {"propose_patch", "propose_new_skill"}
NO_ACTIONS = {"already_covered"}
REJECTED_ACTIONS = {"insufficient_evidence", "public_alternative", "off_limits", "scout_unavailable"}


@dataclass
class ThreadRecord:
    thread_id: str
    title: str
    cwd: str
    rollout_path: Path
    updated_at: float
    archived: bool = False


@dataclass
class Evidence:
    session_id: str
    date: str
    workspace: str
    signal: str
    count: int = 1
    title: str = ""

    def as_report_line(self, include_title: bool = False) -> str:
        title = f" | {self.title}" if include_title and self.title else ""
        return f"`{self.session_id[:8]}` | {self.date} | {self.workspace}{title} | {self.signal} x{self.count}"


@dataclass
class SessionSignals:
    rollout_path: Path
    thread_id: str = ""
    title: str = ""
    timestamp: str = ""
    cwd: str = ""
    workspace: str = ""
    command_counts: Counter[str] = field(default_factory=Counter)
    command_successes: Counter[str] = field(default_factory=Counter)
    corrections: list[str] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    user_texts: list[str] = field(default_factory=list)
    assistant_texts: list[str] = field(default_factory=list)


@dataclass
class SkillInfo:
    name: str
    path: Path
    description: str
    content: str
    source_kind: str
    pinned: bool = False
    search_text: str = ""

    def __post_init__(self) -> None:
        if not self.search_text:
            self.search_text = normalize_text(f"{self.name} {self.description} {self.content}")

    @property
    def mutable(self) -> bool:
        return self.source_kind == "agent_created" and not self.pinned


@dataclass
class Finding:
    kind: str
    action: str
    name: str
    reason: str
    evidence: list[Evidence]
    target_skill: SkillInfo | None = None
    proposed_instruction: str = ""
    install_target: str = ""
    validation: dict[str, Any] = field(default_factory=dict)
    public_gate: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResult:
    ok: bool
    console: str
    run_dir: Path | None
    findings: list[Finding]
    diagnostics: dict[str, Any]


class SkillIndex:
    def __init__(self) -> None:
        self.by_name: dict[str, SkillInfo] = {}

    def add(self, skill: SkillInfo) -> None:
        self.by_name.setdefault(skill.name, skill)

    def all(self) -> list[SkillInfo]:
        return list(self.by_name.values())


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-toolbelt-skill-gardener")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    scan = subparsers.add_parser("scan", help="Stage evidence-backed skill proposals.")
    scan.add_argument("--since-days", type=int, default=14)
    scan.add_argument("--max-sessions", type=int, default=30)
    scan.add_argument("--output-root", default=str(Path.cwd() / "skill-proposals"))
    scan.add_argument("--codex-home", default=str(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))))
    scan.add_argument("--agents-home", default=str(Path.home() / ".agents"))
    scan.add_argument("--dry-run", action="store_true")
    scan.add_argument("--include-archived", action="store_true")
    scan.add_argument("--include-titles", action="store_true")
    return parser


def run_scan(
    *,
    since_days: int,
    max_sessions: int,
    output_root: str,
    codex_home: str,
    agents_home: str,
    dry_run: bool,
    include_archived: bool,
    include_titles: bool,
    scout_runner: Callable[[str, list[str]], dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> ScanResult:
    now = now or datetime.now(timezone.utc)
    codex_home_path = Path(codex_home).expanduser()
    agents_home_path = Path(agents_home).expanduser()

    threads = discover_threads(
        codex_home=codex_home_path,
        since_days=since_days,
        max_sessions=max_sessions,
        include_archived=include_archived,
        now_epoch=now.timestamp(),
    )
    sessions: list[SessionSignals] = []
    for thread in threads:
        parsed = parse_rollout(thread.rollout_path)
        parsed.thread_id = parsed.thread_id or thread.thread_id
        parsed.title = parsed.title or thread.title
        parsed.cwd = parsed.cwd or thread.cwd
        parsed.workspace = parsed.workspace or workspace_name(parsed.cwd)
        sessions.append(parsed)

    skill_index = discover_skill_index(
        discover_skill_roots(codex_home_path, agents_home_path, Path.cwd())
    )
    findings = build_findings(
        sessions=sessions,
        skill_index=skill_index,
        codex_home=codex_home_path,
        agents_home=agents_home_path,
        scout_runner=scout_runner or run_skills_sh_scout,
    )

    diagnostics = {
        "thread_count": len(threads),
        "session_count": len(sessions),
        "skill_count": len(skill_index.by_name),
        "proposal_count": sum(1 for item in findings if item.action in PROPOSAL_ACTIONS),
        "no_action_count": sum(1 for item in findings if item.action in NO_ACTIONS),
        "rejected_count": sum(1 for item in findings if item.action in REJECTED_ACTIONS),
    }

    if dry_run:
        return ScanResult(
            ok=True,
            console=render_console(findings, diagnostics, include_titles, dry_run=True),
            run_dir=None,
            findings=findings,
            diagnostics=diagnostics,
        )

    run_dir = stage_report(
        findings=findings,
        diagnostics=diagnostics,
        output_root=Path(output_root),
        include_titles=include_titles,
    )
    write_provenance_sidecar(skill_index, findings, diagnostics)
    return ScanResult(
        ok=True,
        console=f"Staged {sum(1 for item in findings if item.action in PROPOSAL_ACTIONS)} proposal(s) in {run_dir}",
        run_dir=run_dir,
        findings=findings,
        diagnostics=diagnostics,
    )


def discover_threads(
    *,
    codex_home: Path,
    since_days: int,
    max_sessions: int,
    include_archived: bool,
    now_epoch: float | None = None,
) -> list[ThreadRecord]:
    cutoff = (now_epoch or datetime.now(timezone.utc).timestamp()) - since_days * 86400
    records = discover_threads_from_sqlite(codex_home, cutoff, include_archived)
    if not records:
        records = discover_threads_from_rollouts(codex_home, cutoff)
    records = [record for record in records if record.rollout_path.exists()]
    return sorted(records, key=lambda item: item.updated_at, reverse=True)[:max_sessions]


def discover_threads_from_sqlite(codex_home: Path, cutoff: float, include_archived: bool) -> list[ThreadRecord]:
    db = codex_home / "state_5.sqlite"
    if not db.exists():
        return []
    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "select id, title, cwd, rollout_path, updated_at, archived from threads where rollout_path is not null"
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return []

    records: list[ThreadRecord] = []
    for thread_id, title, cwd, rollout_path, updated_at, archived in rows:
        archived_bool = bool(archived)
        if archived_bool and not include_archived:
            continue
        updated = normalize_epoch(updated_at)
        if updated < cutoff:
            continue
        records.append(
            ThreadRecord(
                thread_id=str(thread_id or ""),
                title=str(title or ""),
                cwd=str(cwd or ""),
                rollout_path=Path(str(rollout_path)),
                updated_at=updated,
                archived=archived_bool,
            )
        )
    return records


def discover_threads_from_rollouts(codex_home: Path, cutoff: float) -> list[ThreadRecord]:
    sessions_root = codex_home / "sessions"
    if not sessions_root.exists():
        return []
    records: list[ThreadRecord] = []
    for rollout in sessions_root.rglob("*.jsonl"):
        try:
            stat = rollout.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff:
            continue
        records.append(
            ThreadRecord(
                thread_id=extract_thread_id_from_name(rollout.name),
                title="",
                cwd="",
                rollout_path=rollout,
                updated_at=stat.st_mtime,
            )
        )
    return records


def parse_rollout(path: Path) -> SessionSignals:
    result = SessionSignals(rollout_path=path)
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return result

    with handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = str(entry.get("timestamp") or "")
            if timestamp and not result.timestamp:
                result.timestamp = timestamp
            payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
            entry_type = str(entry.get("type") or "")

            if entry_type == "session_meta":
                result.thread_id = str(payload.get("id") or result.thread_id)
                result.cwd = str(payload.get("cwd") or result.cwd)

            if entry_type == "turn_context":
                summary = str(payload.get("summary") or "")
                if summary:
                    result.summaries.append(sanitize_inline(summary, 260))

            function_call = payload.get("type") == "function_call"
            if function_call:
                command = command_from_function_call(payload)
                if command:
                    result.command_counts[command_family(command)] += 1

            if "command" in payload:
                command_text = str(payload.get("command") or "")
                if command_text:
                    family = command_family(command_text)
                    result.command_counts[family] += 1
                    if payload.get("exit_code") == 0:
                        result.command_successes[family] += 1

            if payload.get("type") == "message":
                role = str(payload.get("role") or "")
                text = text_from_content(payload.get("content"))
                if not text:
                    continue
                if role == "user":
                    result.user_texts.append(text)
                    result.corrections.extend(extract_durable_corrections(text))
                elif role == "assistant":
                    result.assistant_texts.append(text)

    if not result.thread_id:
        result.thread_id = extract_thread_id_from_name(path.name)
    if not result.workspace:
        result.workspace = workspace_name(result.cwd)
    result.corrections = list(dict.fromkeys(result.corrections))
    return result


def discover_skill_roots(codex_home: Path, agents_home: Path, cwd: Path) -> list[Path]:
    candidates = [
        codex_home / "skills",
        agents_home / "skills",
        cwd / ".codex" / "skills",
        cwd / ".agents" / "skills",
        cwd / "families",
        codex_home / "plugins" / "cache",
    ]
    return [path for path in candidates if path.exists()]


def discover_skill_index(roots: Iterable[Path]) -> SkillIndex:
    index = SkillIndex()
    for root in roots:
        for skill_md in root.rglob("SKILL.md"):
            content = read_text(skill_md)
            frontmatter, _body = read_frontmatter(content)
            name = normalize_skill_name(str(frontmatter.get("name") or skill_md.parent.name))
            if not name:
                continue
            index.add(
                SkillInfo(
                    name=name,
                    path=skill_md,
                    description=str(frontmatter.get("description") or ""),
                    content=content,
                    source_kind=classify_skill_source(skill_md),
                    pinned=False,
                )
            )
    return index


def build_findings(
    *,
    sessions: list[SessionSignals],
    skill_index: SkillIndex,
    codex_home: Path,
    agents_home: Path,
    scout_runner: Callable[[str, list[str]], dict[str, Any]],
) -> list[Finding]:
    findings: list[Finding] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for session in sessions:
        for correction in session.corrections:
            finding = classify_correction_finding(correction, session, skill_index)
            if finding:
                add_finding(findings, seen_keys, finding)

    for finding in command_workflow_findings(
        sessions=sessions,
        skill_index=skill_index,
        codex_home=codex_home,
        agents_home=agents_home,
        scout_runner=scout_runner,
    ):
        add_finding(findings, seen_keys, finding)

    return sorted(
        findings,
        key=lambda item: (
            0 if item.action in PROPOSAL_ACTIONS else 1 if item.action in NO_ACTIONS else 2,
            item.name,
            item.kind,
        ),
    )


def classify_correction_finding(
    correction: str,
    session: SessionSignals,
    skill_index: SkillIndex,
) -> Finding | None:
    text = normalize_text(correction)
    evidence = [
        Evidence(
            session_id=session.thread_id,
            date=session_date(session),
            workspace=session.workspace,
            signal=f"correction {sanitize_inline(correction, 180)}",
            title=session.title,
        )
    ]

    covered = best_coverage_skill(
        correction,
        skill_index,
        allow_description_anchor=mentions_skill_concept(correction),
    )
    if covered:
        return Finding(
            kind="already_covered",
            action="already_covered",
            name=covered.name,
            target_skill=covered,
            reason="Existing skill content already covers the durable instruction.",
            evidence=evidence,
            proposed_instruction=extract_instruction(correction),
        )

    target = explicit_skill_target(correction, session, skill_index)
    if target:
        if not target.mutable:
            return Finding(
                kind="explicit_skill_update",
                action="off_limits",
                name=target.name,
                target_skill=target,
                reason=f"Target skill is {target.source_kind}; stage proposal only and do not mutate it automatically.",
                evidence=evidence,
                proposed_instruction=extract_instruction(correction),
            )
        return Finding(
            kind="explicit_skill_update",
            action="propose_patch",
            name=target.name,
            target_skill=target,
            reason="User correction directly targets an existing mutable skill and the guidance is not covered.",
            evidence=evidence,
            proposed_instruction=extract_instruction(correction),
        )

    if "skill" in text or "skill.md" in text:
        return Finding(
            kind="insufficient_evidence",
            action="insufficient_evidence",
            name=slugify("unmatched skill correction"),
            reason="Correction mentions skills, but no exact target skill or uncovered existing coverage could be proven.",
            evidence=evidence,
            proposed_instruction=extract_instruction(correction),
        )

    return None


def command_workflow_findings(
    *,
    sessions: list[SessionSignals],
    skill_index: SkillIndex,
    codex_home: Path,
    agents_home: Path,
    scout_runner: Callable[[str, list[str]], dict[str, Any]],
) -> list[Finding]:
    by_command: dict[str, list[tuple[SessionSignals, int]]] = defaultdict(list)
    for session in sessions:
        for command, count in session.command_counts.items():
            by_command[command].append((session, count))

    findings: list[Finding] = []
    for command, rows in sorted(by_command.items(), key=lambda item: -sum(count for _session, count in item[1])):
        if not is_candidate_command_family(command):
            continue
        distinct_sessions = {session.thread_id for session, _count in rows}
        total_count = sum(count for _session, count in rows)
        if len(distinct_sessions) < 2 or total_count < 10:
            continue
        learning_rows = [
            (session, count)
            for session, count in rows
            if session_has_learning(session, command)
        ]
        if not learning_rows:
            continue
        workflow = workflow_summary(command, [session for session, _count in learning_rows])
        evidence = [
            Evidence(
                session_id=session.thread_id,
                date=session_date(session),
                workspace=session.workspace,
                signal=f"command `{command}` with reusable learning",
                count=count,
                title=session.title,
            )
            for session, count in learning_rows[:5]
        ]

        covered = best_coverage_skill(workflow, skill_index, allow_description_anchor=False)
        if covered:
            findings.append(
                Finding(
                    kind="already_covered",
                    action="already_covered",
                    name=covered.name,
                    target_skill=covered,
                    reason=f"Existing skill content already covers the repeated `{command}` workflow.",
                    evidence=evidence,
                    proposed_instruction=workflow,
                )
            )
            continue

        public_gate = scout_runner(workflow, [command])
        category = str(public_gate.get("recommendation", {}).get("category") or "")
        if category in {"Install public skill", "Do not create; public alternative is clearly better"}:
            findings.append(
                Finding(
                    kind="new_skill_candidate",
                    action="public_alternative",
                    name=slugify(f"{command} workflow"),
                    reason="A public skill appears to cover this workflow; do not create a duplicate local skill.",
                    evidence=evidence,
                    public_gate=public_gate,
                )
            )
            continue
        if not public_gate.get("ok", True):
            findings.append(
                Finding(
                    kind="new_skill_candidate",
                    action="scout_unavailable",
                    name=slugify(f"{command} workflow"),
                    reason="Public-alternative gate failed; do not stage a new skill without scout evidence.",
                    evidence=evidence,
                    public_gate=public_gate,
                )
            )
            continue

        name = slugify(f"{command} workflow")
        findings.append(
            Finding(
                kind="new_skill_candidate",
                action="propose_new_skill",
                name=name,
                reason=f"Repeated successful `{command}` workflow has reusable learning and no local/public direct cover.",
                evidence=evidence,
                proposed_instruction=workflow,
                install_target=str(agents_home / "skills"),
                public_gate=public_gate,
            )
        )
    return findings


def add_finding(findings: list[Finding], seen_keys: set[tuple[str, str, str]], finding: Finding) -> None:
    key = (finding.action, finding.kind, finding.name)
    if key in seen_keys:
        for existing in findings:
            if (existing.action, existing.kind, existing.name) == key:
                existing.evidence.extend(finding.evidence)
                return
    seen_keys.add(key)
    findings.append(finding)


def best_coverage_skill(
    text: str,
    skill_index: SkillIndex,
    *,
    allow_description_anchor: bool = True,
) -> SkillInfo | None:
    keywords = meaningful_tokens(text)
    if not keywords:
        return None
    best: tuple[int, SkillInfo] | None = None
    for skill in skill_index.all():
        hits = sum(1 for token in keywords if token in skill.search_text)
        exact_skill_name = normalize_skill_name(text) == skill.name
        name_anchor = skill_name_anchor_in_text(skill, text)
        description_anchor = skill_description_anchor_in_text(skill, text)
        score = hits + (4 if exact_skill_name else 0)
        if (
            exact_skill_name
            or (name_anchor and hits >= min(2, len(keywords)))
            or (allow_description_anchor and description_anchor and hits >= min(4, len(keywords)))
        ):
            if best is None or score > best[0]:
                best = (score, skill)
    return best[1] if best else None


def skill_name_anchor_in_text(skill: SkillInfo, text: str) -> bool:
    normalized = normalize_text(text)
    name_parts = {
        part
        for part in re.split(r"[-_\s]+", skill.name)
        if len(part) > 3 and part not in STOPWORDS and part not in GENERIC_MATCH_WORDS
    }
    if not name_parts:
        return False
    hits = sum(1 for part in name_parts if re.search(rf"\b{re.escape(part)}\b", normalized))
    required = 1 if len(name_parts) == 1 else max(2, (len(name_parts) + 1) // 2)
    return hits >= required


def skill_description_anchor_in_text(skill: SkillInfo, text: str) -> bool:
    description_tokens = [
        token
        for token in meaningful_tokens(skill.description)
        if token not in GENERIC_MATCH_WORDS
    ]
    return len(set(description_tokens).intersection(meaningful_tokens(text))) >= 3


def mentions_skill_concept(text: str) -> bool:
    normalized = normalize_text(text)
    return any(marker in normalized for marker in ("skill", "skill.md", "skills", "agent skill"))


def explicit_skill_target(text: str, session: SessionSignals, skill_index: SkillIndex) -> SkillInfo | None:
    combined = normalize_text(text)
    candidates: list[tuple[int, SkillInfo]] = []
    mentions_skill_object = any(marker in combined for marker in ("skill", "skill.md", "skills"))
    has_update_intent = bool(re.search(r"\b(update|patch|fix|improve|refine|edit|add|record)\b", combined))
    if not mentions_skill_object and not has_update_intent:
        return None
    for skill in skill_index.all():
        name_text = normalize_text(skill.name.replace("-", " "))
        if re.search(rf"\b{re.escape(skill.name)}\b", combined) or name_text in combined:
            candidates.append((100, skill))
            continue
        if not mentions_skill_object and not has_update_intent:
            continue
        parts = [part for part in skill.name.split("-") if len(part) > 3 and part not in GENERIC_MATCH_WORDS]
        part_hits = sum(1 for part in parts if re.search(rf"\b{re.escape(part)}\b", combined))
        if parts and part_hits == len(parts):
            candidates.append((part_hits, skill))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item[0], item[1].name))[0][1]


def session_has_learning(session: SessionSignals, command: str) -> bool:
    text = normalize_text(" ".join(session.corrections + session.summaries + session.assistant_texts[-3:]))
    command_tokens = set(meaningful_tokens(command))
    if command_tokens and normalize_text(command) not in text and not all(token in text for token in command_tokens):
        return False
    return any(word in text for word in COMMAND_LEARNING_WORDS)


def is_candidate_command_family(command: str) -> bool:
    normalized = normalize_text(command)
    if not normalized or normalized in COMMON_COMMAND_FAMILIES:
        return False
    if normalized.startswith("git "):
        return False
    if any(marker in normalized for marker in ("=", ";", "@", "'", '"')):
        return False
    tokens = meaningful_tokens(normalized)
    distinctive = [token for token in tokens if token not in GENERIC_MATCH_WORDS]
    return len(distinctive) >= 2


def run_skills_sh_scout(workflow: str, queries: list[str]) -> dict[str, Any]:
    command = shutil.which("agent-toolbelt-skills-sh-scout")
    args: list[str]
    if command:
        args = [command, "scout"]
    else:
        uv = shutil.which("uv")
        repo_root = Path(__file__).resolve().parents[4]
        scout_project = repo_root / "families" / "skills-sh-scout"
        if not uv or not scout_project.exists():
            return {
                "ok": False,
                "operation": "scout",
                "recommendation": {"category": "Create new skill", "summary": "skills-sh-scout executable not found."},
                "errors": ["skills-sh-scout executable not found"],
            }
        args = [uv, "run", "--project", str(scout_project), "agent-toolbelt-skills-sh-scout", "scout"]

    args.extend(["--workflow", workflow, "--max-candidates", "10", "--max-inspect", "3"])
    for query in queries:
        args.extend(["--query", query])
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=45, check=False)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "operation": "scout",
            "recommendation": {"category": "Create new skill", "summary": "skills-sh-scout execution failed."},
            "errors": [str(exc)],
        }
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "operation": "scout",
            "recommendation": {"category": "Create new skill", "summary": "skills-sh-scout returned invalid JSON."},
            "errors": [completed.stderr.strip() or "invalid JSON from skills-sh-scout"],
        }


def stage_report(
    *,
    findings: list[Finding],
    diagnostics: dict[str, Any],
    output_root: Path,
    include_titles: bool,
) -> Path:
    run_dir = output_root / datetime.now().strftime("%Y%m%d-%H%M%S")
    patches_dir = run_dir / "patches"
    new_skills_dir = run_dir / "new-skills"
    patches_dir.mkdir(parents=True, exist_ok=False)
    new_skills_dir.mkdir(parents=True, exist_ok=True)

    for finding in findings:
        if finding.action == "propose_patch":
            path = patches_dir / f"{finding.name}.md"
            path.write_text(render_patch_proposal(finding, include_titles), encoding="utf-8")
            finding.validation = {"ok": True, "type": "proposal_document"}
        elif finding.action == "propose_new_skill":
            skill_dir = new_skills_dir / finding.name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(render_skill_md(finding), encoding="utf-8")
            finding.validation = validate_staged_skill(skill_dir)

    (run_dir / "manifest.json").write_text(
        json.dumps(manifest(findings, diagnostics), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "REPORT.md").write_text(
        render_report(findings, diagnostics, include_titles),
        encoding="utf-8",
    )
    return run_dir


def render_console(findings: list[Finding], diagnostics: dict[str, Any], include_titles: bool, *, dry_run: bool) -> str:
    prefix = "Dry run: no proposal files were written." if dry_run else "Skill gardener scan complete."
    lines = [prefix, ""]
    proposals = [item for item in findings if item.action in PROPOSAL_ACTIONS]
    if proposals:
        lines.append("High-confidence proposals:")
        for item in proposals:
            lines.append(f"- {item.action}: `{item.name}` - {item.reason}")
            for evidence in item.evidence[:2]:
                lines.append(f"  evidence: {evidence.as_report_line(include_titles)}")
    else:
        lines.append("High-confidence proposals: none")
    lines.append("")
    lines.append(f"No-action findings: {diagnostics['no_action_count']}")
    lines.append(f"Rejected candidates: {diagnostics['rejected_count']}")
    return "\n".join(lines)


def render_report(findings: list[Finding], diagnostics: dict[str, Any], include_titles: bool) -> str:
    lines = [
        "# Skill Gardener Review Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "This run staged proposals only. It did not install, modify, delete, or archive active skills.",
        "",
    ]
    append_report_section(lines, "High-confidence proposals", [item for item in findings if item.action in PROPOSAL_ACTIONS], include_titles)
    append_report_section(lines, "No-action findings", [item for item in findings if item.action in NO_ACTIONS], include_titles)
    append_report_section(lines, "Rejected candidates", [item for item in findings if item.action in REJECTED_ACTIONS], include_titles)
    lines.extend(
        [
            "## Diagnostics",
            "",
            "```json",
            json.dumps(diagnostics, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def append_report_section(lines: list[str], title: str, findings: list[Finding], include_titles: bool) -> None:
    lines.extend([f"## {title}", ""])
    if not findings:
        lines.extend(["- None", ""])
        return
    for item in findings:
        lines.append(f"- `{item.name}` ({item.kind}/{item.action})")
        lines.append(f"  - Why: {item.reason}")
        if item.target_skill:
            lines.append(f"  - Target: `{item.target_skill.path}`")
            lines.append(f"  - Source kind: `{item.target_skill.source_kind}`")
        if item.proposed_instruction:
            lines.append(f"  - Proposed instruction: {item.proposed_instruction}")
        if item.public_gate:
            category = item.public_gate.get("recommendation", {}).get("category")
            summary = item.public_gate.get("recommendation", {}).get("summary")
            lines.append(f"  - Public gate: {category or 'unknown'} - {summary or 'no summary'}")
        for evidence in item.evidence[:5]:
            lines.append(f"  - Evidence: {evidence.as_report_line(include_titles)}")
    lines.append("")


def render_patch_proposal(finding: Finding, include_titles: bool) -> str:
    evidence = "\n".join(f"- {item.as_report_line(include_titles)}" for item in finding.evidence)
    target = finding.target_skill.path if finding.target_skill else ""
    return (
        f"# Patch Proposal: {finding.name}\n\n"
        f"Existing skill: `{target}`\n\n"
        "## Why\n\n"
        f"{finding.reason}\n\n"
        "## Suggested Patch\n\n"
        "Add this concise instruction where it best fits the existing workflow or pitfalls section:\n\n"
        f"> {finding.proposed_instruction}\n\n"
        "This is a proposal only. Do not apply it without explicit approval.\n\n"
        "## Evidence\n\n"
        f"{evidence or '- No evidence captured.'}\n"
    )


def render_skill_md(finding: Finding) -> str:
    title = finding.name.replace("-", " ").title()
    return (
        "---\n"
        f"name: {finding.name}\n"
        f"description: Use when Codex needs the repeated workflow captured by: {finding.proposed_instruction[:180]}\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Workflow\n\n"
        f"1. Confirm the requested task matches this narrow workflow: {finding.proposed_instruction}\n"
        "2. Start with read-only inspection before taking side-effectful steps.\n"
        "3. Follow the shortest successful command sequence from the evidence packet.\n"
        "4. Verify the outcome with a direct command or artifact check.\n\n"
        "## Pitfalls\n\n"
        "- Do not copy private session content, credentials, or local account identifiers into reusable instructions.\n"
        "- Keep the trigger narrow; this staged skill must be reviewed before installation.\n\n"
        "## Verification\n\n"
        "- Run one realistic task using the staged skill outside active skill roots before promoting it.\n"
    )


def validate_staged_skill(skill_dir: Path) -> dict[str, Any]:
    skill_md = skill_dir / "SKILL.md"
    errors: list[str] = []
    warnings: list[str] = []
    if not skill_md.exists():
        errors.append("SKILL.md missing")
    else:
        frontmatter, body = read_frontmatter(read_text(skill_md))
        if not frontmatter.get("name"):
            errors.append("frontmatter name missing")
        if not frontmatter.get("description"):
            errors.append("frontmatter description missing")
        if not body.strip():
            errors.append("body missing")
    quick_validate = Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    quick_result = ""
    if quick_validate.exists():
        try:
            completed = subprocess.run(
                [sys.executable, str(quick_validate), str(skill_dir)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            quick_output = (completed.stdout + completed.stderr).strip()
            quick_result = quick_output[-2000:]
            if completed.returncode != 0:
                errors.append("skill-creator quick_validate failed")
        except Exception as exc:  # noqa: BLE001 - validation failure should be reported structurally.
            quick_result = str(exc)
            errors.append("skill-creator quick_validate failed")
    else:
        warnings.append("skill-creator quick_validate.py not found")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "quick_validate": quick_result}


def manifest(findings: list[Finding], diagnostics: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "installed_or_modified_active_skills": False,
        "diagnostics": diagnostics,
        "findings": [
            {
                "kind": item.kind,
                "action": item.action,
                "name": item.name,
                "reason": item.reason,
                "target_path": str(item.target_skill.path) if item.target_skill else "",
                "target_source_kind": item.target_skill.source_kind if item.target_skill else "",
                "proposed_instruction": item.proposed_instruction,
                "validation": item.validation,
                "public_gate": item.public_gate,
                "evidence": [
                    {
                        "session_id": evidence.session_id,
                        "date": evidence.date,
                        "workspace": evidence.workspace,
                        "signal": evidence.signal,
                        "count": evidence.count,
                    }
                    for evidence in item.evidence
                ],
            }
            for item in findings
        ],
    }


def write_provenance_sidecar(skill_index: SkillIndex, findings: list[Finding], diagnostics: dict[str, Any]) -> None:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Tools" / "skill-gardener" / "state"
    try:
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "diagnostics": diagnostics,
            "skills": {
                name: {
                    "path": str(skill.path),
                    "source_kind": skill.source_kind,
                    "pinned": skill.pinned,
                }
                for name, skill in sorted(skill_index.by_name.items())
            },
            "last_findings": [
                {
                    "name": item.name,
                    "kind": item.kind,
                    "action": item.action,
                    "reason": item.reason,
                }
                for item in findings
            ],
        }
        (root / "provenance.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        return


def normalize_epoch(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if number > 10_000_000_000:
        return number / 1000.0
    return number


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_frontmatter(text: str) -> tuple[dict[str, str], str]:
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
        frontmatter[key.strip()] = value.strip().strip("'\"")
    return frontmatter, match.group(2)


def classify_skill_source(skill_md: Path) -> str:
    parts = {part.casefold() for part in skill_md.parts}
    normalized = str(skill_md).replace("\\", "/").casefold()
    if ".system" in parts:
        return "system"
    if "plugins" in parts and "cache" in parts:
        return "plugin_cache"
    if "/families/" in normalized:
        return "repo_managed"
    if ".hub" in parts or "marketplaces" in parts:
        return "public_or_marketplace"
    if ".agents" in parts or ".codex" in parts:
        return "local_unmanaged"
    return "local_unmanaged"


def command_from_function_call(payload: dict[str, Any]) -> str:
    arguments = payload.get("arguments")
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return ""
    elif isinstance(arguments, dict):
        parsed = arguments
    else:
        parsed = {}
    return str(parsed.get("command") or "")


def command_family(command: str) -> str:
    parts = re.findall(r"[^\s]+", command.strip())
    if not parts:
        return ""
    first = Path(parts[0]).name.casefold()
    if first in {"python", "python.exe", "python3"} and len(parts) >= 3 and parts[1] == "-m":
        return f"python -m {parts[2]}"
    if first in {"uv", "uv.exe"} and len(parts) >= 2:
        return f"uv {parts[1]}"
    if first in {"git", "git.exe"} and len(parts) >= 2:
        return f"git {parts[1]}"
    if first in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        return "powershell"
    return first


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "content", "value"):
                    value = item.get(key)
                    if isinstance(value, str):
                        parts.append(value)
        return "\n".join(parts)
    return ""


def extract_durable_corrections(text: str) -> list[str]:
    if not text or looks_like_structured_prompt(text):
        return []
    matches: list[str] = []
    parts = re.split(r"(?:\r?\n)+|(?<=[.!?])\s+", text)
    for part in parts:
        cleaned = sanitize_inline(part, 220)
        if not cleaned or looks_like_structured_prompt(cleaned):
            continue
        if cleaned.endswith("?"):
            continue
        if is_durable_correction(cleaned):
            matches.append(cleaned)
    return list(dict.fromkeys(matches))


def is_durable_correction(text: str) -> bool:
    lowered = normalize_text(text)
    if any(re.search(pattern, lowered) for pattern in DURABLE_PATTERNS):
        return True
    if re.search(r"\bshould\b", lowered):
        if lowered.startswith("we should ") or lowered.startswith("tomorrow we should "):
            return False
        return any(anchor in lowered for anchor in ("skill", "skill.md", "codex should", "agent should", "you should"))
    return False


def looks_like_structured_prompt(text: str) -> bool:
    lowered = normalize_text(text)
    if any(hint in lowered for hint in STRUCTURED_TEXT_HINTS):
        return True
    if "```" in text:
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    structured = sum(1 for line in lines if re.match(r"^(?:#+\s|[-*]\s|\d+\.\s)", line))
    return len(lines) >= 3 and structured >= 2


def workflow_summary(command: str, sessions: list[SessionSignals]) -> str:
    snippets: list[str] = []
    for session in sessions:
        snippets.extend(session.corrections[:2])
        snippets.extend(session.summaries[:2])
    learning = sanitize_inline(" ".join(snippets), 240)
    return f"Use the `{command}` workflow with this reusable learning: {learning}"


def extract_instruction(correction: str) -> str:
    cleaned = sanitize_inline(correction, 220)
    cleaned = re.sub(r"^(ok,?\s*)", "", cleaned, flags=re.IGNORECASE)
    if not cleaned.endswith("."):
        cleaned += "."
    return cleaned


def meaningful_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9_.+-]*", normalize_text(text))
    return [
        token
        for token in tokens
        if len(token) > 2 and token not in STOPWORDS and token not in GENERIC_MATCH_WORDS
    ][:20]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9_.@/+ -]+", " ", text).casefold()).strip()


def sanitize_inline(text: str, limit: int = 180) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def normalize_skill_name(name: str) -> str:
    return slugify(str(name).strip().strip("'\""))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_text(value)).strip("-")
    return slug[:64].strip("-") or "skill-proposal"


def workspace_name(cwd: str) -> str:
    if not cwd:
        return ""
    return Path(cwd).name or cwd


def session_date(session: SessionSignals) -> str:
    if session.timestamp:
        return session.timestamp[:10]
    try:
        return datetime.fromtimestamp(session.rollout_path.stat().st_mtime, timezone.utc).date().isoformat()
    except OSError:
        return ""


def extract_thread_id_from_name(name: str) -> str:
    match = re.search(r"([0-9a-f]{8,}(?:-[0-9a-f-]+)?)", name, re.IGNORECASE)
    return match.group(1) if match else ""
