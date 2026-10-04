from __future__ import annotations

import io
import json
import os
import sqlite3
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

    def disposable_repository(self, name='validation-clone'):
        repository = self.root / name
        repository.mkdir()
        subprocess.run(['git', 'init', str(repository)], check=True, capture_output=True)
        (repository / 'Packs').mkdir()
        (repository / 'Packs' / 'artifact.yml').write_text('name: fixture\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(repository), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(repository), '-c', 'user.name=Cleanup Tests',
                        '-c', 'user.email=cleanup@example.invalid', 'commit', '-m', 'fixture'],
                       check=True, capture_output=True)
        return repository

    def ticket(self):
        review = self.engine.review(self.transaction)
        return self.engine.ticket(self.transaction, review['manifest_sha256'])['ticket_id']

    def test_begin_and_review_are_non_destructive(self):
        out = self.output()
        result = self.engine.review(self.transaction)
        self.assertEqual(result['candidate_bytes'], 9)
        self.assertTrue((out / 'a.bin').exists())
        self.assertFalse(result['discovery_coverage']['complete_host_coverage'])
        self.assertEqual(result['discovery_coverage']['usn'], 'unavailable_v2')
        self.assertTrue(Path(result['manifest_path']).is_file())
        self.assertEqual(result['manifest_ref'], f'sqlite:manifest/{self.transaction}')

    @unittest.skipUnless(os.name == 'nt', 'Windows exact-file application')
    def test_disjoint_writer_between_apply_batches_cannot_stale_the_read_snapshot(self):
        out = self.output()
        for number in range(6):
            (out / f'{number}.bin').write_bytes(b'x')
        ticket = self.ticket()
        other = self.root / 'independent'; other.mkdir()
        other_transaction = self.engine.begin(self.work, [other])['transaction_id']
        delete_exact = fs.delete_exact
        calls = 0
        def delete_with_independent_commit(item, dry_run=False):
            nonlocal calls
            calls += 1
            if calls == 3:
                writer = self.engine.connect()
                try:
                    writer.execute('UPDATE transactions SET progress_processed=1 WHERE transaction_id=?',
                                   (other_transaction,))
                    writer.commit()
                finally:
                    writer.close()
            return delete_exact(item, dry_run=dry_run)
        with patch('agent_toolbelt_transactional_cleanup.engine.BATCH_SIZE', 2), \
             patch.object(fs, 'delete_exact', side_effect=delete_with_independent_commit):
            try:
                result = self.engine.apply(ticket)
            except sqlite3.OperationalError as error:
                self.fail(f'Apply retained stale read snapshot: {error.sqlite_errorname} ({error.sqlite_errorcode})')
        self.assertEqual(result['ticket_state'], 'applied')
        self.assertEqual(result['deleted_bytes'], 15)
        self.assertFalse(out.exists())
        self.assertEqual(self.engine.txn(other_transaction)['state'], 'open')

    def test_apply_pages_preserve_exact_child_before_parent_order(self):
        out = self.output()
        nested = out / 'nested' / 'deeper'
        nested.mkdir(parents=True)
        (nested / 'long-name.bin').write_bytes(b'x')
        self.ticket()
        connection = self.engine.connect()
        try:
            expected = [row[0] for row in connection.execute('''SELECT ordinal FROM manifest
                WHERE transaction_id=? AND decision='candidate'
                ORDER BY directory ASC,LENGTH(path) DESC,path''', (self.transaction,))]
            with patch('agent_toolbelt_transactional_cleanup.engine.BATCH_SIZE', 2):
                actual = [row['ordinal'] for row in self.engine._apply_rows(connection, self.transaction)]
            self.assertEqual(actual, expected)
            plan = connection.execute('''EXPLAIN QUERY PLAN SELECT ordinal FROM manifest
                WHERE transaction_id=? AND decision='candidate'
                ORDER BY directory,-LENGTH(path),path LIMIT 2''', (self.transaction,)).fetchall()
            self.assertTrue(any('manifest_apply_order' in row['detail'] for row in plan))
            self.assertFalse(any('TEMP B-TREE' in row['detail'] for row in plan))
        finally:
            connection.close()

    def test_new_page_revalidates_signed_members_before_deleting(self):
        out = self.output()
        for number in range(4):
            (out / f'{number}.bin').write_bytes(b'x')
        ticket = self.ticket()
        connection = self.engine.connect()
        try:
            victim = connection.execute('''SELECT ordinal,path FROM manifest
                WHERE transaction_id=? AND decision='candidate'
                ORDER BY directory,-LENGTH(path),path LIMIT 1 OFFSET 2''', (self.transaction,)).fetchone()
        finally:
            connection.close()
        flush = self.engine._flush_results
        changed = False
        def flush_and_tamper(*args):
            nonlocal changed
            flush(*args)
            if not changed:
                writer = self.engine.connect()
                try:
                    writer.execute('UPDATE manifest SET item_json=? WHERE transaction_id=? AND ordinal=?',
                                   ('{}', self.transaction, victim['ordinal']))
                    writer.commit()
                finally:
                    writer.close()
                changed = True
        with patch('agent_toolbelt_transactional_cleanup.engine.BATCH_SIZE', 2), \
             patch.object(self.engine, '_flush_results', side_effect=flush_and_tamper):
            with self.assertRaises(CleanupError) as raised:
                self.engine.apply(ticket)
        self.assertEqual(raised.exception.kind, 'review_mismatch')
        self.assertTrue(Path(victim['path']).exists())

    def test_membership_removal_during_dry_run_cannot_report_success(self):
        self.output()
        ticket = self.ticket()
        delete_exact = fs.delete_exact
        changed = False
        def check_and_remove_member(item, dry_run=False):
            nonlocal changed
            if not changed:
                writer = self.engine.connect()
                try:
                    writer.execute('''DELETE FROM manifest WHERE transaction_id=? AND ordinal=
                        (SELECT MAX(ordinal) FROM manifest WHERE transaction_id=?)''',
                                   (self.transaction, self.transaction))
                    writer.commit()
                finally:
                    writer.close()
                changed = True
            return delete_exact(item, dry_run=dry_run)
        with patch.object(fs, 'delete_exact', side_effect=check_and_remove_member):
            with self.assertRaises(CleanupError) as raised:
                self.engine.apply(ticket, dry_run=True)
        self.assertEqual(raised.exception.kind, 'review_mismatch')

    def test_cli_sqlite_errors_are_structured_without_automatic_revocation(self):
        for name, number, kind in (('SQLITE_BUSY_SNAPSHOT', 517, 'state_database_busy'),
                                   ('SQLITE_LOCKED', 6, 'state_database_busy'),
                                   ('SQLITE_CORRUPT', 11, 'state_database_error')):
            with self.subTest(name=name):
                error = sqlite3.OperationalError('private internal SQL must not be exposed')
                error.sqlite_errorcode, error.sqlite_errorname = number, name
                output = io.StringIO()
                with patch.object(cli, 'Engine', side_effect=error), redirect_stdout(output):
                    result = cli.main(['status'])
                data = json.loads(output.getvalue())
                self.assertEqual(result, 1)
                self.assertEqual(data['failure_kind'], kind)
                self.assertEqual(data['sqlite_error_name'], name)
                self.assertEqual(data['sqlite_error_code'], number)
                self.assertFalse(data['automatic_revocation'])
                self.assertEqual(data['retry_after_diagnosis'], kind == 'state_database_busy')
                self.assertNotIn('private internal', output.getvalue())

    def test_review_matching_does_not_compare_every_registration_for_each_file(self):
        for index in range(133):
            self.engine.register(self.transaction, self.work / f'build-{index}', 'compiler-output', f'output {index}')
        entries = [{'path': str(self.work / f'build-{i % 133}' / 'obj' / f'{i}.bin'),
                    'excluded': 'synthetic_inventory'} for i in range(500)]
        with patch.object(self.engine, 'scan', return_value=iter(entries)), patch.object(fs, 'within', wraps=fs.within) as within:
            review = self.engine.review(self.transaction)
        self.assertLess(within.call_count, 5000, 'Matching must not rescan all 133 registrations for every entry')
        manifest = self.engine.inspect(self.transaction, limit=500)
        self.assertEqual([item['evidence'] for item in manifest['page_items']],
                         [f'output {i % 133}' for i in range(500)])

    def test_review_matching_preserves_deepest_first_tie_and_component_boundaries(self):
        out = self.output()
        nested = out / 'nested'
        nested.mkdir()
        (nested / 'one.bin').write_bytes(b'x')
        unrelated = self.work / 'building'
        unrelated.mkdir()
        (unrelated / 'source.py').write_text('keep')
        self.engine.register(self.transaction, nested, 'test-output', 'deep first')
        self.engine.register(self.transaction, str(nested).upper(), 'temporary', 'duplicate must not win')
        review = self.engine.review(self.transaction)
        items = {i['path']: i for i in self.engine.inspect(self.transaction, limit=100)['page_items']}
        self.assertEqual(items[str(nested / 'one.bin')]['evidence'], 'deep first')
        self.assertEqual(items[str(out / 'a.bin')]['evidence'], 'test compiler output')
        self.assertEqual(items[str(unrelated / 'source.py')]['decision'], 'excluded')

    def test_explicit_roots_do_not_scan_workspace(self):
        target = self.root / 'target'
        target.mkdir()
        with patch.object(self.engine, 'scan', wraps=self.engine.scan) as scan:
            result = self.engine.begin(self.work, [target])
            self.assertEqual(scan.call_args_list[0].args[0], [str(target)])
        self.assertFalse(result['discovery_coverage']['workspace'])
        self.assertEqual(result['discovery_coverage']['known_or_explicit_roots'], [str(target)])
        self.assertEqual(result['workspace'], str(self.work))
        with self.assertRaises(CleanupError):
            self.engine.register(result['transaction_id'], self.work, 'temporary', 'workspace remains protected', True)

    def test_default_begin_scans_only_workspace(self):
        with patch.object(self.engine, 'scan', wraps=self.engine.scan) as scan:
            result = self.engine.begin(self.work)
            self.assertEqual(scan.call_args_list[0].args[0], [str(self.work)])
        self.assertEqual(result['discovery_coverage']['known_or_explicit_roots'], [str(self.work)])

    def test_known_temp_roots_require_explicit_opt_in(self):
        known = self.root / 'known-temp'
        known.mkdir()
        with patch.object(self.engine, '_known_temp_roots', return_value=[str(known)]):
            result = self.engine.begin(self.work, include_known_temp_roots=True)
        self.assertEqual(result['discovery_coverage']['known_or_explicit_roots'],
                         [str(self.work), str(known)])

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
        with self.assertRaises(CleanupError):
            self.engine.inspect(self.transaction)
        self.assertNotIn(str(out).encode(), self.engine.db_path.read_bytes())

    def test_tampered_manifest_and_forged_ticket_fail(self):
        self.output()
        ticket = self.ticket()
        connection = self.engine.connect()
        try:
            connection.execute("UPDATE manifest SET item_json='{}' WHERE transaction_id=? AND ordinal=0",
                               (self.transaction,))
            connection.commit()
        finally:
            connection.close()
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

    def test_disposable_repository_requires_explicit_authority(self):
        repository = self.disposable_repository()
        transaction = self.engine.begin(self.work, [repository])['transaction_id']
        with self.assertRaises(CleanupError):
            self.engine.register(transaction, repository, 'disposable-repository',
                                 'temporary Demisto validation clone', regenerated=True)

    def test_disposable_repository_removes_tracked_files_and_git_metadata(self):
        repository = self.disposable_repository()
        transaction = self.engine.begin(self.work, [repository])['transaction_id']
        self.engine.register(transaction, repository, 'disposable-repository',
                             'temporary Demisto validation clone', regenerated=True,
                             allow_disposable_repository=True)
        review = self.engine.review(transaction)
        manifest = self.engine.inspect(transaction, limit=1000)['page_items']
        self.assertGreater(review['candidate_count'], 3)
        self.assertTrue(any('.git' in Path(item['path']).parts for item in manifest
                            if item['decision'] == 'candidate'))
        self.assertTrue(any(item['git_status'] == 'disposable_repository_authorized'
                            for item in manifest if item['decision'] == 'candidate'))
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied', result)
        self.assertFalse(repository.exists())

    def test_disposable_repository_keeps_concurrent_new_file(self):
        repository = self.disposable_repository()
        transaction = self.engine.begin(self.work, [repository])['transaction_id']
        self.engine.register(transaction, repository, 'disposable-repository',
                             'temporary Demisto validation clone', regenerated=True,
                             allow_disposable_repository=True)
        review = self.engine.review(transaction)
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        concurrent = repository / 'arrived-after-review.txt'
        concurrent.write_text('keep', encoding='utf-8')
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'partially_applied', result)
        self.assertTrue(concurrent.exists())
        self.assertFalse((repository / 'Packs' / 'artifact.yml').exists())

    def test_disposable_repository_requires_exact_temp_scan_root_and_gates(self):
        repository = self.disposable_repository()
        cases = [
            ('wrong-kind', True, 'explicit-generated-output'),
            ('missing-regenerated', False, 'disposable-repository'),
        ]
        for label, regenerated, kind in cases:
            with self.subTest(label=label):
                transaction = self.engine.begin(self.work, [repository])['transaction_id']
                with self.assertRaises(CleanupError):
                    self.engine.register(transaction, repository, kind, 'temporary validation clone',
                                         regenerated=regenerated, allow_disposable_repository=True)
        broad_transaction = self.engine.begin(self.work, [self.root])['transaction_id']
        with self.assertRaises(CleanupError):
            self.engine.register(broad_transaction, repository, 'disposable-repository',
                                 'temporary validation clone', regenerated=True,
                                 allow_disposable_repository=True)

        outside_transaction = self.engine.begin(self.work, [repository])['transaction_id']
        with patch.object(self.engine, '_temp_roots', return_value=[self.root / 'other-temp']):
            with self.assertRaises(CleanupError) as error:
                self.engine.register(outside_transaction, repository, 'disposable-repository',
                                     'repository outside the configured temp boundary', regenerated=True,
                                     allow_disposable_repository=True)
        self.assertEqual(error.exception.kind, 'disposable_repository_location')

    def test_disposable_repository_root_replacement_fails_closed(self):
        repository = self.disposable_repository()
        transaction = self.engine.begin(self.work, [repository])['transaction_id']
        self.engine.register(transaction, repository, 'disposable-repository',
                             'temporary Demisto validation clone', regenerated=True,
                             allow_disposable_repository=True)
        review = self.engine.review(transaction)
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        original = repository.with_name(repository.name + '-original')
        repository.rename(original)
        repository.mkdir()
        subprocess.run(['git', 'init', str(repository)], check=True, capture_output=True)
        with self.assertRaises(CleanupError) as error:
            self.engine.apply(ticket)
        self.assertEqual(error.exception.kind, 'disposable_repository_replaced')
        self.assertTrue(repository.exists())
        self.assertTrue((original / 'Packs' / 'artifact.yml').exists())

    def test_linked_worktree_marker_is_not_disposable_repository(self):
        repository = self.root / 'linked-worktree'
        repository.mkdir()
        (repository / '.git').write_text('gitdir: D:/outside/worktrees/fixture\n', encoding='utf-8')
        transaction = self.engine.begin(self.work, [repository])['transaction_id']
        with self.assertRaises(CleanupError):
            self.engine.register(transaction, repository, 'disposable-repository',
                                 'linked worktree must remain protected', regenerated=True,
                                 allow_disposable_repository=True)

    def test_hardlinked_file_protected(self):
        out = self.output()
        os.link(out / 'a.bin', self.root / 'other-link')
        result = self.engine.apply(self.ticket())
        self.assertTrue((out / 'a.bin').exists())
        self.assertTrue((self.root / 'other-link').exists())
        self.assertFalse((out / 'b.bin').exists())

    def test_explicit_hardlink_authority_deletes_only_ticketed_name(self):
        external = self.root / 'external-link.bin'
        out = self.work / 'build'
        self.engine.register(self.transaction, out, 'compiler-output', 'hard-linked build output',
                             allow_hardlinks=True)
        out.mkdir()
        target = out / 'native.obj'
        target.write_bytes(b'native')
        os.link(target, external)
        result = self.engine.apply(self.ticket())
        self.assertEqual(result['ticket_state'], 'applied', result)
        self.assertFalse(target.exists())
        self.assertEqual(external.read_bytes(), b'native')

    @unittest.skipUnless(os.name == 'nt', 'Windows junctions')
    def test_explicit_leaf_reparse_authority_removes_link_not_target(self):
        import _winapi
        out = self.work / 'build'
        target = self.root / 'target'
        target.mkdir()
        (target / 'keep.bin').write_bytes(b'keep')
        self.engine.register(self.transaction, out, 'compiler-output', 'linked build output',
                             allow_leaf_reparse=True)
        out.mkdir()
        link = out / 'linked'
        _winapi.CreateJunction(str(target), str(link))
        result = self.engine.apply(self.ticket())
        self.assertEqual(result['ticket_state'], 'applied', result)
        self.assertFalse(os.path.lexists(link))
        self.assertEqual((target / 'keep.bin').read_bytes(), b'keep')

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
        with patch.object(self.engine, '_flush_results', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.engine.apply(ticket)
        out.mkdir(exist_ok=True)
        (out / 'concurrent.bin').write_bytes(b'keep')
        fresh = Engine(self.root / 'state')
        result = fresh.apply(ticket)
        self.assertEqual(result['deleted_bytes'], 0)
        self.assertTrue((out / 'concurrent.bin').exists())
        counts = fresh.status(self.transaction)['result_counts']
        self.assertEqual(counts['already_missing'], 2)
        self.assertEqual(counts['replaced_after_scan'], 1)

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

    def test_disjoint_root_locks_can_run_concurrently_but_overlaps_are_rejected(self):
        first = self.root / 'first'
        second = self.root / 'second'
        nested = first / 'nested'
        first.mkdir()
        second.mkdir()
        code = '''import sys
from pathlib import Path
from agent_toolbelt_transactional_cleanup.engine import Engine
with Engine(Path(sys.argv[1])).locked([Path(sys.argv[2])], operation='review', transaction='child'):
    print('locked', flush=True)
    sys.stdin.readline()
'''
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        process = subprocess.Popen([sys.executable, '-B', '-c', code, str(self.root / 'state'), str(first)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=environment)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            with self.engine.locked([second], operation='review', transaction='parent'):
                pass
            with self.assertRaises(CleanupError) as raised:
                with self.engine.locked([nested], operation='apply', transaction='overlap'):
                    pass
            self.assertEqual(raised.exception.kind, 'target_busy')
        finally:
            process.stdin.write('\n')
            process.stdin.flush()
            process.wait(timeout=10)
        stderr = process.stderr.read()
        process.stdin.close(); process.stdout.close(); process.stderr.close()
        self.assertEqual(process.returncode, 0, stderr)

    def test_dead_process_claim_is_reclaimed(self):
        target = self.root / 'target'
        target.mkdir()
        code = '''import sys
from pathlib import Path
from agent_toolbelt_transactional_cleanup.engine import Engine
with Engine(Path(sys.argv[1])).locked([Path(sys.argv[2])], operation='review', transaction='child'):
    print('locked', flush=True)
    sys.stdin.readline()
'''
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        process = subprocess.Popen([sys.executable, '-B', '-c', code, str(self.root / 'state'), str(target)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=environment)
        self.assertEqual(process.stdout.readline().strip(), 'locked')
        process.kill()
        process.wait(timeout=10)
        process.stdin.close(); process.stdout.close(); process.stderr.close()
        with self.engine.locked([target], operation='review', transaction='replacement'):
            pass
        self.assertEqual(list((self.root / 'state' / 'claims').iterdir()), [])

    def test_status_is_lock_free_and_reports_progress(self):
        connection = self.engine.connect()
        try:
            self.engine._set_progress(connection, self.transaction, 'review', 'inventory', 256, None, 4096)
            connection.commit()
        finally:
            connection.close()
        with self.engine.locked():
            result = self.engine.status(self.transaction)
        self.assertEqual(result['progress']['operation'], 'review')
        self.assertEqual(result['progress']['processed_items'], 256)
        self.assertEqual(result['progress']['processed_bytes'], 4096)

    def test_begin_progress_is_visible_during_streaming_inventory(self):
        observed = []
        def inventory(_roots):
            for index in range(300):
                if index == 1:
                    observed.append(self.engine.status())
                yield {'path': str(self.work / f'synthetic-{index}'), 'excluded': 'synthetic'}
        with patch.object(self.engine, 'scan', side_effect=inventory):
            self.engine.begin(self.work)
        self.assertEqual(observed[0]['progress']['operation'], 'begin')
        self.assertEqual(observed[0]['progress']['phase'], 'inventory')

    def test_apply_commits_results_in_bounded_batches_not_per_item(self):
        out = self.output()
        for index in range(513):
            (out / f'{index}.bin').write_bytes(b'x')
        ticket = self.ticket()
        with patch.object(self.engine, '_flush_results', wraps=self.engine._flush_results) as flush:
            result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied')
        self.assertEqual(flush.call_count, 3)

    def test_cli_accepts_explicit_link_authorities_and_manifest_paging(self):
        registered = cli.parser().parse_args([
            'register', '--transaction', 'a' * 32, '--path', str(self.work / 'build'),
            '--kind', 'compiler-output', '--evidence', 'fixture',
            '--allow-hardlinks', '--allow-leaf-reparse'])
        self.assertTrue(registered.allow_hardlinks)
        self.assertTrue(registered.allow_leaf_reparse)
        disposable = cli.parser().parse_args([
            'register', '--transaction', 'a' * 32, '--path', str(self.work / 'clone'),
            '--kind', 'disposable-repository', '--evidence', 'validation clone',
            '--regenerated', '--allow-disposable-repository'])
        self.assertTrue(disposable.allow_disposable_repository)
        inspected = cli.parser().parse_args([
            'inspect', '--transaction', 'a' * 32, '--offset', '20', '--limit', '50',
            '--decision', 'candidate'])
        self.assertEqual((inspected.offset, inspected.limit, inspected.decision), (20, 50, 'candidate'))

    def test_non_ntfs_entries_protected_without_fallback_deletion(self):
        out = self.output()
        original = fs.identity
        def fat_identity(path, **kwargs):
            return {**original(path, **kwargs), 'filesystem': 'FAT32'}
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
        self.assertLess(self.engine.db_path.stat().st_size, 2 * 1024 * 1024)

    def test_interrupted_terminal_cleanup_recovers_through_status(self):
        out = self.output()
        ticket = self.ticket()
        with patch.object(self.engine, 'finish', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.engine.apply(ticket)
        self.assertFalse(out.exists())
        result = self.engine.status(self.transaction)
        self.assertTrue(result['detailed_state_retained'])
        self.assertEqual(result['deleted_bytes'], 9)
        self.assertEqual(result['result_counts']['deleted'], 3)
        self.assertEqual(result['progress']['phase'], 'interrupted')

    def test_uncommitted_result_batch_is_recovered(self):
        out = self.output()
        ticket = self.ticket()
        with patch.object(self.engine, '_flush_results', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.engine.apply(ticket)
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied')
        self.assertFalse(out.exists())

    def test_audit_retention_is_bounded(self):
        connection = self.engine.connect()
        try:
            template = connection.execute('SELECT * FROM transactions WHERE transaction_id=?',
                                          (self.transaction,)).fetchone()
            columns = list(template.keys())
            values = [template[column] for column in columns]
            for index in range(101):
                values[columns.index('transaction_id')] = f'{index + 1000:032x}'
                values[columns.index('completed_at')] = f'2026-01-01T00:00:{index:03d}Z'
                connection.execute(f"INSERT INTO transactions ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                   values)
            connection.execute('DELETE FROM transactions WHERE transaction_id=?', (self.transaction,))
            old = [row[0] for row in connection.execute('''SELECT transaction_id FROM transactions
                WHERE completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT -1 OFFSET 100''')]
            connection.executemany('DELETE FROM transactions WHERE transaction_id=?', [(value,) for value in old])
            connection.commit()
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM transactions').fetchone()[0], 100)
        finally:
            connection.close()

    def test_git_failure_protects_registered_outputs(self):
        subprocess.run(['git', 'init', str(self.work)], check=True, capture_output=True)
        self.output()
        with patch('agent_toolbelt_transactional_cleanup.engine.subprocess.run', side_effect=OSError):
            result = self.engine.review(self.transaction)
        self.assertEqual(result['candidate_count'], 0)

    def test_empty_git_marker_does_not_block_explicit_non_repository_output(self):
        (self.work / '.git').mkdir()
        out = self.work / '.codex-temp' / 'go-build-cache'
        out.mkdir(parents=True)
        (out / 'cache.bin').write_bytes(b'generated')
        transaction = self.engine.begin(self.work, [out])['transaction_id']
        self.engine.register(transaction, out, 'explicit-generated-output',
                             'verified disposable Go build cache', regenerated=True)
        result = self.engine.review(transaction)
        self.assertEqual(result['candidate_bytes'], 9)
        self.assertEqual(result['candidate_count'], 2)

    def test_empty_git_files_in_generated_output_are_ticketed(self):
        out = self.work / 'cache'
        out.mkdir()
        (out / '.git').touch()
        (out / '.gitignore').touch()
        transaction = self.engine.begin(self.work, [out])['transaction_id']
        self.engine.register(transaction, out, 'explicit-generated-output',
                             'test-owned disposable cache', regenerated=True)
        result = self.engine.review(transaction)
        self.assertEqual(result['candidate_count'], 3)
        ticket = self.engine.ticket(transaction, result['manifest_sha256'])['ticket_id']
        self.assertEqual(self.engine.apply(ticket)['ticket_state'], 'applied')
        self.assertFalse(out.exists())

    def test_empty_git_directory_in_generated_output_is_ticketed(self):
        out = self.work / 'cache'
        (out / '.git').mkdir(parents=True)
        transaction = self.engine.begin(self.work, [out])['transaction_id']
        self.engine.register(transaction, out, 'explicit-generated-output',
                             'test-owned disposable cache', regenerated=True)
        review = self.engine.review(transaction)
        self.assertEqual(review['candidate_count'], 2)
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        self.assertEqual(self.engine.apply(ticket)['ticket_state'], 'applied')
        self.assertFalse(out.exists())

    def test_nonempty_git_marker_remains_protected(self):
        out = self.work / 'cache'
        out.mkdir()
        (out / '.git').write_text('gitdir: ../real-repository', encoding='utf-8')
        transaction = self.engine.begin(self.work, [out])['transaction_id']
        with self.assertRaises(CleanupError):
            self.engine.register(transaction, out, 'explicit-generated-output',
                                 'test-owned cache', regenerated=True)

    def test_linked_empty_git_marker_is_not_exempt(self):
        marker = self.work / '.git'
        marker.touch()
        with patch.object(fs, 'check_chain', side_effect=ValueError('linked ancestor')):
            self.assertFalse(self.engine._empty_git_marker(marker))

    def test_empty_marker_nested_inside_repository_metadata_stays_protected(self):
        marker = self.work / '.git' / 'objects' / '.git'
        marker.parent.mkdir(parents=True)
        marker.touch()
        self.assertEqual(self.engine.protection(marker), 'filesystem_or_repository_metadata')

    def test_marker_that_gains_repository_content_is_not_deleted(self):
        out = self.work / 'cache'
        out.mkdir()
        marker = out / '.git'
        marker.touch()
        transaction = self.engine.begin(self.work, [out])['transaction_id']
        self.engine.register(transaction, out, 'explicit-generated-output',
                             'test-owned cache', regenerated=True)
        review = self.engine.review(transaction)
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        marker.write_text('gitdir: ../real-repository', encoding='utf-8')
        self.engine.apply(ticket)
        self.assertTrue(marker.exists())

    def test_empty_marker_inside_real_repository_does_not_bypass_tracking(self):
        subprocess.run(['git', 'init', str(self.work)], check=True, capture_output=True)
        out = self.work / 'cache'
        out.mkdir()
        (out / '.git').touch()
        (out / '.gitignore').touch()
        subprocess.run(['git', '-C', str(self.work), 'add', 'cache/.gitignore'],
                       check=True, capture_output=True)
        self.assertEqual(self.engine.git_reason(out / '.gitignore'), 'git_tracked')

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
