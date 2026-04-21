import json
import sys

from . import agent


def main(argv: list[str] | None = None) -> int:
    parser = agent.build_parser()
    args = parser.parse_args(argv)
    result = agent.run_cli(args)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
