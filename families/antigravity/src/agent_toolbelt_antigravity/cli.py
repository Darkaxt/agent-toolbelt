from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import proxy, runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Antigravity exact-model review helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Report helper and external Claude proxy status.")
    update_parser = subparsers.add_parser(
        "update", help="Check or install a helper-owned CLIProxyAPI release."
    )
    update_parser.add_argument("--check", action="store_true", help="Check without installing.")
    update_parser.add_argument("--version", help="Install or check an exact CLIProxyAPI version.")
    login_parser = subparsers.add_parser(
        "login", help="Authenticate the helper-owned Antigravity runtime interactively."
    )
    login_parser.add_argument(
        "--no-browser", action="store_true", help="Use the non-browser OAuth flow."
    )
    subparsers.add_parser("models", help="List models visible to helper-owned authentication.")
    review_parser = subparsers.add_parser(
        "review", help="Review one explicit packet with an exact model."
    )
    review_parser.add_argument("--packet", type=Path, required=True)
    review_parser.add_argument("--instruction", required=True)
    review_parser.add_argument("--model", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        result = runtime.collect_status(runtime.RuntimePaths.default())
    elif args.command == "update":
        result = runtime.run_update(
            runtime.RuntimePaths.default(),
            check_only=args.check,
            version=args.version,
        )
    elif args.command == "login":
        result = proxy.run_login(
            runtime.RuntimePaths.default(),
            no_browser=args.no_browser,
        )
    elif args.command == "models":
        result = proxy.run_models(runtime.RuntimePaths.default())
    elif args.command == "review":
        result = proxy.run_review(
            paths=runtime.RuntimePaths.default(),
            packet=args.packet,
            instruction=args.instruction,
            model=args.model,
        )
    else:  # pragma: no cover - argparse enforces known commands.
        raise AssertionError(f"Unhandled command: {args.command}")

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
