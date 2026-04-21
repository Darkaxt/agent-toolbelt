import argparse
import json
import sys

from . import gemini


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gemini family CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    url_parser = subparsers.add_parser("url", help="Inspect a public URL with Gemini.")
    url_parser.add_argument("--url", required=True)
    url_parser.add_argument("--instruction", required=True)
    url_parser.add_argument("--model")
    url_parser.add_argument("--timeout-sec", type=int, default=180)
    url_parser.add_argument("--allow-env-credentials", action="store_true")
    url_parser.add_argument("--output", choices=("json", "text"), default="json")

    research_parser = subparsers.add_parser(
        "research",
        help="Run an independent Gemini research cross-check.",
    )
    research_parser.add_argument("--question", required=True)
    research_parser.add_argument("--model")
    research_parser.add_argument("--timeout-sec", type=int, default=180)
    research_parser.add_argument("--allow-env-credentials", action="store_true")
    research_parser.add_argument("--output", choices=("json", "text"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "url":
        result = gemini.invoke_gemini_url(
            url=args.url,
            instruction=args.instruction,
            model=args.model,
            timeout_sec=args.timeout_sec,
            allow_env_credentials=args.allow_env_credentials,
        )
    else:
        result = gemini.invoke_gemini_research(
            question=args.question,
            model=args.model,
            timeout_sec=args.timeout_sec,
            allow_env_credentials=args.allow_env_credentials,
        )

    if args.output == "text":
        print(result["response"])
    else:
        print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
