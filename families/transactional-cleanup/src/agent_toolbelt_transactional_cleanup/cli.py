from __future__ import annotations

import argparse
import json
import re
import sqlite3
import os
from pathlib import Path
import subprocess
import sys

from .engine import Engine, CleanupError, KINDS
from . import android, streamlined


def parser():
    result = argparse.ArgumentParser(description='Review generated files and apply exact snapshot cleanup tickets.')
    result.add_argument('--state-root', help='Explicit helper state directory')
    commands = result.add_subparsers(dest='command', required=True)
    android.add_parsers(commands)
    prepare = commands.add_parser('prepare', help='Snapshot and review exact paths in one call (begin+register+review)')
    prepare.add_argument('--path', action='append', required=True, help='Exact generated folder or file; repeat for more')
    prepare.add_argument('--evidence', required=True, help='Concrete generated-output provenance')
    prepare.add_argument('--kind', choices=streamlined.SIMPLE_KINDS, default='temporary')
    prepare.add_argument('--workspace', help='Optional active workspace to protect')
    finish = commands.add_parser('finish', help='Ticket and delete the exact reviewed manifest from prepare')
    finish.add_argument('--transaction', required=True)
    finish.add_argument('--manifest-sha256', required=True)
    finish.add_argument('--dry-run', action='store_true')
    remove = commands.add_parser('remove', help='One call: prepare and delete task scratch below a Temp root')
    remove.add_argument('--path', action='append', required=True, help='Exact folder or file below D:/Temp, E:/Temp or TEMP')
    remove.add_argument('--evidence', required=True, help='What created it and why it is no longer needed')
    remove.add_argument('--kind', choices=streamlined.SIMPLE_KINDS, default='temporary')
    remove.add_argument('--dry-run', action='store_true')
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
    register.add_argument('--allow-disposable-repository', action='store_true',
                          help='Allow an exact reviewed standalone repository beneath a Temp root')
    register.add_argument('--retirement-evidence', help='External JSON ownership and independent recovery evidence')
    register.add_argument('--confirm-retire-repository', help='Explicitly confirm the exact obsolete checkout root')
    register.add_argument('--confirm-git-marker', help='Confirm one generated .git/<namespace>-workflow-tree file')
    register.add_argument('--dependency-evidence', help='External JSON CMake provenance, patch and consumer evidence')
    register.add_argument('--confirm-dependency-repository', help='Confirm one exact generated CMake dependency clone')
    for name in ('review', 'ticket'):
        command = commands.add_parser(name)
        command.add_argument('--transaction', required=True)
        if name == 'ticket':
            command.add_argument('--manifest-sha256', required=True, help='Hash from the separately inspected review')
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--transaction', required=True)
    inspect.add_argument('--offset', type=int, default=0)
    inspect.add_argument('--limit', type=int, default=1000)
    inspect.add_argument('--decision', choices=('candidate', 'excluded'))
    status = commands.add_parser('status')
    status.add_argument('--transaction', help='Omit to inspect the active or most recent transaction')
    apply = commands.add_parser('apply')
    apply.add_argument('--ticket', required=True)
    apply.add_argument('--dry-run', action='store_true')
    revoke = commands.add_parser('revoke')
    revoke.add_argument('--ticket', required=True)
    discard = commands.add_parser('discard', help='Compact an explicitly abandoned unissued snapshot; delete no target files')
    discard.add_argument('--transaction', required=True)
    discard.add_argument('--reason', required=True)
    commands.add_parser('state-inventory', help='Report retained state and live root claims without scanning targets')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        engine = Engine(args.state_root)
        from . import retention
        trimmed = retention.maintain(engine)
        identifier = getattr(args, 'transaction', None) or getattr(args, 'ticket', None)
        if identifier and re.fullmatch('[a-f0-9]{32}|[a-f0-9]{64}', identifier):
            legacy_path = engine.root / (identifier + '.json')
            if legacy_path.is_file() and args.command != 'discard':
                record = retention.authenticated(legacy_path, engine)
                retention.require_current(record)
                active = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'Tools/transactional-cleanup/active.json'
                source = Path(json.loads(active.read_text())['legacy_source'])
                if source.parent.parent != active.parent / 'releases':
                    raise CleanupError('runtime_unavailable', 'Legacy source is outside the owned release directory')
                process = subprocess.run([sys.executable, '-B', '-m', 'agent_toolbelt_transactional_cleanup.cli',
                                          *(sys.argv[1:] if argv is None else argv)],
                                         env={**os.environ, 'PYTHONPATH': str(source), 'PYTHONDONTWRITEBYTECODE': '1'})
                return process.returncode
        if args.command.startswith('adb-'):
            result = android.dispatch(args)
            result['retention'] = trimmed
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0 if result['ok'] else 1
        if args.command == 'status':
            result = engine.status(args.transaction)
        elif args.command == 'state-inventory':
            result = engine.state_inventory()
            result['android'] = android.AndroidCleanup(host_engine=engine).state_inventory()
            result['state_bytes'] += result['android']['state_bytes']
        elif args.command == 'prepare':
            result = streamlined.prepare(engine, args.path, args.evidence, args.kind, args.workspace)
        elif args.command == 'finish':
            result = streamlined.finish(engine, args.transaction, args.manifest_sha256, args.dry_run)
        elif args.command == 'remove':
            result = streamlined.remove(engine, args.path, args.evidence, args.kind, args.dry_run)
        elif args.command == 'discard' and engine.legacy_path(args.transaction).is_file():
            result = engine.discard_legacy(args.transaction, args.reason)
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
                if transaction and args.command not in {'inspect', 'discard', 'revoke'}:
                    row = engine.txn(transaction)
                    retention.require_current(row)
                if args.command == 'begin':
                    result = engine.begin(args.workspace, args.scan_root, args.include_known_temp_roots)
                elif args.command == 'register':
                    result = engine.register(args.transaction, args.path, args.kind, args.evidence,
                                             args.regenerated, args.allow_hardlinks, args.allow_leaf_reparse,
                                             args.allow_disposable_repository, args.retirement_evidence,
                                             args.confirm_retire_repository, args.confirm_git_marker,
                                             args.dependency_evidence, args.confirm_dependency_repository)
                elif args.command == 'review':
                    result = engine.review(args.transaction)
                    result['next'] = (f"inspect --transaction {args.transaction}, then ticket --transaction "
                                      f"{args.transaction} --manifest-sha256 {result['manifest_sha256']}")
                elif args.command == 'ticket':
                    result = engine.ticket(args.transaction, args.manifest_sha256)
                    result['next'] = f"apply --ticket {result['ticket_id']}"
                elif args.command == 'apply':
                    result = engine.apply(args.ticket, args.dry_run)
                elif args.command == 'revoke':
                    result = engine.revoke(args.ticket)
                elif args.command == 'discard':
                    result = engine.discard(args.transaction, args.reason)
                elif args.command == 'inspect':
                    result = engine.inspect(args.transaction, args.offset, args.limit, args.decision)
        result['retention'] = trimmed
    except sqlite3.Error as exc:
        code = getattr(exc, 'sqlite_errorcode', None)
        busy = code is not None and (code & 0xFF) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
        result = {'ok': False, 'operation': args.command,
                  'failure_kind': 'state_database_busy' if busy else 'state_database_error',
                  'sqlite_error_code': code, 'sqlite_error_name': getattr(exc, 'sqlite_errorname', None),
                  'automatic_revocation': False, 'retry_after_diagnosis': busy,
                  'errors': ['Helper state database operation failed; inspect saved status before retrying the same valid ticket. No automatic revocation or alternate deletion was performed.'],
                  'warnings': (['Apply may have removed some exact ticket members before the database failure; committed byte counts are not proof of every filesystem change.']
                               if args.command == 'apply' else [])}
    except (CleanupError, OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError) as exc:
        result = {'ok': False, 'operation': args.command,
                  'failure_kind': getattr(exc, 'kind', type(exc).__name__),
                  'errors': [str(exc)], 'warnings': []}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['ok'] else 1


def entrypoint():
    raise SystemExit(main())


if __name__ == '__main__':
    entrypoint()
