from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cache import DEFAULT_CACHE_PATH, ReputationCache
from .classifier import classify_records
from .providers import default_providers, provider_status


def console_json(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify URL, domain, and IP observables with passive reputation checks.")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    classify = subparsers.add_parser("classify", help="Classify observables from JSON input.")
    classify.add_argument("--input", required=True)
    classify.add_argument("--output")
    classify.add_argument("--no-network", action="store_true", help="Skip all network-backed providers.")
    classify.add_argument("--cache", default=str(DEFAULT_CACHE_PATH))
    classify.add_argument("--cache-ttl-seconds", type=int, default=86400)
    classify.add_argument("--quiet", action="store_true", help="Write output without printing the full report to stdout.")

    providers = subparsers.add_parser("providers", help="Inspect provider configuration.")
    providers.add_argument("--status", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.operation == "providers":
        print(console_json({"providers": provider_status()}))
        return 0
    if args.operation == "classify":
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        report = classify_records(
            payload.get("observables") or [],
            provider_list=default_providers(no_network=args.no_network),
            reputation_cache=ReputationCache(Path(args.cache), ttl_seconds=args.cache_ttl_seconds),
        )
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if not args.quiet:
            print(console_json(report))
        return 0
    parser.error(f"Unsupported operation: {args.operation}")
    return 2


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
