import json
import sys
from pathlib import Path


def bootstrap_core_src() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        pyproject = parent / "pyproject.toml"
        core_src = parent / "packages" / "core" / "src"
        if pyproject.exists() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            if str(core_src) not in sys.path:
                sys.path.insert(0, str(core_src))
            return
    raise RuntimeError("Could not locate the repository packages/core/src directory.")


bootstrap_core_src()

from agent_toolbelt_core.bootstrap import bootstrap_family_package  # noqa: E402

bootstrap_family_package(__file__, family_name="uvrun", package_dir_name="agent_toolbelt_uvrun")

from agent_toolbelt_uvrun import uvrun  # noqa: E402


def main() -> int:
    args = uvrun.parse_args()
    result = uvrun.invoke_script(
        script=args.script,
        script_args=args.script_args,
        cwd=args.cwd,
        timeout_sec=args.timeout_sec,
        check_only=args.check,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
