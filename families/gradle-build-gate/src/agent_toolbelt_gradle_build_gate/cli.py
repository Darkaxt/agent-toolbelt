from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import gate, usage, support, tray
from .queue import queue_status


def main(argv=None):
    parser = argparse.ArgumentParser(description="FIFO Windows Gradle execution tickets and shared mutex supervisor")
    commands = parser.add_subparsers(dest="operation", required=True)
    owner = commands.add_parser('owner', help='Read this caller identity and live Claude session name only')
    owner.add_argument('--thread-name')
    watch = commands.add_parser('watch-support', help='Wait for one current support request or owner exit; diagnostic only')
    watch.add_argument('--ticket', required=True)
    watch.add_argument('--after-request', help='Do not emit this already observed request again')
    status = commands.add_parser("status", help="Read-only activity inspection; not launch clearance")
    status.add_argument("--observe-home", action="append", default=[])
    tray_command = commands.add_parser("tray", help="Read-only desktop task/queue/usage observer; never controls builds")
    tray_command.add_argument("action", choices=["start", "status", "stop"], nargs="?", default="status")
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
    run.add_argument("--owner-task", help="Current operation label for tray and desktop notification")
    run.add_argument("--thread-name", help="Actual Codex/Claude conversation title; omitted names display Unknown")
    run.add_argument("--no-notify", action="store_true", help="Disable optional desktop owner notification")
    run.add_argument("--no-tray", action="store_true", help="Disable optional tray telemetry and auto-start for this request")
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
    run.add_argument("--retire-daemons", choices=["incompatible", "all-idle", "none"], default="all-idle",
                     help="Pre-build graceful retirement policy (default: all confirmed-idle Gradle daemons)")
    run.add_argument('--keep-daemon', action='store_true',
                     help='Opt into reusable Gradle daemons; default is native single-use plus verified retirement')
    run.add_argument("gradle_arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'owner':
            from .caller import resolve
            result = {'ok': True, 'operation': 'owner', 'owner': resolve(args.thread_name)}
        elif args.operation == 'watch-support':
            result = support.wait_request(args.ticket, after_request=args.after_request)
        elif args.operation == "tray":
            result = {"ok": True, "operation": "tray." + args.action, **getattr(tray, args.action)()}
        elif args.operation == "status":
            result = {"ok": True, "operation": "status", "gate_acquired": False,
                      "queue": queue_status(),
                      **gate.inspect_activity(gate.observation_homes(extra=args.observe_home))}
        elif args.operation == "support":
            record = support.read(args.ticket)
            result = {"ok": True, "operation": "support", "request_status": support.request_status(record),
                      "record": record}
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
                                    owner_task=args.owner_task, thread_name=args.thread_name, notify=not args.no_notify,
                                    tray=not args.no_tray,
                                    retire_daemons=args.retire_daemons, collect_all_failures=args.collect_all_failures,
                                    keep_daemon=args.keep_daemon)
        print(json.dumps(result, indent=None if args.operation == 'watch-support' else 2), flush=True)
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
