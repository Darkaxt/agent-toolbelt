from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import re
import shutil
import socket
import subprocess

from . import filesystem as fs

POLICY = '1'
KINDS = ('temporary', 'compiler-output', 'package-cache', 'browser-artifact',
         'media-intermediate', 'test-output', 'generated-report', 'explicit-generated-output')
GENERATED = {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
RETRY = {'locked', 'failed', 'not_empty'}


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def host():
    return digest([socket.gethostname(), os.environ.get('USERDOMAIN'), str(Path.home())])


class CleanupError(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


class Engine:
    def __init__(self, state: Path | str | None = None):
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share'))
        self.root = fs.canonical(state or base / 'Tools/transactional-cleanup/state')
        fs.check_chain(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.key_path = self.root / 'key'
        try:
            with self.key_path.open('xb') as stream:
                stream.write(secrets.token_bytes(32))
        except FileExistsError:
            pass
        self.key = self.key_path.read_bytes()
        if len(self.key) != 32:
            raise CleanupError('invalid_state', 'Invalid helper state key')
        self.repo_cache = {}

    @contextmanager
    def locked(self):
        fs.check_chain(self.root)
        with (self.root / 'operation.lock').open('a+b') as stream:
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise CleanupError('state_busy', 'Another helper operation owns the state; retry after it finishes') from exc
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def path(self, name):
        if not re.fullmatch(r'(?:[a-f0-9]{32}|[a-f0-9]{64})(?:\.manifest)?\.(?:json|journal)', name):
            raise CleanupError('invalid_id', 'Expected a helper-issued identifier')
        return self.root / name

    def save(self, path, payload):
        envelope = {'payload': payload, 'mac': hmac.new(self.key, encoded(payload), 'sha256').hexdigest()}
        temporary = path.with_suffix('.pending')
        with temporary.open('wb') as stream:
            stream.write(encoded(envelope))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def load(self, path):
        fs.check_chain(path)
        try:
            envelope = json.loads(path.read_bytes())
            payload = envelope['payload']
            expected = hmac.new(self.key, encoded(payload), 'sha256').hexdigest()
            if not hmac.compare_digest(expected, envelope['mac']):
                raise ValueError('State signature mismatch')
            if payload['host'] != host() or payload['policy'] != POLICY:
                raise ValueError('Host or policy mismatch')
            return payload
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CleanupError('invalid_state', f'Unknown or invalid helper state: {path.name}') from exc

    def journal(self, ticket, *, dry_run):
        path = self.path(ticket['ticket_id'] + '.journal')
        if not path.exists():
            return
        fs.check_chain(path)
        entries = {i['path']: i for i in ticket['entries']}
        valid_end = 0
        with path.open('rb') as stream:
            for raw in stream:
                if not raw.endswith(b'\n'):
                    break  # An interrupted final append has no authority.
                try:
                    record = json.loads(raw)
                    event = record['event']
                    if not hmac.compare_digest(record['mac'], hmac.new(self.key, encoded(event), 'sha256').hexdigest()):
                        raise ValueError('signature')
                    if event['ticket_id'] != ticket['ticket_id'] or event['path'] not in entries:
                        raise ValueError('membership')
                    entries[event['path']]['result'] = event['result']
                    ticket['deleted_bytes'] = max(ticket['deleted_bytes'], event['deleted_bytes'])
                except (ValueError, KeyError, TypeError) as exc:
                    raise CleanupError('journal_invalid', 'Retry journal failed integrity validation') from exc
                valid_end = stream.tell()
        if not dry_run and path.stat().st_size != valid_end:
            with path.open('r+b') as stream:
                stream.truncate(valid_end)

    def journal_item(self, ticket, item):
        event = {'ticket_id': ticket['ticket_id'], 'path': item['path'],
                 'result': item['result'], 'deleted_bytes': ticket['deleted_bytes']}
        record = {'event': event, 'mac': hmac.new(self.key, encoded(event), 'sha256').hexdigest()}
        with self.path(ticket['ticket_id'] + '.journal').open('ab') as stream:
            stream.write(encoded(record) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())

    def txn(self, transaction):
        return self.load(self.path(transaction + '.json'))

    def protection(self, path):
        path = fs.canonical(path)
        if path == Path(path.anchor) or path == Path.home() or path == Path.home().parent:
            return 'critical_root'
        protected = [self.root, Path(__file__).absolute().parent]
        local = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share'))
        protected.append(fs.canonical(local / 'Tools/transactional-cleanup'))
        for var in ('SystemRoot', 'windir'):
            if os.environ.get(var):
                protected.append(fs.canonical(os.environ[var]))
        for folder in ('.codex', '.agents', '.claude'):
            protected.append(Path.home() / folder)
        if any(fs.within(path, p) for p in protected):
            return 'protected_root'
        if any(fs.within(p, path) for p in protected):
            return 'protected_ancestor'
        temp_roots = [Path('D:/Temp'), Path('E:/Temp')]
        if os.environ.get('TEMP'):
            temp_roots.append(fs.canonical(os.environ['TEMP']))
        if os.environ.get('LOCALAPPDATA'):
            temp_roots.append(fs.canonical(os.environ['LOCALAPPDATA']) / 'Temp')
        if path in temp_roots:
            return 'scan_root'
        for var in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramData', 'LOCALAPPDATA', 'APPDATA'):
            if os.environ.get(var) and path == fs.canonical(os.environ[var]):
                return 'critical_root'
        parts = {p.casefold() for p in path.parts}
        if parts & {'.git', '$recycle.bin', 'system volume information', 'recovery', 'boot', '$extend'}:
            return 'filesystem_or_repository_metadata'
        if (path / '.git').exists():
            return 'repository_root'
        try:
            fs.check_chain(path)
        except ValueError:
            return 'reparse_point'
        return None

    def git_reason(self, path):
        parent = path if path.is_dir() else path.parent
        repo = next((p for p in (parent, *parent.parents) if (p / '.git').exists()), None)
        if repo is None:
            return None
        if repo not in self.repo_cache:
            try:
                result = subprocess.run(['git', '-C', str(repo), 'ls-files', '-z', '--cached'],
                                        capture_output=True, check=True)
                self.repo_cache[repo] = {os.fsdecode(s).replace('\\', '/').casefold()
                                         for s in result.stdout.split(b'\0') if s}
            except (OSError, subprocess.CalledProcessError):
                self.repo_cache[repo] = None
        tracked = self.repo_cache[repo]
        relative = path.relative_to(repo).as_posix().casefold()
        if tracked is None:
            return 'git_unavailable'
        if relative in tracked or (path.is_dir() and any(s.startswith(relative + '/') for s in tracked)):
            return 'git_tracked'
        return None

    def scan(self, roots):
        entries = {}
        for root_value in roots:
            root = fs.canonical(root_value)
            pending = [root]
            while pending:
                path = pending.pop()
                key = str(path)
                if key in entries or not os.path.lexists(path):
                    continue
                reason = self.protection(path)
                if reason:
                    entries[key] = {'path': key, 'excluded': reason}
                    # A repository root itself is protected, but generated descendants can be inventoried.
                    if reason in {'repository_root', 'scan_root', 'protected_ancestor'}:
                        try:
                            pending.extend(path.iterdir())
                        except OSError as exc:
                            entries[key]['scan_error'] = type(exc).__name__
                    continue
                try:
                    info = fs.identity(path)
                    entries[key] = {'path': key, **info}
                    if info['directory']:
                        pending.extend(path.iterdir())
                except (OSError, ValueError) as exc:
                    entries[key] = {'path': key, 'excluded': type(exc).__name__}
        return entries

    def begin(self, workspace, scan_roots=None):
        workspace = fs.canonical(workspace)
        if not workspace.is_dir():
            raise CleanupError('workspace_missing', 'Workspace must be an existing directory')
        roots = [str(workspace)]
        if scan_roots is None:
            roots.extend(str(p) for p in [Path(os.environ.get('TEMP', 'D:/Temp')), Path('D:/Temp'),
                                         Path('E:/Temp'),
                                         Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Temp'] if p.is_dir())
        else:
            roots.extend(str(fs.canonical(p)) for p in scan_roots)
        roots = list(dict.fromkeys(roots))
        transaction = secrets.token_hex(16)
        payload = {'host': host(), 'policy': POLICY, 'transaction_id': transaction,
                   'workspace': str(workspace), 'created_at': now(), 'state': 'open',
                   'roots': roots, 'scan_roots': list(roots), 'baseline': self.scan(roots), 'registrations': [],
                   'free_space': {str(p): shutil.disk_usage(p).free for p in roots if Path(p).exists()},
                   'discovery_coverage': {'workspace': True, 'known_or_explicit_roots': roots,
                                          'explicit_registration': True, 'usn': 'unavailable_v1',
                                          'etw': 'unavailable_v1', 'complete_host_coverage': False}}
        self.save(self.path(transaction + '.json'), payload)
        return self.report('begin', payload)

    def register(self, transaction, path, kind, evidence, regenerated=False):
        payload = self.txn(transaction)
        if payload['state'] != 'open':
            raise CleanupError('review_frozen', 'Registration is closed after review')
        path = fs.canonical(path)
        reason = self.protection(path)
        if reason or str(path) in payload['scan_roots']:
            raise CleanupError('protected_path', reason or 'workspace_root')
        if kind not in KINDS or not evidence.strip():
            raise CleanupError('provenance_required', 'Supply a generated artifact kind and concrete provenance')
        if not any(fs.within(path, Path(root)) for root in payload['roots']):
            payload['baseline'].update(self.scan([path]))
            payload['roots'].append(str(path))
        payload['registrations'].append({'path': str(path), 'kind': kind,
                                         'evidence': evidence, 'regenerated': regenerated})
        self.save(self.path(transaction + '.json'), payload)
        return self.report('register', payload)

    def review(self, transaction):
        payload = self.txn(transaction)
        if payload['state'] != 'open':
            raise CleanupError('review_frozen', 'This snapshot has already been reviewed')
        current = self.scan(payload['roots'])
        items = []
        for key, info in current.items():
            path = Path(key)
            baseline = payload['baseline'].get(key)
            registrations = [r for r in payload['registrations'] if fs.within(path, Path(r['path']))]
            registration = max(registrations, key=lambda r: len(r['path']), default=None)
            git_status = self.git_reason(path) if not info.get('excluded') else None
            reason = info.get('excluded') or git_status
            if path == Path(payload['workspace']) or key in payload['roots'] and not registration:
                reason = reason or 'scan_root'
            if not reason and (info['reparse'] or not info['directory'] and info['links'] != 1):
                reason = 'reparse_or_hardlink'
            if not reason and info.get('filesystem') not in {'NTFS', 'ReFS'}:
                reason = 'stable_identity_unavailable'
            existed = baseline is not None
            if not reason and existed and not (registration and registration['regenerated']):
                reason = 'preexisting_protected'
            generated = registration or bool(set(path.parts) & GENERATED)
            if not reason and not generated:
                reason = 'generated_provenance_missing'
            items.append({**info, 'decision': 'excluded' if reason else 'candidate',
                          'reason': reason or 'attributed_generated_output',
                          'kind': registration['kind'] if registration else 'compiler-output',
                          'evidence': registration['evidence'] if registration else 'recognized cache directory',
                          'discovery_source': 'explicit_registration' if registration else 'baseline_inventory',
                          'git_status': git_status or 'not_tracked_or_outside_repository',
                          'preexisting': existed})
        manifest = {'host': host(), 'policy': POLICY, 'transaction_id': transaction,
                    'created_at': now(), 'workspace': payload['workspace'], 'items': items}
        path = self.path(transaction + '.manifest.json')
        # Immutable in the state machine: subsequent registration/review is rejected.
        self.save(path, manifest)
        payload['state'] = 'reviewed'
        payload['manifest_sha256'] = digest(manifest)
        payload.pop('baseline')
        self.save(self.path(transaction + '.json'), payload)
        return self.report('review', payload, items=items, manifest_path=str(path),
                           manifest_sha256=digest(manifest),
                           diagnostics=[{k: i.get(k) for k in ('path', 'decision', 'reason', 'size', 'kind')}
                                        for i in items[:100]], diagnostics_truncated=len(items) > 100)

    def ticket(self, transaction, manifest_sha256):
        payload = self.txn(transaction)
        if payload['state'] != 'reviewed':
            raise CleanupError('review_required', 'A reviewed snapshot is required; ticket already issued or unavailable')
        manifest = self.load(self.path(transaction + '.manifest.json'))
        if manifest_sha256 != digest(manifest) or payload['manifest_sha256'] != manifest_sha256:
            raise CleanupError('review_mismatch', 'Pass the hash from the reviewed manifest')
        ticket_id = secrets.token_hex(32)
        ticket = {'host': host(), 'policy': POLICY, 'transaction_id': transaction,
                  'ticket_id': ticket_id, 'manifest_sha256': manifest_sha256,
                  'state': 'issued', 'issued_at': now(), 'deleted_bytes': 0,
                  'entries': [{**i, 'result': 'pending'} for i in manifest['items'] if i['decision'] == 'candidate']}
        self.save(self.path(ticket_id + '.json'), ticket)
        payload.update(state='ticketed', ticket_id=ticket_id)
        self.save(self.path(transaction + '.json'), payload)
        return self.report('ticket', payload, items=ticket['entries'], ticket_id=ticket_id,
                           manifest_sha256=manifest_sha256, ticket_state='issued')

    def apply(self, ticket_id, dry_run=False):
        ticket = self.load(self.path(ticket_id + '.json'))
        if ticket.get('ticket_id') != ticket_id or ticket['state'] not in {'issued', 'partially_applied'}:
            raise CleanupError('ticket_terminal', 'Ticket is unknown, already applied, or revoked')
        payload = self.txn(ticket['transaction_id'])
        manifest = self.load(self.path(payload['transaction_id'] + '.manifest.json'))
        if digest(manifest) != ticket['manifest_sha256']:
            raise CleanupError('review_mismatch', 'Reviewed manifest changed')
        expected = {i['path']: i for i in manifest['items'] if i['decision'] == 'candidate'}
        if len(expected) != len(ticket['entries']) or any(
                {k: v for k, v in item.items() if k != 'result'} != expected.get(item['path'])
                for item in ticket['entries']):
            raise CleanupError('ticket_mismatch', 'Ticket membership differs from review')
        if os.name != 'nt':
            raise CleanupError('platform_unsupported', 'Application requires Windows identity and handle disposition')
        self.journal(ticket, dry_run=dry_run)
        self.repo_cache.clear()
        results = []
        entries = sorted(ticket['entries'], key=lambda i: (i['directory'], -len(Path(i['path']).parts)))
        for item in entries:
            if item['result'] not in RETRY | {'pending'}:
                results.append({'path': item['path'], 'result': item['result']})
                continue
            path = fs.canonical(item['path'])
            reason = self.protection(path) or self.git_reason(path)
            if reason:
                result, count = 'protected', 0
            else:
                result, count = fs.delete_exact(item, dry_run=dry_run)
            results.append({'path': str(path), 'result': result})
            if not dry_run:
                item['result'] = result
                ticket['deleted_bytes'] += count
                # Each completed item is journaled; interruption never broadens a retry.
                self.journal_item(ticket, item)
        terminal = all(i['result'] not in RETRY | {'pending'} for i in entries)
        if not dry_run:
            ticket['state'] = 'applied' if terminal else 'partially_applied'
            self.save(self.path(ticket_id + '.json'), ticket)
        result = self.report('apply', payload, items=ticket['entries'], ticket_id=ticket_id,
                             dry_run=dry_run, ticket_state=ticket['state'],
                             result_counts=dict(Counter(i['result'] for i in results)),
                             deleted_bytes=ticket['deleted_bytes'], diagnostics=results[:100],
                             diagnostics_truncated=len(results) > 100)
        if terminal and not dry_run:
            self.finish(payload, ticket, result)
        return result

    def finish(self, payload, ticket, result):
        summary = {k: v for k, v in result.items() if k not in {'diagnostics', 'discovery_coverage'}}
        summary.update(host=host(), policy=POLICY, completed_at=now(), ticket_id=ticket['ticket_id'],
                       state=ticket['state'], discovery_coverage={'complete_host_coverage': False})
        self.save(self.path(payload['transaction_id'] + '.json'), summary)
        self.save(self.path(ticket['ticket_id'] + '.json'), summary)
        self.path(payload['transaction_id'] + '.manifest.json').unlink(missing_ok=True)
        self.path(ticket['ticket_id'] + '.journal').unlink(missing_ok=True)
        # Retain at most 100 compact transaction summaries; active tickets are never pruned.
        summaries = []
        for path in self.root.glob('*.json'):
            if len(path.stem) == 32:
                value = self.load(path)
                if value.get('completed_at'):
                    summaries.append((path, value))
        for path, value in sorted(summaries, key=lambda x: x[1]['completed_at'])[:-100]:
            self.path(value['ticket_id'] + '.json').unlink(missing_ok=True)
            path.unlink()

    def revoke(self, ticket_id):
        ticket = self.load(self.path(ticket_id + '.json'))
        if ticket.get('state') not in {'issued', 'partially_applied'}:
            raise CleanupError('ticket_terminal', 'Ticket is already terminal')
        payload = self.txn(ticket['transaction_id'])
        self.journal(ticket, dry_run=False)
        ticket['state'] = 'revoked'
        result = self.report('revoke', payload, ticket_id=ticket_id, ticket_state='revoked',
                             deleted_bytes=ticket['deleted_bytes'])
        self.finish(payload, ticket, result)
        return result

    def status(self, transaction):
        payload = self.txn(transaction)
        ticket_id = payload.get('ticket_id')
        ticket = self.load(self.path(ticket_id + '.json')) if ticket_id else {}
        if ticket.get('entries'):
            self.journal(ticket, dry_run=True)
        if ticket.get('state') in {'applied', 'revoked'} and 'entries' in ticket:
            report = self.report('status', payload, ticket_id=ticket_id, ticket_state=ticket['state'],
                                 result_counts=dict(Counter(i['result'] for i in ticket['entries'])),
                                 deleted_bytes=ticket['deleted_bytes'])
            self.finish(payload, ticket, report)
            payload = self.txn(transaction)
            ticket = self.load(self.path(ticket_id + '.json'))
        return self.report('status', payload, ticket_id=ticket_id, ticket_state=ticket.get('state'),
                           result_counts=(dict(Counter(i['result'] for i in ticket['entries']))
                                          if 'entries' in ticket else ticket.get('result_counts', {})),
                           deleted_bytes=ticket.get('deleted_bytes', 0),
                           detailed_state_retained=not bool(payload.get('completed_at')),
                           residual_helper_files=[p.name for p in self.root.glob('*.pending')])

    @staticmethod
    def report(operation, payload, items=(), **extra):
        candidates = [i for i in items if i.get('decision') == 'candidate']
        return {'ok': True, 'operation': operation, 'transaction_id': payload['transaction_id'],
                'workspace': payload['workspace'], 'state': payload['state'],
                'discovery_coverage': payload['discovery_coverage'], 'candidate_count': len(candidates),
                'candidate_bytes': sum(i['size'] for i in candidates if not i['directory']),
                'excluded_count': len(items) - len(candidates), 'result_counts': {},
                'deleted_bytes': 0, 'warnings': [], 'errors': [], 'failure_kind': None, **extra}
