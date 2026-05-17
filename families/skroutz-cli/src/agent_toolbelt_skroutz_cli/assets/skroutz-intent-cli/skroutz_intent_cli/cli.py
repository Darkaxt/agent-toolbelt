from __future__ import annotations

import argparse
import sys

from .formatting import render_json, render_text
from .service import SkroutzService
from .session import BrowserSessionError


def build_service() -> SkroutzService:
    return SkroutzService()


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skroutz-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect-identifier")
    inspect_parser.add_argument("identifier")
    inspect_parser.add_argument("--text", action="store_true")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--pages", type=int, default=1)
    search_parser.add_argument("--text", action="store_true")

    get_parser = subparsers.add_parser("get")
    get_parser.add_argument("identifier")
    get_parser.add_argument("--text", action="store_true")

    offers_parser = subparsers.add_parser("offers")
    offers_parser.add_argument("identifier")
    offers_parser.add_argument("--text", action="store_true")

    reviews_parser = subparsers.add_parser("reviews")
    reviews_parser.add_argument("identifier")
    reviews_parser.add_argument("--limit", type=int)
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

    cart_parser = subparsers.add_parser("cart")
    cart_subparsers = cart_parser.add_subparsers(dest="cart_command", required=True)
    cart_list_parser = cart_subparsers.add_parser("list")
    cart_list_parser.add_argument("--text", action="store_true")
    cart_add_parser = cart_subparsers.add_parser("add")
    cart_add_parser.add_argument("identifier")
    cart_add_parser.add_argument("--quantity", type=int, default=1)
    cart_add_parser.add_argument("--confirm-cart-add", action="store_true")
    cart_add_parser.add_argument("--text", action="store_true")
    cart_remove_parser = cart_subparsers.add_parser("remove")
    cart_remove_parser.add_argument("identifier")
    cart_remove_parser.add_argument("--quantity", type=int, default=1)
    cart_remove_parser.add_argument("--confirm-cart-remove", action="store_true")
    cart_remove_parser.add_argument("--text", action="store_true")
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.command == "search" and (args.pages < 1 or args.pages > 5):
        parser.error("--pages must be between 1 and 5")
    if args.command == "reviews" and args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.command == "session" and args.login_timeout_sec < 1:
        parser.error("--login-timeout-sec must be at least 1")
    if args.command == "cart" and getattr(args, "quantity", 1) < 1:
        parser.error("--quantity must be at least 1")
    if args.command == "cart" and args.cart_command == "add" and not args.confirm_cart_add:
        parser.error("cart add requires --confirm-cart-add")
    if args.command == "cart" and args.cart_command == "remove" and not args.confirm_cart_remove:
        parser.error("cart remove requires --confirm-cart-remove")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    service = build_service()
    try:
        if args.command == "inspect-identifier":
            payload = service.inspect_identifier(args.identifier)
        elif args.command == "search":
            payload = service.search(query=args.query, pages=args.pages)
        elif args.command == "get":
            payload = service.get(args.identifier)
        elif args.command == "offers":
            payload = service.offers(args.identifier)
        elif args.command == "reviews":
            payload = service.reviews(args.identifier, limit=args.limit)
        elif args.command == "compare":
            payload = service.compare(args.identifiers)
        elif args.command == "session":
            payload = service.login(login_timeout_sec=args.login_timeout_sec, manual_confirm=args.manual_confirm)
        elif args.command == "cart" and args.cart_command == "list":
            payload = service.cart_list()
        elif args.command == "cart" and args.cart_command == "add":
            payload = service.cart_add(args.identifier, quantity=args.quantity)
        else:
            payload = service.cart_remove(args.identifier, quantity=args.quantity)
    except (BrowserSessionError, ValueError) as exc:
        payload = {
            "command": args.command,
            "error": str(exc),
            "hint": "Run `skroutz-cli session login` for cart workflows, or pass a supported Skroutz product URL/id.",
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
