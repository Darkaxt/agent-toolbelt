from __future__ import annotations

import sys

from . import gardener


def main(argv: list[str] | None = None) -> int:
    parser = gardener.build_arg_parser()
    args = parser.parse_args(argv)

    if args.operation != "scan":
        parser.error("unsupported operation")

    result = gardener.run_scan(
        since_days=args.since_days,
        max_sessions=args.max_sessions,
        output_root=args.output_root,
        codex_home=args.codex_home,
        agents_home=args.agents_home,
        dry_run=args.dry_run,
        include_archived=args.include_archived,
        include_titles=args.include_titles,
    )
    print(result.console)
    return 0 if result.ok else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
