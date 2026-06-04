from __future__ import annotations

import argparse
import sys

from .formatting import render_json, render_text
from .service import AliExpressService
from .session import BrowserSessionError


def build_service() -> AliExpressService:
    return AliExpressService()


def _write_output(output: str) -> None:
    try:
        sys.stdout.write(output)
    except UnicodeEncodeError:
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is None:
            raise
        buffer.write(output.encode("utf-8", errors="replace"))
    if not output.endswith("\n"):
        try:
            sys.stdout.write("\n")
        except UnicodeEncodeError:
            buffer = getattr(sys.stdout, "buffer", None)
            if buffer is None:
                raise
            buffer.write(b"\n")


def add_locale_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ship-to", default="CY")
    parser.add_argument("--currency", default="EUR")
    parser.add_argument("--locale", default="en_US")


def add_session_read_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--use-session",
        action="store_true",
        help="Use the managed logged-in browser profile for this read-only request.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aliexpress-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect-identifier")
    inspect_parser.add_argument("identifier")
    inspect_parser.add_argument("--text", action="store_true")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--pages", type=int, default=1)
    search_parser.add_argument("--sort", choices=("relevance", "orders", "newest", "price-asc", "price-desc"), default="relevance")
    search_parser.add_argument("--min-price", type=float)
    search_parser.add_argument("--max-price", type=float)
    add_locale_args(search_parser)
    add_session_read_arg(search_parser)
    search_parser.add_argument("--text", action="store_true")

    browse_parser = subparsers.add_parser("browse")
    browse_parser.add_argument("--url", required=True)
    browse_parser.add_argument("--pages", type=int, default=1)
    add_session_read_arg(browse_parser)
    browse_parser.add_argument("--text", action="store_true")

    get_parser = subparsers.add_parser("get")
    get_parser.add_argument("identifier")
    add_locale_args(get_parser)
    add_session_read_arg(get_parser)
    get_parser.add_argument("--text", action="store_true")

    reviews_parser = subparsers.add_parser("reviews")
    reviews_parser.add_argument("identifier")
    reviews_parser.add_argument("--limit", type=int)
    add_session_read_arg(reviews_parser)
    reviews_parser.add_argument("--text", action="store_true")

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("identifiers", nargs="+")
    compare_parser.add_argument("--text", action="store_true")

    session_parser = subparsers.add_parser("session")
    session_subparsers = session_parser.add_subparsers(dest="session_command", required=True)
    login_parser = session_subparsers.add_parser("login")
    login_parser.add_argument("--login-timeout-sec", type=int, default=300)
    login_parser.add_argument("--manual-confirm", action="store_true")
    login_parser.add_argument("--text", action="store_true")
    status_parser = session_subparsers.add_parser("status")
    status_parser.add_argument("--text", action="store_true")
    logout_parser = session_subparsers.add_parser("logout")
    logout_parser.add_argument("--text", action="store_true")
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.command in {"search", "browse"} and (args.pages < 1 or args.pages > 5):
        parser.error("--pages must be between 1 and 5")
    if args.command == "reviews" and args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.command == "session" and args.session_command == "login" and args.login_timeout_sec < 1:
        parser.error("--login-timeout-sec must be at least 1")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    service = build_service()
    try:
        if args.command == "inspect-identifier":
            payload = service.inspect_identifier(args.identifier)
        elif args.command == "search":
            payload = service.search(
                query=args.query,
                pages=args.pages,
                sort=args.sort,
                min_price=args.min_price,
                max_price=args.max_price,
                ship_to=args.ship_to,
                currency=args.currency,
                locale=args.locale,
                use_session=args.use_session,
            )
        elif args.command == "browse":
            payload = service.browse(url=args.url, pages=args.pages, use_session=args.use_session)
        elif args.command == "get":
            payload = service.get(
                args.identifier,
                ship_to=args.ship_to,
                currency=args.currency,
                locale=args.locale,
                use_session=args.use_session,
            )
        elif args.command == "reviews":
            payload = service.reviews(args.identifier, limit=args.limit, use_session=args.use_session)
        elif args.command == "compare":
            payload = service.compare(args.identifiers)
        elif args.session_command == "login":
            payload = service.login(login_timeout_sec=args.login_timeout_sec, manual_confirm=args.manual_confirm)
        elif args.session_command == "status":
            payload = service.session_status()
        else:
            payload = service.session_logout()
    except (BrowserSessionError, ValueError) as exc:
        payload = {
            "command": args.command,
            "error": str(exc),
            "hint": "Use a supported AliExpress item URL/id. Run `aliexpress-cli session login` only for logged-in browsing visibility.",
        }
        output = render_text(payload) if getattr(args, "text", False) else render_json(payload)
        _write_output(output)
        return 2
    output = render_text(payload) if getattr(args, "text", False) else render_json(payload)
    _write_output(output)
    return 0


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    entrypoint()
