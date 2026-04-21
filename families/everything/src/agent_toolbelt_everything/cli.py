import json
import sys

from . import everything


def main(argv: list[str] | None = None) -> int:
    parser = everything.build_arg_parser()
    args = parser.parse_args(argv)
    result = everything.lookup(
        query=args.query,
        mode=args.mode,
        root=args.root,
        max_results=args.max_results,
        match_path=args.match_path,
        es_path=args.es_path,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
