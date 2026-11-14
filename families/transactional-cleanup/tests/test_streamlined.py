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
from agent_toolbelt_transactional_cleanup import cli, streamlined
from agent_toolbelt_transactional_cleanup.engine import CleanupError, Engine


@unittest.skipUnless(os.name == 'nt', 'Deletion requires Windows handle disposition')
class StreamlinedCleanupTests(unittest.TestCase):
    def setUp(self):
        scratch = os.environ.get('TRANSACTIONAL_CLEANUP_TEST_ROOT')
        self.temp = tempfile.TemporaryDirectory(dir=scratch or ('D:/Temp' if Path('D:/Temp').is_dir() else None))
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.engine = Engine(self.state)

    def tearDown(self):
        self.temp.cleanup()

    def scratch(self, name='scratch'):
        folder = self.root / name
        (folder / 'nested').mkdir(parents=True)
        (folder / 'a.bin').write_bytes(b'alpha')
        (folder / 'nested' / 'b.bin').write_bytes(b'beta')
        return folder

    def run_cli(self, *arguments):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = cli.main(['--state-root', str(self.state), *arguments])
        return code, json.loads(stream.getvalue())

    def test_prepare_skips_the_baseline_and_such_snapshots_accept_only_regenerated_roots(self):
        folder = self.scratch()
        prepared = streamlined.prepare(self.engine, [folder], 'test scratch')
        self.assertEqual(prepared['discovery_coverage']['baseline'], 'skipped_regenerated_only')
        self.assertEqual(prepared['candidate_count'], 4)
        other = self.scratch('other')
        transaction = self.engine.begin(self.state, [other], baseline=False)['transaction_id']
        with self.assertRaises(CleanupError) as raised:
            self.engine.register(transaction, other, 'temporary', 'not regenerated')
        self.assertEqual(raised.exception.kind, 'regenerated_required')
        self.engine.register(transaction, other, 'temporary', 'regenerated scratch', regenerated=True)
        with self.assertRaises(CleanupError):
            self.engine.begin(self.state, None, baseline=False)

    def test_prepare_summarizes_and_finish_deletes_the_reviewed_manifest(self):
        folder = self.scratch()
        prepared = streamlined.prepare(self.engine, [folder], 'test scratch')
        self.assertEqual(prepared['state'], 'reviewed')
        self.assertEqual(prepared['paths'], [{'path': str(folder), 'files': 2, 'directories': 2, 'bytes': 9}])
        self.assertEqual(prepared['excluded'], [])
        self.assertIn(prepared['manifest_sha256'], prepared['next'])
        self.assertTrue(folder.exists(), 'prepare must not delete anything')
        finished = streamlined.finish(self.engine, prepared['transaction_id'], prepared['manifest_sha256'])
        self.assertEqual(finished['state'], 'applied')
        self.assertFalse(folder.exists())

    def test_finish_rejects_a_hash_that_was_not_reviewed(self):
        folder = self.scratch()
        prepared = streamlined.prepare(self.engine, [folder], 'test scratch')
        with self.assertRaises(CleanupError):
            streamlined.finish(self.engine, prepared['transaction_id'], '0' * 64)
        self.assertTrue(folder.exists())

    def test_remove_deletes_several_scratch_paths_in_one_call(self):
        first, second = self.scratch('one'), self.scratch('two')
        code, result = self.run_cli('remove', '--path', str(first), '--path', str(second),
                                    '--evidence', 'test scratch from this run')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['operation'], 'remove')
        self.assertEqual(result['state'], 'applied')
        self.assertEqual(result['deleted_bytes'], 18)
        self.assertFalse(first.exists()); self.assertFalse(second.exists())

    def test_remove_dry_run_keeps_files_and_finish_resumes_the_same_ticket(self):
        folder = self.scratch()
        dry = streamlined.remove(self.engine, [folder], 'test scratch', dry_run=True)
        self.assertTrue((folder / 'a.bin').exists())
        transaction = dry['transaction_id']
        manifest = self.engine.txn(transaction)['manifest_sha256']
        finished = streamlined.finish(self.engine, transaction, manifest)
        self.assertEqual(finished['ticket_id'], dry['ticket_id'])
        self.assertFalse(folder.exists())

    def test_remove_is_limited_to_temp_roots(self):
        folder = self.scratch()
        with patch.object(Engine, '_temp_roots', return_value=[self.root / 'elsewhere']):
            with self.assertRaises(CleanupError) as raised:
                streamlined.remove(self.engine, [folder], 'test scratch')
        self.assertEqual(raised.exception.kind, 'use_prepare')
        self.assertTrue(folder.exists())

    def test_remove_still_preserves_git_tracked_files(self):
        repository = self.root / 'clone'
        (repository / 'Packs').mkdir(parents=True)
        (repository / 'Packs' / 'tracked.yml').write_text('name: fixture\n', encoding='utf-8')
        subprocess.run(['git', 'init', str(repository)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(repository), 'add', '.'], check=True, capture_output=True)
        (repository / 'Packs' / 'generated.bin').write_bytes(b'generated')
        result = streamlined.remove(self.engine, [repository / 'Packs'], 'test output beside tracked source')
        self.assertTrue((repository / 'Packs' / 'tracked.yml').exists())
        self.assertFalse((repository / 'Packs' / 'generated.bin').exists())
        self.assertTrue(any(item['path'].endswith('tracked.yml') for item in result['excluded']))

    def test_special_kinds_keep_the_step_by_step_workflow(self):
        with self.assertRaises(CleanupError) as raised:
            streamlined.prepare(self.engine, [self.scratch()], 'evidence', kind='retired-repository')
        self.assertEqual(raised.exception.kind, 'use_step_commands')

    def test_missing_path_is_reported_before_any_snapshot(self):
        with self.assertRaises(CleanupError) as raised:
            streamlined.remove(self.engine, [self.root / 'absent'], 'evidence')
        self.assertEqual(raised.exception.kind, 'path_missing')


if __name__ == '__main__':
    unittest.main()
