"""Read-only consistency gate for the destination's final takeover records.

Owning-app, semantic acceptance and native recovery/retirement verification remain
the existing workflow's responsibility. This checks their declared record coverage
and content bindings; it does not grant authority or perform those operations.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any


class CompletionError(ValueError):
    kind = 'completion_records_invalid'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompletionError(message)


def source_ids(record: dict[str, Any]) -> list[str]:
    ids = record.get('source_thread_ids')
    if ids is None:
        ids = [record.get('source_thread_id')]
    require(isinstance(ids, list) and bool(ids) and
            all(isinstance(value, str) and value.strip() for value in ids),
            'Record every exact selected source_thread_id/source_thread_ids.')
    require(len(ids) == len(set(ids)), 'Duplicate selected source IDs.')
    primary = record.get('source_thread_id')
    require(primary is None or primary in ids, 'Primary source is outside the selected source set.')
    return ids


def validate_completion(transfer_directory: str | Path, destination_thread_id: str) -> dict[str, Any]:
    root = Path(transfer_directory).resolve(strict=True)
    records = root / 'Records'
    snapshots: dict[Path, bytes] = {}

    def local_path(value: str) -> Path:
        require(isinstance(value, str) and bool(value.strip()), 'Evidence needs an exact local path.')
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        path = Path(os.path.abspath(path))
        # Evidence for this gate is kept inside the explicitly selected activity.
        require(path.is_relative_to(root) and path.resolve().is_relative_to(root),
                'Evidence path escapes the selected activity: ' + str(path))
        current = path
        while current != root:
            require(not current.is_symlink() and not (
                current.exists() and getattr(current.stat(), 'st_file_attributes', 0) & 0x400),
                'Linked evidence is unsupported: ' + str(current))
            current = current.parent
        return path.resolve()

    def content(path: Path) -> bytes:
        path = local_path(str(path))
        if path not in snapshots:
            try:
                require(path.is_file() and path.stat().st_size <= 4 * 1024 * 1024,
                        'Missing or oversized completion metadata: ' + str(path))
                snapshots[path] = path.read_bytes()
            except OSError as error:
                raise CompletionError('Cannot read completion metadata: ' + str(path)) from error
        return snapshots[path]

    def record(name: str) -> dict[str, Any]:
        path = records / name
        try:
            value = json.loads(content(path).decode('utf-8-sig'))
        except (ValueError, UnicodeError) as error:
            if isinstance(error, CompletionError):
                raise
            raise CompletionError('Unreadable JSON metadata: ' + str(path)) from error
        require(isinstance(value, dict), 'Expected a metadata object: ' + str(path))
        return value

    summary = record('migration-result.json')
    acceptance = record('destination-acceptance.json')
    schedules = record('schedule-ledger.json')
    ids = source_ids(summary)
    require(summary.get('destination_thread_id') == destination_thread_id and
            destination_thread_id not in ids and
            acceptance.get('destination_thread_id') == destination_thread_id,
            'Completion/acceptance must identify the actual independent destination.')
    require(set(source_ids(acceptance)) == set(ids), 'Acceptance does not cover the exact selected source set.')
    require(summary.get('status') == 'COMPLETE', 'Migration status is not COMPLETE.')
    require(summary.get('remaining_migration_actions', []) == [], 'Migration still has remaining actions.')
    require(acceptance.get('handoff_ready') is True and acceptance.get('critical_unmapped_objectives') == [],
            'Destination acceptance is not ready or has unmapped critical objectives.')
    handoff = records / 'CONTEXT_TRANSFER.md'
    require(acceptance.get('handoff_sha256') == hashlib.sha256(content(handoff)).hexdigest(),
            'Accepted handoff digest does not match CONTEXT_TRANSFER.md.')
    try:
        stamp = datetime.fromisoformat(summary['completed_at'].replace('Z', '+00:00'))
        require(stamp.utcoffset() is not None, 'completed_at needs its actual timezone.')
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        if isinstance(error, CompletionError):
            raise
        raise CompletionError('Record the actual timezone-aware completed_at; do not invent a historical date.') from error
    require(summary.get('source_archived_verified') is True and
            type(summary.get('residual_rollout_bytes')) is int and summary['residual_rollout_bytes'] == 0,
            'Source archival and zero rollout residuals are not verified.')
    require(isinstance(summary.get('destination_title'), str) and bool(summary['destination_title'].strip()) and
            summary.get('destination_title_verified') is True,
            'Record the destination title verified through the supported task API.')
    require(summary.get('schedule_reconciled') is True, 'Schedule disposition is not reconciled.')
    require(not schedules.get('pending_changes') and not schedules.get('unresolved_dependencies'),
            'Schedule ledger still has pending changes or unresolved dependencies.')
    evidence = summary.get('evidence')
    require(isinstance(evidence, list) and bool(evidence), 'Declare hashed completion evidence.')
    bound: dict[Path, str] = {}
    for item in evidence:
        require(isinstance(item, dict), 'Evidence entries need path and sha256.')
        path = local_path(item.get('path'))
        require(path != (records / 'migration-result.json').resolve(), 'A summary cannot bind its own digest.')
        digest = hashlib.sha256(content(path)).hexdigest()
        require(item.get('sha256') == digest, 'Evidence digest mismatch: ' + str(path))
        require(path not in bound, 'Duplicate evidence path: ' + str(path))
        bound[path] = digest
    for name in ['destination-acceptance.json', 'schedule-ledger.json', 'CONTEXT_TRANSFER.md']:
        require((records / name).resolve() in bound, 'Missing bound completion evidence: ' + name)
    sources = summary.get('sources')
    require(isinstance(sources, list) and len(sources) == len(ids) and
            all(isinstance(row, dict) and isinstance(row.get('source_thread_id'), str) for row in sources) and
            {row.get('source_thread_id') for row in sources} == set(ids),
            'Per-source completion must cover every selected source exactly once.')
    for row in sources:
        require(row.get('retirement_verified') is True and
                type(row.get('residual_rollout_bytes')) is int and row['residual_rollout_bytes'] == 0,
                'Per-source retirement is incomplete: ' + row['source_thread_id'])
        paths = row.get('evidence_paths')
        require(isinstance(paths, list) and bool(paths), 'Bind retirement receipts for ' + row['source_thread_id'])
        require(all(local_path(path) in bound for path in paths),
                'Per-source receipt is not included in hashed evidence: ' + row['source_thread_id'])
    return {'schema': 'agent_toolbelt_context_transfer.completion_validation.v1', 'ok': True,
            'transfer_directory': str(root), 'source_thread_ids': ids,
            'destination_thread_id': destination_thread_id, 'completed_at': summary['completed_at'],
            'migration_result_sha256': hashlib.sha256(content(records / 'migration-result.json')).hexdigest(),
            'evidence': [{'path': str(path), 'sha256': digest} for path, digest in bound.items()],
            'scope': 'Record consistency and declared metadata bindings; native/app/semantic verification remains required.'}
