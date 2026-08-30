from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from . import context_transfer


DEFAULT_ARCHIVE_ROOT = Path(r"E:\Codex\ThreadArchives")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-toolbelt-context-transfer",
        description="Inspect and safely retire oversized Codex task trees.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Read-only inventory of a source task and all descendant agents.",
    )
    inspect_parser.add_argument("--source-thread-id", required=True)
    inspect_parser.add_argument("--destination-thread-id")
    inspect_parser.add_argument("--codex-home")
    inspect_parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    return parser


def _failure(operation: str, error: context_transfer.ContextTransferError) -> dict[str, Any]:
    return {
        "ok": False,
        "operation": operation,
        "error": {
            "kind": error.kind,
            "message": str(error),
            "details": error.details,
        },
    }


def _destination_thread_id(explicit: str | None) -> str:
    destination = (explicit or os.environ.get("CODEX_THREAD_ID") or "").strip()
    if not destination:
        raise context_transfer.ContextTransferError(
            "destination_thread_required",
            "Pass --destination-thread-id or run from a Codex task with CODEX_THREAD_ID set.",
        )
    return destination


def _codex_home(explicit: str | None) -> Path:
    return Path(explicit or os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "inspect":
            result = context_transfer.inventory_thread_tree(
                source_thread_id=args.source_thread_id,
                destination_thread_id=_destination_thread_id(args.destination_thread_id),
                codex_home=_codex_home(args.codex_home),
                archive_root=args.archive_root,
            )
        else:  # pragma: no cover - argparse owns command validation
            raise context_transfer.ContextTransferError(
                "unsupported_operation",
                f"Unsupported operation: {args.operation}",
            )
        payload: dict[str, Any] = {
            "ok": True,
            "operation": args.operation,
            "result": result,
        }
    except context_transfer.ContextTransferError as exc:
        payload = _failure(args.operation, exc)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    entrypoint()
