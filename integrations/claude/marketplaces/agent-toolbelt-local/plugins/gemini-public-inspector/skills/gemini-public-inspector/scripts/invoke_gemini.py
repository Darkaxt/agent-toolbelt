import json
import sys
from pathlib import Path


def bootstrap_repo_src() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        src_dir = parent / "src"
        if (parent / "pyproject.toml").exists() and (src_dir / "agent_toolbelt").exists():
            if str(src_dir) not in sys.path:
                sys.path.insert(0, str(src_dir))
            return
    raise RuntimeError("Could not locate the repository src/agent_toolbelt directory.")


bootstrap_repo_src()

from agent_toolbelt import gemini  # noqa: E402


def main() -> int:
    parser = gemini.build_url_arg_parser()
    args = parser.parse_args()
    result = gemini.invoke_gemini_url(
        url=args.url,
        instruction=args.instruction,
        model=args.model,
        timeout_sec=args.timeout_sec,
    )
    if args.output == "text":
        print(result["response"])
    else:
        print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
