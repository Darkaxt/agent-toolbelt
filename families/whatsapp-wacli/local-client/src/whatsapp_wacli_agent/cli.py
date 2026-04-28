import json
import sys

from . import agent


def main(argv: list[str] | None = None) -> int:
    parser = agent.build_parser()
    args = parser.parse_args(argv)
    try:
        result = agent.run_cli(args)
    except ValueError as exc:
        result = agent.make_result(
            ok=False,
            operation=getattr(args, "operation", "unknown"),
            warnings=["invalid_request"],
            stderr=str(exc),
            exit_code=2,
        )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
