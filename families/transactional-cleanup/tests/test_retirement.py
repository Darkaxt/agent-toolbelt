from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_transactional_cleanup.engine import Engine, CleanupError
from agent_toolbelt_transactional_cleanup.retirement import RetirementError


@unittest.skipUnless(os.name == 'nt', 'Windows exact-file retirement')
class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='D:/Temp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'current'; self.workspace.mkdir()
        self.repo = self.root / 'obsolete'; self.repo.mkdir()
        self.git('init', str(self.repo))
        (self.repo / 'source.txt').write_text('retained source\n', encoding='utf-8')
        self.git('-C', str(self.repo), 'add', '.')
        self.git('-C', str(self.repo), '-c', 'user.name=Retirement Test',
                 '-c', 'user.email=test@example.invalid', 'commit', '-m', 'source')
        self.recovery = self.root / 'recovery.git'
        self.git('clone', '--mirror', '--no-hardlinks', str(self.repo), str(self.recovery))
        self.evidence = self.root / 'retirement.json'
        self.record = {
            'version': 1, 'repository': str(self.repo),
            'authorization': 'Explicitly retire this test-owned obsolete checkout',
            'recovery_repository': str(self.recovery),
            'recovery_instructions': 'git clone recovery.git restored; restore original refs from signed proof',
            'consumer_review': {'checked_at': '2026-10-11T00:00:00Z',
                                'ownership': 'No task owns the obsolete fixture',
                                'schedulers_services': 'No schedule or service references it',
                                'dependencies': 'Current workspace has no dependency on it',
                                'active_consumers': []}}
        self.evidence.write_text(json.dumps(self.record), encoding='utf-8')
        self.engine = Engine(self.root / 'state')
        self.tx = self.engine.begin(self.workspace, [self.repo])['transaction_id']
        self.processes = patch('agent_toolbelt_transactional_cleanup.retirement.active_processes',
                               return_value=[])
        self.processes.start(); self.addCleanup(self.processes.stop)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout

    def register(self, **kwargs):
        options = dict(regenerated=True, retirement_evidence=str(self.evidence),
                       confirm_retire_repository=str(self.repo))
        options.update(kwargs)
        return self.engine.register(self.tx, self.repo, 'retired-repository',
                                    'Explicit obsolete test checkout retirement', **options)

    def ticket(self):
        self.register()
        review = self.engine.review(self.tx)
        return self.engine.ticket(self.tx, review['manifest_sha256'])['ticket_id']

    def test_retirement_outside_temp_contract_and_exact_deletion(self):
        with patch.object(self.engine, '_temp_roots', return_value=[self.root / 'other-temp']):
            ticket = self.ticket()
            dry = self.engine.apply(ticket, dry_run=True)
            self.assertEqual(dry['deleted_bytes'], 0)
            self.assertTrue(self.repo.exists())
            result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied', result)
        self.assertFalse(self.repo.exists())
        self.assertTrue(self.recovery.exists())
        self.git('clone', str(self.recovery), str(self.root / 'restored'))
        self.assertEqual((self.root / 'restored/source.txt').read_text(), 'retained source\n')

    def test_authority_and_exact_confirmation_required(self):
        for options in ({'regenerated': False}, {'retirement_evidence': None},
                        {'confirm_retire_repository': str(self.workspace)}):
            with self.subTest(options=options), self.assertRaises((CleanupError, RetirementError)):
                self.register(**options)

    def test_dirty_untracked_ignored_and_unrecovered_commits_rejected(self):
        source = self.repo / 'source.txt'
        source.write_text('local changes')
        with self.assertRaises((CleanupError, RetirementError)) as error:
            self.register()
        self.assertEqual(error.exception.kind, 'retirement_local_changes')
        source.write_text('retained source\n')
        extra = self.repo / 'untracked.txt'; extra.write_text('preserve')
        with self.assertRaises((CleanupError, RetirementError)):
            self.register()
        extra.unlink()
        (self.repo / '.git/info/exclude').write_text('ignored.txt\n')
        extra = self.repo / 'ignored.txt'; extra.write_text('preserve ignored')
        with self.assertRaises((CleanupError, RetirementError)):
            self.register()
        extra.unlink()
        source.write_text('unrecovered work\n')
        self.git('-C', str(self.repo), 'add', '.')
        self.git('-C', str(self.repo), '-c', 'user.name=Retirement Test',
                 '-c', 'user.email=test@example.invalid', 'commit', '-m', 'local-only')
        with self.assertRaises((CleanupError, RetirementError)) as error:
            self.register()
        self.assertEqual(error.exception.kind, 'retirement_recovery_incomplete')

    def test_additional_worktree_blocks_retirement(self):
        self.git('-C', str(self.repo), 'worktree', 'add', '-b', 'dependent', str(self.root / 'dependent'))
        with self.assertRaises((CleanupError, RetirementError)) as error:
            self.register()
        self.assertEqual(error.exception.kind, 'retirement_worktrees')

    def test_unanchored_recovery_objects_do_not_prove_durable_recovery(self):
        branch = self.git('-C', str(self.repo), 'symbolic-ref', 'HEAD').strip()
        self.git('-C', str(self.recovery), 'update-ref', '-d', branch)
        with self.assertRaises((CleanupError, RetirementError)) as error:
            self.register()
        self.assertEqual(error.exception.kind, 'retirement_recovery_incomplete')

    def test_active_process_and_owner_attestation_block(self):
        with patch('agent_toolbelt_transactional_cleanup.retirement.active_processes',
                   return_value=[{'pid': 123, 'started_at': 'fixture'}]):
            with self.assertRaises((CleanupError, RetirementError)) as error:
                self.register()
            self.assertEqual(error.exception.kind, 'retirement_active_consumers')
        self.record['consumer_review']['active_consumers'] = ['current task']
        self.evidence.write_text(json.dumps(self.record))
        with self.assertRaises((CleanupError, RetirementError)):
            self.register()

    def test_git_change_after_review_blocks_before_any_deletion(self):
        ticket = self.ticket()
        (self.repo / 'source.txt').write_text('new local work')
        with self.assertRaises((CleanupError, RetirementError)):
            self.engine.apply(ticket)
        self.assertTrue((self.repo / '.git/config').exists())

    def test_concurrent_file_survives_and_partial_retry_works(self):
        ticket = self.ticket()
        # A new untracked file must prevent the first destructive application.
        new_file = self.repo / 'new.txt'; new_file.write_text('keep')
        with self.assertRaises((CleanupError, RetirementError)):
            self.engine.apply(ticket)
        new_file.unlink()
        from agent_toolbelt_transactional_cleanup import filesystem as fs
        original = fs.delete_exact
        created = False
        def create_during_apply(item, dry_run=False):
            nonlocal created
            if not created:
                new_file.write_text('keep concurrent file')
                created = True
            return original(item, dry_run=dry_run)
        with patch.object(fs, 'delete_exact', side_effect=create_during_apply):
            result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'partially_applied')
        self.assertTrue(new_file.exists())
        retry = self.engine.apply(ticket)
        self.assertEqual(retry['ticket_state'], 'partially_applied')
        self.assertEqual(new_file.read_text(), 'keep concurrent file')

    def test_same_identity_edit_during_apply_survives(self):
        ticket = self.ticket()
        from agent_toolbelt_transactional_cleanup import filesystem as fs
        original = fs.delete_exact
        source = self.repo / 'source.txt'
        def edit_during_apply(item, dry_run=False):
            if Path(item['path']) == source:
                source.write_text('preserve concurrent source edit')
            return original(item, dry_run=dry_run)
        with patch.object(fs, 'delete_exact', side_effect=edit_during_apply):
            result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'partially_applied')
        self.assertEqual(source.read_text(), 'preserve concurrent source edit')


if __name__ == '__main__':
    unittest.main()
