from __future__ import annotations

import argparse
import json
import sys

from . import runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Antigravity exact-model review helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Report helper and external Claude proxy status.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        result = runtime.collect_status(runtime.RuntimePaths.default())
    else:  # pragma: no cover - argparse enforces known commands.
        raise AssertionError(f"Unhandled command: {args.command}")

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
