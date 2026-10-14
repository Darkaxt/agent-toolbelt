import io
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


class BrokerProtocolTests(unittest.TestCase):
    def test_protocol_round_trip_and_exact_read(self):
        from agent_toolbelt_windows_elevation_gate import broker
        value = {'op': 'status'}
        stream = io.BytesIO()
        broker.send(stream, value)
        stream.seek(0)
        self.assertEqual(broker.receive(stream), value)

    def test_response_size_and_disconnect_fail_closed(self):
        from agent_toolbelt_windows_elevation_gate import broker
        for value in (struct.pack('<I', 999999), b'\x04', struct.pack('<I', 4) + b'{}'):
            with self.assertRaises((ValueError, EOFError)):
                broker.receive(io.BytesIO(value))

    def test_partial_writes_are_completed_without_resubmission(self):
        from agent_toolbelt_windows_elevation_gate import broker
        class Partial(io.BytesIO):
            def write(self, data):
                return super().write(data[:3])
        stream = Partial()
        broker.send(stream, {'op': 'status'})
        stream.seek(0)
        self.assertEqual(broker.receive(stream), {'op': 'status'})

    def test_disconnect_after_submission_keeps_receipt_and_unknown_execution(self):
        from agent_toolbelt_windows_elevation_gate import broker
        @contextmanager
        def connected():
            yield io.BytesIO(), None, None
        with patch.object(broker, 'connection', connected), patch.object(broker, 'send'), \
             patch.object(broker, 'receive', side_effect=[{'state':'queued','request_id':'receipt'},EOFError()]):
            with self.assertRaises(broker.CompletionUnknown) as error:
                broker.run({'schema':1})
        self.assertEqual(error.exception.receipt['request_id'], 'receipt')

    def test_cli_run_uses_broker_not_a_new_elevation(self):
        from agent_toolbelt_windows_elevation_gate import cli
        argv=['run','--owner-task','Fixture','--thread-name','Fixture','--reason','Read token',
              '--changes','None','--target','Token','--cwd','D:/Temp','--','C:/Windows/System32/whoami.exe']
        with patch.object(cli.engine,'prepare',return_value={'frozen':'request'}), \
             patch.object(cli.engine,'run',side_effect=AssertionError('Per-action elevation attempted')), \
             patch.object(cli.broker,'run',return_value={'ok':True}) as run, \
             patch('sys.stdout',io.StringIO()):
            self.assertEqual(cli.main(argv),0)
        run.assert_called_once_with({'frozen':'request'})

    def test_broker_failure_does_not_fall_back_to_one_shot(self):
        from agent_toolbelt_windows_elevation_gate import cli
        argv=['run','--owner-task','Fixture','--thread-name','Fixture','--reason','Read token',
              '--changes','None','--target','Token','--cwd','D:/Temp','--','C:/Windows/System32/whoami.exe']
        output=io.StringIO()
        with patch.object(cli.engine,'prepare',return_value={}), \
             patch.object(cli.broker,'run',side_effect=cli.broker.BrokerUnavailable('Not running')), \
             patch.object(cli.engine,'run',side_effect=AssertionError('Silent fallback')), patch('sys.stdout',output):
            self.assertEqual(cli.main(argv),1)
        self.assertEqual(json.loads(output.getvalue())['failure_kind'],'broker_unavailable')

    def test_client_payload_has_no_approval_field_or_raw_execute_endpoint(self):
        source = (Path(__file__).resolve().parents[1] / 'assets/WindowsElevationBroker.cs').read_text()
        self.assertIn('approval is broker-owned', source)
        self.assertIn('Wire.Only(data', source)
        self.assertIn('dialog.ShowDialog()==DialogResult.OK', source)
        self.assertIn('new BindingLease(work.Request)', source)
        self.assertIn('new FileStream(opened,FileAccess.Read)', source)
        self.assertIn('if(stopping || !Alive(work))', source)

    def test_stop_dialog_describes_internal_control_not_placeholder_command(self):
        source = (Path(__file__).resolve().parents[1] / 'assets/WindowsElevationBroker.cs').read_text()
        self.assertIn('if(stop) cards.Add(Card("INTERNAL BROKER CONTROL"', source)
        self.assertIn('No external command is executed.', source)

    def test_listener_retains_failure_and_restricts_server_instance_creation(self):
        source = (Path(__file__).resolve().parents[1] / 'assets/WindowsElevationBroker.cs').read_text()
        self.assertIn('BuiltinAdministratorsSid', source)
        self.assertIn('Program.WriteRecord(sid,session,false,listenerError)', source)
        self.assertIn('Client can create server instances', source)

    def test_start_does_not_report_draining_broker_as_success(self):
        from agent_toolbelt_windows_elevation_gate import broker
        with patch.object(broker, 'Native'), patch.object(broker, 'Mutex'), \
             patch.object(broker, 'exchange', return_value={'ok': True, 'accepting': False}):
            with self.assertRaises(broker.BrokerStopping):
                broker.start()

    def test_interactive_broker_does_not_inherit_hidden_worker_launch(self):
        from agent_toolbelt_windows_elevation_gate import broker
        import inspect
        self.assertIn('show_window=True', inspect.getsource(broker.start))


if __name__ == '__main__':
    unittest.main()
