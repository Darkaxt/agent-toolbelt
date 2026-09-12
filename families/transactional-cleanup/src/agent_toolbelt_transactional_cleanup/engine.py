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
import shutil
import socket
import sqlite3
import subprocess

from . import filesystem as fs

POLICY = '2'
KINDS = ('temporary', 'compiler-output', 'package-cache', 'browser-artifact',
         'media-intermediate', 'test-output', 'generated-report', 'explicit-generated-output')
GENERATED = {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
RETRY = {'locked', 'failed', 'not_empty'}
BATCH_SIZE = 256


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def host():
    return digest([socket.gethostname(), os.environ.get('USERDOMAIN'), str(Path.home())])


def path_key(path: str | Path):
    return os.path.normcase(str(path)).casefold()


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
        self.db_path = self.root / 'state.sqlite3'
        self.repo_cache = {}
        self._initialize()

    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=0)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=0')
        connection.execute('PRAGMA secure_delete=ON')
        return connection

    def _initialize(self):
        first = not self.db_path.exists()
        connection = sqlite3.connect(self.db_path, timeout=0)
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('PRAGMA secure_delete=ON')
            if first:
                connection.execute('PRAGMA auto_vacuum=FULL')
                connection.execute('VACUUM')
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY, host TEXT NOT NULL, policy TEXT NOT NULL,
                    workspace TEXT NOT NULL, created_at TEXT NOT NULL, state TEXT NOT NULL,
                    roots_json TEXT NOT NULL, scan_mode TEXT NOT NULL, free_space_json TEXT NOT NULL,
                    discovery_json TEXT NOT NULL, manifest_created_at TEXT, manifest_sha256 TEXT,
                    ticket_id TEXT, candidate_count INTEGER NOT NULL DEFAULT 0,
                    candidate_bytes INTEGER NOT NULL DEFAULT 0, excluded_count INTEGER NOT NULL DEFAULT 0,
                    deleted_bytes INTEGER NOT NULL DEFAULT 0, result_counts_json TEXT NOT NULL DEFAULT '{}',
                    detail_retained INTEGER NOT NULL DEFAULT 1, completed_at TEXT,
                    active_operation TEXT, progress_phase TEXT, progress_processed INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER, progress_bytes INTEGER NOT NULL DEFAULT 0,
                    progress_updated_at TEXT, owner_pid INTEGER
                );
                CREATE TABLE IF NOT EXISTS roots (
                    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, path TEXT NOT NULL, path_key TEXT NOT NULL,
                    PRIMARY KEY (transaction_id, ordinal), UNIQUE (transaction_id, path_key)
                );
                CREATE TABLE IF NOT EXISTS registrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id) ON DELETE CASCADE,
                    path TEXT NOT NULL, path_key TEXT NOT NULL, kind TEXT NOT NULL,
                    evidence TEXT NOT NULL, regenerated INTEGER NOT NULL,
                    allow_hardlinks INTEGER NOT NULL DEFAULT 0,
                    allow_leaf_reparse INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS registrations_lookup ON registrations(transaction_id, path_key);
                CREATE TABLE IF NOT EXISTS baseline (
                    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id) ON DELETE CASCADE,
                    path_key TEXT NOT NULL, path TEXT NOT NULL, item_json TEXT NOT NULL,
                    PRIMARY KEY (transaction_id, path_key)
                );
                CREATE TABLE IF NOT EXISTS manifest (
                    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, path_key TEXT NOT NULL, path TEXT NOT NULL,
                    item_json TEXT NOT NULL, decision TEXT NOT NULL, size INTEGER NOT NULL,
                    directory INTEGER NOT NULL, row_sha256 TEXT NOT NULL, row_mac TEXT NOT NULL,
                    result TEXT, deleted_bytes INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (transaction_id, ordinal), UNIQUE (transaction_id, path_key)
                );
                CREATE INDEX IF NOT EXISTS manifest_candidates
                    ON manifest(transaction_id, decision, result, directory, path);
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY,
                    transaction_id TEXT NOT NULL UNIQUE REFERENCES transactions(transaction_id) ON DELETE CASCADE,
                    host TEXT NOT NULL, policy TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
                    candidate_count INTEGER NOT NULL, state TEXT NOT NULL, issued_at TEXT NOT NULL,
                    deleted_bytes INTEGER NOT NULL DEFAULT 0, completed_at TEXT, ticket_mac TEXT NOT NULL
                );
            ''')
            connection.commit()
        finally:
            connection.close()

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
                raise CleanupError('state_busy', 'Another helper operation owns the state; inspect lock-free status') from exc
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

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
        if any(fs.within(path, value) for value in protected):
            return 'protected_root'
        if any(fs.within(value, path) for value in protected):
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
        parts = {part.casefold() for part in path.parts}
        if parts & {'.git', '$recycle.bin', 'system volume information', 'recovery', 'boot', '$extend'}:
            return 'filesystem_or_repository_metadata'
        if (path / '.git').exists():
            return 'repository_root'
        try:
            fs.check_chain(path, allow_leaf_reparse=True)
        except ValueError:
            return 'reparse_point'
        return None

    def git_reason(self, path):
        parent = path if path.is_dir() else path.parent
        repo = next((value for value in (parent, *parent.parents) if (value / '.git').exists()), None)
        if repo is None:
            return None
        if repo not in self.repo_cache:
            try:
                result = subprocess.run(['git', '-C', str(repo), 'ls-files', '-z', '--cached'],
                                        capture_output=True, check=True)
                self.repo_cache[repo] = {os.fsdecode(value).replace('\\', '/').casefold()
                                         for value in result.stdout.split(b'\0') if value}
            except (OSError, subprocess.CalledProcessError):
                self.repo_cache[repo] = None
        tracked = self.repo_cache[repo]
        relative = path.relative_to(repo).as_posix().casefold()
        if tracked is None:
            return 'git_unavailable'
        if relative in tracked or (path.is_dir() and any(value.startswith(relative + '/') for value in tracked)):
            return 'git_tracked'
        return None

    def scan(self, roots):
        """Yield metadata one object at a time; callers own bounded persistence."""
        for root_value in roots:
            root = fs.canonical(root_value)
            pending = [root]
            while pending:
                path = pending.pop()
                if not os.path.lexists(path):
                    continue
                key = str(path)
                reason = self.protection(path)
                if reason:
                    item = {'path': key, 'excluded': reason}
                    if reason in {'repository_root', 'scan_root', 'protected_ancestor'}:
                        try:
                            pending.extend(path.iterdir())
                        except OSError as exc:
                            item['scan_error'] = type(exc).__name__
                    yield item
                    continue
                try:
                    info = fs.identity(path, allow_leaf_reparse=True)
                    yield {'path': key, **info}
                    if info['directory'] and not info['reparse']:
                        pending.extend(path.iterdir())
                except (OSError, ValueError) as exc:
                    yield {'path': key, 'excluded': type(exc).__name__}

    def _known_temp_roots(self):
        candidates = [Path(os.environ.get('TEMP', 'D:/Temp')), Path('D:/Temp'), Path('E:/Temp'),
                      Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Temp']
        return [str(fs.canonical(path)) for path in candidates if path.is_dir()]

    def _set_progress(self, connection, transaction, operation, phase, processed=0, total=None, processed_bytes=0):
        connection.execute('''UPDATE transactions SET active_operation=?, progress_phase=?,
            progress_processed=?, progress_total=?, progress_bytes=?, progress_updated_at=?, owner_pid=?
            WHERE transaction_id=?''',
                           (operation, phase, processed, total, processed_bytes, now(), os.getpid(), transaction))

    def _clear_progress(self, connection, transaction, phase='idle'):
        connection.execute('''UPDATE transactions SET active_operation=NULL, progress_phase=?,
            progress_updated_at=?, owner_pid=NULL WHERE transaction_id=?''', (phase, now(), transaction))

    def _insert_baseline(self, connection, transaction, roots):
        processed = processed_bytes = 0
        batch = []
        for item in self.scan(roots):
            batch.append((transaction, path_key(item['path']), item['path'], encoded(item).decode()))
            processed += 1
            processed_bytes += int(item.get('size', 0)) if not item.get('directory') else 0
            if len(batch) >= BATCH_SIZE:
                connection.executemany('INSERT OR REPLACE INTO baseline VALUES (?,?,?,?)', batch)
                self._set_progress(connection, transaction, 'begin', 'inventory', processed, None, processed_bytes)
                connection.commit()
                batch.clear()
        if batch:
            connection.executemany('INSERT OR REPLACE INTO baseline VALUES (?,?,?,?)', batch)
        return processed, processed_bytes

    def begin(self, workspace, scan_roots=None, include_known_temp_roots=False):
        workspace = fs.canonical(workspace)
        if not workspace.is_dir():
            raise CleanupError('workspace_missing', 'Workspace must be an existing directory')
        if scan_roots:
            roots = [str(fs.canonical(path)) for path in scan_roots]
            scan_mode = 'explicit'
        else:
            roots = [str(workspace)]
            scan_mode = 'workspace'
            if include_known_temp_roots:
                roots.extend(self._known_temp_roots())
                scan_mode = 'workspace_and_known_temp'
        roots = list(dict.fromkeys(roots))
        transaction = secrets.token_hex(16)
        free_space = {root: shutil.disk_usage(root).free for root in roots if Path(root).exists()}
        coverage = {'workspace': any(fs.within(workspace, Path(root)) for root in roots),
                    'known_or_explicit_roots': roots, 'explicit_registration': True,
                    'usn': 'unavailable_v2', 'etw': 'unavailable_v2', 'complete_host_coverage': False}
        connection = self.connect()
        try:
            connection.execute('''INSERT INTO transactions
                (transaction_id,host,policy,workspace,created_at,state,roots_json,scan_mode,
                 free_space_json,discovery_json,active_operation,progress_phase,progress_updated_at,owner_pid)
                VALUES (?,?,?,?,?,'open',?,?,?,?,?,?,?,?)''',
                               (transaction, host(), POLICY, str(workspace), now(), encoded(roots).decode(),
                                scan_mode, encoded(free_space).decode(), encoded(coverage).decode(),
                                'begin', 'inventory', now(), os.getpid()))
            connection.executemany('INSERT INTO roots VALUES (?,?,?,?)',
                                   [(transaction, index, root, path_key(root)) for index, root in enumerate(roots)])
            connection.commit()
            processed, processed_bytes = self._insert_baseline(connection, transaction, roots)
            self._clear_progress(connection, transaction)
            connection.commit()
        except BaseException:
            try:
                self._clear_progress(connection, transaction, 'interrupted')
                connection.commit()
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()
        payload = self.txn(transaction)
        return self.report('begin', payload, progress={'phase': 'idle', 'processed_items': processed,
                                                       'processed_bytes': processed_bytes})

    def _row(self, connection, transaction):
        row = connection.execute('SELECT * FROM transactions WHERE transaction_id=?', (transaction,)).fetchone()
        if row is None:
            raise CleanupError('invalid_state', 'Unknown helper transaction')
        if row['host'] != host() or row['policy'] != POLICY:
            raise CleanupError('invalid_state', 'Host or policy mismatch')
        return row

    def txn(self, transaction):
        connection = self.connect()
        try:
            return self._payload(self._row(connection, transaction))
        finally:
            connection.close()

    @staticmethod
    def _payload(row):
        return {'transaction_id': row['transaction_id'], 'host': row['host'], 'policy': row['policy'],
                'workspace': row['workspace'], 'created_at': row['created_at'], 'state': row['state'],
                'roots': json.loads(row['roots_json']), 'scan_roots': json.loads(row['roots_json']),
                'scan_mode': row['scan_mode'], 'free_space': json.loads(row['free_space_json']),
                'discovery_coverage': json.loads(row['discovery_json']),
                'manifest_sha256': row['manifest_sha256'], 'ticket_id': row['ticket_id'],
                'candidate_count': row['candidate_count'], 'candidate_bytes': row['candidate_bytes'],
                'excluded_count': row['excluded_count'], 'deleted_bytes': row['deleted_bytes'],
                'result_counts': json.loads(row['result_counts_json']),
                'detail_retained': bool(row['detail_retained']), 'completed_at': row['completed_at']}

    def register(self, transaction, path, kind, evidence, regenerated=False,
                 allow_hardlinks=False, allow_leaf_reparse=False):
        path = fs.canonical(path)
        reason = self.protection(path)
        if kind not in KINDS or not evidence.strip():
            raise CleanupError('provenance_required', 'Supply a generated artifact kind and concrete provenance')
        connection = self.connect()
        try:
            row = self._row(connection, transaction)
            if row['state'] != 'open':
                raise CleanupError('review_frozen', 'Registration is closed after review')
            if reason or path == Path(row['workspace']):
                raise CleanupError('protected_path', reason or 'workspace_root')
            roots = json.loads(row['roots_json'])
            if not any(fs.within(path, Path(root)) for root in roots):
                roots.append(str(path))
                ordinal = connection.execute('SELECT COALESCE(MAX(ordinal),-1)+1 FROM roots WHERE transaction_id=?',
                                             (transaction,)).fetchone()[0]
                connection.execute('INSERT INTO roots VALUES (?,?,?,?)',
                                   (transaction, ordinal, str(path), path_key(path)))
                connection.execute('UPDATE transactions SET roots_json=? WHERE transaction_id=?',
                                   (encoded(roots).decode(), transaction))
                self._insert_baseline(connection, transaction, [str(path)])
            connection.execute('''INSERT INTO registrations
                (transaction_id,path,path_key,kind,evidence,regenerated,allow_hardlinks,allow_leaf_reparse)
                VALUES (?,?,?,?,?,?,?,?)''',
                               (transaction, str(path), path_key(path), kind, evidence, int(regenerated),
                                int(allow_hardlinks), int(allow_leaf_reparse)))
            connection.commit()
            return self.report('register', self._payload(self._row(connection, transaction)))
        finally:
            connection.close()

    def _registrations(self, connection, transaction):
        mapping = {}
        for row in connection.execute('''SELECT * FROM registrations WHERE transaction_id=?
            ORDER BY LENGTH(path) DESC, id ASC''', (transaction,)):
            mapping.setdefault(row['path_key'], dict(row))
        return mapping

    @staticmethod
    def _registration_for(path, registrations):
        for ancestor in (path, *path.parents):
            registration = registrations.get(path_key(ancestor))
            if registration is not None:
                return registration
        return None

    def _classify_batch(self, connection, transaction, workspace, roots, registrations, batch, start_ordinal):
        keys = [path_key(item['path']) for item in batch]
        placeholders = ','.join('?' for _ in keys)
        existing = {row[0] for row in connection.execute(
            f'SELECT path_key FROM baseline WHERE transaction_id=? AND path_key IN ({placeholders})',
            (transaction, *keys))} if keys else set()
        records, diagnostics = [], []
        candidate_count = candidate_bytes = excluded_count = 0
        for offset, info in enumerate(batch):
            path = Path(info['path'])
            registration = self._registration_for(path, registrations)
            git_status = self.git_reason(path) if not info.get('excluded') else None
            reason = info.get('excluded') or git_status
            if path == workspace or (str(path) in roots and not registration):
                reason = reason or 'scan_root'
            allow_reparse = bool(registration and registration['allow_leaf_reparse'])
            allow_hardlinks = bool(registration and registration['allow_hardlinks'])
            if not reason and info['reparse'] and not allow_reparse:
                reason = 'reparse_point'
            if not reason and not info['directory'] and info['links'] != 1 and not allow_hardlinks:
                reason = 'hardlink'
            if not reason and info.get('filesystem') not in {'NTFS', 'ReFS'}:
                reason = 'stable_identity_unavailable'
            preexisting = path_key(path) in existing
            if not reason and preexisting and not (registration and registration['regenerated']):
                reason = 'preexisting_protected'
            generated = registration or bool({part.casefold() for part in path.parts} & GENERATED)
            if not reason and not generated:
                reason = 'generated_provenance_missing'
            item = {**info, 'allow_hardlinks': allow_hardlinks,
                    'allow_leaf_reparse': allow_reparse,
                    'decision': 'excluded' if reason else 'candidate',
                    'reason': reason or 'attributed_generated_output',
                    'kind': registration['kind'] if registration else 'compiler-output',
                    'evidence': registration['evidence'] if registration else 'recognized cache directory',
                    'discovery_source': 'explicit_registration' if registration else 'baseline_inventory',
                    'git_status': git_status or 'not_tracked_or_outside_repository',
                    'preexisting': preexisting}
            item_text = encoded(item).decode()
            row_sha = hashlib.sha256(item_text.encode()).hexdigest()
            ordinal = start_ordinal + offset
            row_mac = hmac.new(self.key, encoded([transaction, ordinal, row_sha]), 'sha256').hexdigest()
            size = int(item.get('size', 0)) if not item.get('directory') else 0
            records.append((transaction, ordinal, path_key(path), str(path), item_text, item['decision'],
                            size, int(bool(item.get('directory'))), row_sha, row_mac))
            if item['decision'] == 'candidate':
                candidate_count += 1; candidate_bytes += size
            else:
                excluded_count += 1
            diagnostics.append({key: item.get(key) for key in ('path', 'decision', 'reason', 'size', 'kind')})
        return records, diagnostics, candidate_count, candidate_bytes, excluded_count

    @staticmethod
    def _manifest_header(row):
        return {'host': row['host'], 'policy': row['policy'], 'transaction_id': row['transaction_id'],
                'created_at': row['manifest_created_at'], 'workspace': row['workspace']}

    def _manifest_digest(self, connection, row, validate=True):
        checksum = hashlib.sha256(encoded(self._manifest_header(row)) + b'\n')
        for item in connection.execute('''SELECT ordinal,item_json,row_sha256,row_mac FROM manifest
                                          WHERE transaction_id=? ORDER BY ordinal''', (row['transaction_id'],)):
            actual = hashlib.sha256(item['item_json'].encode()).hexdigest()
            expected_mac = hmac.new(self.key, encoded([row['transaction_id'], item['ordinal'], actual]), 'sha256').hexdigest()
            if validate and (actual != item['row_sha256'] or not hmac.compare_digest(expected_mac, item['row_mac'])):
                raise CleanupError('review_mismatch', 'Reviewed manifest row failed integrity validation')
            checksum.update(actual.encode() + b'\n')
        return checksum.hexdigest()

    def review(self, transaction):
        connection = self.connect()
        try:
            row = self._row(connection, transaction)
            if row['state'] != 'open':
                raise CleanupError('review_frozen', 'This snapshot has already been reviewed')
            roots, workspace = json.loads(row['roots_json']), Path(row['workspace'])
            registrations, created_at = self._registrations(connection, transaction), now()
            connection.execute('DELETE FROM manifest WHERE transaction_id=?', (transaction,))
            connection.execute('UPDATE transactions SET manifest_created_at=? WHERE transaction_id=?',
                               (created_at, transaction))
            self._set_progress(connection, transaction, 'review', 'inventory')
            connection.commit()
            ordinal = candidate_count = candidate_bytes = excluded_count = processed_bytes = 0
            diagnostics, batch = [], []
            self.repo_cache.clear()
            for info in self.scan(roots):
                batch.append(info)
                if len(batch) < BATCH_SIZE:
                    continue
                records, notes, count, size, excluded = self._classify_batch(
                    connection, transaction, workspace, roots, registrations, batch, ordinal)
                connection.executemany('''INSERT INTO manifest
                    (transaction_id,ordinal,path_key,path,item_json,decision,size,directory,row_sha256,row_mac)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''', records)
                ordinal += len(records); candidate_count += count; candidate_bytes += size; excluded_count += excluded
                processed_bytes += sum(int(item.get('size', 0)) for item in batch if not item.get('directory'))
                diagnostics.extend(notes[:max(0, 100 - len(diagnostics))])
                self._set_progress(connection, transaction, 'review', 'inventory', ordinal, None, processed_bytes)
                connection.commit(); batch.clear()
            if batch:
                records, notes, count, size, excluded = self._classify_batch(
                    connection, transaction, workspace, roots, registrations, batch, ordinal)
                connection.executemany('''INSERT INTO manifest
                    (transaction_id,ordinal,path_key,path,item_json,decision,size,directory,row_sha256,row_mac)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''', records)
                ordinal += len(records); candidate_count += count; candidate_bytes += size; excluded_count += excluded
                diagnostics.extend(notes[:max(0, 100 - len(diagnostics))])
            row = self._row(connection, transaction)
            manifest_sha = self._manifest_digest(connection, row)
            connection.execute('''UPDATE transactions SET state='reviewed', manifest_sha256=?,
                candidate_count=?,candidate_bytes=?,excluded_count=? WHERE transaction_id=?''',
                               (manifest_sha, candidate_count, candidate_bytes, excluded_count, transaction))
            connection.execute('DELETE FROM baseline WHERE transaction_id=?', (transaction,))
            self._clear_progress(connection, transaction); connection.commit()
            payload = self._payload(self._row(connection, transaction))
            return self.report('review', payload, manifest_path=str(self.db_path),
                               manifest_ref=f'sqlite:manifest/{transaction}', manifest_sha256=manifest_sha,
                               diagnostics=diagnostics, diagnostics_truncated=ordinal > 100)
        except BaseException:
            try:
                self._clear_progress(connection, transaction, 'interrupted'); connection.commit()
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def inspect(self, transaction, offset=0, limit=100, decision=None):
        if offset < 0 or not 1 <= limit <= 1000:
            raise CleanupError('invalid_page', 'Offset must be non-negative and limit must be 1..1000')
        if decision not in {None, 'candidate', 'excluded'}:
            raise CleanupError('invalid_filter', 'Decision must be candidate or excluded')
        connection = self.connect()
        try:
            row = self._row(connection, transaction)
            if not row['detail_retained']:
                raise CleanupError('detail_compacted', 'Detailed manifest was removed after terminal cleanup')
            clause = ' AND decision=?' if decision else ''
            parameters = (transaction, decision, limit, offset) if decision else (transaction, limit, offset)
            rows = connection.execute(f'''SELECT item_json FROM manifest WHERE transaction_id=?{clause}
                                           ORDER BY ordinal LIMIT ? OFFSET ?''', parameters)
            items = [json.loads(value['item_json']) for value in rows]
            total = connection.execute(f'SELECT COUNT(*) FROM manifest WHERE transaction_id=?{clause}',
                                       (transaction, decision) if decision else (transaction,)).fetchone()[0]
            return self.report('inspect', self._payload(row), items=items, page_items=items,
                               offset=offset, limit=limit,
                               total_items=total, next_offset=offset + len(items) if offset + len(items) < total else None)
        finally:
            connection.close()

    def _ticket_mac(self, ticket):
        fields = [ticket[key] for key in ('ticket_id', 'transaction_id', 'host', 'policy',
                                          'manifest_sha256', 'candidate_count', 'issued_at')]
        return hmac.new(self.key, encoded(fields), 'sha256').hexdigest()

    def ticket(self, transaction, manifest_sha256):
        connection = self.connect()
        try:
            row = self._row(connection, transaction)
            if row['state'] != 'reviewed':
                raise CleanupError('review_required', 'A reviewed snapshot is required; ticket already issued or unavailable')
            actual = self._manifest_digest(connection, row)
            if manifest_sha256 != actual or row['manifest_sha256'] != manifest_sha256:
                raise CleanupError('review_mismatch', 'Pass the hash from the reviewed manifest')
            candidate_count = connection.execute(
                "SELECT COUNT(*) FROM manifest WHERE transaction_id=? AND decision='candidate'", (transaction,)).fetchone()[0]
            ticket_id = secrets.token_hex(32)
            ticket = {'ticket_id': ticket_id, 'transaction_id': transaction, 'host': host(), 'policy': POLICY,
                      'manifest_sha256': manifest_sha256, 'candidate_count': candidate_count, 'issued_at': now()}
            connection.execute('''INSERT INTO tickets
                (ticket_id,transaction_id,host,policy,manifest_sha256,candidate_count,state,issued_at,ticket_mac)
                VALUES (?,?,?,?,?,?,'issued',?,?)''',
                               (ticket_id, transaction, ticket['host'], POLICY, manifest_sha256,
                                candidate_count, ticket['issued_at'], self._ticket_mac(ticket)))
            connection.execute("UPDATE transactions SET state='ticketed',ticket_id=? WHERE transaction_id=?",
                               (ticket_id, transaction)); connection.commit()
            return self.report('ticket', self._payload(self._row(connection, transaction)), ticket_id=ticket_id,
                               manifest_sha256=manifest_sha256, ticket_state='issued')
        finally:
            connection.close()

    def _ticket(self, connection, ticket_id):
        row = connection.execute('SELECT * FROM tickets WHERE ticket_id=?', (ticket_id,)).fetchone()
        if row is None:
            raise CleanupError('ticket_terminal', 'Ticket is unknown, already applied, or revoked')
        ticket = dict(row)
        if (ticket['host'] != host() or ticket['policy'] != POLICY or
                not hmac.compare_digest(self._ticket_mac(ticket), ticket['ticket_mac'])):
            raise CleanupError('invalid_state', 'Ticket host, policy, or integrity validation failed')
        return ticket

    def _verify_ticket_membership(self, connection, ticket, transaction_row):
        if self._manifest_digest(connection, transaction_row) != ticket['manifest_sha256']:
            raise CleanupError('review_mismatch', 'Reviewed manifest changed')
        count = connection.execute(
            "SELECT COUNT(*) FROM manifest WHERE transaction_id=? AND decision='candidate'",
            (ticket['transaction_id'],)).fetchone()[0]
        if count != ticket['candidate_count']:
            raise CleanupError('ticket_mismatch', 'Ticket membership differs from review')

    def _flush_results(self, connection, ticket, batch, processed, processed_bytes):
        if not batch:
            return
        connection.executemany('''UPDATE manifest SET result=?,deleted_bytes=?
            WHERE transaction_id=? AND ordinal=? AND decision='candidate' ''',
                               [(result, count, ticket['transaction_id'], ordinal)
                                for ordinal, result, count in batch])
        added = sum(count for _, _, count in batch)
        connection.execute('UPDATE tickets SET deleted_bytes=deleted_bytes+? WHERE ticket_id=?',
                           (added, ticket['ticket_id']))
        connection.execute('UPDATE transactions SET deleted_bytes=deleted_bytes+? WHERE transaction_id=?',
                           (added, ticket['transaction_id']))
        self._set_progress(connection, ticket['transaction_id'], 'apply', 'deleting', processed,
                           ticket['candidate_count'], processed_bytes)
        connection.commit(); batch.clear()

    def apply(self, ticket_id, dry_run=False):
        if os.name != 'nt':
            raise CleanupError('platform_unsupported', 'Application requires Windows identity and handle disposition')
        connection = self.connect()
        try:
            ticket = self._ticket(connection, ticket_id)
            if ticket['state'] not in {'issued', 'partially_applied'}:
                raise CleanupError('ticket_terminal', 'Ticket is unknown, already applied, or revoked')
            transaction_row = self._row(connection, ticket['transaction_id'])
            self._verify_ticket_membership(connection, ticket, transaction_row)
            if not dry_run:
                self._set_progress(connection, ticket['transaction_id'], 'apply', 'deleting', 0,
                                   ticket['candidate_count'], ticket['deleted_bytes']); connection.commit()
            self.repo_cache.clear()
            diagnostics, result_counts, batch = [], Counter(), []
            processed, processed_bytes = 0, ticket['deleted_bytes']
            rows = connection.execute('''SELECT ordinal,item_json,result,deleted_bytes FROM manifest
                WHERE transaction_id=? AND decision='candidate' ORDER BY directory ASC,LENGTH(path) DESC,path''',
                                      (ticket['transaction_id'],))
            for row in rows:
                prior = row['result']
                if not dry_run and prior and prior not in RETRY:
                    result_counts[prior] += 1; processed += 1
                    continue
                item = json.loads(row['item_json'])
                path = fs.canonical(item['path'])
                reason = self.protection(path) or self.git_reason(path)
                result, count = ('protected', 0) if reason else fs.delete_exact(item, dry_run=dry_run)
                result_counts[result] += 1; processed += 1
                if len(diagnostics) < 100:
                    diagnostics.append({'path': str(path), 'result': result})
                if not dry_run:
                    batch.append((row['ordinal'], result, count)); processed_bytes += count
                    if len(batch) >= BATCH_SIZE:
                        self._flush_results(connection, ticket, batch, processed, processed_bytes)
            if not dry_run:
                self._flush_results(connection, ticket, batch, processed, processed_bytes)
                unresolved = connection.execute("""SELECT COUNT(*) FROM manifest WHERE transaction_id=?
                    AND decision='candidate' AND (result IS NULL OR result IN ('locked','failed','not_empty'))""",
                                                (ticket['transaction_id'],)).fetchone()[0]
                ticket_state = 'applied' if unresolved == 0 else 'partially_applied'
                connection.execute('UPDATE tickets SET state=? WHERE ticket_id=?', (ticket_state, ticket_id))
                connection.execute('UPDATE transactions SET state=? WHERE transaction_id=?',
                                   (ticket_state, ticket['transaction_id']))
                self._clear_progress(connection, ticket['transaction_id']); connection.commit()
            else:
                ticket_state = ticket['state']
            result_counts = self._result_counts(connection, ticket['transaction_id']) if not dry_run else dict(result_counts)
            payload = self._payload(self._row(connection, ticket['transaction_id']))
            current_ticket = self._ticket(connection, ticket_id)
            result = self.report('apply', payload, ticket_id=ticket_id, dry_run=dry_run,
                                 ticket_state=ticket_state, result_counts=result_counts,
                                 deleted_bytes=current_ticket['deleted_bytes'], diagnostics=diagnostics,
                                 diagnostics_truncated=ticket['candidate_count'] > 100,
                                 durability_batch_size=BATCH_SIZE)
            if ticket_state == 'applied' and not dry_run:
                self.finish(connection, payload, current_ticket, result)
            return result
        except BaseException:
            if 'ticket' in locals() and not dry_run:
                try:
                    self._clear_progress(connection, ticket['transaction_id'], 'interrupted'); connection.commit()
                except sqlite3.Error:
                    pass
            raise
        finally:
            connection.close()

    @staticmethod
    def _result_counts(connection, transaction):
        return {row['result']: row['count'] for row in connection.execute('''SELECT result,COUNT(*) count
            FROM manifest WHERE transaction_id=? AND decision='candidate' AND result IS NOT NULL GROUP BY result''',
                                                                           (transaction,))}

    def finish(self, connection, payload, ticket, result):
        transaction = payload['transaction_id']
        counts, completed = result.get('result_counts') or self._result_counts(connection, transaction), now()
        connection.execute('''UPDATE transactions SET state=?,completed_at=?,detail_retained=0,
            result_counts_json=?,deleted_bytes=?,active_operation=NULL,progress_phase='complete',owner_pid=NULL
            WHERE transaction_id=?''',
                           (ticket['state'], completed, encoded(counts).decode(), ticket['deleted_bytes'], transaction))
        connection.execute('UPDATE tickets SET completed_at=? WHERE ticket_id=?', (completed, ticket['ticket_id']))
        connection.execute('DELETE FROM baseline WHERE transaction_id=?', (transaction,))
        connection.execute('DELETE FROM registrations WHERE transaction_id=?', (transaction,))
        connection.execute('DELETE FROM manifest WHERE transaction_id=?', (transaction,))
        old = [row['transaction_id'] for row in connection.execute('''SELECT transaction_id FROM transactions
            WHERE completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT -1 OFFSET 100''')]
        if old:
            connection.executemany('DELETE FROM transactions WHERE transaction_id=?', [(value,) for value in old])
        connection.commit(); connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')

    def revoke(self, ticket_id):
        connection = self.connect()
        try:
            ticket = self._ticket(connection, ticket_id)
            if ticket['state'] not in {'issued', 'partially_applied'}:
                raise CleanupError('ticket_terminal', 'Ticket is already terminal')
            connection.execute("UPDATE tickets SET state='revoked' WHERE ticket_id=?", (ticket_id,))
            connection.execute("UPDATE transactions SET state='revoked' WHERE transaction_id=?",
                               (ticket['transaction_id'],)); connection.commit()
            ticket = self._ticket(connection, ticket_id)
            payload = self._payload(self._row(connection, ticket['transaction_id']))
            result = self.report('revoke', payload, ticket_id=ticket_id, ticket_state='revoked',
                                 deleted_bytes=ticket['deleted_bytes'])
            self.finish(connection, payload, ticket, result)
            return result
        finally:
            connection.close()

    def status(self, transaction=None):
        connection = self.connect()
        try:
            if transaction is None:
                row = connection.execute('''SELECT * FROM transactions ORDER BY
                    CASE WHEN active_operation IS NULL THEN 1 ELSE 0 END, progress_updated_at DESC, created_at DESC
                    LIMIT 1''').fetchone()
                if row is None:
                    return {'ok': True, 'operation': 'status', 'transaction_id': None, 'state': 'empty',
                            'progress': None, 'warnings': [], 'errors': [], 'failure_kind': None}
                if row['host'] != host() or row['policy'] != POLICY:
                    raise CleanupError('invalid_state', 'Host or policy mismatch')
            else:
                row = self._row(connection, transaction)
            payload = self._payload(row)
            ticket = connection.execute('SELECT * FROM tickets WHERE transaction_id=?',
                                        (row['transaction_id'],)).fetchone()
            progress = {'operation': row['active_operation'], 'phase': row['progress_phase'],
                        'processed_items': row['progress_processed'], 'total_items': row['progress_total'],
                        'processed_bytes': row['progress_bytes'], 'updated_at': row['progress_updated_at'],
                        'owner_pid': row['owner_pid']}
            return self.report('status', payload, ticket_id=ticket['ticket_id'] if ticket else None,
                               ticket_state=ticket['state'] if ticket else None,
                               result_counts=(self._result_counts(connection, row['transaction_id'])
                                              if row['detail_retained'] else payload['result_counts']),
                               deleted_bytes=ticket['deleted_bytes'] if ticket else payload['deleted_bytes'],
                               detailed_state_retained=bool(row['detail_retained']), progress=progress,
                               state_database=str(self.db_path), residual_helper_files=[])
        finally:
            connection.close()

    @staticmethod
    def report(operation, payload, items=(), **extra):
        candidates = [item for item in items if item.get('decision') == 'candidate']
        return {'ok': True, 'operation': operation, 'transaction_id': payload['transaction_id'],
                'workspace': payload['workspace'], 'state': payload['state'],
                'discovery_coverage': payload['discovery_coverage'],
                'candidate_count': payload.get('candidate_count', len(candidates)),
                'candidate_bytes': payload.get('candidate_bytes', sum(item.get('size', 0) for item in candidates
                                                                      if not item.get('directory'))),
                'excluded_count': payload.get('excluded_count', len(items) - len(candidates)),
                'result_counts': payload.get('result_counts', {}), 'deleted_bytes': payload.get('deleted_bytes', 0),
                'warnings': [], 'errors': [], 'failure_kind': None, **extra}
