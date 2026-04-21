import json
import sys

from . import whatsapp_wacli


def main(argv: list[str] | None = None) -> int:
    parser = whatsapp_wacli.build_parser()
    args = parser.parse_args(argv)
    result = whatsapp_wacli.invoke_client(
        operation_args=whatsapp_wacli.build_operation_args(args),
        timeout_sec=args.timeout_sec,
        client_home=args.client_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
