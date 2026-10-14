"""Device-bound cleanup of reviewed task files and helper-baselined test apps."""
from __future__ import annotations

from collections import Counter
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import shutil
import subprocess

from .engine import CleanupError, Engine, digest, encoded, host, now
from . import filesystem as fs

MAX_MEMBERS = 10000
PROTECTED = {'android', 'dcim', 'download', 'downloads', 'documents', 'pictures',
             'movies', 'music', 'alarms', 'notifications', 'ringtones', 'podcasts',
             'rom', 'roms', 'saves', 'backups', 'games'}
ID = re.compile(r'^[0-9a-f]{32}$')
PACKAGE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$')


def safe_path(path, *, root=False):
    path = str(path)
    parts = path.split('/')
    if (not path.startswith('/storage/emulated/0/') or any(ord(c) < 32 or ord(c) == 127 for c in path)
            or any(p in {'', '.', '..'} for p in parts[1:])
            or parts[4].casefold() in PROTECTED or (root and len(parts) != 5)):
        raise CleanupError('protected_android_path', 'Use one exact task-owned directory under /storage/emulated/0; no user-data roots or traversal')
    return path


def ancestry_script(path):
    # Inspect each component, not just the leaf. /storage itself must not redirect.
    paths = list(reversed(PurePosixPath(path).parents)) + [PurePosixPath(path)]
    return '\n'.join(f'[ ! -L {shlex.quote(str(p))} ] || exit 42' for p in paths)


def snapshot_script(path):
    p = shlex.quote(path)
    return f'''set -eu
{ancestry_script(path)}
[ -e {p} ] || exit 44
if [ -d {p} ]; then
  stat -c '%d:%i:%f' {p}
  printf 'directory\\n'
elif [ -f {p} ]; then
  before=$(stat -c '%d:%i:%f:%s:%Y:%Z' {p})
  hash=$(sha256sum {p})
  after=$(stat -c '%d:%i:%f:%s:%Y:%Z' {p})
  [ "$before" = "$after" ] || exit 45
  printf '%s\\nfile\\n%s\\n' "$before" "${{hash%% *}}"
else
  exit 42
fi
'''


def removal_script(item, dry_run=False):
    path = item['path']
    p = shlex.quote(path)
    check = ancestry_script(path)
    identity = shlex.quote(item['identity'])
    if item['directory']:
        operation = "printf 'would_delete\\n'" if dry_run else f"rmdir {p} && printf 'deleted\\n'"
        return f'''set -eu
{check}
[ -e {p} ] || {{ printf 'missing\\n'; exit 0; }}
[ -d {p} ] && [ "$(stat -c '%d:%i:%f' {p})" = {identity} ] || {{ printf 'changed_after_review\\n'; exit 0; }}
contents=$(find {p} -mindepth 1 -maxdepth 1 -print -quit)
[ -z "$contents" ] || {{ printf 'not_empty\\n'; exit 0; }}
{operation}
'''
    sha = shlex.quote(item['sha256'])
    operation = "printf 'would_delete\\n'" if dry_run else f'''rm {p}
[ ! -e {p} ] && [ ! -L {p} ] || exit 46
printf 'deleted\\n' '''
    return f'''set -eu
{check}
[ -e {p} ] || {{ printf 'missing\\n'; exit 0; }}
[ -f {p} ] && [ "$(stat -c '%d:%i:%f:%s:%Y:%Z' {p})" = {identity} ] || {{ printf 'changed_after_review\\n'; exit 0; }}
hash=$(sha256sum {p})
[ "${{hash%% *}}" = {sha} ] && [ "$(stat -c '%d:%i:%f:%s:%Y:%Z' {p})" = {identity} ] || {{ printf 'changed_after_review\\n'; exit 0; }}
{check}
{operation}
'''


class AdbDevice:
    def __init__(self, serial, adb_path=None, runner=subprocess.run):
        if not serial or serial.startswith('-') or any(c.isspace() for c in serial):
            raise CleanupError('explicit_device_required', 'Pass the exact authorized --serial')
        candidates = [adb_path, os.getenv('ADB_PATH'), os.getenv('ANDROID_ADB')]
        candidates += [str(Path(os.environ[v]) / 'platform-tools/adb.exe')
                       for v in ('ANDROID_HOME', 'ANDROID_SDK_ROOT') if os.getenv(v)]
        candidates += [str(Path(os.getenv('LOCALAPPDATA', '')) / 'Android/Sdk/platform-tools/adb.exe'),
                       shutil.which('adb.exe') or shutil.which('adb')]
        self.adb = next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()), None)
        if not self.adb:
            raise CleanupError('adb_unavailable', 'ADB not found; provide --adb-path or an Android SDK')
        self.serial, self.runner = serial, runner
        self.last_error = None

    def command(self, *arguments, script=None, allow_failure=False):
        result = self.runner([self.adb, '-s', self.serial, *arguments],
                             input=None if script is None else script.encode('utf-8'), capture_output=True)
        if result.returncode and not allow_failure:
            detail = result.stderr.decode('utf-8', errors='replace').strip()[:1000]
            raise CleanupError('adb_failed', f'ADB operation failed (exit {result.returncode}): {detail}')
        return result

    def shell(self, script, *, allow_failure=False):
        return self.command('shell', '-T', 'sh', script=script, allow_failure=allow_failure)

    def endpoint(self):
        if self.command('get-state').stdout.strip() != b'device':
            raise CleanupError('device_not_ready', 'Selected endpoint is not ready')
        output = self.shell('getprop\n').stdout.decode('utf-8', errors='strict')
        props = dict(re.findall(r'^\[([^]]+)\]:\s*\[(.*)\]$', output, re.M))
        identity = {'serial': self.serial, 'android_serial': props.get('ro.serialno') or props.get('ro.boot.serialno'),
                    'fingerprint': props.get('ro.build.fingerprint'), 'model': props.get('ro.product.model')}
        if not all(identity.values()):
            raise CleanupError('device_identity_unavailable', 'Hardware serial, build fingerprint and model are required')
        return identity

    def snapshot(self, path):
        if (not path.startswith('/') or any(part in {'', '.', '..'} for part in path.split('/')[1:])
                or any(ord(c) < 32 or ord(c) == 127 for c in path)):
            raise CleanupError('unsafe_android_member', 'Invalid absolute member path')
        result = self.shell(snapshot_script(path), allow_failure=True)
        if result.returncode == 44:
            return None
        if result.returncode:
            raise CleanupError('unsafe_android_member', f'Cannot safely snapshot {path} (exit {result.returncode})')
        fields = result.stdout.decode('utf-8', errors='strict').splitlines()
        if len(fields) == 2 and fields[1] == 'directory' and re.fullmatch(r'\d+:\d+:[0-9a-f]+', fields[0]):
            return {'path': path, 'directory': True, 'identity': fields[0]}
        if (len(fields) == 3 and fields[1] == 'file' and re.fullmatch(r'[0-9a-f]{64}', fields[2])
                and re.fullmatch(r'\d+:\d+:[0-9a-f]+:\d+:\d+:\d+', fields[0])):
            return {'path': path, 'directory': False, 'identity': fields[0],
                    'size': int(fields[0].split(':')[3]), 'sha256': fields[2]}
        raise CleanupError('invalid_adb_response', f'Unsupported stat/hash output for {path}')

    def inventory(self, root):
        head = self.snapshot(root)
        if not head or not head['directory']:
            raise CleanupError('invalid_android_root', 'Task root must be an existing ordinary directory')
        output = self.shell(f'set -eu\n{ancestry_script(root)}\nfind {shlex.quote(root)} -print0\n').stdout
        paths = output.decode('utf-8', errors='strict').split('\0')
        if paths[-1] != '' or len(paths) > MAX_MEMBERS + 1 or len(set(paths[:-1])) != len(paths) - 1:
            raise CleanupError('invalid_inventory', 'Malformed, duplicate or oversized inventory; narrow the task directory')
        records = []
        for path in paths[:-1]:
            safe_path(path)
            if path != root and not path.startswith(root + '/'):
                raise CleanupError('invalid_inventory', 'Device returned a member outside the task root')
            item = self.snapshot(path)
            if item:
                records.append(item)
        if self.snapshot(root) != head:
            raise CleanupError('android_root_changed', 'Task directory changed identity during inventory')
        return records

    def remove(self, item, dry_run):
        result = self.shell(removal_script(item, dry_run), allow_failure=True)
        if result.returncode == 42:
            return 'linked_or_changed_ancestor'
        if result.returncode:
            self.last_error = {'failure_kind': 'adb_member_failed', 'exit_code': result.returncode,
                               'message': result.stderr.decode('utf-8', errors='replace').strip()[:1000]}
            return 'failed'
        status = result.stdout.decode('utf-8', errors='strict').strip()
        if status not in {'deleted', 'would_delete', 'missing', 'not_empty', 'changed_after_review'}:
            raise CleanupError('invalid_adb_response', 'Unrecognized exact-member deletion result')
        if dry_run and item['directory'] and status == 'not_empty':
            return 'would_remove_if_empty'
        return status

    def package(self, package):
        if not PACKAGE.fullmatch(package):
            raise CleanupError('invalid_package', 'Use one exact Android package identifier')
        users_text = self.shell('pm list users\n').stdout.decode('utf-8', errors='strict')
        users = re.findall(r'UserInfo\{(\d+):', users_text)
        if not users or len(users) != len(set(users)):
            raise CleanupError('package_identity_unavailable', 'Could not enumerate Android users')
        retained = []
        for user in users:
            response = self.shell(f'pm list packages -u --user {user}\n')
            if response.stderr.strip():
                raise CleanupError('package_identity_unavailable', 'Package enumeration emitted diagnostics; absence is unproven')
            output = response.stdout.decode('utf-8', errors='strict')
            lines = output.splitlines()
            if any(line and not re.fullmatch(r'package:[A-Za-z0-9_.]+', line) for line in lines):
                raise CleanupError('package_identity_unavailable', 'Package enumeration returned an error or unsupported output')
            if 'package:' + package in lines:
                retained.append(user)
        if not retained:
            return None
        if retained != ['0']:
            raise CleanupError('preexisting_or_shared_package', 'Only a test app belonging exclusively to Android user 0 is eligible')
        p = shlex.quote(package)
        data = self.shell(f'dumpsys package {p}\n').stdout.decode('utf-8', errors='strict')
        fields = re.findall(r'^\s*((?:codePath|versionCode|firstInstallTime|lastUpdateTime|userId|pkgFlags)=.*)$', data, re.M)
        if any('SYSTEM' in f for f in fields) or not all(any(f.startswith(k + '=') for f in fields)
                                                        for k in ('codePath', 'versionCode', 'firstInstallTime', 'lastUpdateTime', 'userId')):
            raise CleanupError('package_identity_unavailable', 'System app or incomplete package install identity')
        paths = self.shell(f'pm path --user 0 {p}\n').stdout.decode('utf-8', errors='strict').splitlines()
        if not paths or any(not line.startswith('package:/data/app/') for line in paths):
            raise CleanupError('protected_package', 'Only ordinary installed test APKs under /data/app are eligible')
        apks = []
        for line in paths:
            path = line.removeprefix('package:')
            item = self.snapshot(path)
            if not item or item['directory']:
                raise CleanupError('package_identity_unavailable', 'Installed APK unavailable')
            apks.append(item)
        return {'package': package, 'user': 0, 'install_identity': sorted(fields),
                'apk_hashes': sorted(apks, key=lambda item: item['path'])}

    def uninstall(self, package):
        output = self.shell(f'pm uninstall --user 0 {shlex.quote(package)}\n').stdout.strip()
        if output != b'Success':
            raise CleanupError('package_uninstall_failed', output.decode('utf-8', errors='replace')[:1000])
        listing = self.shell('pm list packages --user 0\n').stdout.decode('utf-8', errors='strict').splitlines()
        if any(line and not re.fullmatch(r'package:[A-Za-z0-9_.]+', line) for line in listing) or 'package:' + package in listing:
            raise CleanupError('package_uninstall_unverified', 'Package removal was not verified for Android user 0')


class AndroidCleanup:
    def __init__(self, state=None, *, device=None, serial=None, adb_path=None, host_engine=None):
        self.host = host_engine or Engine(state)
        self.root = self.host.root / 'android'
        fs.check_chain(self.root)
        self.root.mkdir(exist_ok=True)
        self.device = device
        self.serial, self.adb_path = serial, adb_path

    def transport(self, manifest=None):
        return self.device or AdbDevice(self.serial or manifest['device']['serial'], self.adb_path)

    def record_path(self, identifier):
        if not ID.fullmatch(identifier):
            raise CleanupError('invalid_android_id', 'Expected an opaque Android transaction or ticket ID')
        return self.root / (identifier + '.json')

    def save(self, identifier, payload):
        path = self.record_path(identifier)
        fs.check_chain(path)
        pending = path.with_suffix('.pending')
        fs.check_chain(pending)
        mac = hmac.new(self.host.key, encoded(payload), 'sha256').hexdigest()
        with pending.open('w', encoding='utf-8') as stream:
            json.dump({'payload': payload, 'mac': mac}, stream, ensure_ascii=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)

    def load(self, identifier):
        path = self.record_path(identifier)
        fs.check_chain(path)
        value = json.loads(path.read_text(encoding='utf-8'))
        payload = value['payload']
        mac = hmac.new(self.host.key, encoded(payload), 'sha256').hexdigest()
        if not hmac.compare_digest(mac, value['mac']) or payload['host'] != host():
            raise CleanupError('invalid_android_signature', 'Android state authentication failed')
        return payload

    def locks(self, manifest):
        key = digest(manifest['device'])
        target = manifest.get('root') or ('packages/' + manifest['package'])
        # Synthetic host paths let the existing exact-root claims coordinate ADB
        # operations without acquiring the Gradle gate or creating device files.
        return [self.root / 'targets' / key / target.lstrip('/')]

    def check_device(self, device, manifest):
        if device.endpoint() != manifest['device']:
            raise CleanupError('device_identity_changed', 'Selected endpoint no longer matches the reviewed device')

    def new(self, manifest, state='reviewed', identifier=None):
        identifier = identifier or secrets.token_hex(16)
        record = {'host': host(), 'version': 1, 'transaction_id': identifier, 'state': state,
                  'manifest': manifest, 'manifest_sha256': digest(manifest), 'results': {},
                  'deleted_bytes': 0, 'created_at': now(), 'detailed_state_retained': True}
        self.save(identifier, record)
        return record

    def review(self, root, owner_task, evidence):
        root = safe_path(root, root=True)
        if not owner_task.strip() or not evidence.strip():
            raise CleanupError('missing_provenance', 'Task ownership and concrete disposable-output provenance are required')
        device = self.transport()
        manifest = {'kind': 'files', 'device': device.endpoint(), 'root': root,
                    'owner_task': owner_task, 'evidence': evidence}
        with self.host.locked(self.locks(manifest), operation='adb-review'):
            manifest['items'] = device.inventory(root)
            self.check_device(device, manifest)
            record = self.new(manifest)
        return self.summary(record)

    def package_baseline(self, package, owner_task, evidence, apk_sha256):
        if (not PACKAGE.fullmatch(package) or not owner_task.strip() or not evidence.strip()
                or not apk_sha256 or any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in apk_sha256)):
            raise CleanupError('invalid_package_provenance', 'Exact package, task ownership, test purpose and expected APK SHA-256 hashes required')
        device = self.transport()
        manifest = {'kind': 'package', 'device': device.endpoint(), 'package': package,
                    'owner_task': owner_task, 'evidence': evidence, 'expected_apk_sha256': sorted(apk_sha256)}
        with self.host.locked(self.locks(manifest), operation='adb-package-baseline'):
            if device.package(package) is not None:
                raise CleanupError('preexisting_package', 'Package or retained package data existed before the task installation')
            self.check_device(device, manifest)
            record = self.new(manifest, 'absent_baseline')
        return self.summary(record)

    def package_review(self, identifier):
        before = self.load(identifier)
        with self.host.locked(self.locks(before['manifest']), operation='adb-package-review', transaction=identifier):
            record = self.load(identifier)
            if record['state'] != 'absent_baseline':
                raise CleanupError('invalid_android_state', 'A pre-install absent baseline is required; never invent historical evidence')
            manifest = record['manifest']
            device = self.transport(manifest)
            self.check_device(device, manifest)
            installed = device.package(manifest['package'])
            if installed is None:
                raise CleanupError('test_package_missing', 'No installed test package to review')
            if sorted(apk['sha256'] for apk in installed['apk_hashes']) != manifest['expected_apk_sha256']:
                raise CleanupError('test_package_mismatch', 'Installed APK hashes differ from the task installation baseline')
            manifest['installed'] = installed
            manifest['baseline_created_at'] = record['created_at']
            record.update(state='reviewed', manifest_sha256=digest(manifest))
            self.save(identifier, record)
        return self.summary(record)

    def summary(self, record):
        manifest = record['manifest']
        return {'ok': True, 'transaction_id': record['transaction_id'], 'state': record['state'],
                'manifest_sha256': record['manifest_sha256'], 'kind': manifest['kind'],
                'device': manifest['device'], 'root': manifest.get('root'), 'package': manifest.get('package'),
                'candidate_count': record.get('candidate_count', len(manifest.get('items', []))),
                'candidate_bytes': record.get('candidate_bytes', sum(item.get('size', 0) for item in manifest.get('items', []))),
                'deleted_bytes': record['deleted_bytes'], 'counts': record.get('counts', {}),
                'detailed_state_retained': record['detailed_state_retained'],
                'warnings': ['ADB checks are not handle-bound; stop producers before cleanup. App uninstall removes test app data for user 0.']}

    def inspect(self, identifier, offset=0, limit=100):
        if offset < 0 or not 1 <= limit <= 100:
            raise CleanupError('invalid_page', 'Use offset >= 0 and limit 1..100')
        record = self.load(identifier)
        manifest = record['manifest']
        result = self.summary(record)
        result.update(owner_task=manifest['owner_task'], evidence=manifest['evidence'],
                      expected_apk_sha256=manifest.get('expected_apk_sha256'),
                      items=manifest.get('items', [manifest['installed']] if 'installed' in manifest else [])[offset:offset + limit],
                      next_offset=offset + limit if offset + limit < len(manifest.get('items', [])) else None)
        return result

    def ticket(self, identifier, manifest_sha256, confirm_test_app_data=False):
        before = self.load(identifier)
        with self.host.locked(self.locks(before['manifest']), operation='adb-ticket', transaction=identifier):
            record = self.load(identifier)
            if record['state'] != 'reviewed' or record['manifest_sha256'] != manifest_sha256:
                raise CleanupError('invalid_android_review', 'A separately inspected current manifest digest is required')
            if record['manifest']['kind'] == 'package' and not confirm_test_app_data:
                raise CleanupError('test_app_data_confirmation_required', 'Ticket issuance requires --confirm-test-app-data')
            ticket = secrets.token_hex(16)
            record.update(state='ticketed', ticket_id=ticket)
            self.save(identifier, record)
            self.save(ticket, {'host': host(), 'transaction_id': identifier, 'ticket_id': ticket})
        return {'ok': True, 'ticket_id': ticket, 'transaction_id': identifier}

    def ticket_record(self, ticket):
        link = self.load(ticket)
        record = self.load(link['transaction_id'])
        if record.get('ticket_id') != ticket or link.get('ticket_id') != ticket:
            raise CleanupError('invalid_android_ticket', 'Ticket does not bind this transaction')
        return record

    def compact(self, record, state):
        record['candidate_count'] = len(record['manifest'].get('items', []))
        record['candidate_bytes'] = sum(item.get('size', 0) for item in record['manifest'].get('items', []))
        record['state'] = state
        record['completed_at'] = now()
        record['detailed_state_retained'] = False
        record['manifest'].pop('items', None)
        record['manifest'].pop('installed', None)
        record.pop('results', None)

    def revoke(self, ticket):
        before = self.ticket_record(ticket)
        with self.host.locked(self.locks(before['manifest']), operation='adb-revoke'):
            record = self.ticket_record(ticket)
            if record['state'] not in {'ticketed', 'partially_applied'}:
                raise CleanupError('invalid_android_state', 'Only unresolved tickets can be revoked')
            self.compact(record, 'revoked')
            self.save(record['transaction_id'], record)
        return self.summary(record)

    def discard(self, identifier, reason):
        before = self.load(identifier)
        with self.host.locked(self.locks(before['manifest']), operation='adb-discard'):
            record = self.load(identifier)
            if record['state'] not in {'reviewed', 'absent_baseline'} or not reason.strip():
                raise CleanupError('invalid_android_state', 'Discard requires an unissued review/baseline and a reason')
            record['discard_reason'] = reason
            self.compact(record, 'discarded')
            self.save(identifier, record)
        return self.summary(record)

    def status(self, identifier):
        return self.summary(self.load(identifier))

    def state_inventory(self):
        total = 0
        unfinished = []
        count = 0
        errors = []
        for path in self.root.iterdir():
            if path.is_file():
                total += path.stat().st_size
            if path.suffix == '.json' and ID.fullmatch(path.stem):
                try:
                    record = self.load(path.stem)
                    if record.get('state') in {'reviewed', 'absent_baseline', 'ticketed', 'partially_applied'}:
                        count += 1
                        if len(unfinished) < 100:
                            unfinished.append({'transaction_id': record['transaction_id'], 'state': record['state'],
                                               'ticket_id': record.get('ticket_id'), 'bytes': path.stat().st_size})
                except (CleanupError, OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append({'file': path.name, 'error': str(exc)[:300]})
        return {'state_bytes': total, 'unfinished_count': count, 'unfinished_transactions': unfinished,
                'errors': errors[:100], 'listing_capped': count > 100}

    def apply(self, ticket, dry_run=False):
        before = self.ticket_record(ticket)
        with self.host.locked(self.locks(before['manifest']), operation='adb-apply', transaction=before['transaction_id']):
            record = self.ticket_record(ticket)
            if record['state'] == 'applied':
                return self.summary(record)
            if record['state'] not in {'ticketed', 'partially_applied'}:
                raise CleanupError('invalid_android_state', 'Ticket is not applicable')
            manifest = record['manifest']
            if digest(manifest) != record['manifest_sha256']:
                raise CleanupError('invalid_android_manifest', 'Manifest changed after review')
            device = self.transport(manifest)
            self.check_device(device, manifest)
            results = dict(record['results'])
            if manifest['kind'] == 'package':
                current = device.package(manifest['package'])
                if current is None:
                    results['package'] = 'missing'
                elif current != manifest['installed']:
                    results['package'] = 'changed_after_review'
                elif dry_run:
                    results['package'] = 'would_delete'
                else:
                    try:
                        device.uninstall(manifest['package'])
                        results['package'] = 'deleted'
                    except CleanupError as exc:
                        results['package'] = 'failed'
                        record['last_error'] = {'failure_kind': exc.kind, 'message': str(exc)}
            else:
                items = sorted(manifest['items'], key=lambda item: (item['directory'], -len(item['path'])))
                # A replaced root invalidates all descendants, even if a file's hash matches.
                root_item = next(item for item in items if item['path'] == manifest['root'])
                current_root = device.snapshot(manifest['root'])
                if current_root is not None and current_root != root_item:
                    raise CleanupError('android_root_changed', 'Task root identity changed; no members deleted')
                directories = {item['path']: item for item in items if item['directory']}
                try:
                    for index, item in enumerate(items):
                        path = item['path']
                        if results.get(path) in {'deleted', 'missing'}:
                            continue
                        self.check_device(device, manifest)
                        ancestors = [directories[str(parent)] for parent in PurePosixPath(path).parents
                                     if str(parent) in directories]
                        parent_states = [(parent, device.snapshot(parent['path'])) for parent in ancestors]
                        changed_parent = any(current is not None and current != parent for parent, current in parent_states)
                        status = 'changed_ancestor' if changed_parent else device.remove(item, dry_run)
                        if status == 'failed' and getattr(device, 'last_error', None):
                            record['last_error'] = device.last_error
                        if dry_run and item['directory'] and status == 'not_empty':
                            status = 'would_remove_if_empty'
                        results[path] = status
                        if not dry_run:
                            if status == 'deleted':
                                record['deleted_bytes'] += item.get('size', 0)
                            if index % 64 == 63:
                                record.update(results=results, state='partially_applied')
                                self.save(record['transaction_id'], record)
                finally:
                    if not dry_run:
                        record.update(results=results, state='partially_applied')
                        self.save(record['transaction_id'], record)
            complete = all(value in {'deleted', 'missing', 'would_delete', 'would_remove_if_empty'} for value in results.values())
            record['counts'] = dict(Counter(results.values()))
            if not dry_run:
                record['results'] = results
                record['state'] = 'partially_applied'
                if complete:
                    self.compact(record, 'applied')
                self.save(record['transaction_id'], record)
            result = self.summary(record)
            result.update(ok=complete, dry_run=dry_run, counts=dict(Counter(results.values())))
            if not complete:
                result['failure_kind'] = 'android_cleanup_partial'
                result['last_error'] = record.get('last_error')
            return result


def add_parsers(commands):
    review = commands.add_parser('adb-review', help='Snapshot exact task-generated Android files; no deletion')
    baseline = commands.add_parser('adb-package-baseline', help='Record package absence BEFORE task installation')
    for command in (review, baseline):
        command.add_argument('--serial', required=True)
        command.add_argument('--adb-path')
        command.add_argument('--owner-task', required=True)
        command.add_argument('--evidence', required=True)
    review.add_argument('--root', required=True)
    baseline.add_argument('--package', required=True)
    baseline.add_argument('--apk-sha256', action='append', required=True,
                          help='SHA-256 of each exact APK intended for installation; repeat for split APKs')
    for name in ('adb-package-review', 'adb-inspect', 'adb-ticket', 'adb-status', 'adb-discard'):
        command = commands.add_parser(name)
        command.add_argument('--transaction', required=True)
        if name == 'adb-package-review':
            command.add_argument('--adb-path')
        elif name == 'adb-inspect':
            command.add_argument('--offset', type=int, default=0)
            command.add_argument('--limit', type=int, default=100)
        elif name == 'adb-ticket':
            command.add_argument('--manifest-sha256', required=True)
            command.add_argument('--confirm-test-app-data', action='store_true')
        elif name == 'adb-discard':
            command.add_argument('--reason', required=True)
    for name in ('adb-apply', 'adb-revoke'):
        command = commands.add_parser(name)
        command.add_argument('--ticket', required=True)
        if name == 'adb-apply':
            command.add_argument('--adb-path')
            command.add_argument('--dry-run', action='store_true')


def dispatch(args):
    engine = AndroidCleanup(args.state_root, serial=getattr(args, 'serial', None),
                            adb_path=getattr(args, 'adb_path', None))
    if args.command == 'adb-review':
        return engine.review(args.root, args.owner_task, args.evidence)
    if args.command == 'adb-package-baseline':
        return engine.package_baseline(args.package, args.owner_task, args.evidence, args.apk_sha256)
    if args.command == 'adb-package-review':
        return engine.package_review(args.transaction)
    if args.command == 'adb-inspect':
        return engine.inspect(args.transaction, args.offset, args.limit)
    if args.command == 'adb-ticket':
        return engine.ticket(args.transaction, args.manifest_sha256, args.confirm_test_app_data)
    if args.command == 'adb-status':
        return engine.status(args.transaction)
    if args.command == 'adb-discard':
        return engine.discard(args.transaction, args.reason)
    if args.command == 'adb-revoke':
        return engine.revoke(args.ticket)
    return engine.apply(args.ticket, args.dry_run)
