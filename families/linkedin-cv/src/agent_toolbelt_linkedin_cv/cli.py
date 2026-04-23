import json
import sys

from . import linkedin_cv


def main(argv: list[str] | None = None) -> int:
    parser = linkedin_cv.build_parser()
    args = parser.parse_args(argv)
    result = linkedin_cv.dispatch(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
