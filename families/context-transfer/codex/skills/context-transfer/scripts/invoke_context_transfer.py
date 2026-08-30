from __future__ import annotations

from pathlib import Path
import sys


sys.dont_write_bytecode = True
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_bootstrap


if __name__ == "__main__":
    target = runtime_bootstrap.resolve_execution_target(script_path=Path(__file__))
    raise SystemExit(runtime_bootstrap.execute_cli(target, sys.argv[1:]))
