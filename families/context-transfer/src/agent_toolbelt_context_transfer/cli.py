from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from . import archive, context_transfer, handoff


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
    inspect_parser.add_argument("--output")

    pack_parser = subparsers.add_parser(
        "pack",
        help="Build and verify a recovery archive from a reviewed inspection manifest.",
    )
    pack_parser.add_argument("--manifest", required=True)
    pack_parser.add_argument("--handoff", required=True)
    pack_parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    pack_parser.add_argument("--seven-zip-path")
    pack_parser.add_argument("--dictionary-mib", type=int)

    verify_parser = subparsers.add_parser(
        "verify",
        help="Re-test an existing recovery archive and its external evidence.",
    )
    verify_parser.add_argument("--archive", required=True)
    verify_parser.add_argument("--seven-zip-path")

    catalog_parser = subparsers.add_parser(
        "catalog",
        help="Stream a source tree into bounded excerpts and exact rollout offsets.",
    )
    catalog_parser.add_argument("--manifest", required=True)
    catalog_parser.add_argument("--max-entries-per-thread", type=int, default=12)
    catalog_parser.add_argument("--max-total-entries", type=int, default=1200)
    catalog_parser.add_argument("--excerpt-chars", type=int, default=600)
    catalog_parser.add_argument("--output")

    validate_handoff_parser = subparsers.add_parser(
        "validate-handoff",
        help="Validate CONTEXT_TRANSFER.md against the selected task tree.",
    )
    validate_handoff_parser.add_argument("--manifest", required=True)
    validate_handoff_parser.add_argument("--handoff", required=True)

    validate_acceptance_parser = subparsers.add_parser(
        "validate-acceptance",
        help="Validate destination acceptance and its handoff binding.",
    )
    validate_acceptance_parser.add_argument("--manifest", required=True)
    validate_acceptance_parser.add_argument("--handoff", required=True)
    validate_acceptance_parser.add_argument("--acceptance", required=True)
    return parser


def _failure(operation: str, error: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "operation": operation,
        "error": {
            "kind": getattr(error, "kind", "unexpected_error"),
            "message": str(error),
            "details": getattr(error, "details", {}),
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


def _write_explicit_output(payload: dict[str, Any], value: str | None) -> str | None:
    if not value:
        return None
    output = Path(value).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.partial")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, output)
    return str(output)


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
            output_path = _write_explicit_output(result, args.output)
        elif args.operation == "pack":
            result = archive.pack_recovery(
                inspection_manifest_path=args.manifest,
                handoff_path=args.handoff,
                archive_root=args.archive_root,
                seven_zip_path=args.seven_zip_path,
                dictionary_mib=args.dictionary_mib,
            )
            output_path = None
        elif args.operation == "verify":
            result = archive.verify_recovery_archive(
                args.archive,
                seven_zip_path=args.seven_zip_path,
            )
            output_path = None
        elif args.operation == "catalog":
            result = handoff.build_evidence_catalog(
                inspection_manifest_path=args.manifest,
                max_entries_per_thread=args.max_entries_per_thread,
                max_total_entries=args.max_total_entries,
                excerpt_chars=args.excerpt_chars,
            )
            output_path = _write_explicit_output(result, args.output)
        elif args.operation == "validate-handoff":
            result = handoff.validate_handoff(
                handoff_path=args.handoff,
                inspection_manifest_path=args.manifest,
            )
            output_path = None
        elif args.operation == "validate-acceptance":
            result = handoff.validate_destination_acceptance(
                acceptance_path=args.acceptance,
                handoff_path=args.handoff,
                inspection_manifest_path=args.manifest,
            )
            output_path = None
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
        if output_path:
            payload["output_path"] = output_path
    except (
        context_transfer.ContextTransferError,
        archive.ArchiveError,
        handoff.HandoffError,
    ) as exc:
        payload = _failure(args.operation, exc)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    entrypoint()
