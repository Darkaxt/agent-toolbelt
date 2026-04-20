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

from agent_toolbelt import everything  # noqa: E402


def main() -> int:
    parser = everything.build_arg_parser()
    args = parser.parse_args()
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


if __name__ == "__main__":
    raise SystemExit(main())
