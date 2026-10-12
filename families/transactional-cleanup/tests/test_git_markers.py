from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_transactional_cleanup.engine import CleanupError, Engine
from agent_toolbelt_transactional_cleanup import cli


@unittest.skipUnless(os.name == 'nt', 'Windows identity and handle deletion')
class GitMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='D:/Temp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init')
        (self.repo / 'source.txt').write_text('preserve source', encoding='utf-8')
        self.git('add', 'source.txt')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '-m', 'fixture')
        self.marker = self.repo / '.git/fixture-premerge-workflow-tree'
        self.marker.write_text(self.git('rev-parse', 'HEAD^{tree}').strip() + '\n', encoding='ascii')
        self.engine = Engine(self.root / 'state')
        self.transaction = self.engine.begin(self.repo, [self.marker])['transaction_id']

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def authorize(self, path=None, **options):
        path = path or self.marker
        return self.engine.register(self.transaction, path, 'generated-git-marker',
                                    'fixture automation wrote this disposable workflow tree pointer',
                                    regenerated=True, confirm_git_marker=path, **options)

    def review_ticket(self):
        self.authorize()
        review = self.engine.review(self.transaction)
        self.assertEqual(review['candidate_count'], 1)
        return self.engine.ticket(self.transaction, review['manifest_sha256'])['ticket_id']

    def test_exact_marker_deleted_without_touching_source_or_tree_object(self):
        tree = self.marker.read_text().strip()
        ticket = self.review_ticket()
        later = self.marker.parent / 'later-workflow-tree'
        later.write_text(tree, encoding='ascii')
        dry = self.engine.apply(ticket, dry_run=True)
        self.assertEqual(dry['result_counts'], {'eligible': 1})
        self.assertTrue(self.marker.exists())
        result = self.engine.apply(ticket)
        self.assertEqual(result['result_counts'], {'deleted': 1})
        self.assertFalse(self.marker.exists())
        self.assertTrue(later.exists())
        self.assertEqual(self.git('cat-file', '-t', tree).strip(), 'tree')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_default_protection_and_explicit_confirmation_required(self):
        self.assertEqual(self.engine.protection(self.marker), 'filesystem_or_repository_metadata')
        with self.assertRaises(CleanupError):
            self.engine.register(self.transaction, self.marker, 'generated-git-marker',
                                 'fixture', regenerated=True)
        with self.assertRaises(CleanupError):
            self.engine.register(self.transaction, self.marker, 'temporary', 'fixture',
                                 regenerated=True, confirm_git_marker=self.marker)

    def test_native_metadata_directories_and_invalid_contents_rejected(self):
        for relative in ('HEAD', 'config', 'index', 'objects', 'refs', 'hooks',
                         'logs/fixture-workflow-tree'):
            with self.subTest(relative=relative), self.assertRaises((CleanupError, ValueError)):
                self.authorize(self.repo / '.git' / relative)
        self.marker.write_text('not a tree pointer', encoding='ascii')
        with self.assertRaises(CleanupError):
            self.authorize()

    def test_edited_marker_is_preserved(self):
        ticket = self.review_ticket()
        self.marker.write_text('changed after review', encoding='ascii')
        result = self.engine.apply(ticket)
        self.assertEqual(result['result_counts'], {'modified_after_review': 1})
        self.assertTrue(self.marker.exists())

    def test_replaced_marker_is_preserved(self):
        ticket = self.review_ticket()
        original = self.marker.with_suffix('.saved')
        self.marker.rename(original)
        self.marker.write_bytes(original.read_bytes())
        result = self.engine.apply(ticket)
        self.assertEqual(result['result_counts'], {'replaced_after_scan': 1})

    def test_parent_registration_does_not_authorize_git_marker(self):
        transaction = self.engine.begin(self.repo, [self.repo / '.git'])['transaction_id']
        with self.assertRaises(CleanupError):
            self.engine.register(transaction, self.repo / '.git', 'generated-git-marker',
                                 'fixture', regenerated=True, confirm_git_marker=self.repo / '.git')

    def test_hardlinked_marker_is_rejected(self):
        sibling = self.marker.with_suffix('.linked')
        os.link(self.marker, sibling)
        with self.assertRaises(CleanupError):
            self.authorize()

    def test_replaced_repository_ancestor_prevents_application(self):
        ticket = self.review_ticket()
        saved = self.root / 'original-repository'
        self.repo.rename(saved)
        self.repo.mkdir()
        (self.repo / '.git').mkdir()
        self.marker.write_bytes((saved / '.git' / self.marker.name).read_bytes())
        result = self.engine.apply(ticket)
        self.assertEqual(result['result_counts'], {'protected': 1})
        self.assertTrue(self.marker.exists())
        self.assertTrue((saved / 'source.txt').exists())

    def test_linked_worktree_metadata_is_not_eligible(self):
        worktree = self.root / 'linked-worktree'
        self.git('worktree', 'add', '--detach', str(worktree))
        with self.assertRaises(CleanupError):
            self.authorize(worktree / '.git/fixture-workflow-tree')

    def test_cli_accepts_exact_marker_confirmation(self):
        args = cli.parser().parse_args(['register', '--transaction', self.transaction,
            '--path', str(self.marker), '--kind', 'generated-git-marker', '--evidence', 'fixture',
            '--regenerated', '--confirm-git-marker', str(self.marker)])
        self.assertEqual(args.confirm_git_marker, str(self.marker))
