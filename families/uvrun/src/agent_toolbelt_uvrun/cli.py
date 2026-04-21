import json
import sys

from . import uvrun


def main(argv: list[str] | None = None) -> int:
    args = uvrun.parse_args(argv)
    result = uvrun.invoke_script(
        script=args.script,
        script_args=args.script_args,
        cwd=args.cwd,
        timeout_sec=args.timeout_sec,
        check_only=args.check,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
