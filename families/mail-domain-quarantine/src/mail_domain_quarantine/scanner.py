from __future__ import annotations

import copy
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import policy, state


OUTLOOK_CLI_ENV = "MAIL_DOMAIN_QUARANTINE_OUTLOOK_CLI"
REPUTATION_CLI_ENV = "MAIL_DOMAIN_QUARANTINE_REPUTATION_CLI"
OUTLOOK_CLI = "agent-toolbelt-outlook-classic-mail"
REPUTATION_CLI = "agent-toolbelt-observable-reputation"
REPUTATION_ORDER = {"malicious": 5, "suspicious": 4, "error": 3, "clean": 2, "unknown": 1, "skipped": 0}
DEFAULT_REPORT_RETENTION_DAYS = 30
DEFAULT_REPORT_MAX_MB = 100
DEFAULT_OUTLOOK_TIMEOUT_SECONDS = 900
SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


@dataclass(frozen=True)
class AccountConfig:
    account: str
    quarantine_folder: str
    source_folders: tuple[str, ...]


ACCOUNTS = (
    AccountConfig(
        account="josemiguelsdlc@gmail.com",
        quarantine_folder="custom:Inbox/Quarantine",
        source_folders=("inbox", "custom:[Gmail]/Spam"),
    ),
    AccountConfig(
        account="darkaxt.remaxku@gmail.com",
        quarantine_folder="custom:Inbox/Quarantine",
        source_folders=("inbox", "custom:[Gmail]/Spam"),
    ),
    AccountConfig(
        account="darkaxt_remaxku@outlook.es",
        quarantine_folder="custom:Bandeja de entrada/Quarantine",
        source_folders=("inbox", "custom:Correo no deseado"),
    ),
)


def run_outlook_client(args: list[str], *, timeout_seconds: int = DEFAULT_OUTLOOK_TIMEOUT_SECONDS) -> dict[str, Any]:
    command = [os.getenv(OUTLOOK_CLI_ENV) or OUTLOOK_CLI, *args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "operation": args[0] if args else "unknown",
            "result": {},
            "stderr": f"{command[0]} timed out after {exc.timeout} seconds",
            "exit_code": None,
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "operation": args[0] if args else "unknown",
            "result": {},
            "stderr": completed.stderr or completed.stdout,
            "exit_code": completed.returncode,
        }
    return payload


def scan_folder(
    *,
    account: str,
    folder: str,
    days: int,
    limit: int,
    young_days: int,
    with_blocklists: bool = False,
    blocklist_profile: str = "threat",
    outlook_timeout_seconds: int = DEFAULT_OUTLOOK_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    args = [
        "scan-domain-refs",
        "--account",
        account,
        "--folder",
        folder,
        "--days",
        str(days),
        "--limit",
        str(limit),
        "--young-days",
        str(young_days),
        "--rdap-cache",
        str(state.DOMAIN_CACHE_PATH),
        "--with-rdap",
    ]
    if with_blocklists:
        args.extend(
            [
                "--with-blocklists",
                "--blocklist-profile",
                blocklist_profile,
                "--blocklist-cache",
                str(state.BLOCKLIST_CACHE_PATH),
            ]
        )
    return run_outlook_client(args, timeout_seconds=outlook_timeout_seconds)


def move_message(*, account: str, message_id: str, target_folder: str) -> dict[str, Any]:
    return run_outlook_client(
        [
            "move-message",
            "--account",
            account,
            "--message-id",
            message_id,
            "--target-folder",
            target_folder,
            "--confirm",
        ]
    )


def run_observable_reputation(observables: list[dict[str, Any]]) -> dict[str, Any]:
    state.ensure_state()
    unique_observables, unique_keys, original_keys = deduplicate_reputation_observables(observables)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
    input_path = state.STATE_DIR / f"reputation-input-{stamp}.json"
    output_path = state.STATE_DIR / f"reputation-output-{stamp}.json"
    input_path.write_text(json.dumps({"observables": unique_observables}, ensure_ascii=False), encoding="utf-8")
    command = [
        os.getenv(REPUTATION_CLI_ENV) or REPUTATION_CLI,
        "classify",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--quiet",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "error": f"observable-reputation timed out after {exc.timeout} seconds", "observables": []}
    if completed.returncode != 0:
        return {"ok": False, "error": completed.stderr or completed.stdout, "observables": []}
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc), "observables": []}
    payload["observables"] = expand_reputation_results(
        observables,
        original_keys,
        unique_keys,
        payload.get("observables") or [],
    )
    payload["deduplication"] = {
        "input_observables": len(observables),
        "unique_observables": len(unique_observables),
    }
    payload["ok"] = True
    return payload


def deduplicate_reputation_observables(observables: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    unique_by_key: dict[str, dict[str, Any]] = {}
    unique_keys: list[str] = []
    original_keys: list[str] = []
    for observable in observables:
        key = reputation_observable_key(observable)
        original_keys.append(key)
        if key in unique_by_key:
            continue
        unique_by_key[key] = observable
        unique_keys.append(key)
    return [unique_by_key[key] for key in unique_keys], unique_keys, original_keys


def reputation_observable_key(observable: dict[str, Any]) -> str:
    observable_type = str(observable.get("type", "")).strip().lower()
    value = str(observable.get("value", "")).strip()
    if observable_type in {"domain", "ip"}:
        value = value.lower()
    return f"{observable_type}:{value}"


def expand_reputation_results(
    original_observables: list[dict[str, Any]],
    original_keys: list[str],
    unique_keys: list[str],
    unique_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result_by_key = {key: result for key, result in zip(unique_keys, unique_results)}
    expanded: list[dict[str, Any]] = []
    for observable, key in zip(original_observables, original_keys):
        result = copy.deepcopy(result_by_key.get(key) or {})
        result["source"] = observable.get("source", "")
        result["context"] = dict(observable.get("context") or {})
        expanded.append(result)
    return expanded


def build_reputation_observables(scan_payload: dict[str, Any], *, include_urls: bool = True) -> list[dict[str, Any]]:
    account = scan_payload.get("account", "")
    folder_path = (scan_payload.get("folder") or {}).get("path", "")
    observables: list[dict[str, Any]] = []
    for record in scan_payload.get("messages", []):
        message = record.get("message") or {}
        context = {
            "message_entry_id": message.get("entry_id", ""),
            "account": account,
            "folder_path": folder_path,
            "subject": message.get("subject", ""),
            "sender_email": message.get("sender_email", ""),
        }
        for ref in record.get("domain_references") or []:
            domain = ref.get("registrable_domain")
            if domain:
                observables.append(
                    {
                        "type": "domain",
                        "value": domain,
                        "source": ref.get("source", ""),
                        "context": {**context, "raw_value": ref.get("raw_value", "")},
                    }
                )
            raw_value = str(ref.get("raw_value", ""))
            if include_urls and raw_value.lower().startswith(("http://", "https://")):
                observables.append(
                    {
                        "type": "url",
                        "value": raw_value,
                        "source": ref.get("source", ""),
                        "context": {**context, "raw_value": raw_value},
                    }
                )
        for ref in record.get("ip_references") or []:
            ip = ref.get("ip")
            if ip:
                observables.append(
                    {
                        "type": "ip",
                        "value": ip,
                        "source": ref.get("source", ""),
                        "context": {**context, "raw_value": ref.get("raw_value", "")},
                    }
                )
    return observables


def build_candidate_reputation_observables(folder_result: dict[str, Any]) -> list[dict[str, Any]]:
    observables: list[dict[str, Any]] = []
    for row in folder_result.get("candidates") or []:
        message = row.get("message") or {}
        context = {
            "message_entry_id": message.get("entry_id", ""),
            "account": row.get("account", ""),
            "folder_path": row.get("source_folder", ""),
            "subject": message.get("subject", ""),
            "sender_email": message.get("sender_email", ""),
        }
        for domain in row.get("young_domains") or []:
            observables.append(
                {
                    "type": "domain",
                    "value": domain,
                    "source": "young-domain",
                    "context": {**context, "raw_value": domain},
                }
            )
    return observables


def build_reputation_observables_for_profile(
    scan_payload: dict[str, Any],
    folder_result: dict[str, Any],
    *,
    reputation_profile: str,
) -> list[dict[str, Any]]:
    candidate_observables = build_candidate_reputation_observables(folder_result)
    if reputation_profile != "full":
        return candidate_observables

    candidate_ids = candidate_message_ids(folder_result)
    scoped_observables = [
        observable
        for observable in build_reputation_observables(scan_payload, include_urls=True)
        if ((observable.get("context") or {}).get("message_entry_id") or "") in candidate_ids
    ]
    return [*candidate_observables, *scoped_observables]


def candidate_message_ids(folder_result: dict[str, Any]) -> set[str]:
    return {
        message_id
        for row in folder_result.get("candidates") or []
        if (message_id := str(((row.get("message") or {}).get("entry_id") or "")))
    }


def reputation_by_message(reputation_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for result in reputation_report.get("observables") or []:
        message_id = ((result.get("context") or {}).get("message_entry_id") or "")
        if not message_id:
            continue
        current = grouped.setdefault(
            message_id,
            {
                "verdict": "unknown",
                "score": 0,
                "observables": [],
                "evidence": [],
                "errors": [],
                "provider_summary": empty_provider_summary(),
                "explanations": [],
                "normalized_observables": [],
            },
        )
        current["observables"].append(result)
        current["evidence"].extend(result.get("evidence") or [])
        current["errors"].extend(result.get("errors") or [])
        merge_provider_summary(current["provider_summary"], result.get("provider_summary") or {})
        explanation = str(result.get("explanation") or "")
        if explanation and explanation not in current["explanations"]:
            current["explanations"].append(explanation)
        current["normalized_observables"].append(reputation_observable_summary(result))
        if REPUTATION_ORDER.get(result.get("verdict"), 0) > REPUTATION_ORDER.get(current["verdict"], 0):
            current["verdict"] = result.get("verdict", "unknown")
        current["score"] = max(int(current.get("score") or 0), int(result.get("score") or 0))
    return grouped


def empty_provider_summary() -> dict[str, Any]:
    return {
        "provider_count": 0,
        "skipped_count": 0,
        "error_count": 0,
        "evidence_count": 0,
        "verdicts": {},
    }


def merge_provider_summary(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("provider_count", "skipped_count", "error_count", "evidence_count"):
        target[key] = int(target.get(key) or 0) + int(source.get(key) or 0)
    verdicts = target.setdefault("verdicts", {})
    for verdict, count in (source.get("verdicts") or {}).items():
        verdicts[verdict] = int(verdicts.get(verdict) or 0) + int(count or 0)


def reputation_observable_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": result.get("type"),
        "value": result.get("value"),
        "raw_value": result.get("raw_value"),
        "normalized_value": result.get("normalized_value") or result.get("value"),
        "domain": result.get("domain"),
        "source": result.get("source"),
        "normalization": result.get("normalization") or {},
    }


def evaluate_scan_payload(
    scan_payload: dict[str, Any],
    *,
    quarantine_folder: str,
    trusted_domains: set[str],
    apply: bool,
    blocklist_suppressions: dict[str, str] | None = None,
    move_message: Callable[..., Any] = move_message,
    reputation_by_message: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    account = scan_payload.get("account", "")
    source_folder = (scan_payload.get("folder") or {}).get("path", "")
    candidates: list[dict[str, Any]] = []
    allowed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for record in scan_payload.get("messages", []):
        message = record.get("message") or {}
        blocklist_hits, suppressed_blocklist_hits = split_blocklist_hits_for_record(
            record,
            blocklist_suppressions or {},
        )
        blocklisted_domains = blocklisted_domains_from_hits(blocklist_hits)
        decision = policy.decide_quarantine(
            domain_ages=record.get("domain_ages") or [],
            trusted_domains=trusted_domains,
            blocklisted_domains=blocklisted_domains,
        )
        structure_signals = structure_signals_for_record(record) if decision.action == "quarantine" else []
        row = {
            "account": account,
            "source_folder": source_folder,
            "quarantine_folder": quarantine_folder,
            "message": message,
            "young_domains": decision.young_domains,
            "blocklisted_domains": blocklisted_domains,
            "blocklist_hits": blocklist_hits,
            "suppressed_blocklist_hits": suppressed_blocklist_hits,
            "structure_signals": structure_signals,
            "reason": decision.reason,
            "action": decision.action,
        }
        reputation = (reputation_by_message or {}).get(message.get("entry_id", ""))
        if reputation is not None:
            row["reputation"] = reputation
        if decision.action != "quarantine":
            allowed.append(row)
            continue

        if apply:
            state.write_ledger_entry(
                account=account,
                message=message,
                quarantine_folder=quarantine_folder,
                domains=decision.young_domains,
                reason=decision.reason,
            )
            move_result = move_message(
                account=account,
                message_id=message.get("entry_id", ""),
                target_folder=quarantine_folder,
            )
            row["move_result"] = move_result
            if not move_result.get("ok"):
                errors.append({"message": message, "error": move_result.get("stderr")})
        candidates.append(row)

    return {"candidates": candidates, "allowed": allowed, "errors": errors}


def blocklist_hits_for_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    active, _suppressed = split_blocklist_hits_for_record(record, {})
    return active


def blocklisted_domains_from_hits(hits: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(hit.get("domain") or "").strip(".").lower()
            for hit in hits
            if str(hit.get("profile") or "threat").lower() == "threat"
            and str(hit.get("domain") or "").strip(".")
        }
    )


def split_blocklist_hits_for_record(
    record: dict[str, Any],
    blocklist_suppressions: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    suppressions = {
        str(domain).strip(".").lower(): str(reason)
        for domain, reason in blocklist_suppressions.items()
        if domain
    }
    hits: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for domain_age in record.get("domain_ages") or []:
        domain = str(domain_age.get("domain") or "").strip(".").lower()
        for hit in domain_age.get("blocklist_hits") or []:
            hit_row = {"domain": domain, **hit}
            reason = suppressions.get(domain)
            if reason:
                suppressed.append({**hit_row, "suppression_reason": reason})
            else:
                hits.append(hit_row)
    return hits, suppressed


def structure_signals_for_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for item in record.get("domain_structure") or []:
        tags = item.get("evidence_tags") or []
        if not tags:
            continue
        key = (str(item.get("domain") or ""), tuple(str(tag) for tag in tags))
        if key in seen:
            continue
        seen.add(key)
        signals.append(dict(item))
    return signals


def attach_reputation_to_rows(folder_result: dict[str, Any], reputation_map: dict[str, dict[str, Any]]) -> None:
    for bucket in ("candidates", "allowed"):
        for row in folder_result.get(bucket) or []:
            message_id = ((row.get("message") or {}).get("entry_id") or "")
            reputation = reputation_map.get(message_id)
            if reputation is not None:
                row["reputation"] = reputation


def attach_message_clusters(folder_result: dict[str, Any]) -> None:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in list(folder_result.get("candidates") or []) + list(folder_result.get("allowed") or []):
        key = message_cluster_key(row.get("message") or {})
        if key:
            groups.setdefault(key, []).append(row)
    for rows in groups.values():
        domains = sorted({domain for row in rows for domain in row.get("young_domains") or []})
        if len(rows) < 2 or len(domains) < 2:
            continue
        cluster = {
            "type": "rotating_young_domains",
            "message_count": len(rows),
            "young_domains": domains,
        }
        for row in rows:
            row["cluster"] = cluster


def message_cluster_key(message: dict[str, Any]) -> str | None:
    subject = text_fingerprint(str(message.get("subject") or ""), max_tokens=8)
    body = text_fingerprint(str(message.get("body_excerpt") or ""), max_tokens=16)
    if not subject:
        return None
    return f"{subject}|{body}"


def text_fingerprint(value: str, *, max_tokens: int) -> str:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 3 and not token.isdigit()
    ]
    return " ".join(tokens[:max_tokens])


def run_scan(
    *,
    apply: bool,
    days: int,
    limit: int,
    young_days: int,
    with_reputation: bool = False,
    reputation_profile: str = "light",
    with_blocklists: bool = False,
    blocklist_profile: str = "threat",
    report_retention_days: int = DEFAULT_REPORT_RETENTION_DAYS,
    report_max_mb: int = DEFAULT_REPORT_MAX_MB,
    rotate_report_files: bool = True,
    outlook_timeout_seconds: int = DEFAULT_OUTLOOK_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    state.ensure_state()
    trusted_domains = state.load_trusted_domains()
    blocklist_suppressions = state.load_blocklist_suppressions()
    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
        "limit": limit,
        "young_days": young_days,
        "with_reputation": with_reputation,
        "reputation_profile": reputation_profile if with_reputation else None,
        "with_blocklists": with_blocklists,
        "blocklist_profile": blocklist_profile if with_blocklists else None,
        "accounts": [],
        "errors": [],
    }

    for account_config in ACCOUNTS:
        account_report = {
            "account": account_config.account,
            "quarantine_folder": account_config.quarantine_folder,
            "folders": [],
        }
        for folder in account_config.source_folders:
            payload = scan_folder(
                account=account_config.account,
                folder=folder,
                days=days,
                limit=limit,
                young_days=young_days,
                with_blocklists=with_blocklists,
                blocklist_profile=blocklist_profile,
                outlook_timeout_seconds=outlook_timeout_seconds,
            )
            if not payload.get("ok"):
                account_report["folders"].append(
                    {
                        "folder_selector": folder,
                        "ok": False,
                        "error": payload.get("stderr") or payload.get("result"),
                    }
                )
                continue
            reputation_map: dict[str, dict[str, Any]] = {}
            reputation_error = None
            folder_result = evaluate_scan_payload(
                payload.get("result") or {},
                quarantine_folder=account_config.quarantine_folder,
                trusted_domains=trusted_domains,
                blocklist_suppressions=blocklist_suppressions,
                apply=apply,
                reputation_by_message={},
            )
            if with_reputation:
                reputation_observables = build_reputation_observables_for_profile(
                    payload.get("result") or {},
                    folder_result,
                    reputation_profile=reputation_profile,
                )
                if reputation_observables:
                    reputation_payload = run_observable_reputation(reputation_observables)
                    if reputation_payload.get("ok"):
                        reputation_map = reputation_by_message(reputation_payload)
                        attach_reputation_to_rows(folder_result, reputation_map)
                        folder_result["reputation_diagnostics"] = reputation_payload.get("diagnostics") or {}
                        folder_result["rejected_reputation_observables"] = reputation_payload.get("rejected_observables") or []
                    else:
                        reputation_error = reputation_payload.get("error")
            if reputation_error:
                folder_result["reputation_error"] = reputation_error
            attach_message_clusters(folder_result)
            account_report["folders"].append(
                {
                    "folder_selector": folder,
                    "ok": True,
                    **folder_result,
                }
            )
        report["accounts"].append(account_report)

    if with_reputation:
        report["reputation_diagnostics"] = summarize_report_reputation_diagnostics(report)

    write_reports(
        report,
        retention_days=report_retention_days,
        max_mb=report_max_mb,
        rotate_report_files=rotate_report_files,
    )
    return report


def summarize_report_reputation_diagnostics(report: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "folder_count": 0,
        "observable_count": 0,
        "rejected_observable_count": 0,
        "cache": {"hit_count": 0, "miss_count": 0},
        "providers": {
            "result_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "verdicts": {},
        },
    }
    for account in report.get("accounts") or []:
        for folder in account.get("folders") or []:
            diagnostics = folder.get("reputation_diagnostics") or {}
            if not diagnostics:
                continue
            summary["folder_count"] += 1
            summary["observable_count"] += int(diagnostics.get("observable_count") or 0)
            summary["rejected_observable_count"] += int(diagnostics.get("rejected_observable_count") or 0)
            cache = diagnostics.get("cache") or {}
            summary["cache"]["hit_count"] += int(cache.get("hit_count") or 0)
            summary["cache"]["miss_count"] += int(cache.get("miss_count") or 0)
            providers = diagnostics.get("providers") or {}
            summary["providers"]["result_count"] += int(providers.get("result_count") or 0)
            summary["providers"]["skipped_count"] += int(providers.get("skipped_count") or 0)
            summary["providers"]["error_count"] += int(providers.get("error_count") or 0)
            verdicts = summary["providers"]["verdicts"]
            for verdict, count in (providers.get("verdicts") or {}).items():
                verdicts[verdict] = int(verdicts.get(verdict) or 0) + int(count or 0)
    return summary


def write_reports(
    report: dict[str, Any],
    *,
    retention_days: int = DEFAULT_REPORT_RETENTION_DAYS,
    max_mb: int = DEFAULT_REPORT_MAX_MB,
    rotate_report_files: bool = True,
) -> None:
    clean_report = replace_invalid_surrogates(report)
    report.clear()
    report.update(clean_report)
    state.ensure_state()
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    mode = report["mode"]
    json_path = state.REPORT_DIR / f"{stamp}-{mode}.json"
    md_path = state.REPORT_DIR / f"{stamp}-{mode}.md"
    report["report_json"] = str(json_path)
    report["report_markdown"] = str(md_path)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    if rotate_report_files:
        report["report_rotation"] = rotate_reports(
            report_dir=state.REPORT_DIR,
            current_paths={json_path, md_path},
            retention_days=retention_days,
            max_bytes=max_mb * 1024 * 1024,
            now=datetime.now(),
        )
    else:
        report["report_rotation"] = {
            "enabled": False,
            "deleted_files": [],
            "bytes_before": report_dir_size(state.REPORT_DIR),
            "bytes_after": report_dir_size(state.REPORT_DIR),
            "retention_days": retention_days,
            "max_bytes": max_mb * 1024 * 1024,
        }
    for _ in range(3):
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(render_markdown_report(report), encoding="utf-8")
        bytes_after = report_dir_size(state.REPORT_DIR)
        if report["report_rotation"]["bytes_after"] == bytes_after:
            break
        report["report_rotation"]["bytes_after"] = bytes_after


def rotate_reports(
    *,
    report_dir: Path,
    current_paths: set[Path],
    retention_days: int,
    max_bytes: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    resolved_current = {path.resolve() for path in current_paths}
    files = [path for path in report_dir.glob("*") if path.is_file() and path.suffix.lower() in {".json", ".md"}]
    bytes_before = sum(path.stat().st_size for path in files if path.exists())
    deleted_files: list[str] = []
    cutoff = (now or datetime.now()) - timedelta(days=retention_days)

    def delete_group(paths: list[Path]) -> None:
        for path in paths:
            if path.resolve() in resolved_current or not path.exists():
                continue
            deleted_files.append(str(path))
            path.unlink()

    for group in report_groups(report_dir).values():
        if any(path.resolve() in resolved_current for path in group):
            continue
        if all(datetime.fromtimestamp(path.stat().st_mtime) < cutoff for path in group if path.exists()):
            delete_group(group)

    while report_dir_size(report_dir) > max_bytes:
        groups = [
            group
            for group in report_groups(report_dir).values()
            if group and not any(path.resolve() in resolved_current for path in group)
        ]
        if not groups:
            break
        oldest = min(groups, key=lambda group: min(path.stat().st_mtime for path in group if path.exists()))
        delete_group(oldest)

    return {
        "enabled": True,
        "deleted_files": deleted_files,
        "bytes_before": bytes_before,
        "bytes_after": report_dir_size(report_dir),
        "retention_days": retention_days,
        "max_bytes": max_bytes,
    }


def report_groups(report_dir: Path) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for path in report_dir.glob("*"):
        if path.is_file() and path.suffix.lower() in {".json", ".md"}:
            groups.setdefault(path.stem, []).append(path)
    return groups


def report_dir_size(report_dir: Path) -> int:
    if not report_dir.exists():
        return 0
    return sum(path.stat().st_size for path in report_dir.glob("*") if path.is_file())


def replace_invalid_surrogates(value: Any) -> Any:
    if isinstance(value, str):
        return SURROGATE_RE.sub("\uFFFD", value)
    if isinstance(value, list):
        return [replace_invalid_surrogates(item) for item in value]
    if isinstance(value, tuple):
        return tuple(replace_invalid_surrogates(item) for item in value)
    if isinstance(value, dict):
        return {
            replace_invalid_surrogates(key): replace_invalid_surrogates(item)
            for key, item in value.items()
        }
    return value


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Mail Domain Quarantine {report['mode']}",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Window: {report['days']} days",
        f"- Young domain threshold: {report['young_days']} days",
        f"- Blocklist enrichment: {'on' if report.get('with_blocklists') else 'off'}",
        f"- Blocklist profile: {report.get('blocklist_profile') or 'none'}",
        f"- Reputation enrichment: {'on' if report.get('with_reputation') else 'off'}",
        f"- Reputation profile: {report.get('reputation_profile') or 'none'}",
        "",
    ]
    for account in report["accounts"]:
        lines.append(f"## {account['account']}")
        for folder in account["folders"]:
            lines.append(f"- Folder `{folder['folder_selector']}`: {'ok' if folder['ok'] else 'error'}")
            if not folder["ok"]:
                lines.append(f"  - Error: {folder['error']}")
                continue
            if folder.get("reputation_diagnostics"):
                lines.append(
                    f"  - Reputation diagnostics: {summarize_reputation_diagnostics(folder['reputation_diagnostics'])}"
                )
            for candidate in folder["candidates"]:
                message = candidate["message"]
                domains = sorted(set(candidate.get("young_domains") or []) | set(candidate.get("blocklisted_domains") or []))
                lines.append(
                    "  - Quarantine: "
                    f"{message.get('sender_email', '')} | {message.get('subject', '')} | "
                    f"{', '.join(domains)}"
                )
                if candidate.get("reputation"):
                    reputation = candidate["reputation"]
                    lines.append(f"    - Reputation: {summarize_reputation_result(reputation)}")
                    if reputation.get("explanations"):
                        lines.append(f"    - Reputation explanation: {reputation['explanations'][0]}")
                if candidate.get("blocklist_hits"):
                    hit_summary = summarize_blocklist_hits(candidate["blocklist_hits"])
                    lines.append(f"    - Blocklists: {hit_summary}")
                if candidate.get("structure_signals"):
                    lines.append(f"    - Structure: {summarize_structure_signals(candidate['structure_signals'])}")
                if candidate.get("cluster"):
                    cluster = candidate["cluster"]
                    lines.append(
                        "    - Cluster: "
                        f"{cluster.get('type')} messages={cluster.get('message_count')} "
                        f"domains={', '.join(cluster.get('young_domains') or [])}"
                    )
            for allowed in folder["allowed"]:
                if allowed.get("blocklist_hits"):
                    message = allowed["message"]
                    lines.append(
                        "  - Blocklist-only: "
                        f"{message.get('sender_email', '')} | {message.get('subject', '')} | "
                        f"{summarize_blocklist_hits(allowed['blocklist_hits'])}"
                    )
                reputation = allowed.get("reputation")
                if not reputation or reputation.get("verdict") in {"clean", "unknown", "skipped"}:
                    continue
                message = allowed["message"]
                lines.append(
                    "  - Reputation-only: "
                    f"{message.get('sender_email', '')} | {message.get('subject', '')} | "
                    f"{summarize_reputation_result(reputation)}"
                )
            if folder.get("reputation_error"):
                lines.append(f"  - Reputation error: {folder['reputation_error']}")
        lines.append("")
    return "\n".join(lines)


def summarize_blocklist_hits(hits: list[dict[str, Any]]) -> str:
    parts = []
    for hit in hits[:8]:
        parts.append(
            f"{hit.get('domain')}->{hit.get('category')}:{hit.get('source')}({hit.get('matched_domain')})"
        )
    if len(hits) > 8:
        parts.append(f"+{len(hits) - 8} more")
    return ", ".join(parts)


def summarize_structure_signals(signals: list[dict[str, Any]]) -> str:
    grouped: dict[str, set[str]] = {}
    for signal in signals:
        domain = str(signal.get("domain") or "")
        if not domain:
            continue
        grouped.setdefault(domain, set()).update(signal.get("evidence_tags") or [])
    parts = []
    for domain, tags in list(grouped.items())[:5]:
        parts.append(f"{domain}[{','.join(sorted(tags))}]")
    if len(grouped) > 5:
        parts.append(f"+{len(grouped) - 5} more")
    return ", ".join(parts)


def summarize_reputation_result(reputation: dict[str, Any]) -> str:
    provider_summary = reputation.get("provider_summary") or {}
    evidence_count = len(reputation.get("evidence") or []) or int(provider_summary.get("evidence_count") or 0)
    error_count = len(reputation.get("errors") or []) or int(provider_summary.get("error_count") or 0)
    return (
        f"{reputation.get('verdict')} score={reputation.get('score')} "
        f"evidence={evidence_count} errors={error_count}"
    )


def summarize_reputation_diagnostics(diagnostics: dict[str, Any]) -> str:
    cache = diagnostics.get("cache") or {}
    providers = diagnostics.get("providers") or {}
    return (
        f"observables={int(diagnostics.get('observable_count') or 0)} "
        f"rejected={int(diagnostics.get('rejected_observable_count') or 0)} "
        f"cache={int(cache.get('hit_count') or 0)}/{int(cache.get('miss_count') or 0)} "
        f"providers={int(providers.get('result_count') or 0)} "
        f"skipped={int(providers.get('skipped_count') or 0)} "
        f"errors={int(providers.get('error_count') or 0)}"
    )
