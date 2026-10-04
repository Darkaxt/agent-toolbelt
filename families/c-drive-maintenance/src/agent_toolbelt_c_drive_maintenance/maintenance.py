from __future__ import annotations

import hashlib
import json
import ntpath
from pathlib import Path
import re
import shutil
import subprocess
import sys


class MaintenanceError(ValueError):
    pass


# These are routing anchors, not deletion patterns. Match directory rollups only.
ROUTES = (
    (r'\\\.gradle$', 'gradle', 'read-only inventory, migrate owners, recheck consumers; no build mutex for cleanup'),
    (r'\\\.android\\avd(?:\\[^\\]+\.avd)?$', 'emulator', 'inspect emulator ownership; native snapshot/AVD lifecycle'),
    (r'\\android\\sdk$', 'android-sdk', 'map project pins; sdkmanager uninstall exact unused packages'),
    (r'\\(?:\.codex|\.claude)\\(?:sessions|archived_sessions|projects|jobs|cache|tools|file-history)$',
     'agent-state', 'inspect active owners; context-transfer or helper-native lifecycle'),
    (r'\\tools\\transactional-cleanup$', 'helper-state', 'reconcile transactions; never unlink live state database'),
    (r'\\(?:\.codex-temp|\.claude\\worktrees)$', 'build-worktrees', 'inspect Git ownership; cleanup generated subtrees, not worktrees'),
    (r'\\(?:appdata\\local\\temp|windows\\temp)$', 'temp', 'select exact inactive generated children; transactional-cleanup'),
    (r'\\(?:\.nuget\\packages|nuget\\v3-cache|uv\\cache|go-build|pnpm|npm-cache|electron\\cache|ms-playwright|\.m2)$',
     'package-cache', 'inspect consumers and offline needs; supported package cache lifecycle'),
    (r'\\(?:scoop|\.cache|\.rustup|\.cargo|\.konan)$', 'toolchain-cache', 'separate persistent assets and consumers; package-native lifecycle'),
    (r'\\(?:nvidia corporation|nvidia gpu computing toolkit|nvidiaapp)$',
     'nvidia', 'distinguish downloads, shader caches, active driver and CUDA consumers'),
    (r'\\appdata\\local\\packages$', 'app-state', 'installed-app ownership; WSL supported move/compaction, not VHD deletion'),
    (r'\\(?:windows\\(?:winsxs|installer|system32\\driverstore)|programdata\\package cache)$',
     'system-managed', 'supported Windows servicing only; no generic file deletion'),
    (r'\\(?:dotnet|visual studio|reloaded-ii\\mods|taildns)$',
     'persistent', 'dependency, rollback or user-content lifecycle; preserve by default'),
)


def path_key(path):
    return ntpath.normpath(str(path).replace('/', '\\')).casefold()


def classify(path):
    key = path_key(path)
    for pattern, category, route in ROUTES:
        if re.search(pattern, key):
            return category, route
    return None


def read_inventory(lines, limit=20, volume='C:'):
    if not 1 <= limit <= 200:
        raise MaintenanceError('limit must be 1..200')
    drive = volume.rstrip('\\/').upper()
    if not re.fullmatch('[A-Z]:', drive):
        raise MaintenanceError('volume must be a local drive such as C:')
    valid = invalid = 0
    root_bytes = None
    anchors = {}
    checksum = hashlib.sha256()
    for line in lines:
        checksum.update(line.encode('utf-8'))
        try:
            path, size, count = line.rstrip('\r\n').lstrip('\ufeff').rsplit(',', 2)
            size, count = int(size), int(count)
            if path.upper() == drive:
                path += '\\'  # RidNacs writes its drive root as C:, not C:\.
            if (size < 0 or count < 0 or not ntpath.isabs(path)
                    or path.startswith(('\\\\', '//')) or ntpath.splitdrive(path)[0].upper() != drive):
                raise ValueError('invalid local directory row')
        except ValueError:
            invalid += 1
            continue
        valid += 1
        key = path_key(path)
        if key == drive.lower() + '\\':
            root_bytes = size
        route = classify(path)
        if route:
            if key in anchors and anchors[key]['bytes'] != size:
                raise MaintenanceError('Conflicting duplicate directory rollups: ' + path)
            anchors[key] = {'path': path, 'bytes': size, 'file_count': count,
                            'category': route[0], 'next_action': route[1],
                            'status': 'needs_live_evidence', 'deletion_authorized': False}
    # Parent-inclusive export rows cannot be added to their descendants.
    disjoint = []
    for key in sorted(anchors, key=lambda value: (value.count('\\'), value)):
        if not any(key == parent or key.startswith(parent + '\\') for parent, _ in disjoint):
            disjoint.append((key, anchors[key]))
    ranked = sorted((row for _, row in disjoint), key=lambda row: (-row['bytes'], path_key(row['path'])))
    return {'ok': True, 'operation': 'inventory', 'valid_rows': valid, 'invalid_rows': invalid,
            'export_digest': checksum.hexdigest(), 'export_root_bytes': root_bytes,
            'hotspots': ranked[:limit], 'omitted_hotspots': max(0, len(ranked) - limit),
            'ranked_inclusive_bytes': sum(row['bytes'] for row in ranked[:limit]),
            'deletion_authorized': False, 'coverage': 'known lifecycle anchors; not a full physical allocation audit',
            'warnings': ['Historical directory rollups: no age-based deletion authority or reclaimed-byte claim.']}


def inventory(csv_path, limit=20, volume='C:', target_free_gib=200):
    if target_free_gib <= 0:
        raise MaintenanceError('target-free-gib must be positive')
    with Path(csv_path).open(encoding='utf-8-sig', newline='') as stream:
        result = read_inventory(stream, limit, volume)
    result['source'] = str(Path(csv_path).resolve())
    result['target_free_gib'] = target_free_gib
    try:
        usage = shutil.disk_usage(volume.rstrip('\\/') + '\\')
        result['live_free_bytes'] = usage.free
        result['target_gap_bytes'] = max(0, int(target_free_gib * 1024**3) - usage.free)
    except OSError as error:
        result['live_free_bytes'] = None
        result['warnings'].append('Live free-space measurement unavailable: ' + str(error))
    return result


def check_cleanup_route(path):
    key = path_key(path)
    # Also check ancestors: a native-managed leaf remains native-managed.
    while key:
        route = classify(key)
        if route and route[0] not in {'temp', 'build-worktrees'}:
            raise MaintenanceError('Use the reviewed native/shared lifecycle, not generic cleanup: ' + str(path))
        parent = ntpath.dirname(key)
        if parent == key:
            break
        key = parent


def cleanup_wrapper():
    for agent in ('.codex', '.claude', '.agents'):
        wrapper = Path.home() / agent / 'skills/transactional-cleanup/scripts/invoke_transactional_cleanup.py'
        if wrapper.is_file():
            return wrapper
    raise MaintenanceError('Install transactional-cleanup first; no alternate deletion will be attempted')


def invoke_cleanup(arguments, state_root=None):
    command = [sys.executable, '-B', str(cleanup_wrapper())]
    if state_root:
        command += ['--state-root', str(state_root)]
    completed = subprocess.run(command + arguments, capture_output=True, text=True,
                               encoding='utf-8', errors='replace', shell=False)
    try:
        result = json.loads(completed.stdout)
        if not isinstance(result, dict) or not isinstance(result.get('ok'), bool):
            raise ValueError('missing structured ok')
    except (ValueError, TypeError) as error:
        raise MaintenanceError('Cleanup returned an invalid response; inspect its saved state, do not rerun blindly') from error
    result['helper_exit_code'] = completed.returncode
    if completed.returncode:
        result['ok'] = False
    if completed.stderr.strip():
        result['helper_stderr'] = completed.stderr[-4000:]
    return result


def prepare_cleanup(workspace, target, evidence, confirmed=False, state_root=None):
    if not confirmed or not evidence.strip():
        raise MaintenanceError('Explicit disposable-output authority and concrete provenance are required')
    check_cleanup_route(target)
    begin = invoke_cleanup(['begin', '--workspace', str(workspace), '--scan-root', str(target)], state_root)
    if not begin['ok']:
        return begin
    transaction = begin['transaction_id']
    for arguments in (
        ['register', '--transaction', transaction, '--path', str(target), '--kind', 'explicit-generated-output',
         '--evidence', evidence, '--regenerated'],
        ['review', '--transaction', transaction],
    ):
        try:
            result = invoke_cleanup(arguments, state_root)
        except (OSError, MaintenanceError) as error:
            return {'ok': False, 'operation': arguments[0], 'transaction_id': transaction,
                    'automatic_revocation': False, 'errors': [str(error)]}
        result.update(transaction_id=transaction, automatic_revocation=False)
        if not result['ok']:
            return result
    result.update(status='awaiting_manifest_review', next_action='Inspect the candidate manifest through transactional-cleanup before cleanup-apply')
    return result


def apply_cleanup(transaction, manifest_sha256, dry_run=False, state_root=None):
    if not re.fullmatch('[a-f0-9]{64}', manifest_sha256):
        raise MaintenanceError('Supply the exact manifest SHA256 from the inspected review')
    offset = 0
    while True:
        page = invoke_cleanup(['inspect', '--transaction', transaction, '--decision', 'candidate',
                               '--offset', str(offset), '--limit', '1000'], state_root)
        if not page['ok']:
            return page
        if 'page_items' not in page or 'next_offset' not in page:
            raise MaintenanceError('Missing manifest coverage; cannot authorize application')
        for item in page['page_items']:
            check_cleanup_route(item['path'])
        next_offset = page['next_offset']
        if next_offset is None:
            break
        if not isinstance(next_offset, int) or next_offset <= offset:
            raise MaintenanceError('Invalid manifest pagination; cannot authorize application')
        offset = next_offset
    # The cleanup helper authenticates this digest against its own saved manifest.
    ticket = invoke_cleanup(['ticket', '--transaction', transaction, '--manifest-sha256', manifest_sha256], state_root)
    if not ticket['ok']:
        return ticket
    arguments = ['apply', '--ticket', ticket['ticket_id']]
    if dry_run:
        arguments.append('--dry-run')
    try:
        result = invoke_cleanup(arguments, state_root)
    except (OSError, MaintenanceError) as error:
        result = {'ok': False, 'operation': 'apply', 'errors': [str(error)]}
    result.update(transaction_id=transaction, ticket_id=ticket['ticket_id'], automatic_revocation=False)
    return result


def owner_request(project, task_id, toolchain, current_version, target_version):
    project = Path(project).resolve(strict=True)
    if not project.is_dir() or not task_id.strip():
        raise MaintenanceError('An existing project directory and exact existing owner task ID are required')
    if toolchain not in {'gradle', 'android-sdk', 'ndk', 'cuda', 'jdk', 'package'}:
        raise MaintenanceError('Unsupported toolchain')
    if any(not re.fullmatch(r'[A-Za-z0-9._+:-]+', v) for v in (current_version, target_version)):
        raise MaintenanceError('Use explicit version identifiers, not commands or latest')
    if current_version == target_version or target_version.lower() == 'latest':
        raise MaintenanceError('A distinct explicit candidate version is required')
    prompt = (f'Bounded maintenance request for {project}: evaluate {toolchain} {current_version} -> '
              f'{target_version} as a common installed baseline, not a forced latest upgrade. '
              'Establish compatibility with this project and its plugins, runtime, native dependencies and CI. '
              'Preserve dirty work, signing identity, required JVM flags, wrapper checksums, offline and rollback needs. '
              'If compatible, migrate only this dependency, run the required focused verification, and commit the '
              'verified change. Use gradle-build-gate for every Windows Gradle command. Do not delete shared caches '
              'or release/deploy the app. Report exact before/after versions, verification evidence, commit, current '
              'references and remaining compatibility exceptions; update usage registrations/reservations. If incompatible, '
              'provide the exact incompatibility and retained-version requirement. Coordinate with the current stage; '
              'do not interrupt active work or claim completion from a proposed edit.')
    return {'ok': True, 'operation': 'request', 'task_id': task_id, 'project': str(project),
            'toolchain': toolchain, 'current_version': current_version, 'target_version': target_version,
            'sent': False, 'prompt': prompt, 'next_action': 'Verify owner, send once through the task API, then wait for evidence'}
