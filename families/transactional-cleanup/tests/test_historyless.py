from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_transactional_cleanup.engine import Engine, CleanupError


@unittest.skipUnless(os.name == 'nt', 'Windows identity and handle disposition')
class HistorylessFixtureTests(unittest.TestCase):
    """Test-fixture .git markers with no object history, and hard links whose
    every name lies inside the registration."""

    def setUp(self):
        scratch = os.environ.get('TRANSACTIONAL_CLEANUP_TEST_ROOT') or 'D:/Temp'
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'
        self.work.mkdir()
        self.engine = Engine(self.root / 'state')
        self.fixtures = self.root / 'pytest-fixtures'
        self.fixtures.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def fixture_repository(self, name='repo'):
        repository = self.fixtures / name
        git = repository / '.git'
        (git / 'info').mkdir(parents=True)
        (git / 'worktrees' / 'feature').mkdir(parents=True)
        (git / 'objects' / 'pack').mkdir(parents=True)
        (git / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
        (git / 'config').write_text('[core]\n\tbare = false\n', encoding='utf-8')
        (git / 'info' / 'exclude').write_text('*.log\n', encoding='utf-8')
        (git / 'worktrees' / 'feature' / 'commondir').write_text('../..\n', encoding='utf-8')
        (repository / 'tracked.txt').write_text('fixture\n', encoding='utf-8')
        linked = self.fixtures / 'feature'
        linked.mkdir()
        (linked / '.git').write_text(f'gitdir: {git / "worktrees" / "feature"}\n', encoding='utf-8')
        dangling = self.fixtures / 'dangling'
        dangling.mkdir()
        (dangling / '.git').write_text(f'gitdir: {self.fixtures / "gone"}\n', encoding='utf-8')
        return repository

    def run_cleanup(self, allow=True):
        transaction = self.engine.begin(self.work, [self.fixtures])['transaction_id']
        self.engine.register(transaction, self.fixtures, 'explicit-generated-output',
                             'pytest fixture tree from a finished test run', regenerated=True,
                             allow_historyless_git=allow)
        review = self.engine.review(transaction)
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        return transaction, review, ticket

    def test_fixture_markers_are_protected_without_authority(self):
        repository = self.fixture_repository()
        _, review, ticket = self.run_cleanup(allow=False)
        self.engine.apply(ticket)
        self.assertTrue((repository / '.git' / 'HEAD').exists())
        self.assertTrue((repository / 'tracked.txt').exists())
        self.assertTrue((self.fixtures / 'feature' / '.git').exists())

    def test_historyless_fixture_markers_are_removed_with_authority(self):
        self.fixture_repository()
        _, review, ticket = self.run_cleanup()
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied', result)
        self.assertFalse(self.fixtures.exists())

    def test_marker_with_object_history_stays_protected(self):
        repository = self.fixture_repository()
        (repository / '.git' / 'objects' / 'ab').mkdir()
        (repository / '.git' / 'objects' / 'ab' / 'cdef').write_bytes(b'object')
        _, review, ticket = self.run_cleanup()
        self.engine.apply(ticket)
        self.assertTrue((repository / '.git' / 'objects' / 'ab' / 'cdef').exists())
        self.assertTrue((repository / 'tracked.txt').exists())
        # The linked pointer targets a Git directory that now has history.
        self.assertTrue((self.fixtures / 'feature' / '.git').exists())
        self.assertFalse((self.fixtures / 'dangling').exists())

    def test_objects_added_after_review_protect_members_at_apply(self):
        repository = self.fixture_repository()
        _, review, ticket = self.run_cleanup()
        (repository / '.git' / 'objects' / 'pack' / 'pack-1.pack').write_bytes(b'pack')
        self.engine.apply(ticket)
        self.assertTrue((repository / '.git' / 'HEAD').exists())
        self.assertTrue((repository / 'tracked.txt').exists())
        self.assertTrue((repository / '.git' / 'objects' / 'pack' / 'pack-1.pack').exists())

    def test_real_repository_stays_protected(self):
        repository = self.fixtures / 'real'
        repository.mkdir()
        subprocess.run(['git', 'init', str(repository)], check=True, capture_output=True)
        (repository / 'file.txt').write_text('source\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(repository), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(repository), '-c', 'user.name=T', '-c', 'user.email=t@example.invalid',
                        'commit', '-m', 'x'], check=True, capture_output=True)
        _, review, ticket = self.run_cleanup()
        self.engine.apply(ticket)
        self.assertTrue((repository / 'file.txt').exists())
        self.assertTrue((repository / '.git' / 'HEAD').exists())

    def test_authority_requires_regenerated_and_temp_descendant(self):
        transaction = self.engine.begin(self.work, [self.fixtures])['transaction_id']
        with self.assertRaises(CleanupError) as raised:
            self.engine.register(transaction, self.fixtures, 'explicit-generated-output',
                                 'fixtures', allow_historyless_git=True)
        self.assertEqual(raised.exception.kind, 'historyless_git_contract')
        with self.assertRaises(CleanupError) as raised:
            self.engine.register(transaction, Path('D:/Temp'), 'explicit-generated-output',
                                 'fixtures', regenerated=True, allow_historyless_git=True)

    def test_leaf_link_to_repository_is_removed_without_touching_target(self):
        import _winapi
        target = self.root / 'real-target'
        target.mkdir()
        subprocess.run(['git', 'init', str(target)], check=True, capture_output=True)
        (target / 'keep.txt').write_text('keep\n', encoding='utf-8')
        link = self.fixtures / 'marketplace'
        _winapi.CreateJunction(str(target), str(link))
        transaction = self.engine.begin(self.work, [self.fixtures])['transaction_id']
        self.engine.register(transaction, self.fixtures, 'explicit-generated-output', 'fixtures',
                             regenerated=True)
        self.engine.register(transaction, link, 'explicit-generated-output', 'fixture link',
                             regenerated=True, allow_leaf_reparse=True)
        review = self.engine.review(transaction)
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied', result)
        self.assertFalse(os.path.lexists(link))
        self.assertEqual((target / 'keep.txt').read_text(encoding='utf-8'), 'keep\n')
        self.assertTrue((target / '.git' / 'HEAD').exists())

    def test_hardlinks_with_every_name_inside_registration_are_removed(self):
        incremental = self.fixtures / 'incremental'
        incremental.mkdir()
        (incremental / 'a.o').write_bytes(b'object')
        os.link(incremental / 'a.o', incremental / 'b.o')
        _, review, ticket = self.run_cleanup(allow=False)
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied', result)
        self.assertFalse(self.fixtures.exists())

    def test_hardlink_with_a_name_outside_registration_stays_protected(self):
        (self.fixtures / 'a.o').write_bytes(b'object')
        os.link(self.fixtures / 'a.o', self.root / 'outside.o')
        _, review, ticket = self.run_cleanup(allow=False)
        self.engine.apply(ticket)
        self.assertTrue((self.fixtures / 'a.o').exists())
        self.assertEqual((self.root / 'outside.o').read_bytes(), b'object')

    def test_hardlink_name_added_outside_after_review_is_protected(self):
        (self.fixtures / 'a.o').write_bytes(b'object')
        os.link(self.fixtures / 'a.o', self.fixtures / 'b.o')
        _, review, ticket = self.run_cleanup(allow=False)
        os.link(self.fixtures / 'a.o', self.root / 'late.o')
        self.engine.apply(ticket)
        self.assertTrue((self.fixtures / 'a.o').exists() or (self.fixtures / 'b.o').exists())
        self.assertEqual((self.root / 'late.o').read_bytes(), b'object')


if __name__ == '__main__':
    unittest.main()
