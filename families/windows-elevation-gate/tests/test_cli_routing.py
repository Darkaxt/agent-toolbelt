"""Public administrator commands never select per-action native UAC."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_windows_elevation_gate import cli


class ElevationRoutingTests(unittest.TestCase):
    def arguments(self, legacy=False):
        return ['run', '--owner-task', 'Read identity', '--thread-name', 'Fixture',
                '--reason', 'Read token', '--changes', 'None', '--target', 'Token',
                '--cwd', 'D:/Temp', *(['--one-shot'] if legacy else []),
                '--', 'C:/Windows/System32/whoami.exe', '/user']

    def invoke(self, legacy=False, failure=None):
        output = io.StringIO()
        with patch.object(cli.engine, 'prepare', return_value={'exact': 'request'}), \
             patch.object(cli.engine, 'run', side_effect=AssertionError('Native UAC launched')), \
             patch.object(cli.broker, 'run', return_value={'ok': True}, side_effect=failure) as submit, \
             patch('sys.stdout', output):
            code = cli.main(self.arguments(legacy))
        submit.assert_called_once_with({'exact': 'request'})
        return code, json.loads(output.getvalue())

    def test_normal_and_legacy_flag_each_submit_exactly_once_to_broker(self):
        self.assertEqual(self.invoke()[0], 0)
        code, result = self.invoke(legacy=True)
        self.assertEqual(code, 0)
        self.assertEqual(result['routing_notice']['deprecated_flag'], '--one-shot')
        self.assertEqual(result['routing_notice']['route'], 'persistent_broker')

    def test_broker_unavailable_or_stopping_never_falls_back(self):
        for failure in (cli.broker.BrokerUnavailable('Not started'),
                        cli.broker.BrokerStopping('Draining')):
            with self.subTest(failure=type(failure).__name__):
                code, result = self.invoke(legacy=True, failure=failure)
                self.assertEqual(code, 1)
                self.assertFalse(result['launched'])
                self.assertIn(result['failure_kind'], ('broker_unavailable', 'broker_stopping'))

    def test_lost_completion_keeps_receipt_without_resubmission(self):
        failure = cli.broker.CompletionUnknown({'request_id': 'exact-receipt'})
        code, result = self.invoke(legacy=True, failure=failure)
        self.assertEqual(code, 1)
        self.assertEqual(result['failure_kind'], 'completion_unverified')
        self.assertEqual(result['receipt'], {'request_id': 'exact-receipt'})


if __name__ == '__main__':
    unittest.main()
