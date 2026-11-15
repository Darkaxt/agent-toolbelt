from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .device import Device, SafError, parse_devices, resolve_adb, run_process
from .saf import Saf, apply_plan, make_plan, parse_target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adb-saf", description="Documents-provider (SAF) access over ADB.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="operation", required=True)

    def bound(name: str, help_text: str) -> argparse.ArgumentParser:
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--serial")
        command.add_argument("--adb")
        return command

    devices = sub.add_parser("devices", help="List ADB endpoints.")
    devices.add_argument("--adb")
    providers = bound("providers", "List documents providers and whether this ADB user can read them.")
    providers.add_argument("--no-probe", action="store_true")
    roots = bound("roots", "List a provider's roots.")
    roots.add_argument("authority")
    for name, help_text in (("ls", "List a directory document's children."), ("stat", "Show one document."),
                            ("sha256", "Hash one document on the device.")):
        command = bound(name, help_text)
        command.add_argument("target", help="AUTHORITY:DOCUMENT_ID")
        command.add_argument("--path", help="Child path below the target, by display names")
    pull = bound("pull", "Copy one document to an absent host file, verified by hash.")
    pull.add_argument("target")
    pull.add_argument("--path")
    pull.add_argument("--output", required=True)

    plan = bound("plan", "Record a reviewed change without performing it.")
    plan.add_argument("action", choices=["put", "mkdir", "rename", "delete"])
    plan.add_argument("--manifest", required=True, help="Absent JSON path in a task-owned folder")
    plan.add_argument("--target", help="AUTHORITY:DOCUMENT_ID of the existing document")
    plan.add_argument("--parent", help="AUTHORITY:DOCUMENT_ID of the directory")
    plan.add_argument("--name", help="New document name")
    plan.add_argument("--source", help="Host file for put")
    plan.add_argument("--mime-type")
    apply = bound("apply", "Apply one reviewed plan after re-verifying it.")
    apply.add_argument("--manifest", required=True)
    apply.add_argument("--confirm", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict:
    if args.operation == "devices":
        adb = resolve_adb(args.adb)
        return {"devices": parse_devices(run_process([adb, "devices", "-l"]).text)}
    saf = Saf(Device.bind(serial=args.serial, adb=args.adb))
    if args.operation == "providers":
        return {"device": saf.device.identity(), "providers": saf.providers(probe=not args.no_probe)}
    if args.operation == "roots":
        return {"authority": args.authority, "roots": saf.roots(args.authority)}
    if args.operation in ("ls", "stat", "sha256", "pull"):
        authority, document_id = parse_target(args.target)
        document_id = saf.resolve_path(authority, document_id, args.path)
        if args.operation == "ls":
            return {"authority": authority, "document_id": document_id,
                    "children": saf.children(authority, document_id)}
        if args.operation == "stat":
            return {"authority": authority, "document": saf.stat(authority, document_id)}
        if args.operation == "sha256":
            return {"authority": authority, "document_id": document_id, "sha256": saf.sha256(authority, document_id)}
        return saf.pull(authority, document_id, Path(args.output))
    if args.operation == "plan":
        return make_plan(saf, action=args.action, manifest=Path(args.manifest), target=args.target,
                         parent=args.parent, name=args.name, source=Path(args.source) if args.source else None,
                         mime_type=args.mime_type)
    if args.operation == "apply":
        return apply_plan(saf, Path(args.manifest), confirm=args.confirm)
    raise SafError("invalid_operation", args.operation)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = {"ok": True, "operation": args.operation, **run(args)}
    except SafError as error:
        payload = {"ok": False, "operation": args.operation, "failure_kind": error.kind,
                   "error": str(error), "details": error.details}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
