import json
import sys

from . import outlook_classic_mail


def main(argv: list[str] | None = None) -> int:
    parser = outlook_classic_mail.build_parser()
    args = parser.parse_args(argv)
    result = outlook_classic_mail.invoke_client(
        operation_args=outlook_classic_mail.build_operation_args(args),
        timeout_sec=args.timeout_sec,
        queue_timeout_sec=args.queue_timeout_sec,
        client_home=args.client_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
