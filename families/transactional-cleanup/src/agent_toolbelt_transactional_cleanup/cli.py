from __future__ import annotations

import argparse
import json

from .engine import Engine, CleanupError, KINDS


def parser():
    result = argparse.ArgumentParser(description='Review generated files and apply exact snapshot cleanup tickets.')
    result.add_argument('--state-root', help='Explicit helper state directory')
    commands = result.add_subparsers(dest='command', required=True)
    begin = commands.add_parser('begin')
    begin.add_argument('--workspace', required=True)
    begin.add_argument('--scan-root', action='append', help='Scan only these roots when supplied; otherwise workspace and known temp roots')
    register = commands.add_parser('register')
    register.add_argument('--transaction', required=True)
    register.add_argument('--path', required=True)
    register.add_argument('--kind', choices=KINDS, required=True)
    register.add_argument('--evidence', required=True, help='Concrete generated-output provenance')
    register.add_argument('--regenerated', action='store_true', help='Explicitly identify a pre-existing disposable generated output')
    for name in ('review', 'status', 'ticket'):
        command = commands.add_parser(name)
        command.add_argument('--transaction', required=True)
        if name == 'ticket':
            command.add_argument('--manifest-sha256', required=True, help='Hash from the separately inspected review')
    apply = commands.add_parser('apply')
    apply.add_argument('--ticket', required=True)
    apply.add_argument('--dry-run', action='store_true')
    revoke = commands.add_parser('revoke')
    revoke.add_argument('--ticket', required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        engine = Engine(args.state_root)
        with engine.locked():
            if args.command == 'begin':
                result = engine.begin(args.workspace, args.scan_root)
            elif args.command == 'register':
                result = engine.register(args.transaction, args.path, args.kind, args.evidence, args.regenerated)
            elif args.command == 'ticket':
                result = engine.ticket(args.transaction, args.manifest_sha256)
            elif args.command == 'apply':
                result = engine.apply(args.ticket, args.dry_run)
            elif args.command == 'revoke':
                result = engine.revoke(args.ticket)
            else:
                result = getattr(engine, args.command)(args.transaction)
    except (CleanupError, OSError, ValueError, RuntimeError) as exc:
        result = {'ok': False, 'operation': args.command,
                  'failure_kind': getattr(exc, 'kind', type(exc).__name__),
                  'errors': [str(exc)], 'warnings': []}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['ok'] else 1


def entrypoint():
    raise SystemExit(main())


if __name__ == '__main__':
    entrypoint()
