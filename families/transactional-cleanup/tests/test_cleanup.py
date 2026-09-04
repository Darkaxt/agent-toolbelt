from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_transactional_cleanup import filesystem as fs
from agent_toolbelt_transactional_cleanup.engine import Engine, CleanupError
from agent_toolbelt_transactional_cleanup import cli


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='D:/Temp' if Path('D:/Temp').is_dir() else None)
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'
        self.work.mkdir()
        self.engine = Engine(self.root / 'state')
        self.transaction = self.engine.begin(self.work, [])['transaction_id']

    def tearDown(self):
        self.temp.cleanup()

    def output(self, path=None):
        path = path or self.work / 'build'
        self.engine.register(self.transaction, path, 'compiler-output', 'test compiler output')
        path.mkdir()
        (path / 'a.bin').write_bytes(b'alpha')
        (path / 'b.bin').write_bytes(b'beta')
        return path

    def ticket(self):
        review = self.engine.review(self.transaction)
        return self.engine.ticket(self.transaction, review['manifest_sha256'])['ticket_id']

    def test_begin_and_review_are_non_destructive(self):
        out = self.output()
        result = self.engine.review(self.transaction)
        self.assertEqual(result['candidate_bytes'], 9)
        self.assertTrue((out / 'a.bin').exists())
        self.assertFalse(result['discovery_coverage']['complete_host_coverage'])
        self.assertEqual(result['discovery_coverage']['usn'], 'unavailable_v1')
        self.assertTrue(Path(result['manifest_path']).is_file())

    def test_explicit_roots_do_not_scan_workspace(self):
        target = self.root / 'target'
        target.mkdir()
        with patch.object(self.engine, 'scan', wraps=self.engine.scan) as scan:
            result = self.engine.begin(self.work, [target])
            scan.assert_called_once_with([str(target)])
        self.assertFalse(result['discovery_coverage']['workspace'])
        self.assertEqual(result['discovery_coverage']['known_or_explicit_roots'], [str(target)])
        self.assertEqual(result['workspace'], str(self.work))
        with self.assertRaises(CleanupError):
            self.engine.register(result['transaction_id'], self.work, 'temporary', 'workspace remains protected', True)

    def test_targeted_existing_output_workflow(self):
        target = self.root / 'old-build'
        target.mkdir()
        (target / 'out.bin').write_bytes(b'generated')
        transaction = self.engine.begin(self.work, [target])['transaction_id']
        self.engine.register(transaction, target, 'compiler-output', 'verified disposable fixture', True)
        review = self.engine.review(transaction)
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        self.assertEqual(self.engine.apply(ticket)['deleted_bytes'], 9)
        self.assertFalse(target.exists())
        self.assertTrue(self.work.exists())

    def test_explicit_broad_temp_root_still_protected(self):
        with patch.object(self.engine, 'scan', return_value={}):
            transaction = self.engine.begin(self.work, ['D:/Temp'])['transaction_id']
        with self.assertRaises(CleanupError):
            self.engine.register(transaction, 'D:/Temp', 'temporary', 'cannot approve a whole Temp root', True)

    def test_installed_helper_metadata_is_protected_with_custom_state(self):
        local = self.root / 'local'
        with patch.dict(os.environ, LOCALAPPDATA=str(local)):
            for relative in ('active.json', 'releases/abc/release.json', 'state/key'):
                target = local / 'Tools/transactional-cleanup' / relative
                with self.assertRaises(CleanupError):
                    self.engine.register(self.transaction, target, 'temporary', 'must not authorize helper files', True)

    def test_external_root_registered_before_creation(self):
        out = self.output(self.root / 'external')
        ticket = self.ticket()
        result = self.engine.apply(ticket)
        self.assertFalse(out.exists())
        self.assertEqual(result['deleted_bytes'], 9)

    def test_preexisting_modified_files_are_protected(self):
        (self.work / 'existing.bin').write_bytes(b'original')
        transaction = self.engine.begin(self.work, [])['transaction_id']
        self.engine.register(transaction, self.work / 'existing.bin', 'temporary', 'registered without replacement authority')
        (self.work / 'existing.bin').write_bytes(b'changed')
        review = self.engine.review(transaction)
        self.assertEqual(review['candidate_count'], 0)
        self.assertIn('preexisting_protected', str(review))

    def test_explicit_existing_generated_registration(self):
        out = self.root / 'old-build'
        out.mkdir()
        (out / 'old.bin').write_bytes(b'old')
        self.engine.register(self.transaction, out, 'explicit-generated-output',
                             'verified previous build output with independently installed runtime', regenerated=True)
        result = self.engine.apply(self.ticket())
        self.assertEqual(result['deleted_bytes'], 3)
        self.assertFalse(out.exists())

    def test_new_unattributed_untracked_source_is_protected(self):
        (self.work / 'feature.py').write_text('source')
        result = self.engine.review(self.transaction)
        self.assertEqual(result['candidate_count'], 0)

    def test_same_identity_modified_file_remains_eligible(self):
        out = self.output()
        ticket = self.ticket()
        before = fs.identity(out / 'a.bin')['identity']
        (out / 'a.bin').write_bytes(b'longer generated content')
        self.assertEqual(before, fs.identity(out / 'a.bin')['identity'])
        result = self.engine.apply(ticket)
        self.assertFalse(out.exists())
        self.assertEqual(result['deleted_bytes'], 28)

    def test_new_files_survive_and_nonempty_directory_can_be_retried(self):
        out = self.output()
        ticket = self.ticket()
        (out / 'new.bin').write_bytes(b'new')
        result = self.engine.apply(ticket)
        self.assertTrue((out / 'new.bin').exists())
        self.assertFalse((out / 'a.bin').exists())
        self.assertEqual(result['ticket_state'], 'partially_applied')
        self.assertEqual(result['result_counts']['not_empty'], 1)
        second = self.engine.apply(ticket)
        self.assertEqual(second['deleted_bytes'], 9)
        self.assertTrue((out / 'new.bin').exists())
        (out / 'new.bin').unlink()
        self.assertEqual(self.engine.apply(ticket)['ticket_state'], 'applied')

    def test_replacement_survives(self):
        out = self.output()
        ticket = self.ticket()
        (out / 'a.bin').rename(self.root / 'original.bin')
        (out / 'a.bin').write_bytes(b'alpha')
        result = self.engine.apply(ticket)
        self.assertEqual(result['result_counts']['replaced_after_scan'], 1)
        self.assertTrue((out / 'a.bin').exists())
        self.assertTrue((self.root / 'original.bin').exists())

    def test_dry_run_does_not_consume_ticket(self):
        out = self.output()
        ticket = self.ticket()
        result = self.engine.apply(ticket, True)
        self.assertTrue((out / 'a.bin').exists())
        self.assertEqual(result['ticket_state'], 'issued')
        self.assertEqual(self.engine.apply(ticket)['ticket_state'], 'applied')

    def test_missing_file_and_replay(self):
        out = self.output()
        ticket = self.ticket()
        (out / 'a.bin').unlink()
        result = self.engine.apply(ticket)
        self.assertEqual(result['result_counts']['already_missing'], 1)
        with self.assertRaises(CleanupError):
            self.engine.apply(ticket)
        state = self.engine.status(self.transaction)
        self.assertFalse(state['detailed_state_retained'])
        self.assertFalse(self.engine.path(self.transaction + '.manifest.json').exists())
        self.assertNotIn(str(out), self.engine.path(ticket + '.json').read_text())

    def test_tampered_manifest_and_forged_ticket_fail(self):
        self.output()
        ticket = self.ticket()
        path = self.engine.path(self.transaction + '.manifest.json')
        data = json.loads(path.read_bytes())
        data['payload']['items'][0]['path'] = str(self.root / 'unrelated')
        path.write_text(json.dumps(data))
        with self.assertRaises(CleanupError):
            self.engine.apply(ticket)
        with self.assertRaises(CleanupError):
            self.engine.apply('f' * 64)

    def test_ticket_requires_reviewed_hash_and_registration_freezes(self):
        with self.assertRaises(CleanupError):
            self.engine.ticket(self.transaction, 'unknown')
        self.output()
        self.engine.review(self.transaction)
        with self.assertRaises(CleanupError):
            self.engine.ticket(self.transaction, 'unknown')
        with self.assertRaises(CleanupError):
            self.engine.register(self.transaction, self.work / 'later', 'temporary', 'later')

    def test_dangerous_paths_and_state_protected(self):
        for path in (Path(self.work.anchor), Path.home(), self.engine.root, self.work / '.git', self.work):
            with self.subTest(path=path), self.assertRaises(CleanupError):
                self.engine.register(self.transaction, path, 'temporary', 'not sufficient', regenerated=True)

    def test_git_tracked_and_newly_staged_files_survive(self):
        subprocess.run(['git', 'init', str(self.work)], check=True, capture_output=True)
        out = self.output()
        (out / 'tracked.py').write_text('tracked code')
        subprocess.run(['git', '-C', str(self.work), 'add', 'build/tracked.py'], check=True)
        ticket = self.ticket()
        subprocess.run(['git', '-C', str(self.work), 'add', 'build/a.bin'], check=True)
        self.engine.apply(ticket)
        self.assertTrue((out / 'a.bin').exists())
        self.assertTrue((out / 'tracked.py').exists())
        self.assertFalse((out / 'b.bin').exists())

    def test_hardlinked_file_protected(self):
        out = self.output()
        os.link(out / 'a.bin', self.root / 'other-link')
        result = self.engine.apply(self.ticket())
        self.assertTrue((out / 'a.bin').exists())
        self.assertTrue((self.root / 'other-link').exists())
        self.assertFalse((out / 'b.bin').exists())

    def test_revoke_preserves_files_and_rejects_apply(self):
        out = self.output()
        ticket = self.ticket()
        self.engine.revoke(ticket)
        with self.assertRaises(CleanupError):
            self.engine.apply(ticket)
        self.assertTrue((out / 'a.bin').exists())

    def test_lock_failure_does_not_prevent_other_files_and_retry(self):
        out = self.output()
        ticket = self.ticket()
        if os.name != 'nt':
            self.skipTest('Windows file sharing test')
        with fs.handle(out / 'a.bin', ancestor=True):
            result = self.engine.apply(ticket)
            self.assertEqual(result['result_counts'].get('locked'), 1, result)
            self.assertFalse((out / 'b.bin').exists())
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied')
        self.assertEqual(result['deleted_bytes'], 9)

    def test_cli_json_contains_no_source_content(self):
        (self.work / 'private.txt').write_text('SECRET_SOURCE_MARKER')
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(['--state-root', str(self.root / 'cli-state'), 'begin',
                             '--workspace', str(self.work), '--scan-root', str(self.work)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())['ok'])
        self.assertNotIn('SECRET_SOURCE_MARKER', output.getvalue())

    def test_host_binding_and_unsupported_platform(self):
        self.output()
        ticket = self.ticket()
        with patch('agent_toolbelt_transactional_cleanup.engine.host', return_value='other'):
            with self.assertRaises(CleanupError):
                self.engine.apply(ticket)

    @unittest.skipUnless(os.name == 'nt', 'Windows junctions')
    def test_junction_in_generated_directory_is_not_followed(self):
        import _winapi
        out = self.output()
        target = self.root / 'keep'
        target.mkdir()
        (target / 'important.bin').write_bytes(b'keep')
        link = out / 'linked'
        _winapi.CreateJunction(str(target), str(link))
        try:
            review = self.engine.review(self.transaction)
            self.assertIn('reparse_point', str(review))
            ticket = self.engine.ticket(self.transaction, review['manifest_sha256'])['ticket_id']
            self.engine.apply(ticket)
            self.assertEqual((target / 'important.bin').read_bytes(), b'keep')
        finally:
            link.rmdir()

    @unittest.skipUnless(os.name == 'nt', 'Windows junctions')
    def test_parent_replaced_by_junction_after_review(self):
        import _winapi
        out = self.output()
        ticket = self.ticket()
        moved = self.root / 'moved'
        out.rename(moved)
        _winapi.CreateJunction(str(moved), str(out))
        try:
            result = self.engine.apply(ticket)
            self.assertEqual(result['result_counts']['protected'], 3)
            self.assertTrue((moved / 'a.bin').exists())
        finally:
            out.rmdir()

    def test_hardlink_added_after_review_is_protected(self):
        out = self.output()
        ticket = self.ticket()
        os.link(out / 'a.bin', self.root / 'alias')
        self.engine.apply(ticket)
        self.assertTrue((out / 'a.bin').exists())

    def test_interrupted_apply_replays_only_original_snapshot(self):
        out = self.output()
        ticket = self.ticket()
        original = self.engine.journal_item
        calls = []
        def crash_after_record(t, item):
            original(t, item)
            calls.append(item['path'])
            raise KeyboardInterrupt()
        with patch.object(self.engine, 'journal_item', side_effect=crash_after_record):
            with self.assertRaises(KeyboardInterrupt):
                self.engine.apply(ticket)
        (out / 'concurrent.bin').write_bytes(b'keep')
        fresh = Engine(self.root / 'state')
        result = fresh.apply(ticket)
        self.assertEqual(result['deleted_bytes'], 9)
        self.assertTrue((out / 'concurrent.bin').exists())
        self.assertEqual(fresh.status(self.transaction)['result_counts']['deleted'], 2)

    def test_state_lock_is_process_owned_and_released(self):
        code = '''import sys
from pathlib import Path
from agent_toolbelt_transactional_cleanup.engine import Engine, CleanupError
try:
    with Engine(Path(sys.argv[1])).locked(): pass
except CleanupError as error:
    print(error.kind)
'''
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        with self.engine.locked():
            result = subprocess.run([sys.executable, '-B', '-c', code, str(self.root / 'state')],
                                    capture_output=True, text=True, env=environment, check=True)
        self.assertIn('state_busy', result.stdout)
        with self.engine.locked():
            pass

    def test_non_ntfs_entries_protected_without_fallback_deletion(self):
        out = self.output()
        original = fs.identity
        def fat_identity(path):
            return {**original(path), 'filesystem': 'FAT32'}
        with patch.object(fs, 'identity', side_effect=fat_identity):
            review = self.engine.review(self.transaction)
        self.assertEqual(review['candidate_count'], 0)
        self.assertTrue((out / 'a.bin').exists())

    def test_same_snapshot_scale_and_terminal_detail_cleanup(self):
        out = self.output()
        for index in range(200):
            (out / f'{index}.bin').write_bytes(b'x')
        ticket = self.ticket()
        result = self.engine.apply(ticket)
        self.assertEqual(result['deleted_bytes'], 209)
        self.assertTrue(result['diagnostics_truncated'])
        self.assertLessEqual(len(result['diagnostics']), 100)
        self.assertFalse(out.exists())
        self.assertFalse(self.engine.path(ticket + '.journal').exists())

    def test_interrupted_terminal_cleanup_recovers_through_status(self):
        out = self.output()
        ticket = self.ticket()
        with patch.object(self.engine, 'finish', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.engine.apply(ticket)
        self.assertFalse(out.exists())
        result = self.engine.status(self.transaction)
        self.assertFalse(result['detailed_state_retained'])
        self.assertEqual(result['deleted_bytes'], 9)
        self.assertEqual(result['result_counts']['deleted'], 3)
        self.assertFalse(self.engine.path(self.transaction + '.manifest.json').exists())

    def test_truncated_last_journal_record_is_recovered(self):
        out = self.output()
        ticket = self.ticket()
        with fs.handle(out / 'a.bin', ancestor=True):
            self.engine.apply(ticket)
        with self.engine.path(ticket + '.journal').open('ab') as stream:
            stream.write(b'{"interrupted":')
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied')
        self.assertFalse(out.exists())

    def test_audit_retention_is_bounded(self):
        for index in range(101):
            transaction = f'{index + 1000:032x}'
            ticket = {'ticket_id': f'{index + 1000:064x}', 'state': 'applied'}
            payload = {'transaction_id': transaction}
            result = {'transaction_id': transaction, 'workspace': str(self.work),
                      'deleted_bytes': 0, 'state': 'applied'}
            self.engine.finish(payload, ticket, result)
        summaries = [p for p in self.engine.root.glob('*.json') if len(p.stem) == 32
                     and self.engine.load(p).get('completed_at')]
        self.assertEqual(len(summaries), 100)

    def test_git_failure_protects_registered_outputs(self):
        subprocess.run(['git', 'init', str(self.work)], check=True, capture_output=True)
        self.output()
        with patch('agent_toolbelt_transactional_cleanup.engine.subprocess.run', side_effect=OSError):
            result = self.engine.review(self.transaction)
        self.assertEqual(result['candidate_count'], 0)

    def test_review_root_cannot_become_authority_for_all_temp(self):
        for path in (Path(self.work.anchor), Path('D:/Temp')):
            with self.subTest(path=path), self.assertRaises(CleanupError):
                self.engine.register(self.transaction, path, 'temporary', 'bad root', True)
        scan = self.root / 'known-temp'
        scan.mkdir()
        with patch.dict(os.environ, TEMP=str(scan)):
            transaction = self.engine.begin(self.work, [scan])['transaction_id']
            with self.assertRaises(CleanupError):
                self.engine.register(transaction, scan, 'temporary', 'entire configured Temp root', True)


if __name__ == '__main__':
    unittest.main()
