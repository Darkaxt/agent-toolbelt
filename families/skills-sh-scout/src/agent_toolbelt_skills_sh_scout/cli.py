import json
import sys
from pathlib import Path

from . import scout


def main(argv: list[str] | None = None) -> int:
    parser = scout.build_arg_parser()
    args = parser.parse_args(argv)

    if args.operation != "scout":
        parser.error("unsupported operation")

    report = scout.build_scout_report(
        workflow=args.workflow,
        explicit_queries=args.query or [],
        compare_local_skill=args.compare_local_skill,
        max_candidates=args.max_candidates,
        max_inspect=args.max_inspect,
    )

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report.get("ok") else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))

