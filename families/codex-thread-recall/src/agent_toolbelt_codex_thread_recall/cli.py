from __future__ import annotations

import argparse
import json
import sys

from . import thread_recall


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect the current Codex thread's rollout history for bounded self-recall."
    )
    parser.add_argument("--thread-id", help="Override CODEX_THREAD_ID for offline debugging.")
    parser.add_argument("--codex-home", dest="home_override", help="Override the default Codex home directory.")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Resolve the current thread and show metadata.")

    collect_parser = subparsers.add_parser("collect", help="Warm recall indexes for current, recent, or workspace threads.")
    collect_parser.add_argument("--thread-source", choices=["current", "recent", "workspace"], default="recent")
    collect_parser.add_argument("--max-threads", type=int, default=10)
    collect_parser.add_argument("--updated-within-hours", type=int, default=48)
    collect_parser.add_argument("--max-run-seconds", type=int, default=90)
    collect_parser.add_argument("--json-log")

    recall_parser = subparsers.add_parser("recall", help="Summarize the current thread's raw rollout history.")
    recall_parser.add_argument("--evidence-limit", type=int, default=25)
    recall_parser.add_argument("--profile", choices=["general", "shipping", "debug"], default="general")
    recall_parser.add_argument("--scope", choices=["current", "thread", "episode"], default="current")
    recall_parser.add_argument("--episode-id")
    recall_parser.add_argument("--thread-source", choices=["current", "workspace"], default="current")
    recall_parser.add_argument("--max-threads", type=int, default=10)

    grep_parser = subparsers.add_parser("grep", help="Search the current thread's rollout before looking elsewhere.")
    grep_parser.add_argument("--pattern", required=True)
    grep_parser.add_argument("--limit", type=int, default=10)
    grep_parser.add_argument("--all", dest="all_matches", action="store_true")
    grep_parser.add_argument("--sort", choices=["relevance", "time-asc", "time-desc"], default="relevance")
    grep_parser.add_argument("--query-mode", choices=["literal", "fts"], default="literal")
    grep_parser.add_argument("--context", type=int, default=0)
    grep_parser.add_argument("--role")
    grep_parser.add_argument("--entry-type")
    grep_parser.add_argument("--payload-type")
    grep_parser.add_argument("--after")
    grep_parser.add_argument("--before")
    grep_parser.add_argument("--include-noise", action="store_true")
    grep_parser.add_argument("--scope", choices=["current", "thread", "episode"], default="thread")
    grep_parser.add_argument("--episode-id")
    grep_parser.add_argument("--thread-source", choices=["current", "workspace"], default="current")
    grep_parser.add_argument("--max-threads", type=int, default=10)

    timeline_parser = subparsers.add_parser("timeline", help="Build a structured timeline from the current thread.")
    timeline_parser.add_argument("--kind", choices=["shipped", "published", "merged", "pushed", "installed", "validated", "all"], default="shipped")
    timeline_parser.add_argument("--group", choices=["entity", "repo", "none"], default="entity")
    timeline_parser.add_argument("--limit", type=int, default=10)
    timeline_parser.add_argument("--all", dest="all_matches", action="store_true")
    timeline_parser.add_argument("--sort", choices=["time-asc", "time-desc"], default="time-asc")
    timeline_parser.add_argument("--scope", choices=["current", "thread", "episode"], default="current")
    timeline_parser.add_argument("--episode-id")
    timeline_parser.add_argument("--include-meta", action="store_true")
    timeline_parser.add_argument("--thread-source", choices=["current", "workspace"], default="current")
    timeline_parser.add_argument("--max-threads", type=int, default=10)

    worklog_parser = subparsers.add_parser("worklog", help="Compute the first/last active work span for one or more patterns.")
    worklog_parser.add_argument("--pattern", action="append", required=True)
    worklog_parser.add_argument("--query-mode", choices=["literal", "fts"], default="literal")
    worklog_parser.add_argument("--role")
    worklog_parser.add_argument("--entry-type")
    worklog_parser.add_argument("--payload-type")
    worklog_parser.add_argument("--after")
    worklog_parser.add_argument("--before")
    worklog_parser.add_argument("--scope", choices=["current", "thread", "episode"], default="thread")
    worklog_parser.add_argument("--episode-id")
    worklog_parser.add_argument("--include-incidental", action="store_true")
    worklog_parser.add_argument("--include-noise", action="store_true")
    worklog_parser.add_argument("--thread-source", choices=["current", "workspace"], default="current")
    worklog_parser.add_argument("--max-threads", type=int, default=10)

    memory_parser = subparsers.add_parser("memory", help="Manage opt-in portable recall memory bundles.")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)

    memory_export = memory_subparsers.add_parser("export", help="Export distilled current-thread recall facts.")
    memory_export.add_argument("--scope", choices=["current", "thread", "episode"], default="current")
    memory_export.add_argument("--episode-id")
    memory_export.add_argument("--output")

    memory_import = memory_subparsers.add_parser("import", help="Import a portable recall memory bundle.")
    memory_import.add_argument("--path", required=True)

    memory_subparsers.add_parser("list", help="List imported recall memory bundles.")

    memory_show = memory_subparsers.add_parser("show", help="Show an imported recall memory bundle.")
    memory_show.add_argument("--bundle-id", required=True)

    memory_search = memory_subparsers.add_parser("search", help="Search imported recall memory bundles.")
    memory_search.add_argument("--pattern", required=True)
    memory_search.add_argument("--query-mode", choices=["literal", "fts"], default="literal")
    memory_search.add_argument("--limit", type=int, default=10)
    memory_search.add_argument("--all", dest="all_matches", action="store_true")
    memory_search.add_argument("--sort", choices=["relevance", "time-asc", "time-desc"], default="relevance")

    memory_forget = memory_subparsers.add_parser("forget", help="Forget an imported recall memory bundle.")
    memory_forget.add_argument("--bundle-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "status":
        payload = thread_recall.status(thread_id=args.thread_id, codex_home=args.home_override)
    elif args.command == "collect":
        payload = thread_recall.collect(
            thread_id=args.thread_id,
            codex_home=args.home_override,
            thread_source=args.thread_source,
            max_threads=args.max_threads,
            updated_within_hours=args.updated_within_hours,
            max_run_seconds=args.max_run_seconds,
            json_log=args.json_log,
        )
    elif args.command == "recall":
        payload = thread_recall.recall(
            thread_id=args.thread_id,
            codex_home=args.home_override,
            evidence_limit=args.evidence_limit,
            profile=args.profile,
            scope=args.scope,
            episode_id=args.episode_id,
            thread_source=args.thread_source,
            max_threads=args.max_threads,
        )
    elif args.command == "grep":
        payload = thread_recall.grep_rollout(
            pattern=args.pattern,
            thread_id=args.thread_id,
            codex_home=args.home_override,
            limit=args.limit,
            all_matches=args.all_matches,
            sort=args.sort,
            query_mode=args.query_mode,
            context=args.context,
            role=args.role,
            entry_type=args.entry_type,
            payload_type=args.payload_type,
            after=args.after,
            before=args.before,
            include_noise=args.include_noise,
            scope=args.scope,
            episode_id=args.episode_id,
            thread_source=args.thread_source,
            max_threads=args.max_threads,
        )
    elif args.command == "timeline":
        payload = thread_recall.timeline(
            thread_id=args.thread_id,
            codex_home=args.home_override,
            kind=args.kind,
            group=args.group,
            limit=args.limit,
            all_matches=args.all_matches,
            sort=args.sort,
            scope=args.scope,
            episode_id=args.episode_id,
            include_meta=args.include_meta,
            thread_source=args.thread_source,
            max_threads=args.max_threads,
        )
    elif args.command == "worklog":
        payload = thread_recall.worklog(
            patterns=args.pattern,
            thread_id=args.thread_id,
            codex_home=args.home_override,
            query_mode=args.query_mode,
            role=args.role,
            entry_type=args.entry_type,
            payload_type=args.payload_type,
            after=args.after,
            before=args.before,
            include_incidental=args.include_incidental,
            include_noise=args.include_noise,
            scope=args.scope,
            episode_id=args.episode_id,
            thread_source=args.thread_source,
            max_threads=args.max_threads,
        )
    elif args.memory_command == "export":
        payload = thread_recall.memory_export(
            thread_id=args.thread_id,
            codex_home=args.home_override,
            scope=args.scope,
            episode_id=args.episode_id,
            output_path=args.output,
        )
    elif args.memory_command == "import":
        payload = thread_recall.memory_import(
            codex_home=args.home_override,
            bundle_path=args.path,
        )
    elif args.memory_command == "list":
        payload = thread_recall.memory_list(codex_home=args.home_override)
    elif args.memory_command == "show":
        payload = thread_recall.memory_show(codex_home=args.home_override, bundle_id=args.bundle_id)
    elif args.memory_command == "search":
        payload = thread_recall.memory_search(
            codex_home=args.home_override,
            pattern=args.pattern,
            query_mode=args.query_mode,
            limit=args.limit,
            all_matches=args.all_matches,
            sort=args.sort,
        )
    else:
        payload = thread_recall.memory_forget(codex_home=args.home_override, bundle_id=args.bundle_id)

    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("ok") else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    entrypoint()
