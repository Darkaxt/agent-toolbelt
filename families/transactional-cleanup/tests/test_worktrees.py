from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from agent_toolbelt_transactional_cleanup.engine import Engine, CleanupError
from agent_toolbelt_transactional_cleanup import filesystem as fs, worktrees


@unittest.skipUnless(os.name == 'nt', 'Windows exact handle deletion')
class LinkedWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TRANSACTIONAL_CLEANUP_TEST_ROOT', 'D:/Temp'))
        self.base = Path(self.temp.name)
        self.main, self.target, self.sibling = [self.base/name for name in ('main', 'finished', 'sibling')]
        self.main.mkdir()
        self.git(self.main, 'init')
        (self.main/'source.txt').write_text('preserve original\n')
        self.git(self.main, 'add', '.')
        self.git(self.main, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
        self.git(self.main, 'worktree', 'add', '-b', 'finished', str(self.target))
        self.git(self.main, 'worktree', 'add', '-b', 'sibling', str(self.sibling))
        self.engine = Engine(self.base/'state')
        self.processes = patch.object(worktrees.retirement, 'active_processes', return_value=[])
        self.processes.start()
        self.before = self.snapshot(self.main, self.sibling)

    def tearDown(self):
        self.processes.stop()
        self.temp.cleanup()

    @staticmethod
    def git(root, *args):
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                              text=True, check=True).stdout

    @staticmethod
    def snapshot(*roots):
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for root in roots for path in root.rglob('*') if path.is_file()
                and 'worktrees' not in path.parts}

    def prepare(self):
        transaction = self.engine.begin(self.main, [self.target])['transaction_id']
        self.engine.register(transaction, self.target, 'disposable-repository',
            'finished temporary task publication worktree', regenerated=True,
            allow_disposable_repository=True)
        reviewed = self.engine.review(transaction)
        members = self.engine.inspect(transaction, limit=1000)['page_items']
        self.assertTrue(all(item['decision'] == 'candidate' for item in members), members)
        self.assertTrue(all('content_sha256' in item for item in members if not item['directory']))
        self.metadata = Path(next(item['worktree_proof']['metadata'] for item in members if 'worktree_proof' in item))
        self.assertEqual(set(self.engine.transaction_roots(transaction)), {str(self.target), str(self.metadata)})
        return transaction, self.engine.ticket(transaction, reviewed['manifest_sha256'])['ticket_id']

    def test_real_worktree_removal_settles_registration_preserving_shared_repo_and_sibling(self):
        _, ticket = self.prepare()
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied', result)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.metadata.exists())
        listing = self.git(self.main, 'worktree', 'list', '--porcelain')
        self.assertNotIn(self.target.as_posix(), listing)
        self.assertIn(self.sibling.as_posix(), listing)
        self.assertEqual(self.before, self.snapshot(self.main, self.sibling))

    def test_dirty_untracked_locked_and_active_preserved(self):
        for mode in ('dirty', 'untracked', 'locked', 'active'):
            with self.subTest(mode=mode):
                marker = self.target/'.git'
                metadata = Path(marker.read_text().split('gitdir: ', 1)[1].strip())
                if mode == 'dirty':
                    (self.target/'source.txt').write_text('user edit')
                if mode == 'untracked':
                    (self.target/'new.txt').write_text('user data')
                if mode == 'locked':
                    (metadata/'locked').write_text('retained')
                with patch.object(worktrees.retirement, 'active_processes', return_value=[1] if mode == 'active' else []):
                    transaction = self.engine.begin(self.main, [self.target])['transaction_id']
                    with self.assertRaises(CleanupError):
                        self.engine.register(transaction, self.target, 'disposable-repository',
                            'finished worktree', True, allow_disposable_repository=True)
                self.assertTrue(marker.exists())
                self.assertTrue(metadata.exists())
                if mode == 'dirty':
                    (self.target/'source.txt').write_text('preserve original\n')
                if mode == 'untracked':
                    (self.target/'new.txt').unlink()
                if mode == 'locked':
                    (metadata/'locked').unlink()

    def test_replaced_root_does_not_touch_original_or_new_root(self):
        _, ticket = self.prepare()
        original = self.base/'original'
        self.target.rename(original)
        self.target.mkdir()
        (self.target/'new.txt').write_text('keep')
        with self.assertRaises(worktrees.WorktreeError):
            self.engine.apply(ticket)
        self.assertTrue((original/'source.txt').exists())
        self.assertTrue((self.target/'new.txt').exists())

    def test_concurrent_edited_and_new_members_survive_with_git_association(self):
        _, ticket = self.prepare()
        original = fs.delete_exact
        injected = False
        def delete(item, **kwargs):
            nonlocal injected
            if not injected:
                injected = True
                (self.target/'source.txt').write_text('new edit')
                (self.target/'new.txt').write_text('new arrival')
            return original(item, **kwargs)
        with patch.object(fs, 'delete_exact', side_effect=delete):
            result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'partially_applied', result)
        self.assertEqual((self.target/'source.txt').read_text(), 'new edit')
        self.assertTrue((self.target/'.git').exists())
        self.assertTrue(self.metadata.exists())
        self.assertEqual(self.git(self.target, 'rev-parse', '--absolute-git-dir').strip(), self.metadata.as_posix())

    def test_arrival_after_marker_removal_restores_binding_and_resumes_original_ticket(self):
        _, ticket = self.prepare()
        original = fs.delete_exact
        def delete(item, **kwargs):
            result = original(item, **kwargs)
            if Path(item['path']) == self.target/'.git':
                (self.target/'late.txt').write_text('preserve')
            return result
        with patch.object(fs, 'delete_exact', side_effect=delete):
            first = self.engine.apply(ticket)
        self.assertEqual(first['ticket_state'], 'partially_applied', first)
        self.assertTrue((self.target/'.git').exists())
        self.assertTrue(self.metadata.exists())
        self.assertEqual(self.git(self.target, 'rev-parse', '--absolute-git-dir').strip(), self.metadata.as_posix())
        # Simulate the owner removing its newly arrived fixture. The old ticket
        # itself must never adopt/delete this unreviewed member.
        (self.target/'late.txt').unlink()
        second = self.engine.apply(ticket)
        self.assertEqual(second['ticket_state'], 'applied', second)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.metadata.exists())

    def test_replaced_restored_marker_is_not_adopted(self):
        _, ticket = self.prepare()
        original = fs.delete_exact
        def delete(item, **kwargs):
            result = original(item, **kwargs)
            if Path(item['path']) == self.target/'.git':
                (self.target/'late.txt').write_text('keep')
            return result
        with patch.object(fs, 'delete_exact', side_effect=delete):
            self.engine.apply(ticket)
        marker = self.target/'.git'
        text = marker.read_text()
        marker.rename(self.base/'preserved-marker')
        marker.write_text(text)
        with self.assertRaises(worktrees.WorktreeError):
            self.engine.apply(ticket)
        self.assertTrue((self.target/'late.txt').exists())
        self.assertTrue(self.metadata.exists())


if __name__ == '__main__':
    unittest.main()
