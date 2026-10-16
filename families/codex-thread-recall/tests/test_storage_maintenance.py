import json
import sqlite3
import sys
import tempfile
import unittest
import io
from contextlib import closing
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_codex_thread_recall import THREAD_ID, make_codex_home, make_entry, thread_recall
from agent_toolbelt_codex_thread_recall import cache_maintenance, cli


class StorageMaintenanceTests(unittest.TestCase):
    def fixture(self, root):
        home, rollout = make_codex_home(root, rollout_entries=[
            make_entry('2026-10-16T00:00:00Z', 'event_msg',
                       {'type': 'user_message', 'text': 'Review storage widget.py and commit abcdef123.'})])
        result = thread_recall.recall(thread_id=THREAD_ID, codex_home=home)
        self.assertTrue(result['ok'], result)
        return home, rollout

    def test_collector_summary_bounds_and_counts_legacy_duplicates(self):
        skipped = [{'thread_id': str(i), 'reason': 'old', 'thread_title': 'PRIVATE'} for i in range(1000)]
        payload = {'thread_source': {'skipped_threads': skipped}, 'skipped_threads': skipped, 'threads': []}
        compact = thread_recall.compact_collector_payload(payload)
        self.assertEqual(compact['skipped_thread_count'], 1000)
        self.assertEqual(compact['skipped_by_reason'], {'old': 1000})
        self.assertLessEqual(len(compact['skipped_threads']), 10)
        self.assertNotIn('skipped_threads', compact['thread_source'])
        self.assertNotIn('PRIVATE', json.dumps(compact))
        self.assertEqual(thread_recall.compact_collector_payload(compact), compact)

    def test_log_retention_keeps_complete_recent_records_and_latest(self):
        with tempfile.TemporaryDirectory() as root:
            log = Path(root) / 'collector.jsonl'
            log.write_bytes(b'{"legacy": 1}\n' * 1000)
            with patch.object(thread_recall, 'COLLECTOR_LOG_MAX_BYTES', 1024):
                thread_recall.append_collector_json_log(log, {'started_at': 'latest', 'threads': []})
            self.assertLessEqual(log.stat().st_size, 1024)
            rows = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(rows[-1]['started_at'], 'latest')

    def test_concurrent_log_writers_keep_each_complete_record(self):
        with tempfile.TemporaryDirectory() as root:
            log = Path(root) / 'collector.jsonl'
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda n: thread_recall.append_collector_json_log(log, {'sequence': n}), range(20)))
            rows = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(sorted(r['sequence'] for r in rows), list(range(20)))

    def test_inventory_read_only_and_apply_evicts_missing_then_compacts(self):
        with tempfile.TemporaryDirectory() as root:
            home, rollout = self.fixture(root)
            rollout.unlink()
            db = thread_recall.cache_db_path(home)
            before = db.read_bytes()
            plan = cache_maintenance.inventory(home)
            self.assertEqual(db.read_bytes(), before)
            self.assertEqual(plan['candidates'][0]['thread_id'], THREAD_ID)
            state_before = (home / 'state_5.sqlite').read_bytes()
            bundles = thread_recall.memory_bundle_root(home)
            bundles.mkdir()
            (bundles / 'keep.json').write_text('keep')
            result = cache_maintenance.apply(home, plan, compact=True)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['deleted_entries'], 1)
            self.assertEqual((home / 'state_5.sqlite').read_bytes(), state_before)
            self.assertEqual((bundles / 'keep.json').read_text(), 'keep')
            self.assertEqual(result['integrity_check'], ['ok'])
            self.assertEqual(cache_maintenance.inventory(home)['candidates'], [])

    def test_restored_or_relocated_source_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            home, rollout = self.fixture(root)
            content = rollout.read_bytes()
            rollout.unlink()
            plan = cache_maintenance.inventory(home)
            restored = rollout.with_name('moved.jsonl')
            restored.write_bytes(content)
            with closing(sqlite3.connect(home / 'state_5.sqlite')) as conn, conn:
                conn.execute('update threads set rollout_path=? where id=?', (str(restored), THREAD_ID))
            result = cache_maintenance.apply(home, plan)
            self.assertEqual(result['deleted_entries'], 0)
            self.assertEqual(len(result['preserved']), 1)
            self.assertEqual(cache_maintenance.inventory(home)['candidates'], [])

    def test_access_error_is_not_missing(self):
        with tempfile.TemporaryDirectory() as root:
            home, _ = self.fixture(root)
            with patch.object(cache_maintenance, 'source_state', return_value='unreadable'):
                self.assertEqual(cache_maintenance.inventory(home)['candidates'], [])

    def test_busy_thread_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            home, rollout = self.fixture(root)
            rollout.unlink()
            plan = cache_maintenance.inventory(home)
            with thread_recall.ThreadIndexLock(codex_home=home, thread={'id': THREAD_ID, 'rollout_path': str(rollout)}):
                result = cache_maintenance.apply(home, plan)
            self.assertEqual(result['deleted_entries'], 0)
            self.assertEqual(result['preserved'][0]['reason'], 'busy')

    def test_changed_index_and_wrong_home_are_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            home, rollout = self.fixture(root)
            rollout.unlink()
            plan = cache_maintenance.inventory(home)
            with closing(sqlite3.connect(thread_recall.cache_db_path(home))) as conn, conn:
                conn.execute("update rollout_indexes set built_at='changed'")
            result = cache_maintenance.apply(home, plan)
            self.assertEqual(result['deleted_entries'], 0)
            self.assertEqual(result['preserved'][0]['reason'], 'changed')
            self.assertFalse(cache_maintenance.apply(Path(root) / 'other', plan)['ok'])

    def test_retained_composite_indexes_support_value_and_entry_queries(self):
        with tempfile.TemporaryDirectory() as root:
            home, _ = self.fixture(root)
            with closing(thread_recall.connect_cache(home)) as conn, conn:
                for _, (table, column) in thread_recall.FACET_TABLES.items():
                    indexes = {r['name'] for r in conn.execute(f'pragma index_list({table})')}
                    self.assertNotIn(f'idx_{table}_value', indexes)
                    query_plan = conn.execute(f'explain query plan select entry_id from {table} where {column}=?', ('value',)).fetchone()[3]
                    self.assertIn(f'idx_{table}_value_entry', query_plan)

    def test_old_prefix_indexes_are_removed_without_touching_rows(self):
        with tempfile.TemporaryDirectory() as root:
            home, _ = self.fixture(root)
            with closing(thread_recall.connect_cache(home)) as conn, conn:
                conn.execute('create index idx_entry_paths_value on entry_paths(path)')
                conn.commit()
            plan = cache_maintenance.inventory(home)
            self.assertIn('idx_entry_paths_value', plan['redundant_indexes'])
            result = cache_maintenance.apply(home, plan)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['deleted_entries'], 0)
            self.assertIn('idx_entry_paths_value', result['removed_indexes'])
            recalled = thread_recall.grep_rollout(pattern='storage', thread_id=THREAD_ID, codex_home=home)
            self.assertTrue(recalled['ok'], recalled)

    def test_cli_requires_review_hash_and_rejects_modified_plan(self):
        with tempfile.TemporaryDirectory() as root:
            home, rollout = self.fixture(root)
            rollout.unlink()
            plan = cache_maintenance.inventory(home)
            file = Path(root) / 'plan.json'
            file.write_text(json.dumps(plan))
            with redirect_stdout(io.StringIO()) as output:
                code = cli.main(['--codex-home', str(home), 'maintain-cache', '--plan', str(file)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())['error'], 'confirmation_required')
            with redirect_stdout(io.StringIO()) as output:
                code = cli.main(['--codex-home', str(home), 'maintain-cache', '--plan', str(file),
                                 '--confirm-plan-sha256', plan['plan_sha256'], '--compact'])
            self.assertEqual(code, 0, output.getvalue())
            self.assertEqual(json.loads(output.getvalue())['deleted_entries'], 1)
            plan['candidates'][0]['entry_count'] += 1
            self.assertFalse(cache_maintenance.apply(home, plan)['ok'])

    def test_orphan_rows_are_removed_with_their_facets_and_fts(self):
        with tempfile.TemporaryDirectory() as root:
            home, rollout = self.fixture(root)
            rollout.unlink()
            with closing(thread_recall.connect_cache(home)) as conn, conn:
                conn.execute('delete from rollout_indexes')
            plan = cache_maintenance.inventory(home)
            self.assertEqual(plan['candidates'][0]['reason'], 'orphan_entries')
            result = cache_maintenance.apply(home, plan)
            self.assertTrue(result['ok'], result)
            with closing(thread_recall.connect_cache(home)) as conn:
                for table in ['entries', 'entries_fts', 'entry_paths', 'episodes', 'entry_episode_links']:
                    self.assertEqual(conn.execute(f'select count(*) from {table}').fetchone()[0], 0)

    def test_interrupted_orphan_index_with_available_raw_history_is_evictable(self):
        with tempfile.TemporaryDirectory() as root:
            home, rollout = self.fixture(root)
            original = rollout.read_bytes()
            with closing(thread_recall.connect_cache(home)) as conn, conn:
                conn.execute('delete from rollout_indexes')
                conn.execute('delete from entries_fts')
            plan = cache_maintenance.inventory(home)
            self.assertEqual(plan['candidates'][0]['reason'], 'orphan_entries')
            self.assertIn('available', plan['candidates'][0]['sources'].values())
            result = cache_maintenance.apply(home, plan)
            self.assertTrue(result['ok'], result)
            self.assertEqual(rollout.read_bytes(), original)
            rebuilt = thread_recall.recall(thread_id=THREAD_ID, codex_home=home)
            self.assertTrue(rebuilt['ok'], rebuilt)
            self.assertTrue(rebuilt['index']['built'])

    def test_native_writer_conflict_returns_diagnostics_without_partial_delete(self):
        with tempfile.TemporaryDirectory() as root:
            home, rollout = self.fixture(root)
            rollout.unlink()
            plan = cache_maintenance.inventory(home)
            with closing(thread_recall.connect_cache(home)) as owner:
                owner.execute('begin immediate')
                result = cache_maintenance.apply(home, plan, compact=True)
                owner.rollback()
            self.assertFalse(result['ok'])
            self.assertEqual(result['sqlite_error_name'], 'SQLITE_BUSY')
            self.assertEqual(cache_maintenance.inventory(home)['candidates'][0]['entry_count'], 1)

    def test_same_named_different_collation_prefix_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            home, _ = self.fixture(root)
            with closing(thread_recall.connect_cache(home)) as conn, conn:
                conn.execute('create index idx_entry_paths_value on entry_paths(path collate nocase)')
                self.assertNotIn('idx_entry_paths_value', cache_maintenance.redundant_indexes(conn))


if __name__ == '__main__':
    unittest.main()
