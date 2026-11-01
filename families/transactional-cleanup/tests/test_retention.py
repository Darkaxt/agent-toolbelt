import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_transactional_cleanup import cli, retention, android
from agent_toolbelt_transactional_cleanup.engine import Engine, encoded, host
import hashlib
import hmac


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TRANSACTIONAL_CLEANUP_TEST_ROOT', 'D:/Temp'))
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'
        self.work.mkdir()
        self.engine = Engine(self.root / 'state')

    def tearDown(self):
        self.temp.cleanup()

    def reviewed(self):
        transaction = self.engine.begin(self.work)['transaction_id']
        out = self.work / 'generated'; out.mkdir(exist_ok=True)
        (out / 'keep.bin').write_bytes(b'never delete on expiry')
        self.engine.register(transaction, out, 'explicit-generated-output', 'test generation', regenerated=True)
        return transaction, self.engine.review(transaction)

    def age(self, transaction):
        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        with closing(self.engine.connect()) as c, c:
            c.execute('UPDATE transactions SET created_at=?,manifest_created_at=?,progress_updated_at=? WHERE transaction_id=?',
                      (old, old, old, transaction))
            ticket = c.execute('SELECT * FROM tickets WHERE transaction_id=?', (transaction,)).fetchone()
            if ticket:
                value = dict(ticket); value['issued_at'] = old
                c.execute('UPDATE tickets SET issued_at=?,ticket_mac=? WHERE transaction_id=?',
                          (old, self.engine._ticket_mac(value), transaction))

    def call(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(['--state-root', str(self.engine.root), *args])
        return code, json.loads(output.getvalue())

    def test_next_read_only_call_expires_issued_ticket_and_preserves_target(self):
        transaction, review = self.reviewed()
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        self.age(transaction)
        code, result = self.call('state-inventory')
        self.assertEqual(code, 0, result)
        self.assertIn(transaction, result['retention']['windows']['expired'])
        self.assertEqual(self.engine.txn(transaction)['state'], 'expired')
        self.assertEqual(self.engine.status(transaction)['ticket_state'], 'expired')
        self.assertTrue((self.work / 'generated/keep.bin').exists())
        code, result = self.call('apply', '--ticket', ticket)
        self.assertNotEqual(code, 0)
        self.assertEqual(result['failure_kind'], 'ticket_expired')
        with closing(self.engine.connect()) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM manifest').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM baseline').fetchone()[0], 0)

    def test_active_exact_root_claim_prevents_expiry_then_next_call_trims(self):
        transaction, _ = self.reviewed(); self.age(transaction)
        with self.engine.locked([self.work], operation='apply', transaction=transaction):
            result = retention.maintain(self.engine)
            self.assertIn(transaction, result['windows']['live_preserved'])
            self.assertEqual(self.engine.txn(transaction)['state'], 'reviewed')
        self.assertIn(transaction, retention.maintain(self.engine)['windows']['expired'])

    def test_current_review_and_ticket_still_delete_only_reviewed_output(self):
        transaction, review = self.reviewed()
        code, ticket = self.call('ticket', '--transaction', transaction, '--manifest-sha256', review['manifest_sha256'])
        self.assertEqual(code, 0, ticket)
        (self.work / 'generated/new.bin').write_bytes(b'new concurrent file')
        code, result = self.call('apply', '--ticket', ticket['ticket_id'])
        self.assertEqual(code, 0, result)
        self.assertFalse((self.work / 'generated/keep.bin').exists())
        self.assertTrue((self.work / 'generated/new.bin').exists())

    def test_partial_ticket_expires_without_losing_deleted_byte_summary(self):
        transaction, review = self.reviewed()
        ticket = self.engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
        with closing(self.engine.connect()) as c, c:
            c.execute("UPDATE tickets SET state='partially_applied',deleted_bytes=19 WHERE ticket_id=?", (ticket,))
            c.execute("UPDATE transactions SET state='partially_applied',deleted_bytes=19 WHERE transaction_id=?", (transaction,))
        self.age(transaction)
        retention.maintain(self.engine)
        self.assertEqual(self.engine.status(transaction)['deleted_bytes'], 19)

    def test_status_does_not_extend_reported_expiration(self):
        transaction, _ = self.reviewed()
        first = self.engine.status(transaction)['expires_at']
        code, result = self.call('status', '--transaction', transaction)
        self.assertEqual(code, 0)
        self.assertEqual(result['expires_at'], first)

    def test_legacy_expiry_authenticates_and_compacts_before_old_runtime_routing(self):
        identifier = 'a' * 32
        payload = {'host': host(), 'policy': '1', 'transaction_id': identifier, 'workspace': str(self.work),
                   'roots': [str(self.work)], 'created_at': (datetime.now(timezone.utc)-timedelta(days=8)).isoformat(),
                   'state': 'open', 'baseline': {'bulk': 'x' * 10000}}
        path = self.engine.root / (identifier + '.json')
        path.write_bytes(encoded({'payload': payload, 'mac': hmac.new(self.engine.key, encoded(payload), hashlib.sha256).hexdigest()}))
        code, result = self.call('register', '--transaction', identifier, '--path', str(self.work / 'old'),
                                 '--kind', 'temporary', '--evidence', 'test')
        self.assertEqual(result['failure_kind'], 'ticket_expired')
        self.assertLess(path.stat().st_size, 1000)
        self.assertEqual(retention.authenticated(path, self.engine)['state'], 'expired')

    def test_android_expiry_needs_no_adb_and_preserves_device_files(self):
        from test_android import FakeDevice
        device = FakeDevice()
        mobile = android.AndroidCleanup(host_engine=self.engine, device=device)
        review = mobile.review('/storage/emulated/0/S12-fixture', 'test', 'fixture output')
        identifier = review['transaction_id']
        ticket = mobile.ticket(identifier, review['manifest_sha256'])['ticket_id']
        record = mobile.load(identifier)
        record['created_at'] = record['updated_at'] = (datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
        retention.save_summary(mobile.record_path(identifier), record, self.engine)
        result = retention.maintain(self.engine)
        self.assertIn(identifier, result['android']['expired'])
        self.assertEqual(mobile.status(identifier)['state'], 'expired')
        self.assertEqual(device.calls, [])
        with self.assertRaisesRegex(Exception, 'expired'):
            mobile.apply(ticket)


if __name__ == '__main__':
    unittest.main()
