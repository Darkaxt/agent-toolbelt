from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import gate
from .queue import queue_status


def main(argv=None):
    parser = argparse.ArgumentParser(description="FIFO Windows Gradle execution tickets and shared mutex supervisor")
    commands = parser.add_subparsers(dest="operation", required=True)
    status = commands.add_parser("status", help="Read-only activity inspection; not launch clearance")
    status.add_argument("--observe-home", action="append", default=[])
    run = commands.add_parser("run", help="Queue in FIFO order, wait, inspect, and run under the shared mutex")
    run.add_argument("--project", required=True, type=Path)
    run.add_argument("--observe-home", action="append", default=[])
    run.add_argument("--log", type=Path)
    run.add_argument("--gradle-heap-gb", type=int, default=3)
    run.add_argument("--kotlin-heap-gb", type=int, default=3)
    run.add_argument("--memory-reason")
    run.add_argument("--kotlin-strategy", choices=["daemon", "in-process", "out-of-process"])
    run.add_argument("--retire-daemons", choices=["incompatible", "all-idle", "none"], default="incompatible",
                     help="Gracefully retire incompatible idle daemons before building (default: version/heap mismatch)")
    run.add_argument("gradle_arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.operation == "status":
            result = {"ok": True, "operation": "status", "gate_acquired": False,
                      "queue": queue_status(),
                      **gate.inspect_activity(gate.observation_homes(extra=args.observe_home))}
        else:
            arguments = args.gradle_arguments
            if arguments[:1] == ["--"]:
                arguments = arguments[1:]
            result = gate.run_build(args.project, arguments, extra_homes=args.observe_home, log_path=args.log,
                                    gradle_heap=args.gradle_heap_gb, kotlin_heap=args.kotlin_heap_gb,
                                    memory_reason=args.memory_reason, kotlin_strategy=args.kotlin_strategy,
                                    retire_daemons=args.retire_daemons)
        print(json.dumps(result, indent=2))
        return result.get("exit_code", 0)
    except (ValueError, OSError, RuntimeError) as exc:
        result = {"ok": False, "operation": args.operation,
                  "failure_kind": getattr(exc, "failure_kind", "gate_or_configuration_error"),
                  "error": str(exc), "safe_to_continue": False}
        if isinstance(exc, gate.RetirementFailure):
            result["retirement_diagnostics"] = exc.diagnostics
        print(json.dumps(result))
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "operation": args.operation, "failure_kind": "interrupted_before_launch",
                          "safe_to_continue": False}))
        return 130


def entrypoint():
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
