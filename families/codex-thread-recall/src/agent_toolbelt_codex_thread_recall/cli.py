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

    grep_parser = subparsers.add_parser("grep", help="Search the current thread's rollout before looking elsewhere.")
    grep_parser.add_argument("--pattern", required=True)
    grep_parser.add_argument("--limit", type=int, default=10)
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
        )
    else:
        payload = thread_recall.grep_rollout(
            pattern=args.pattern,
            thread_id=args.thread_id,
            codex_home=args.home_override,
            limit=args.limit,
        )

    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("ok") else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
