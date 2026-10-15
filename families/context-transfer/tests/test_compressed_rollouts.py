from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
try:
    from compression import zstd
except ImportError:
    zstd = None

from test_context_transfer import CodexFixture
from agent_toolbelt_context_transfer import activity, context_transfer, database_evidence, handoff


@unittest.skipIf(zstd is None, 'Compressed rollout fixtures require Python 3.14')
class CompressedRolloutTests(unittest.TestCase):
    def test_missing_decompressor_is_an_explicit_error(self):
        from agent_toolbelt_context_transfer.rollout_io import open_rollout
        with mock.patch.dict('sys.modules', {'compression': None, 'compression.zstd': None}):
            with self.assertRaisesRegex(OSError, 'Python 3.14'):
                open_rollout(Path('rollout.jsonl.zst'))

    def test_stale_pointer_discovers_compressed_segments_and_catalogues(self):
        with tempfile.TemporaryDirectory(dir=r'D:\Temp') as tmp:
            fixture = CodexFixture(Path(tmp))
            self.addCleanup(fixture.close)
            tid = '01a0290c-9cd4-7380-9386-36ad8df95f98'
            raw = fixture.sessions / f'rollout-2026-08-22T12-38-07-{tid}.jsonl'
            content = (json.dumps({'type': 'session_meta', 'payload': {'id': tid}}) + '\n' +
                       json.dumps({'type': 'response_item', 'payload': {'type': 'message',
                                   'role': 'user', 'content': [{'type': 'input_text',
                                   'text': 'Preserve the exact active objective.'}]}}) + '\n').encode()
            compressed = fixture.add_thread(tid, zstd.compress(content),
                                            rollout_path=Path(str(raw) + '.zst'))
            fixture.connection.execute('UPDATE threads SET rollout_path=? WHERE id=?', (str(raw), tid))
            fixture.connection.commit()
            fixture.close()
            inv = context_transfer.inventory_thread_tree(source_thread_id=tid,
                destination_thread_id='destination', codex_home=fixture.codex_home,
                archive_root=Path(tmp)/'recovery')
            self.assertTrue(inv['retirement_ready'], inv['blockers'])
            self.assertEqual(inv['rollout_count'], 1)
            record = inv['threads'][0]
            self.assertEqual(record['rollout_path'], str(compressed))
            activity.validate_current_state(inv)
            entries, stats = handoff._catalog_thread(record, max_entries=10, excerpt_chars=100)
            self.assertEqual(entries[0]['excerpt'], 'Preserve the exact active objective.')
            self.assertEqual(entries[0]['byte_offset_space'], 'decompressed')
            self.assertEqual(stats['malformed_lines'], 0)
            fixture.close()

    def test_compressed_headers_preserve_fork_dependencies(self):
        with tempfile.TemporaryDirectory(dir=r'D:\Temp') as tmp:
            fixture = CodexFixture(Path(tmp))
            self.addCleanup(fixture.close)
            for tid, parent in [('owner', None), ('fork', 'owner')]:
                header = {'type': 'session_meta', 'payload': {'id': tid, 'forked_from_id': parent}}
                raw = fixture.sessions / f'rollout-{tid}.jsonl'
                fixture.add_thread(tid, zstd.compress((json.dumps(header)+'\n').encode()),
                                   rollout_path=Path(str(raw)+'.zst'))
                fixture.connection.execute('UPDATE threads SET rollout_path=? WHERE id=?', (str(raw), tid))
            fixture.connection.commit()
            fixture.close()
            ancestors = database_evidence.history_ancestors(fixture.codex_home, 'fork')
            self.assertEqual(ancestors[0]['thread_id'], 'owner')
            refs = database_evidence.fork_references(fixture.codex_home, ['owner'])
            self.assertEqual(refs[0]['dependent_thread_id'], 'fork')
            fixture.close()
