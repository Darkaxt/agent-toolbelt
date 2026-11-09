"""Expire deletion authority and compact helper metadata, never target files."""
from datetime import datetime, timedelta, timezone
from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets

from .engine import CleanupError, encoded, host
from . import filesystem as fs

DAYS = 7
SUMMARIES = 100
TERMINAL = {'applied', 'revoked', 'discarded', 'expired'}


def deadline(record):
    dates = [datetime.fromisoformat(record[key]) for key in
             ('created_at', 'issued_at', 'manifest_created_at', 'progress_updated_at', 'updated_at')
             if record.get(key)]
    if not dates or any(value.tzinfo is None for value in dates):
        raise CleanupError('invalid_expiry', 'State has no valid timezone-aware authority timestamp')
    return max(dates) + timedelta(days=DAYS)


def require_current(record):
    if record.get('state') == 'expired' or (
            record.get('state') not in TERMINAL and datetime.now(timezone.utc) >= deadline(record)):
        raise CleanupError('ticket_expired', 'Cleanup authority expired; create and inspect a fresh review. No target files deleted.')


def expire_windows(engine, at):
    expired, busy = [], []
    with closing(engine.connect()) as connection:
        rows = [dict(row) for row in connection.execute('''SELECT t.*,k.issued_at FROM transactions t
            LEFT JOIN tickets k USING(transaction_id) WHERE t.detail_retained=1''')]
    for before in rows:
        if deadline(before) > at:
            continue
        identifier = before['transaction_id']
        try:
            with engine.locked(json.loads(before['roots_json']), operation='expire', transaction=identifier):
                connection = engine.connect()
                try:
                    connection.execute('BEGIN IMMEDIATE')
                    if connection.execute('SELECT 1 FROM transactions WHERE transaction_id=?', (identifier,)).fetchone() is None:
                        connection.rollback()
                        continue
                    row = dict(engine._row(connection, identifier))
                    ticket = connection.execute('SELECT * FROM tickets WHERE transaction_id=?', (identifier,)).fetchone()
                    if ticket:
                        ticket = engine._ticket(connection, ticket['ticket_id'])
                        row['issued_at'] = ticket['issued_at']
                    if not row['detail_retained'] or deadline(row) > at:
                        connection.rollback()
                        continue
                    counts = engine._result_counts(connection, identifier)
                    connection.execute("UPDATE transactions SET state='expired',discard_reason=? WHERE transaction_id=?",
                                       ('Seven-day cleanup authority expired; targets preserved', identifier))
                    if ticket:
                        connection.execute("UPDATE tickets SET state='expired' WHERE ticket_id=?", (ticket['ticket_id'],))
                    engine.finish(connection, engine._payload(row),
                                  {'state': 'expired', 'ticket_id': ticket['ticket_id'] if ticket else None,
                                   'deleted_bytes': row['deleted_bytes']}, {'result_counts': counts})
                    expired.append(identifier)
                finally:
                    connection.close()
        except CleanupError as error:
            if error.kind not in {'target_busy', 'state_busy'}:
                raise
            busy.append(identifier)
    return {'expired': expired, 'live_preserved': busy}


def authenticated(path, engine):
    fs.check_chain(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        from .legacy import open_snapshot
        payload, _ = open_snapshot(path, engine.key, host())
        return payload
    value = json.loads(path.read_text(encoding='utf-8'))
    payload = value['payload']
    signature = hmac.new(engine.key, encoded(payload), 'sha256').hexdigest()
    if payload['host'] != host() or not hmac.compare_digest(signature, value['mac']):
        raise CleanupError('invalid_state', 'Retained JSON state authentication failed: ' + path.name)
    return payload


def save_summary(path, payload, engine):
    fs.check_chain(path)
    pending = path.with_suffix('.' + secrets.token_hex(8) + '.retention.pending')
    value = {'payload': payload, 'mac': hmac.new(engine.key, encoded(payload), 'sha256').hexdigest()}
    try:
        with pending.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def expire_legacy(engine, at):
    expired, busy, terminal = [], [], []
    try:
        with engine._legacy_lock():
            with engine._coordination_lock():
                claims = engine._live_claims()
                for path in engine.root.glob('*.json'):
                    if not re.fullmatch('[a-f0-9]{32}|[a-f0-9]{64}', path.stem):
                        continue
                    payload = authenticated(path, engine)
                    if payload.get('policy') != '1':
                        continue
                    if payload.get('state') in TERMINAL:
                        terminal.append((payload.get('completed_at', payload.get('created_at', '')), path))
                        continue
                    if deadline(payload) > at:
                        continue
                    roots = [fs.canonical(root) for root in payload.get('roots', [])]
                    if not roots and payload.get('transaction_id'):
                        transaction = engine.root / (payload['transaction_id'] + '.json')
                        if transaction != path and transaction.is_file():
                            roots = [fs.canonical(root) for root in authenticated(transaction, engine).get('roots', [])]
                    # Unknown roots cannot safely be expired alongside live legacy work.
                    if any(not roots or engine._roots_overlap(roots, [fs.canonical(r) for r in claim['roots']]) for claim in claims):
                        busy.append(path.stem)
                        continue
                    summary = {key: value for key, value in payload.items() if key not in
                               {'baseline', 'manifest', 'items', 'registrations', 'results'}}
                    summary.update(state='expired', completed_at=at.isoformat(), detail_retained=False,
                                   discard_reason='Seven-day cleanup authority expired; targets preserved')
                    save_summary(path, summary, engine)
                    expired.append(path.stem)
                    terminal.append((summary['completed_at'], path))
                # Authenticated compact terminal receipts only; no pending authority or keys.
                for _, path in sorted(terminal, key=lambda row: row[0], reverse=True)[SUMMARIES:]:
                    fs.check_chain(path)
                    path.unlink()
    except CleanupError as error:
        if error.kind != 'state_busy':
            raise
        busy.append('legacy-operation')
    return {'expired': expired, 'live_preserved': busy}


def expire_android(engine, at):
    from .android import AndroidCleanup, ID
    android = AndroidCleanup(host_engine=engine)
    expired, busy, terminal = [], [], []
    for path in android.root.glob('*.json'):
        if not ID.fullmatch(path.stem):
            continue
        record = android.load(path.stem)
        if 'state' not in record:  # Ticket link; its authoritative transaction is processed below.
            continue
        if record['state'] in TERMINAL:
            terminal.append((record.get('completed_at', record['created_at']), record))
            continue
        if deadline(record) > at:
            continue
        try:
            with engine.locked(android.locks(record['manifest']), operation='adb-expire', transaction=record['transaction_id']):
                record = android.load(path.stem)
                if record['state'] in TERMINAL or deadline(record) > at:
                    continue
                android.compact(record, 'expired')
                android.save(path.stem, record)
                expired.append(path.stem)
                terminal.append((record['completed_at'], record))
        except CleanupError as error:
            if error.kind not in {'target_busy', 'state_busy'}:
                raise
            busy.append(path.stem)
    for _, record in sorted(terminal, key=lambda row: row[0], reverse=True)[SUMMARIES:]:
        with engine.locked(android.locks(record['manifest']), operation='adb-trim'):
            for identifier in (record.get('ticket_id'), record['transaction_id']):
                if identifier:
                    android.record_path(identifier).unlink(missing_ok=True)
    return {'expired': expired, 'live_preserved': busy}


def maintain(engine, at=None):
    at = at or datetime.now(timezone.utc)
    return {'expiry_days': DAYS, 'target_files_deleted': 0,
            'windows': expire_windows(engine, at), 'legacy': expire_legacy(engine, at),
            'android': expire_android(engine, at)}
