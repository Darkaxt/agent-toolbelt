from __future__ import annotations

import argparse
import sys

from .amazon import AmazonBlockedError
from .formatting import render_json, render_text
from .intent import IntentResolutionError
from .marketplaces import DEFAULT_MARKETPLACE, get_marketplace
from .service import AmazonService
from .session import BrowserSessionError, SUPPORTED_PORTALS, make_session_key


def build_service() -> AmazonService:
    return AmazonService()


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amazon-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--marketplace", default=DEFAULT_MARKETPLACE)
        command_parser.add_argument("--text", action="store_true")

    def add_search_flags(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("base")
        command_parser.add_argument("--brand")
        command_parser.add_argument("--model")
        command_parser.add_argument("--min-price", type=float)
        command_parser.add_argument("--max-price", type=float)
        command_parser.add_argument("--pages", type=int, default=1)
        command_parser.add_argument("--refresh-intent", action="store_true")
        add_common_flags(command_parser)

    search_parser = subparsers.add_parser("search")
    add_search_flags(search_parser)

    similar_parser = subparsers.add_parser("similar")
    add_search_flags(similar_parser)

    get_parser = subparsers.add_parser("get")
    get_parser.add_argument("identifier")
    add_common_flags(get_parser)

    reviews_parser = subparsers.add_parser("reviews")
    reviews_parser.add_argument("identifier")
    reviews_parser.add_argument("--limit", type=int)
    reviews_parser.add_argument("--portal", default="retail", choices=sorted(SUPPORTED_PORTALS))
    reviews_parser.add_argument("--user-data-dir", help=argparse.SUPPRESS)
    reviews_parser.add_argument("--profile-directory", help=argparse.SUPPRESS)
    reviews_parser.add_argument("--isolated", action="store_true", help=argparse.SUPPRESS)
    add_common_flags(reviews_parser)

    offers_parser = subparsers.add_parser("offers")
    offers_parser.add_argument("identifier")
    offers_parser.add_argument("--portal", default="retail", choices=sorted(SUPPORTED_PORTALS))
    offers_parser.add_argument("--marketplaces")
    offers_parser.add_argument("--vat-mode", choices=["auto", "incl", "excl"], default="auto")
    offers_parser.add_argument("--include-shipping", dest="include_shipping", action="store_true", default=True)
    offers_parser.add_argument("--no-include-shipping", dest="include_shipping", action="store_false")
    add_common_flags(offers_parser)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("identifiers", nargs="+")
    add_common_flags(compare_parser)

    address_parser = subparsers.add_parser("address")
    address_subparsers = address_parser.add_subparsers(dest="address_command", required=True)
    address_inspect_parser = address_subparsers.add_parser("inspect")
    address_inspect_parser.add_argument("--portal", default="retail", choices=sorted(SUPPORTED_PORTALS))
    address_inspect_parser.add_argument("--marketplaces")
    address_inspect_parser.add_argument("--reference-marketplace", default=DEFAULT_MARKETPLACE)
    address_inspect_parser.add_argument("--text", action="store_true")

    session_parser = subparsers.add_parser("session")
    session_subparsers = session_parser.add_subparsers(dest="session_command", required=True)

    def add_session_login_flags(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--marketplace", default=DEFAULT_MARKETPLACE)
        command_parser.add_argument("--portal", default="retail", choices=sorted(SUPPORTED_PORTALS))
        command_parser.add_argument("--text", action="store_true")
        command_parser.add_argument("--browser-executable")
        command_parser.add_argument("--headless", action="store_true")
        command_parser.add_argument("--url")
        command_parser.add_argument("--user-data-dir", help=argparse.SUPPRESS)
        command_parser.add_argument("--profile-directory", help=argparse.SUPPRESS)
        command_parser.add_argument("--isolated", action="store_true", help=argparse.SUPPRESS)

    add_session_login_flags(session_subparsers.add_parser("login"))
    add_session_login_flags(session_subparsers.add_parser("bootstrap"))

    return parser


def _validate_search_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if getattr(args, "model", None) and not getattr(args, "brand", None):
        parser.error("--model requires --brand")
    min_price = getattr(args, "min_price", None)
    max_price = getattr(args, "max_price", None)
    if min_price is not None and max_price is not None and min_price > max_price:
        parser.error("--min-price cannot be greater than --max-price")
    pages = getattr(args, "pages", 1)
    if pages < 1 or pages > 5:
        parser.error("--pages must be between 1 and 5")


def _validate_reviews_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    limit = getattr(args, "limit", None)
    if limit is not None and limit < 1:
        parser.error("--limit must be at least 1")


def _validate_portal_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    portal = getattr(args, "portal", None)
    if portal is None:
        return
    marketplace = getattr(args, "marketplace", DEFAULT_MARKETPLACE)
    try:
        make_session_key(marketplace, portal)
    except ValueError as exc:
        parser.error(str(exc))


def _parse_marketplaces_csv(parser: argparse.ArgumentParser, value: str | None) -> list[str] | None:
    if value is None:
        return None
    marketplaces = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not marketplaces:
        parser.error("--marketplaces must include at least one marketplace code")
    for marketplace in marketplaces:
        try:
            get_marketplace(marketplace)
        except ValueError as exc:
            parser.error(str(exc))
    return marketplaces


def _validate_managed_session_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if (
        getattr(args, "user_data_dir", None)
        or getattr(args, "profile_directory", None)
        or getattr(args, "isolated", False)
    ):
        parser.error(
            "--user-data-dir, --profile-directory, and --isolated are no longer supported. "
            "Use managed sessions with `amazon-cli session login --marketplace <code> --portal retail`."
        )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    get_marketplace(getattr(args, "marketplace", DEFAULT_MARKETPLACE))
    if args.command in {"search", "similar"}:
        _validate_search_args(parser, args)
    if args.command == "reviews":
        _validate_reviews_args(parser, args)
        _validate_portal_args(parser, args)
        _validate_managed_session_args(parser, args)
    if args.command == "offers":
        _validate_portal_args(parser, args)
        args.marketplaces = _parse_marketplaces_csv(parser, args.marketplaces)
    if args.command == "address":
        _validate_portal_args(parser, args)
        args.marketplaces = _parse_marketplaces_csv(parser, args.marketplaces)
        try:
            get_marketplace(args.reference_marketplace)
        except ValueError as exc:
            parser.error(str(exc))
    if args.command == "session":
        _validate_portal_args(parser, args)
        _validate_managed_session_args(parser, args)

    service = build_service()
    try:
        if args.command == "search":
            mode = "exact" if args.brand and args.model else "plain"
            payload = service.search(
                args.base,
                args.marketplace,
                args.refresh_intent,
                mode,
                brand=args.brand,
                model=args.model,
                min_price=args.min_price,
                max_price=args.max_price,
                pages=args.pages,
            )
        elif args.command == "similar":
            payload = service.search(
                args.base,
                args.marketplace,
                args.refresh_intent,
                "similar",
                brand=args.brand,
                model=args.model,
                min_price=args.min_price,
                max_price=args.max_price,
                pages=args.pages,
            )
        elif args.command == "get":
            payload = service.get(args.identifier, args.marketplace)
        elif args.command == "reviews":
            payload = service.reviews(
                args.identifier,
                args.marketplace,
                args.limit,
                portal=args.portal,
                user_data_dir=args.user_data_dir,
                profile_directory=args.profile_directory,
                isolated=args.isolated,
            )
        elif args.command == "offers":
            payload = service.offers(
                args.identifier,
                args.marketplace,
                portal=args.portal,
                marketplaces=args.marketplaces,
                include_shipping=args.include_shipping,
                vat_mode=args.vat_mode,
            )
        elif args.command == "compare":
            payload = service.compare(args.identifiers, args.marketplace)
        elif args.command == "address":
            payload = service.address_inspect(
                portal=args.portal,
                marketplaces=args.marketplaces,
                reference_marketplace=args.reference_marketplace,
            )
        else:
            payload = service.bootstrap_session(
                args.marketplace,
                args.browser_executable,
                args.headless,
                args.url,
                portal=args.portal,
                user_data_dir=args.user_data_dir,
                profile_directory=args.profile_directory,
                isolated=args.isolated,
            )
    except (AmazonBlockedError, IntentResolutionError, BrowserSessionError, ValueError) as exc:
        marketplace = getattr(args, "marketplace", "de")
        portal = getattr(args, "portal", "retail")
        payload = {
            "error": str(exc),
            "hint": f"Run `amazon-cli session login --marketplace {marketplace} --portal {portal} --browser-executable <path>` to capture a managed Amazon session.",
        }
        output = render_text(payload) if getattr(args, "text", False) else render_json(payload)
        _write_output(output)
        return 2

    output = render_text(payload) if args.text else render_json(payload)
    _write_output(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
