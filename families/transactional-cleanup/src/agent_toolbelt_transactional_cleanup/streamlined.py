"""Two-step and one-step cleanup built from the reviewed engine operations.

`prepare` = begin + register + review, returning a per-path summary and every
exclusion. `finish` = ticket + apply for that exact reviewed manifest.
`remove` = prepare + finish in one call, limited to paths below a recognized
Temp root. Every engine safeguard still applies: protected, tracked, linked,
replaced and new files are excluded or survive exactly as with the step-by-step
commands; only the separate invocations are removed.
"""
from __future__ import annotations

import collections
from pathlib import Path

from . import filesystem as fs
from . import retention
from .engine import CleanupError

# Kinds that need their own evidence documents keep the step-by-step workflow.
SIMPLE_KINDS = ('temporary', 'compiler-output', 'package-cache', 'browser-artifact', 'media-intermediate',
                'test-output', 'generated-report', 'explicit-generated-output', 'disposable-repository')
EXCLUSION_LIMIT = 200


def _paths(values):
    paths = list(dict.fromkeys(str(fs.canonical(value)) for value in values))
    for path in paths:
        if not Path(path).exists():
            raise CleanupError('path_missing', f'Nothing to clean at {path}')
    return paths


def _workspace(engine, workspace):
    # The workspace is protected from registration. A neutral default (the
    # helper's own state directory) never overlaps a scratch target.
    return str(fs.canonical(workspace)) if workspace else str(engine.root)


def _summary(engine, transaction, paths):
    """Per-path candidate counts and every exclusion, read from the frozen manifest."""
    per_path = {path: {'path': path, 'files': 0, 'directories': 0, 'bytes': 0} for path in paths}
    excluded, reasons, offset = [], collections.Counter(), 0
    while offset is not None:
        page = engine.inspect(transaction, offset, 1000)
        for item in page['page_items']:
            if item['decision'] == 'excluded':
                reasons[item.get('reason')] += 1
                if len(excluded) < EXCLUSION_LIMIT:
                    excluded.append({key: item.get(key) for key in ('path', 'reason', 'size', 'directory')})
                continue
            owner = next((path for path in paths if fs.within(Path(item['path']), Path(path))), None)
            if owner is None:
                continue
            entry = per_path[owner]
            if item.get('directory'):
                entry['directories'] += 1
            else:
                entry['files'] += 1
                entry['bytes'] += int(item.get('size') or 0)
        offset = page['next_offset']
    return {'paths': list(per_path.values()), 'excluded': excluded,
            'excluded_reasons': dict(reasons), 'excluded_truncated': sum(reasons.values()) > len(excluded)}


def prepare(engine, paths, evidence, kind='temporary', workspace=None):
    if kind not in SIMPLE_KINDS:
        raise CleanupError('use_step_commands', f'Kind {kind} needs the step-by-step workflow and its evidence options')
    paths = _paths(paths)
    workspace = _workspace(engine, workspace)
    with engine.locked(paths, operation='prepare'):
        transaction = engine.begin(workspace, paths)['transaction_id']
    roots = engine.transaction_roots(transaction)
    with engine.locked(roots, operation='prepare', transaction=transaction):
        for path in paths:
            engine.register(transaction, path, kind, evidence, regenerated=True,
                            allow_disposable_repository=kind == 'disposable-repository')
        reviewed = engine.review(transaction)
        summary = _summary(engine, transaction, paths)
    reviewed.update(operation='prepare', **summary)
    reviewed['next'] = (f'finish --transaction {transaction} --manifest-sha256 {reviewed["manifest_sha256"]}'
                        if reviewed['candidate_count'] else f'discard --transaction {transaction} --reason "nothing to delete"')
    return reviewed


def finish(engine, transaction, manifest_sha256, dry_run=False):
    roots = engine.transaction_roots(transaction)
    with engine.locked(roots, operation='finish', transaction=transaction):
        row = engine.txn(transaction)
        retention.require_current(row)
        if row['state'] == 'reviewed':
            ticket = engine.ticket(transaction, manifest_sha256)['ticket_id']
        elif row['state'] in {'ticketed', 'partially_applied'} and row['manifest_sha256'] == manifest_sha256:
            ticket = row['ticket_id']  # resume after a dry run or a retryable partial apply
        else:
            raise CleanupError('review_required', f'Transaction is {row["state"]}; prepare a fresh review')
        result = engine.apply(ticket, dry_run)
    result['operation'] = 'finish'
    result['ticket_id'] = ticket
    if result.get('state') == 'partially_applied':
        result['next'] = f'finish --transaction {transaction} --manifest-sha256 {manifest_sha256}'
    return result


def remove(engine, paths, evidence, kind='temporary', dry_run=False):
    temp_roots = engine._temp_roots()
    for path in _paths(paths):
        if not any(Path(path) != root and fs.within(Path(path), root) for root in temp_roots):
            raise CleanupError('use_prepare',
                               f'One-step remove is limited to folders below a Temp root; use prepare/finish for {path}')
    prepared = prepare(engine, paths, evidence, kind)
    if not prepared['candidate_count']:
        engine.discard(prepared['transaction_id'], 'remove found nothing eligible to delete')
        prepared.update(operation='remove', next=None)
        return prepared
    result = finish(engine, prepared['transaction_id'], prepared['manifest_sha256'], dry_run)
    result.update(operation='remove', paths=prepared['paths'], excluded=prepared['excluded'],
                  excluded_reasons=prepared['excluded_reasons'], excluded_truncated=prepared['excluded_truncated'])
    return result
