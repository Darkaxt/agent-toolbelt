import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_bootstrap  # noqa: E402


def main() -> int:
    target = runtime_bootstrap.resolve_execution_target(
        script_path=Path(__file__).resolve(),
        env=os.environ,
    )
    return runtime_bootstrap.execute_cli(target, sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
