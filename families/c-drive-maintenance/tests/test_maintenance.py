import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_c_drive_maintenance import maintenance as m


class MaintenanceTests(unittest.TestCase):
    def test_unquoted_commas_and_no_rollup_double_count(self):
        text = ('C:\\,1000,4\nC:\\Users\\demo\\.gradle,600,2\n'
                'C:\\Users\\demo\\.gradle\\caches,500,2\n'
                'C:\\Users\\demo\\AppData\\Local\\Temp,200,2\n'
                'C:\\Users\\demo\\AppData\\Local\\Temp\\a,b,100,1\n')
        result = m.read_inventory(io.StringIO(text), limit=20)
        self.assertEqual(result['valid_rows'], 5)
        self.assertEqual(result['ranked_inclusive_bytes'], 800)
        self.assertEqual(len(result['hotspots']), 2)
        self.assertFalse(result['deletion_authorized'])

    def test_bad_rows_and_nonlocal_paths_are_not_targets(self):
        result = m.read_inventory(io.StringIO('oops\nC:\\a,-1,0\n\\\\server\\share,10,1\n'))
        self.assertEqual(result['invalid_rows'], 3)
        self.assertEqual(result['hotspots'], [])

    def test_ridnacs_drive_root_without_slash(self):
        result = m.read_inventory(io.StringIO('C:,1234,10\n'))
        self.assertEqual(result['valid_rows'], 1)
        self.assertEqual(result['export_root_bytes'], 1234)

    def test_conflicting_duplicates_not_silently_counted(self):
        with self.assertRaises(m.MaintenanceError):
            m.read_inventory(io.StringIO('C:\\Users\\demo\\.gradle,10,1\nC:\\Users\\demo\\.gradle,20,1\n'))

    def test_agent_bundles_match_and_cleanup_does_not_hold_build_gate(self):
        family = Path(__file__).resolve().parents[1]
        codex = family / 'codex/skills/c-drive-maintenance'
        claude = family / 'claude/marketplaces/agent-toolbelt-local/plugins/c-drive-maintenance/skills/c-drive-maintenance'
        for relative in ('SKILL.md', 'agents/openai.yaml', 'references/actions.md',
                         'references/ledger.md', 'scripts/invoke_c_drive_maintenance.py'):
            self.assertEqual((codex / relative).read_bytes(), (claude / relative).read_bytes())
        text = (codex / 'SKILL.md').read_text()
        self.assertIn('Cleanup MUST NOT acquire the Gradle build mutex', text)
        self.assertIn('sent: false', text)
        self.assertIn('Do not abandon all cache cleanup', text)
        self.assertIn('activity_evidence', text)
        self.assertIn('does NOT remove paginated SQLite history', (codex / 'references/actions.md').read_text())

    def test_isolated_install_works_without_repo_bootstrap(self):
        import os
        import subprocess
        family = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home, local = root / 'home', root / 'local'
            command = [sys.executable, '-B', str(family / 'scripts/install.py'),
                       '--home', str(home), '--local-appdata', str(local)]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertTrue(json.loads(result.stdout)['ok'])
            environment = {**os.environ, 'LOCALAPPDATA': str(local)}
            environment.pop('AGENT_TOOLBELT_HOME', None)
            for agent in ('.codex', '.agents', '.claude'):
                wrapper = home / agent / 'skills/c-drive-maintenance/scripts/invoke_c_drive_maintenance.py'
                completed = subprocess.run([sys.executable, '-B', str(wrapper), '--help'],
                                           cwd=root, env=environment, capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn('cleanup-apply', completed.stdout)

    def test_shared_and_native_targets_do_not_use_generic_cleanup(self):
        for path in (r'C:\Users\demo\.gradle\caches\8.6',
                     r'C:\Users\demo\.android\avd\QA.avd\snapshots',
                     r'C:\Users\demo\AppData\Local\Android\Sdk\ndk\29',
                     r'C:\Windows\Installer', r'C:\Users\demo\.codex\archived_sessions',
                     r'C:\ProgramData\NVIDIA Corporation\Downloader'):
            with self.subTest(path=path), self.assertRaises(m.MaintenanceError):
                m.check_cleanup_route(path)

    def test_missing_authorization_never_invokes_cleanup(self):
        with patch.object(m, 'invoke_cleanup') as invoke:
            with self.assertRaises(m.MaintenanceError):
                m.prepare_cleanup('workspace', 'target', 'evidence', confirmed=False)
            invoke.assert_not_called()

    def test_prepare_stops_after_review_and_returns_resumable_id(self):
        responses = [{'ok': True, 'transaction_id': 'tx'}, {'ok': True},
                     {'ok': True, 'manifest_sha256': 'a' * 64, 'transaction_id': 'tx'}]
        with patch.object(m, 'check_cleanup_route'), patch.object(m, 'invoke_cleanup', side_effect=responses) as invoke:
            result = m.prepare_cleanup('workspace', 'target', 'observed build output', confirmed=True)
        self.assertEqual(result['transaction_id'], 'tx')
        self.assertEqual(result['status'], 'awaiting_manifest_review')
        self.assertEqual([c.args[0][0] for c in invoke.call_args_list], ['begin', 'register', 'review'])

    def test_failed_prepare_preserves_transaction(self):
        with patch.object(m, 'check_cleanup_route'), patch.object(m, 'invoke_cleanup', side_effect=[
            {'ok': True, 'transaction_id': 'tx'}, {'ok': False, 'failure_kind': 'target_busy'}]):
            result = m.prepare_cleanup('workspace', 'target', 'evidence', confirmed=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['transaction_id'], 'tx')
        self.assertFalse(result['automatic_revocation'])

    def test_apply_requires_reviewed_hash(self):
        with patch.object(m, 'invoke_cleanup') as invoke:
            with self.assertRaises(m.MaintenanceError):
                m.apply_cleanup('tx', 'wrong')
            invoke.assert_not_called()

    def test_apply_uses_ticket_and_can_dry_run_without_re_review(self):
        with patch.object(m, 'check_cleanup_route'), patch.object(m, 'invoke_cleanup', side_effect=[
            {'ok': True, 'page_items': [{'path': 'target'}], 'next_offset': None},
            {'ok': True, 'ticket_id': 'ticket'}, {'ok': True, 'dry_run': True}]) as invoke:
            result = m.apply_cleanup('tx', 'a' * 64, dry_run=True)
        self.assertTrue(result['ok'])
        self.assertEqual(invoke.call_args_list[-1].args[0], ['apply', '--ticket', 'ticket', '--dry-run'])
        self.assertNotIn('review', [c.args[0][0] for c in invoke.call_args_list])

    def test_missing_manifest_coverage_blocks_application(self):
        with patch.object(m, 'invoke_cleanup', return_value={'ok': True, 'manifest_sha256': 'a' * 64}):
            with self.assertRaises(m.MaintenanceError):
                m.apply_cleanup('tx', 'a' * 64)

    def test_native_targets_in_ticket_manifest_block_application(self):
        with patch.object(m, 'invoke_cleanup', return_value={'ok': True, 'page_items': [
            {'path': r'C:\Users\demo\.gradle\caches\8.6\file'}], 'next_offset': None}) as invoke:
            with self.assertRaises(m.MaintenanceError):
                m.apply_cleanup('tx', 'a' * 64)
            self.assertEqual(invoke.call_count, 1)

    def test_prepare_protocol_failure_preserves_transaction(self):
        with patch.object(m, 'check_cleanup_route'), patch.object(m, 'invoke_cleanup', side_effect=[
            {'ok': True, 'transaction_id': 'tx'}, m.MaintenanceError('invalid response')]):
            result = m.prepare_cleanup('workspace', 'target', 'evidence', confirmed=True)
        self.assertEqual(result['transaction_id'], 'tx')
        self.assertFalse(result['ok'])

    def test_apply_protocol_failure_preserves_ticket(self):
        with patch.object(m, 'invoke_cleanup', side_effect=[
            {'ok': True, 'page_items': [], 'next_offset': None},
            {'ok': True, 'ticket_id': 'ticket'}, m.MaintenanceError('invalid response')]):
            result = m.apply_cleanup('tx', 'a' * 64)
        self.assertEqual(result['ticket_id'], 'ticket')
        self.assertFalse(result['automatic_revocation'])

    def test_installed_cleanup_exact_snapshot_end_to_end(self):
        try:
            m.cleanup_wrapper()
        except m.MaintenanceError:
            self.skipTest('transactional-cleanup installed integration prerequisite absent')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'checkout'
            workspace.mkdir()
            target = root / 'disposable-build'
            target.mkdir()
            payload = target / 'old-output.bin'
            payload.write_bytes(b'fixture output')
            state = root / 'isolated-state'
            review = m.prepare_cleanup(workspace, target, 'Synthetic build fixture generated by this test',
                                       confirmed=True, state_root=state)
            self.assertTrue(review['ok'], review)
            self.assertTrue(payload.exists())
            late = target / 'concurrent-output.bin'
            late.write_bytes(b'new file must survive')
            result = m.apply_cleanup(review['transaction_id'], review['manifest_sha256'], state_root=state)
            self.assertTrue(result['ok'], result)
            self.assertFalse(payload.exists())
            self.assertTrue(late.exists())
            self.assertEqual(result['deleted_bytes'], len(b'fixture output'))

    def test_request_is_bounded_and_requires_verification_not_blind_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            result = m.owner_request(directory, 'task-123', 'gradle', '8.6', '9.8.0')
        self.assertEqual(result['task_id'], 'task-123')
        self.assertFalse(result['sent'])
        self.assertIn('compatibility', result['prompt'])
        self.assertIn('gradle-build-gate', result['prompt'])
        self.assertIn('Do not delete shared caches', result['prompt'])
        self.assertIn('commit', result['prompt'])

    def test_cli_help(self):
        from agent_toolbelt_c_drive_maintenance.cli import parser
        self.assertEqual(parser().parse_args(['inventory', '--csv', 'C.csv']).command, 'inventory')


if __name__ == '__main__':
    unittest.main()
