from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .cache import DEFAULT_CACHE_PATH, ReputationCache
from .classifier import classify_records
from .exports import write_csv_report, write_stix_bundle
from .observables import normalize_report
from .providers import default_providers, provider_status


def console_json(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify URL, domain, and IP observables with passive reputation checks.")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    normalize = subparsers.add_parser("normalize", help="Normalize observables without provider lookups.")
    normalize.add_argument("--input", required=True)
    normalize.add_argument("--output")

    classify = subparsers.add_parser("classify", help="Classify observables from JSON input.")
    classify.add_argument("--input", required=True)
    classify.add_argument("--output")
    classify.add_argument("--auto-detect", action="store_true", help="Accept raw strings or records with omitted/auto type.")
    classify.add_argument("--csv-output", help="Write one-row-per-observable CSV summary.")
    classify.add_argument("--stix-output", help="Write STIX 2.1 indicators for malicious/suspicious observables.")
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
    if args.operation == "normalize":
        payload = read_json_payload(Path(args.input))
        report = normalize_report(payload_records(payload), auto_detect=True)
        write_optional_json(report, args.output)
        print(console_json(report))
        return 0
    if args.operation == "classify":
        payload = read_json_payload(Path(args.input))
        report = classify_records(
            payload_records(payload),
            auto_detect=args.auto_detect,
            provider_list=default_providers(no_network=args.no_network),
            reputation_cache=ReputationCache(Path(args.cache), ttl_seconds=args.cache_ttl_seconds),
        )
        write_optional_json(report, args.output)
        if args.csv_output:
            write_csv_report(report, Path(args.csv_output))
        if args.stix_output:
            write_stix_bundle(report, Path(args.stix_output))
        if not args.quiet:
            print(console_json(report))
        return 0
    parser.error(f"Unsupported operation: {args.operation}")
    return 2


def read_json_payload(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def payload_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        records = payload.get("observables")
        return list(records) if isinstance(records, list) else []
    return []


def write_optional_json(report: dict[str, Any], output: str | None) -> None:
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
