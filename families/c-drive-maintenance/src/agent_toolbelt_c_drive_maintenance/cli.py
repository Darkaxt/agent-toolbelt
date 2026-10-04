import argparse
import json

from . import maintenance


def parser():
    result = argparse.ArgumentParser(description='Active maintenance routing and reviewed cleanup; no background monitor.')
    result.add_argument('--cleanup-state-root', help='Optional isolated transactional-cleanup state, for testing')
    commands = result.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('inventory')
    scan.add_argument('--csv', required=True)
    scan.add_argument('--limit', type=int, default=20)
    scan.add_argument('--volume', default='C:')
    scan.add_argument('--target-free-gib', type=float, default=200)
    prepare = commands.add_parser('cleanup-prepare')
    prepare.add_argument('--workspace', required=True)
    prepare.add_argument('--target', required=True)
    prepare.add_argument('--evidence', required=True)
    prepare.add_argument('--confirm-disposable', action='store_true')
    apply = commands.add_parser('cleanup-apply')
    apply.add_argument('--transaction', required=True)
    apply.add_argument('--manifest-sha256', required=True)
    apply.add_argument('--dry-run', action='store_true')
    request = commands.add_parser('request')
    request.add_argument('--project', required=True)
    request.add_argument('--task-id', required=True)
    request.add_argument('--toolchain', required=True, choices=('gradle', 'android-sdk', 'ndk', 'cuda', 'jdk', 'package'))
    request.add_argument('--current-version', required=True)
    request.add_argument('--target-version', required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'inventory':
            result = maintenance.inventory(args.csv, args.limit, args.volume, args.target_free_gib)
        elif args.command == 'cleanup-prepare':
            result = maintenance.prepare_cleanup(args.workspace, args.target, args.evidence,
                                                 args.confirm_disposable, args.cleanup_state_root)
        elif args.command == 'cleanup-apply':
            result = maintenance.apply_cleanup(args.transaction, args.manifest_sha256,
                                               args.dry_run, args.cleanup_state_root)
        else:
            result = maintenance.owner_request(args.project, args.task_id, args.toolchain,
                                               args.current_version, args.target_version)
    except (OSError, ValueError, KeyError) as error:
        result = {'ok': False, 'operation': args.command, 'errors': [str(error)],
                  'failure_kind': 'maintenance_blocked', 'automatic_revocation': False}
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result['ok'] else 1


def entrypoint():
    raise SystemExit(main())


if __name__ == '__main__':
    entrypoint()
