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
    begin.add_argument('--scan-root', action='append', help='Scan only these roots when supplied; otherwise scan only the workspace')
    begin.add_argument('--include-known-temp-roots', action='store_true',
                       help='Explicitly add known Temp roots to the workspace inventory')
    register = commands.add_parser('register')
    register.add_argument('--transaction', required=True)
    register.add_argument('--path', required=True)
    register.add_argument('--kind', choices=KINDS, required=True)
    register.add_argument('--evidence', required=True, help='Concrete generated-output provenance')
    register.add_argument('--regenerated', action='store_true', help='Explicitly identify a pre-existing disposable generated output')
    register.add_argument('--allow-hardlinks', action='store_true',
                          help='Allow deletion of exact ticketed hard-link names; other links remain intact')
    register.add_argument('--allow-leaf-reparse', action='store_true',
                          help='Allow deletion of exact ticketed leaf symlinks/junctions without traversing targets')
    for name in ('review', 'ticket'):
        command = commands.add_parser(name)
        command.add_argument('--transaction', required=True)
        if name == 'ticket':
            command.add_argument('--manifest-sha256', required=True, help='Hash from the separately inspected review')
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--transaction', required=True)
    inspect.add_argument('--offset', type=int, default=0)
    inspect.add_argument('--limit', type=int, default=100)
    inspect.add_argument('--decision', choices=('candidate', 'excluded'))
    status = commands.add_parser('status')
    status.add_argument('--transaction', help='Omit to inspect the active or most recent transaction')
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
        if args.command == 'status':
            result = engine.status(args.transaction)
        else:
            transaction = getattr(args, 'transaction', None)
            if args.command == 'begin':
                roots = engine.begin_roots(args.workspace, args.scan_root, args.include_known_temp_roots)
            elif args.command == 'register':
                roots = [*engine.transaction_roots(args.transaction), args.path]
            elif args.command in {'apply', 'revoke'}:
                roots, transaction = engine.ticket_roots(args.ticket)
            else:
                roots = engine.transaction_roots(args.transaction)
            with engine.locked(roots, operation=args.command, transaction=transaction):
                if args.command == 'begin':
                    result = engine.begin(args.workspace, args.scan_root, args.include_known_temp_roots)
                elif args.command == 'register':
                    result = engine.register(args.transaction, args.path, args.kind, args.evidence,
                                             args.regenerated, args.allow_hardlinks, args.allow_leaf_reparse)
                elif args.command == 'review':
                    result = engine.review(args.transaction)
                elif args.command == 'ticket':
                    result = engine.ticket(args.transaction, args.manifest_sha256)
                elif args.command == 'apply':
                    result = engine.apply(args.ticket, args.dry_run)
                elif args.command == 'revoke':
                    result = engine.revoke(args.ticket)
                elif args.command == 'inspect':
                    result = engine.inspect(args.transaction, args.offset, args.limit, args.decision)
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
