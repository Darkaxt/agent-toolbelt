from __future__ import annotations

import argparse
import json
import sys

from . import transfer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-toolbelt-adb-archive-transfer")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    devices = subparsers.add_parser("devices", help="List connected ADB endpoints and transfer capabilities.")
    devices.add_argument("--adb-path")

    plan = subparsers.add_parser("plan", help="Inventory files and write an endpoint-bound transfer manifest.")
    plan.add_argument("--source", required=True)
    plan.add_argument("--destination", required=True)
    plan.add_argument("--serial")
    plan.add_argument("--manifest")
    plan.add_argument("--temp-root")
    plan.add_argument("--adb-path")
    plan.add_argument("--seven-zip-path")
    plan.add_argument("--tiny-max-mib", type=int, default=64)
    plan.add_argument("--large-min-gib", type=int, default=1)
    plan.add_argument("--bundle-max-gib", type=int, default=4)

    apply = subparsers.add_parser("apply", help="Apply one reviewed transfer manifest.")
    apply.add_argument("--manifest", required=True)
    apply.add_argument("--confirm-transfer", action="store_true")
    apply.add_argument("--keep-manifest", action="store_true")

    cleanup = subparsers.add_parser("cleanup", help="Remove only manifest-owned transfer staging.")
    cleanup.add_argument("--manifest", required=True)
    cleanup.add_argument("--confirm-cleanup", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "devices":
            payload = transfer.devices_command(adb_path=args.adb_path)
        elif args.operation == "plan":
            payload = transfer.plan_transfer(
                source=args.source,
                destination=args.destination,
                serial=args.serial,
                manifest_path=args.manifest,
                temp_root=args.temp_root,
                adb_path=args.adb_path,
                seven_zip_path=args.seven_zip_path,
                tiny_max_bytes=args.tiny_max_mib * 1024 * 1024,
                large_min_bytes=args.large_min_gib * 1024**3,
                bundle_max_bytes=args.bundle_max_gib * 1024**3,
            )
        elif args.operation == "apply":
            payload = transfer.apply_transfer(
                args.manifest,
                confirm_transfer=args.confirm_transfer,
                keep_manifest=args.keep_manifest,
            )
        elif args.operation == "cleanup":
            payload = transfer.cleanup_transfer(
                args.manifest,
                confirm_cleanup=args.confirm_cleanup,
            )
        else:  # pragma: no cover - argparse owns operation validation
            raise ValueError(f"Unsupported operation: {args.operation}")
    except transfer.TransferError as exc:
        payload = transfer.failure_payload(args.operation, exc)
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
