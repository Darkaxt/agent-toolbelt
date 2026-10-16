"""Explicit maintenance of rebuildable recall indexes, never application history."""
from __future__ import annotations

import json
import sqlite3
import stat
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

from . import thread_recall as recall

PLAN_FORMAT = 'codex-thread-recall.maintenance.v1'


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def existing_connection(path, *, readonly=True):
    mode = 'ro' if readonly else 'rw'
    conn = sqlite3.connect('file:' + quote(path.resolve().as_posix(), safe='/:') + '?mode=' + mode,
                           uri=True, timeout=0)
    conn.row_factory = sqlite3.Row
    conn.execute('pragma query_only=' + ('on' if readonly else 'off'))
    conn.execute('pragma foreign_keys=on')
    return conn


def source_state(path):
    if not path:
        return 'missing'
    try:
        info = Path(path).stat()
        return 'available' if stat.S_ISREG(info.st_mode) else 'unreadable'
    except FileNotFoundError:
        return 'missing'
    except OSError:
        return 'unreadable'


def file_identity(path):
    info = path.stat()
    return [info.st_dev, info.st_ino]


def storage(conn, path):
    page_size = conn.execute('pragma page_size').fetchone()[0]
    return {'file_bytes': path.stat().st_size,
            'wal_bytes': Path(str(path) + '-wal').stat().st_size if Path(str(path) + '-wal').exists() else 0,
            'page_count': conn.execute('pragma page_count').fetchone()[0],
            'free_bytes': conn.execute('pragma freelist_count').fetchone()[0] * page_size}


def redundant_indexes(conn):
    """Only the known nonunique, nonpartial prefixes of retained composites."""
    pairs = [(table, f'idx_{table}_value', f'idx_{table}_value_entry', column)
             for table, column in recall.FACET_TABLES.values()]
    pairs.append(('entry_entity_mentions', 'idx_entry_entity_mentions_entity',
                  'idx_entry_entity_mentions_entity_entry', 'entity'))
    removable = []
    for table, prefix, composite, column in pairs:
        indexes = {row['name']: dict(row) for row in conn.execute(f'pragma index_list({table})')}
        if prefix not in indexes or composite not in indexes:
            continue
        prefix_columns = [r['name'] for r in conn.execute(f'pragma index_info({prefix})')]
        composite_columns = [r['name'] for r in conn.execute(f'pragma index_info({composite})')]
        prefix_key = [(r['name'], r['coll'], r['desc']) for r in conn.execute(f'pragma index_xinfo({prefix})') if r['key']]
        composite_key = [(r['name'], r['coll'], r['desc']) for r in conn.execute(f'pragma index_xinfo({composite})') if r['key']]
        if (prefix_columns == [column] and composite_columns == [column, 'entry_id']
                and prefix_key == composite_key[:1]
                and not indexes[prefix]['unique'] and not indexes[prefix]['partial']
                and not indexes[composite]['partial']):
            removable.append(prefix)
    return removable


def thread_snapshot(conn, state, thread_id):
    metadata = recall.cache_metadata_row(conn, thread_id)
    registered = state.execute('select rollout_path from threads where id=?', (thread_id,)).fetchone()
    paths = [row[0] for row in conn.execute('''
        select distinct rp.path from rollout_paths rp where rp.id in (
            select rollout_path_id from entries where thread_id=?
            union select rollout_path_id from rollout_indexes where thread_id=?) order by rp.path
        ''', (thread_id, thread_id))]
    registered_path = registered[0] if registered is not None else None
    count = conn.execute('select count(*) from entries where thread_id=?', (thread_id,)).fetchone()[0]
    snapshot = {'thread_id': thread_id, 'metadata': dict(metadata) if metadata is not None else None,
                'entry_count': count, 'cached_paths': paths, 'registered_path': registered_path}
    snapshot['sources'] = {p: source_state(p) for p in paths}
    if registered_path:
        snapshot['sources'][registered_path] = source_state(registered_path)
    # Without completion metadata these rows cannot serve recall; normal recall
    # must rebuild them from raw source. Do not retain interrupted-build residue.
    states = list(snapshot['sources'].values())
    snapshot['eligible'] = (all(s == 'missing' for s in states)
                            or (metadata is None and count > 0 and 'unreadable' not in states))
    snapshot['reason'] = 'source_unavailable' if metadata is not None else 'orphan_entries'
    return snapshot


def inventory(home):
    home = Path(home).resolve()
    path = recall.cache_db_path(home)
    try:
        with closing(existing_connection(path)) as conn, closing(existing_connection(recall.state_db_path(home))) as state:
            conn.execute('begin')
            state.execute('begin')
            if not recall.table_exists(conn, 'rollout_indexes') or not recall.table_exists(conn, 'entries'):
                return recall.failure('cache_schema_unavailable', 'A current recall cache is required')
            versions = {r[0] for r in conn.execute('select distinct schema_version from rollout_indexes')}
            if versions - {recall.CACHE_SCHEMA_VERSION}:
                return recall.failure('cache_schema_unavailable', 'Refresh incompatible cache schema before maintenance')
            ids = [r[0] for r in conn.execute('select thread_id from rollout_indexes union select distinct thread_id from entries')]
            candidates = []
            preserved_count = 0
            for thread_id in ids:
                snapshot = thread_snapshot(conn, state, thread_id)
                if snapshot['eligible']:
                    candidates.append(snapshot)
                else:
                    preserved_count += 1
            plan = {'ok': True, 'format': PLAN_FORMAT, 'codex_home': str(home),
                    'cache_identity': file_identity(path), 'storage': storage(conn, path),
                    'candidates': candidates, 'preserved_thread_count': preserved_count,
                    'redundant_indexes': redundant_indexes(conn)}
            plan['plan_sha256'] = digest(plan)
            return plan
    except (OSError, sqlite3.Error) as exc:
        return recall.failure('maintenance_inventory_failed', str(exc))


def apply(home, plan, *, compact=False):
    home = Path(home).resolve()
    path = recall.cache_db_path(home)
    unsigned = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if (plan.get('format') != PLAN_FORMAT or plan.get('codex_home') != str(home)
            or digest(unsigned) != plan.get('plan_sha256')):
        return recall.failure('maintenance_plan_invalid', 'Use an unchanged review plan for this exact Codex home')
    result = {'ok': True, 'operation': 'maintain-cache', 'deleted_entries': 0,
              'evicted_threads': [], 'preserved': [], 'removed_indexes': [],
              'application_databases_mutated': False, 'raw_sources_mutated': False,
              'memory_bundles_mutated': False, 'compacted': False}
    try:
        if file_identity(path) != plan['cache_identity']:
            return recall.failure('maintenance_cache_replaced', 'Review the replacement cache before maintenance')
        with closing(existing_connection(path, readonly=False)) as conn, closing(existing_connection(recall.state_db_path(home))) as state:
            result['before'] = storage(conn, path)
            for selected in plan['candidates']:
                thread_id = selected['thread_id']
                lock_state = recall.classify_lock_state(recall.read_lock_metadata(recall.thread_lock_path(home, thread_id)))
                if lock_state['state'] in recall.COLLECTOR_LOCK_SKIP_STATES:
                    result['preserved'].append({'thread_id': thread_id, 'reason': 'busy'})
                    continue
                with recall.ThreadIndexLock(codex_home=home, thread={'id': thread_id, 'rollout_path': 'cache-maintenance'}):
                    try:
                        conn.execute('begin immediate')
                        state.execute('begin')
                        current = thread_snapshot(conn, state, thread_id)
                        if current != selected or not current['eligible']:
                            result['preserved'].append({'thread_id': thread_id, 'reason': 'changed'})
                            conn.rollback()
                            continue
                        # FTS rowids are explicit entry IDs: avoid scanning all FTS
                        # content once per retired cache during a large maintenance run.
                        if recall.fts_table_exists(conn):
                            conn.execute('delete from entries_fts where rowid in (select id from entries where thread_id=?)', (thread_id,))
                        conn.execute('delete from episodes where thread_id=?', (thread_id,))
                        conn.execute('delete from entries where thread_id=?', (thread_id,))
                        conn.execute('delete from rollout_indexes where thread_id=?', (thread_id,))
                        conn.commit()
                        result['deleted_entries'] += current['entry_count']
                        result['evicted_threads'].append(thread_id)
                    finally:
                        state.rollback()
                        conn.rollback()
            allowed_indexes = set(redundant_indexes(conn))
            with conn:
                for name in plan['redundant_indexes']:
                    if name in allowed_indexes:
                        conn.execute(f'drop index {name}')
                        result['removed_indexes'].append(name)
                conn.execute('''delete from rollout_paths where not exists
                    (select 1 from entries where rollout_path_id=rollout_paths.id) and not exists
                    (select 1 from rollout_indexes where rollout_path_id=rollout_paths.id)''')
            if compact:
                # Native VACUUM retains SQLite's own transaction/locking protocol,
                # including existing readers; no database-file replacement or kill.
                if recall.fts_table_exists(conn):
                    conn.execute("insert into entries_fts(entries_fts) values('optimize')")
                    conn.commit()
                conn.execute('vacuum')
                result['compacted'] = True
                result['checkpoint'] = list(conn.execute('pragma wal_checkpoint(truncate)').fetchone())
            result['integrity_check'] = [r[0] for r in conn.execute('pragma quick_check')]
            result['foreign_key_violations'] = [list(r) for r in conn.execute('pragma foreign_key_check')]
            if recall.fts_table_exists(conn):
                conn.execute("insert into entries_fts(entries_fts) values('integrity-check')")
                conn.commit()
                result['fts_integrity_checked'] = True
            result['after'] = storage(conn, path)
            result['ok'] = result['integrity_check'] == ['ok'] and not result['foreign_key_violations']
            if compact and result['checkpoint'][0] != 0:
                result['ok'] = False
                result['error'] = 'checkpoint_busy'
            return result
    except (OSError, sqlite3.Error) as exc:
        result.update(ok=False, error='maintenance_failed', message=str(exc),
                      sqlite_error_name=getattr(exc, 'sqlite_errorname', None))
        return result
