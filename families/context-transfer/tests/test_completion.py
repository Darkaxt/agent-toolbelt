from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
WRAPPER = Path(os.environ.get('CONTEXT_TRANSFER_TEST_WRAPPER', str(
    REPO / 'families/context-transfer/codex/skills/context-transfer/scripts/invoke_context_transfer.py')))


class CompletionRecordsTests(unittest.TestCase):
    def setUp(self):
        # The outer task transaction owns these fixtures; no live chats are used.
        self.root = Path(tempfile.mkdtemp(prefix='completion-', dir=os.environ['CONTEXT_TRANSFER_TEST_TEMP']))
        self.records = self.root / 'Records'
        self.records.mkdir()

    def write(self, name, value):
        path = self.records / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def fixture(self, ids=('source',)):
        handoff = self.records / 'CONTEXT_TRANSFER.md'
        handoff.write_text('# accepted test handoff', encoding='utf-8')
        acceptance = {'source_thread_ids': list(ids), 'destination_thread_id': 'destination',
                      'handoff_ready': True, 'critical_unmapped_objectives': [],
                      'handoff_sha256': hashlib.sha256(handoff.read_bytes()).hexdigest()}
        self.write('destination-acceptance.json', acceptance)
        self.write('schedule-ledger.json', {'associations': [], 'disposition': 'None found in test fixture'})
        sources = []
        for source in ids:
            path = self.write(source + '-retirement.json', {'fixture': True, 'source': source})
            sources.append({'source_thread_id': source, 'retirement_verified': True,
                            'residual_rollout_bytes': 0, 'evidence_paths': ['Records/' + path.name]})
        summary = {'status': 'COMPLETE', 'source_thread_ids': list(ids),
                   'destination_thread_id': 'destination', 'completed_at': '2026-10-16T00:00:00+03:00',
                   'source_archived_verified': True, 'residual_rollout_bytes': 0,
                   'destination_title': 'Actual activity', 'destination_title_verified': True,
                   'schedule_reconciled': True, 'sources': sources,
                   'evidence': [{'path': 'Records/' + p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                                for p in sorted(self.records.iterdir())
                                if p.name not in ('migration-result.json', 'completion-validation.json')]}
        self.write('migration-result.json', summary)
        return summary

    def invoke(self, ok=True, destination='destination', extra=()):
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        # Repository wrapper finds its checkout; installed wrappers exercise the selected runtime.
        env.pop('AGENT_TOOLBELT_HOME', None)
        result = subprocess.run([sys.executable, '-B', str(WRAPPER), 'validate-completion',
                                 '--transfer-directory', str(self.root),
                                 '--destination-thread-id', destination, *map(str, extra)], capture_output=True, text=True, env=env)
        value = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
        self.assertEqual(value['ok'], ok, value)
        return value

    def test_single_and_aggregate_completion_preserve_historical_time_and_read_only_inputs(self):
        for ids in [('source',), ('research', 'implementation')]:
            with self.subTest(ids=ids):
                self.setUp()
                self.fixture(ids)
                before = {p: p.read_bytes() for p in self.records.iterdir()}
                value = self.invoke()['result']
                self.assertEqual(value['source_thread_ids'], list(ids))
                self.assertEqual(value['completed_at'], '2026-10-16T00:00:00+03:00')
                self.assertEqual(before, {p: p.read_bytes() for p in self.records.iterdir()})

    def test_missing_canonical_record_is_not_completed(self):
        self.fixture()
        (self.records / 'migration-result.json').rename(self.records / 'legacy-result.json')
        value = self.invoke(ok=False)
        self.assertEqual(value['error']['kind'], 'completion_records_invalid')
        self.assertIn('migration-result.json', value['error']['message'])

    def test_changed_bound_evidence_is_rejected(self):
        self.fixture()
        (self.records / 'source-retirement.json').write_text('changed', encoding='utf-8')
        self.assertIn('digest', self.invoke(ok=False)['error']['message'])

    def test_partial_or_truthy_claims_and_missing_group_source_fail(self):
        for field, value in [('status', 'PARTIAL'), ('source_archived_verified', 'true'),
                             ('residual_rollout_bytes', False), ('destination_title_verified', False),
                             ('schedule_reconciled', False), ('sources', [])]:
            with self.subTest(field=field):
                self.setUp()
                summary = self.fixture(('research', 'implementation'))
                summary[field] = value
                self.write('migration-result.json', summary)
                self.invoke(ok=False)

    def test_wrong_destination_and_changed_acceptance_fail(self):
        self.fixture()
        self.invoke(ok=False, destination='another-owner')
        self.write('destination-acceptance.json', {'handoff_ready': False})
        self.invoke(ok=False)

    def test_missing_bound_schedule_or_handoff_and_critical_objective_fail(self):
        for name in ['schedule-ledger.json', 'CONTEXT_TRANSFER.md']:
            with self.subTest(name=name):
                self.setUp()
                summary = self.fixture()
                summary['evidence'] = [r for r in summary['evidence'] if not r['path'].endswith(name)]
                self.write('migration-result.json', summary)
                self.invoke(ok=False)
        self.setUp()
        self.fixture()
        acceptance = json.loads((self.records / 'destination-acceptance.json').read_text())
        acceptance['critical_unmapped_objectives'] = ['required objective']
        self.write('destination-acceptance.json', acceptance)
        self.invoke(ok=False)

    def test_pending_schedule_and_partial_source_cannot_hide_behind_complete_summary(self):
        self.fixture()
        self.write('schedule-ledger.json', {'pending_changes': ['retarget required']})
        self.assertIn('Schedule ledger', self.invoke(ok=False)['error']['message'])
        summary = self.fixture()
        summary['sources'][0]['retirement_verified'] = False
        self.write('migration-result.json', summary)
        self.assertIn('retirement is incomplete', self.invoke(ok=False)['error']['message'])

    def test_output_cannot_overwrite_inputs_and_evidence_cannot_escape_activity(self):
        summary = self.fixture()
        before = (self.records / 'migration-result.json').read_bytes()
        self.invoke(ok=False, extra=['--output', self.records / 'migration-result.json'])
        self.assertEqual(before, (self.records / 'migration-result.json').read_bytes())
        outside = self.root.parent / (self.root.name + '-outside.json')
        outside.write_text('{}', encoding='utf-8')
        summary['evidence'].append({'path': str(outside), 'sha256': hashlib.sha256(outside.read_bytes()).hexdigest()})
        self.write('migration-result.json', summary)
        self.assertIn('escapes', self.invoke(ok=False)['error']['message'])

    def test_validation_receipt_binds_actual_summary_and_preserves_inputs(self):
        self.fixture()
        output = self.records / 'completion-validation.json'
        packet = self.invoke(extra=['--output', output])
        saved = json.loads(output.read_text())
        self.assertEqual(saved, packet['result'])
        self.assertEqual(saved['migration_result_sha256'], hashlib.sha256((self.records / 'migration-result.json').read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
