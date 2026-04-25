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

    recall_parser = subparsers.add_parser("recall", help="Summarize the current thread's raw rollout history.")
    recall_parser.add_argument("--evidence-limit", type=int, default=25)
    recall_parser.add_argument("--profile", choices=["general", "shipping", "debug"], default="general")

    grep_parser = subparsers.add_parser("grep", help="Search the current thread's rollout before looking elsewhere.")
    grep_parser.add_argument("--pattern", required=True)
    grep_parser.add_argument("--limit", type=int, default=10)
    grep_parser.add_argument("--role")
    grep_parser.add_argument("--entry-type")
    grep_parser.add_argument("--payload-type")
    grep_parser.add_argument("--after")
    grep_parser.add_argument("--before")
    grep_parser.add_argument("--include-noise", action="store_true")

    timeline_parser = subparsers.add_parser("timeline", help="Build a structured timeline from the current thread.")
    timeline_parser.add_argument("--kind", choices=["shipped", "published", "merged", "pushed", "installed", "validated", "all"], default="shipped")
    timeline_parser.add_argument("--group", choices=["entity", "repo", "none"], default="entity")
    timeline_parser.add_argument("--limit", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "status":
        payload = thread_recall.status(thread_id=args.thread_id, codex_home=args.home_override)
    elif args.command == "recall":
        payload = thread_recall.recall(
            thread_id=args.thread_id,
            codex_home=args.home_override,
            evidence_limit=args.evidence_limit,
            profile=args.profile,
        )
    elif args.command == "grep":
        payload = thread_recall.grep_rollout(
            pattern=args.pattern,
            thread_id=args.thread_id,
            codex_home=args.home_override,
            limit=args.limit,
            role=args.role,
            entry_type=args.entry_type,
            payload_type=args.payload_type,
            after=args.after,
            before=args.before,
            include_noise=args.include_noise,
        )
    else:
        payload = thread_recall.timeline(
            thread_id=args.thread_id,
            codex_home=args.home_override,
            kind=args.kind,
            group=args.group,
            limit=args.limit,
        )

    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("ok") else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
