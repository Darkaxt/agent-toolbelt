from __future__ import annotations

import argparse
import json
import sys

from . import scanner


def console_json(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quarantine recent mail referencing young domains.")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    scan = subparsers.add_parser("scan", help="Scan recent Inbox and Spam mail.")
    mode = scan.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Report candidates without moving mail.")
    mode.add_argument("--apply", action="store_true", help="Move candidates to Inbox\\Quarantine.")
    scan.add_argument("--days", type=int, default=7)
    scan.add_argument("--limit", type=int, default=200)
    scan.add_argument("--young-days", type=int, default=365)
    scan.add_argument("--with-blocklists", action="store_true")
    scan.add_argument("--blocklist-profile", choices=("threat", "debug-all"), default="threat")
    scan.add_argument("--with-reputation", action="store_true")
    scan.add_argument("--report-retention-days", type=int, default=scanner.DEFAULT_REPORT_RETENTION_DAYS)
    scan.add_argument("--report-max-mb", type=int, default=scanner.DEFAULT_REPORT_MAX_MB)
    scan.add_argument("--no-report-rotation", action="store_true")
    scan.add_argument("--outlook-timeout-seconds", type=int, default=scanner.DEFAULT_OUTLOOK_TIMEOUT_SECONDS)
    scan.add_argument(
        "--reputation-profile",
        choices=("light", "full"),
        default="light",
        help="light checks domains and IPs; full also checks exact URLs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.operation == "scan":
        report = scanner.run_scan(
            apply=bool(args.apply),
            days=args.days,
            limit=args.limit,
            young_days=args.young_days,
            with_reputation=bool(args.with_reputation),
            reputation_profile=args.reputation_profile,
            with_blocklists=bool(args.with_blocklists),
            blocklist_profile=args.blocklist_profile,
            report_retention_days=args.report_retention_days,
            report_max_mb=args.report_max_mb,
            rotate_report_files=not bool(args.no_report_rotation),
            outlook_timeout_seconds=args.outlook_timeout_seconds,
        )
        print(console_json(report))
        return 0
    parser.error(f"Unsupported operation: {args.operation}")
    return 2


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
