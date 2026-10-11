from __future__ import annotations

import hmac
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_transactional_cleanup.engine import Engine, CleanupError, encoded, host
from agent_toolbelt_transactional_cleanup import legacy


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='D:/Temp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'; self.work.mkdir()
        (self.work / 'keep.txt').write_text('keep')
        self.engine = Engine(self.root / 'state')

    def test_discard_compacts_open_and_reviewed_without_deleting_targets(self):
        for reviewed in (False, True):
            transaction = self.engine.begin(self.work)['transaction_id']
            if reviewed:
                self.engine.review(transaction)
            with self.engine.locked(self.engine.transaction_roots(transaction), operation='discard', transaction=transaction):
                result = self.engine.discard(transaction, 'strategy replaced; fresh snapshot required')
            self.assertEqual(result['state'], 'discarded')
            self.assertEqual(result['target_files_deleted'], 0)
            with closing(self.engine.connect()) as connection:
                for table in ('baseline', 'manifest', 'registrations'):
                    self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table} WHERE transaction_id=?',
                                                        (transaction,)).fetchone()[0], 0)
            self.assertFalse(self.engine.status(transaction)['detailed_state_retained'])
        self.assertEqual((self.work / 'keep.txt').read_text(), 'keep')

    def test_issued_ticket_cannot_be_discarded(self):
        transaction = self.engine.begin(self.work)['transaction_id']
        review = self.engine.review(transaction)
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        with self.assertRaises(CleanupError) as error:
            self.engine.discard(transaction, 'not allowed')
        self.assertEqual(error.exception.kind, 'discard_ticket_exists')
        self.assertEqual(self.engine.status(transaction)['ticket_id'], ticket)

    def test_discard_returns_database_pages_to_disk(self):
        transaction = self.engine.begin(self.work)['transaction_id']
        with closing(self.engine.connect()) as connection:
            connection.executemany('INSERT INTO baseline VALUES (?,?,?,?)',
                                   [(transaction, f'fixture-{i}', f'fixture-{i}', 'x' * 4096) for i in range(1024)])
            connection.commit()
            connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        before = self.engine.db_path.stat().st_size
        self.engine.discard(transaction, 'synthetic abandoned inventory')
        self.assertLess(self.engine.db_path.stat().st_size, before // 2)
        self.assertTrue((self.work / 'keep.txt').exists())

    def test_live_operation_blocks_discard_and_inventory_does_not_scan_targets(self):
        transaction = self.engine.begin(self.work)['transaction_id']
        with self.engine.locked([self.work], operation='review', transaction=transaction):
            inventory = self.engine.state_inventory()
            self.assertEqual(len(inventory['live_claims']), 1)
            with self.assertRaises(CleanupError) as error:
                with self.engine.locked([self.work], operation='discard', transaction=transaction):
                    self.engine.discard(transaction, 'not allowed')
            self.assertEqual(error.exception.kind, 'target_busy')
        self.assertEqual(inventory['unfinished_transactions'][0]['baseline_rows'], 2)

    def legacy_snapshot(self):
        transaction = 'a' * 32
        payload = {'host': host(), 'policy': '1', 'transaction_id': transaction,
                   'workspace': str(self.work), 'created_at': 'fixture', 'state': 'open',
                   'roots': [str(self.work)], 'discovery_coverage': {},
                   'baseline': {'large': 'x' * (3 * 1024 * 1024)}}
        path = self.engine.legacy_path(transaction)
        path.write_bytes(encoded({'payload': payload,
                                  'mac': hmac.new(self.engine.key, encoded(payload), 'sha256').hexdigest()}))
        return path, transaction

    def test_bounded_legacy_discard_authenticates_and_reclaims_without_deletion(self):
        path, transaction = self.legacy_snapshot()
        result = self.engine.discard_legacy(transaction, 'obsolete unissued baseline')
        self.assertGreater(result['state_bytes_removed'], 3 * 1024 * 1024 - 1024)
        summary = json.loads(path.read_bytes())
        self.assertEqual(summary['payload']['state'], 'discarded')
        self.assertEqual(summary['mac'], hmac.new(self.engine.key, encoded(summary['payload']), 'sha256').hexdigest())
        self.assertLess(path.stat().st_size, 2048)
        self.assertTrue((self.work / 'keep.txt').exists())

    def test_legacy_tampering_ticket_and_live_claim_block_discard(self):
        path, transaction = self.legacy_snapshot()
        with self.engine.locked([self.work], operation='review'):
            with self.assertRaises(CleanupError):
                self.engine.discard_legacy(transaction, 'not allowed')
        ticket = self.engine.root / ('b' * 64 + '.json')
        ticket.write_text('{"transaction_id":"' + transaction + '"}')
        with self.assertRaises(CleanupError):
            self.engine.discard_legacy(transaction, 'not allowed')
        ticket.unlink()
        with path.open('r+b') as stream:
            stream.seek(1000); stream.write(b'z')
        with self.assertRaises(ValueError):
            legacy.open_snapshot(path, self.engine.key, host())
        self.assertGreater(path.stat().st_size, 3 * 1024 * 1024)

    def test_disjoint_live_operation_does_not_block_legacy_compaction(self):
        path, transaction = self.legacy_snapshot()
        other = self.root / 'other'; other.mkdir()
        with self.engine.locked([other], operation='begin'):
            result = self.engine.discard_legacy(transaction, 'independent abandoned snapshot')
        self.assertEqual(result['state'], 'discarded')


if __name__ == '__main__':
    unittest.main()
