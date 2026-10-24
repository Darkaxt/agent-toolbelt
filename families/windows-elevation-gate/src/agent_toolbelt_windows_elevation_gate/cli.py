"""JSON interface; the worker subcommand is exclusively native-UAC launched."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_toolbelt_windows_elevation_gate import engine
from agent_toolbelt_windows_elevation_gate import broker
from agent_toolbelt_windows_elevation_gate.queue import Queue


def parser():
    result = argparse.ArgumentParser(description="Queue explained Windows administrator requests.")
    commands = result.add_subparsers(dest="operation", required=True)
    for name in ("run", "preview"):
        command = commands.add_parser(name)
        for flag in ("owner-task", "thread-name", "reason", "changes", "cwd"):
            command.add_argument("--" + flag, required=True)
        command.add_argument("--target", action="append", required=True)
        command.add_argument("--bind-file", action="append", default=[])
        command.add_argument("command", nargs=argparse.REMAINDER)
        if name == "preview":
            command.add_argument("--show-dialog", action="store_true",
                                 help="Show a non-elevating visual preview; no queue or UAC request")
        else:
            command.add_argument("--one-shot", action="store_true", help="Deprecated compatibility flag; run always uses the persistent broker, never per-action UAC")
    commands.add_parser("status")
    commands.add_parser("one-shot-status", help="Inspect the legacy per-action UAC queue")
    for name in ("broker-start", "broker-status", "broker-stop"):
        commands.add_parser(name)
    finalization = commands.add_parser("finalize")
    finalization.add_argument("--request-id", required=True)
    recovery = commands.add_parser("recover")
    recovery.add_argument("--request-id", required=True)
    recovery.add_argument("--confirm-old-prompt-settled", action="store_true", required=True)
    worker = commands.add_parser("worker", help="Internal native-UAC worker; not a user entry point")
    worker.add_argument("--request", required=True)
    worker.add_argument("--sha256", required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.operation == "worker":
        return engine.worker(args.request, args.sha256)
    try:
        if args.operation in ("status", "broker-status"):
            result = broker.status()
        elif args.operation == "one-shot-status":
            result = Queue().status()
        elif args.operation == "broker-start":
            result = broker.start()
        elif args.operation == "broker-stop":
            result = broker.stop()
        elif args.operation == "recover":
            result = Queue().recover(args.request_id, args.confirm_old_prompt_settled)
        elif args.operation == "finalize":
            result = engine.finalize(args.request_id)
        else:
            request = engine.prepare(args.command, cwd=args.cwd, task=args.owner_task,
                                     thread_name=args.thread_name, reason=args.reason,
                                     changes=args.changes, targets=args.target, bind_files=args.bind_file)
            result = ({"ok": True, "operation": "preview", "request": request, "launched": False}
                      if args.operation == "preview" else broker.run(request))
            if args.operation == "preview" and args.show_dialog:
                result["dialog"] = broker.preview(request)
    except broker.CompletionUnknown as exc:
        result = {"ok": False, "operation": args.operation, "failure_kind": "completion_unverified", "error": str(exc), "receipt": exc.receipt}
    except broker.BrokerUnavailable as exc:
        result = {"ok": False, "operation": args.operation, "failure_kind": "broker_unavailable", "error": str(exc), "launched": False}
    except broker.BrokerStopping as exc:
        result = {"ok": False, "operation": args.operation, "failure_kind": "broker_stopping", "error": str(exc), "launched": False}
    except (OSError, ValueError, RuntimeError, EOFError) as exc:
        result = {"ok": False, "operation": args.operation, "failure_kind": "request_failed", "error": str(exc)}
    if args.operation == "run" and args.one_shot:
        result["routing_notice"] = {"deprecated_flag": "--one-shot", "route": "persistent_broker",
                                    "message": "Public run always uses broker approval. Native-UAC bootstrap is reserved for the fixed protected-component installer."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 3 if result.get("failure_kind") == "user_declined" else 1


def entrypoint():
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
