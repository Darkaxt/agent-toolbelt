from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import gate, usage, support
from .queue import queue_status


def main(argv=None):
    parser = argparse.ArgumentParser(description="FIFO Windows Gradle execution tickets and shared mutex supervisor")
    commands = parser.add_subparsers(dest="operation", required=True)
    status = commands.add_parser("status", help="Read-only activity inspection; not launch clearance")
    status.add_argument("--observe-home", action="append", default=[])
    inspect_support = commands.add_parser("support", help="Read one build's owner-support record")
    inspect_support.add_argument("--ticket", required=True)
    response = commands.add_parser("respond", help="Acknowledge a current support request; never releases the gate")
    response.add_argument("--ticket", required=True)
    response.add_argument("--request", required=True)
    response.add_argument("--decision", choices=["continue", "cancel"], required=True)
    response.add_argument("--reason", required=True)
    cancel = commands.add_parser("cancel", help="Request Ctrl+C for one current owned build, never force-kill")
    cancel.add_argument("--ticket", required=True)
    cancel.add_argument("--request", required=True)
    cancel.add_argument("--reason", required=True)
    register = commands.add_parser("register-project", help="Register a wrapper and optional rollback/offline reservations; no build or upgrade")
    register.add_argument("--project", type=Path, required=True)
    register.add_argument("--keep-version", action="append", default=None)
    register.add_argument("--clear-reservations", action="store_true")
    register.add_argument("--gradle-home", type=Path)
    unregister = commands.add_parser("unregister-project", help="Remove catalog reference only, not project files")
    unregister.add_argument("--project", type=Path, required=True)
    for name in ("inventory", "cleanup-plan"):
        command = commands.add_parser(name, help="Read-only known-project/version inventory" if name == "inventory" else "Reviewed cleanup candidates only; never deletes")
        command.add_argument("--project", type=Path, action="append", default=[])
        command.add_argument("--observe-home", type=Path, action="append", default=[])
    run = commands.add_parser("run", help="Queue in FIFO order, wait, inspect, and run under the shared mutex")
    run.add_argument("--project", required=True, type=Path)
    run.add_argument("--observe-home", action="append", default=[])
    run.add_argument("--log", type=Path)
    run.add_argument("--diagnostic-quiet-seconds", type=int, default=300,
                     help="Quiet interval for diagnostics/support only; never a build deadline")
    run.add_argument("--collect-all-failures", action="store_true",
                     help="Run the complete test suite instead of native fail-fast; failures still fail the build")
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
        elif args.operation == "support":
            result = {"ok": True, "operation": "support", "record": support.read(args.ticket)}
        elif args.operation == "respond":
            result = support.respond(args.ticket, args.request, args.decision, args.reason)
        elif args.operation == "cancel":
            result = support.respond(args.ticket, args.request, "cancel", args.reason)
        elif args.operation == "register-project":
            if args.clear_reservations and args.keep_version:
                raise ValueError("Choose --keep-version or --clear-reservations, not both")
            result = {"operation": args.operation, **usage.record_project(args.project,
                      keep_versions=[] if args.clear_reservations else args.keep_version, home=args.gradle_home)}
        elif args.operation == "unregister-project":
            result = {"operation": args.operation, **usage.unregister_project(args.project)}
        elif args.operation in ("inventory", "cleanup-plan"):
            function = usage.inventory if args.operation == "inventory" else usage.cleanup_plan
            result = function(projects=args.project, extra_homes=args.observe_home)
        else:
            arguments = args.gradle_arguments
            if arguments[:1] == ["--"]:
                arguments = arguments[1:]
            result = gate.run_build(args.project, arguments, extra_homes=args.observe_home, log_path=args.log,
                                    gradle_heap=args.gradle_heap_gb, kotlin_heap=args.kotlin_heap_gb,
                                    memory_reason=args.memory_reason, kotlin_strategy=args.kotlin_strategy,
                                    diagnostic_quiet_seconds=args.diagnostic_quiet_seconds,
                                    retire_daemons=args.retire_daemons, collect_all_failures=args.collect_all_failures)
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
