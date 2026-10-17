import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from test_gate import temporary_workspace


class CallerSupport(unittest.TestCase):
    def test_claude_own_ancestor_name_and_identity_override_inherited_codex(self):
        caller = importlib.import_module('agent_toolbelt_gradle_build_gate.caller')
        with temporary_workspace() as folder:
            root = Path(folder)
            session = '12345678-1234-4234-8234-123456789abc'
            (root / '12.json').write_text(json.dumps({
                'pid': 12, 'procStart': '100', 'sessionId': session, 'name': 'Navic'}))
            with patch.object(caller, 'ancestors', return_value=[(13, 110), (12, 100)]), \
                    patch.dict(os.environ, {'CODEX_THREAD_ID': 'inherited'}, clear=True):
                identity = caller.resolve(root=root)
                self.assertEqual(identity['system'], 'claude')
                self.assertEqual(identity['session_id'], session)
                self.assertEqual(identity['thread_name'], 'Navic')
                self.assertEqual(caller.resolve('Explicit title', root=root)['thread_name'], 'Explicit title')
                (root / '12.json').write_text(json.dumps({
                    'pid': 12, 'procStart': '99', 'sessionId': session, 'name': 'Stale'}))
                self.assertEqual(caller.resolve(root=root)['system'], 'codex')
                self.assertIsNone(caller.resolve(root=root)['thread_name'])

    def test_unknown_caller_does_not_scan_unrelated_registrations_or_invent_name(self):
        caller = importlib.import_module('agent_toolbelt_gradle_build_gate.caller')
        with temporary_workspace() as folder, patch.dict(os.environ, {}, clear=True), \
                patch.object(caller, 'ancestors', return_value=[(12, 100)]):
            (Path(folder) / '99.json').write_text('{"name":"Other project"}')
            self.assertEqual(caller.resolve(root=Path(folder)), {
                'system': 'unknown', 'session_id': None, 'thread_name': None,
                'name_source': 'unavailable'})

    @unittest.skipUnless(os.name == 'nt', 'Native process ancestry')
    def test_native_ancestry_binds_current_process_and_creation_time(self):
        caller = importlib.import_module('agent_toolbelt_gradle_build_gate.caller')
        from agent_toolbelt_gradle_build_gate.queue import NativeWait
        native = NativeWait()
        handle, ticks = native.process(os.getpid())
        native.k.CloseHandle(handle)
        self.assertEqual(caller.ancestors()[0], (os.getpid(), ticks))

    def test_only_current_running_unanswered_revision_is_actionable(self):
        support = importlib.import_module('agent_toolbelt_gradle_build_gate.support')
        state = {'status': 'running', 'revision': 2, 'request': {
            'id': 'current', 'revision': 2, 'response': None}}
        self.assertEqual(support.request_status(state), 'action_required')
        self.assertEqual(support.request_status({**state, 'revision': 3}), 'progress_resumed')
        self.assertEqual(support.request_status({**state, 'status': 'completed'}), 'build_exited')
        self.assertEqual(support.request_status({**state, 'status': 'unexpected'}), 'state_unknown')
        self.assertEqual(support.request_status({**state, 'request': {
            **state['request'], 'response': {'decision': 'continue'}}}), 'answered')

    def test_watch_cli_emits_exactly_one_monitor_event_without_controlling_build(self):
        cli = importlib.import_module('agent_toolbelt_gradle_build_gate.cli')
        support = importlib.import_module('agent_toolbelt_gradle_build_gate.support')
        result = {'ok': True, 'state': 'owner_support_requested', 'ticket_id': 'a' * 32,
                  'request_id': 'current'}
        output = io.StringIO()
        with patch.object(support, 'wait_request', return_value=result) as wait, \
                patch.object(support, 'respond') as respond, redirect_stdout(output):
            self.assertEqual(cli.main(['watch-support', '--ticket', 'a' * 32,
                                       '--after-request', 'previous']), 0)
        wait.assert_called_once_with('a' * 32, after_request='previous')
        respond.assert_not_called()
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(output.getvalue()), result)

    def test_optional_watch_signal_failure_does_not_fail_build_support_writes(self):
        support = importlib.import_module('agent_toolbelt_gradle_build_gate.support')
        with patch.object(support, 'NativeWait', side_effect=OSError('fixture unavailable')), \
                patch('sys.stderr', new_callable=io.StringIO) as output:
            support.signal_change('a' * 32)
        self.assertTrue(json.loads(output.getvalue())['build_still_supervised'])

    def test_auto_name_reaches_both_observers_and_wrapper_owner_without_requeue(self):
        from test_gate import ExecutionTicket
        gate = importlib.import_module('agent_toolbelt_gradle_build_gate.gate')
        caller = importlib.import_module('agent_toolbelt_gradle_build_gate.caller')
        identity = {'system': 'claude', 'session_id': 'fixture', 'thread_name': 'Navic',
                    'name_source': 'live_registration'}
        mutex = MagicMock()
        with temporary_workspace() as folder:
            (Path(folder) / 'gradlew.bat').touch()
            with patch.object(caller, 'resolve', return_value=identity), \
                    patch('agent_toolbelt_gradle_build_gate.queue.TicketQueue', return_value=ExecutionTicket()) as queue, \
                    patch.object(gate, 'NamedMutex', return_value=mutex), \
                    patch.object(gate, 'LifecycleObserver'), \
                    patch.object(gate, 'inspect_activity', return_value={'safe_to_start': True, 'processes': []}), \
                    patch('agent_toolbelt_gradle_build_gate.usage.record_project', return_value={'ok': True}), \
                    patch('agent_toolbelt_gradle_build_gate.tray.BuildTelemetry') as telemetry, \
                    patch('agent_toolbelt_gradle_build_gate.notifications.BuildNotification') as notification, \
                    patch.object(gate, 'execute_wrapper', return_value={'exit_code': 0}) as execute:
                gate.run_build(Path(folder), ['test'], owner_task='Verify playback',
                               retire_daemons='none', keep_daemon=True)
        self.assertEqual(telemetry.call_args.kwargs['thread_name'], 'Navic')
        self.assertEqual(notification.call_args.kwargs['thread_name'], 'Navic')
        self.assertEqual(execute.call_args.args[1]['_owner'], {**identity, 'operation': 'Verify playback'})
        queue.assert_called_once()

    @unittest.skipUnless(os.name == 'nt', 'Native diagnostic event')
    def test_wait_subscribes_before_read_and_skips_answered_or_superseded_requests(self):
        support = importlib.import_module('agent_toolbelt_gradle_build_gate.support')
        from agent_toolbelt_gradle_build_gate.queue import NativeWait
        with temporary_workspace() as folder:
            native = NativeWait()
            handle, ticks = native.process(os.getpid())
            native.k.CloseHandle(handle)
            ticket = {'id': 'e' * 32, 'pid': os.getpid(), 'created_ticks': ticks}
            monitor = support.BuildSupport(ticket, folder, Path(folder) / 'build.log', root=folder,
                                           owner={'system': 'claude', 'session_id': 'exact', 'thread_name': 'Navic'})
            self.assertIsNone(monitor.state['owner_task'])
            monitor.update(request={'id': 'stale', 'revision': 0, 'response': None}, revision=1)
            subscribed = threading.Event()
            result = []
            original = support.read
            def observed(*args):
                state = original(*args)
                subscribed.set()
                return state
            with patch.object(support, 'read', side_effect=observed):
                watcher = threading.Thread(target=lambda: result.append(support.wait_request(ticket['id'], root=folder)))
                watcher.start()
                try:
                    self.assertTrue(subscribed.wait(5))
                    self.assertEqual(result, [])
                    monitor.update(request={'id': 'next', 'revision': 1, 'response': None})
                    watcher.join(5)
                    self.assertFalse(watcher.is_alive())
                    self.assertEqual(result[0]['request_id'], 'next')
                    self.assertEqual(result[0]['owner']['thread_name'], 'Navic')
                finally:
                    monitor.finish(0)
                    watcher.join(5)
            self.assertEqual(support.wait_request(ticket['id'], root=folder)['state'], 'build_exited')

    @unittest.skipUnless(os.name == 'nt', 'Native diagnostic subscription race')
    def test_state_change_between_snapshot_and_wait_is_not_lost(self):
        support = importlib.import_module('agent_toolbelt_gradle_build_gate.support')
        with temporary_workspace() as folder:
            native = support.NativeWait()
            handle, ticks = native.process(os.getpid())
            native.k.CloseHandle(handle)
            ticket = {'id': 'a' * 32, 'pid': os.getpid(), 'created_ticks': ticks}
            monitor = support.BuildSupport(ticket, folder, Path(folder) / 'log', root=folder)
            monitor.update()
            original = support.read
            reads = []
            def racing_read(*args):
                state = original(*args)
                reads.append(state)
                if len(reads) == 1:
                    monitor.update(request={'id': 'raced', 'revision': 0, 'response': None})
                return state
            try:
                with patch.object(support, 'read', side_effect=racing_read):
                    self.assertEqual(support.wait_request(ticket['id'], root=folder)['request_id'], 'raced')
                self.assertEqual(len(reads), 2)
            finally:
                monitor.finish(0)

    @unittest.skipUnless(os.name == 'nt', 'Native supervisor exit')
    def test_wait_returns_exact_supervisor_exit_without_claiming_build_completion(self):
        support = importlib.import_module('agent_toolbelt_gradle_build_gate.support')
        from agent_toolbelt_gradle_build_gate.queue import NativeWait
        with temporary_workspace() as folder:
            child = subprocess.Popen([sys.executable, '-B', '-c', 'import sys; sys.stdin.read()'],
                                     stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                native = NativeWait()
                handle, ticks = native.process(child.pid)
                native.k.CloseHandle(handle)
                ticket = {'id': 'f' * 32, 'pid': child.pid, 'created_ticks': ticks}
                support.save(support.ticket_path(ticket['id'], folder), {
                    'schema': 1, 'ticket': ticket, 'status': 'running', 'revision': 0, 'request': None,
                    'watch_protocol': 1})
                child.stdin.close()
                child.wait()
                result = support.wait_request(ticket['id'], root=folder)
                self.assertEqual(result['state'], 'supervisor_exited')
                self.assertFalse(result['completion_verified'])
            finally:
                if child.poll() is None:
                    child.stdin.close()
                    child.wait()


if __name__ == '__main__':
    unittest.main()
