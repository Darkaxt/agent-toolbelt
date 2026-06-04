from __future__ import annotations

import json
import sys

from . import aliexpress_cli


def main(argv: list[str] | None = None) -> int:
    parser = aliexpress_cli.build_parser()
    args = parser.parse_args(argv)
    result = aliexpress_cli.invoke_client(
        operation_args=aliexpress_cli.build_operation_args(args),
        timeout_sec=args.timeout_sec,
        client_home=args.client_home,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))

