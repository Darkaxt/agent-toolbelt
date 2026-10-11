import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import base64
import subprocess
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

from test_gate import ExecutionTicket, temporary_workspace

notifications = importlib.import_module('agent_toolbelt_gradle_build_gate.notifications')
gate = importlib.import_module('agent_toolbelt_gradle_build_gate.gate')


class NotificationContracts(unittest.TestCase):
    def test_payload_is_silent_escaped_and_ticket_scoped(self):
        payload = notifications.payload(Path('D:/Temp/A & B'), 'abc123', 'Task <one> & two',
                                        thread_name='Thread <one> & two')
        xml = ET.fromstring(payload['xml'])
        self.assertEqual(xml.find('audio').attrib, {'silent': 'true'})
        text = [node.text for node in xml.findall('.//text')]
        self.assertIn('Task: Task <one> & two', text)
        self.assertIn('Thread Name: Thread <one> & two', text)
        self.assertFalse(any(s.startswith('Project:') for s in text))
        missing = ET.fromstring(notifications.payload(Path('D:/not-a-thread'), 'missing', 'Task')['xml'])
        self.assertIn('Thread Name: Unknown', [node.text for node in missing.findall('.//text')])
        self.assertNotEqual(payload['tag'], notifications.payload(Path('D:/other'), 'def456', 'Other')['tag'])
        first = notifications.payload(Path('D:/same'), 'a' * 16 + 'b' * 16, 'One')
        second = notifications.payload(Path('D:/same'), 'a' * 16 + 'c' * 16, 'Two')
        self.assertNotEqual((first['tag'], first['group']), (second['tag'], second['group']))

    def test_owner_fallback_does_not_invent_a_title(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIn('unknown', notifications.owner_label(None).lower())
        with patch.dict(os.environ, {'CODEX_THREAD_ID': 'codex-id'}, clear=True):
            self.assertEqual(notifications.owner_label(None), 'Codex task codex-id')
            self.assertEqual(notifications.owner_label('Human task'), 'Human task')
        with patch.dict(os.environ, {'CLAUDE_SESSION_ID': 'claude-id'}, clear=True):
            self.assertEqual(notifications.owner_label(None), 'Claude session claude-id')

    def test_thread_name_is_explicit_sanitized_and_independent_of_task(self):
        self.assertEqual(notifications.thread_label('  Actual\r\n thread  '), 'Actual thread')
        self.assertEqual(notifications.thread_label(' \t\n '), 'Unknown')
        with patch.dict(os.environ, {'CODEX_THREAD_ID': 'id-not-a-title'}, clear=True):
            self.assertEqual(notifications.thread_label(None), 'Unknown')
        notice = notifications.BuildNotification(Path('D:/Project'), 'Compile app',
                                                 thread_name='Actual conversation', enabled=False)
        self.assertEqual(notice.result['thread_name'], 'Actual conversation')
        self.assertEqual(notice.result['owner_task'], 'Compile app')

    def test_transport_failure_is_diagnostic_and_disabled_mode_is_noop(self):
        with patch.object(notifications, 'transport', side_effect=OSError('private detail')):
            with notifications.BuildNotification(Path('D:/fixture'), 'Task') as notice:
                notice.start({'id': 'ticket'})
            self.assertEqual(notice.result['state'], 'unavailable')
            self.assertNotIn('private detail', json.dumps(notice.result))
        with patch.object(notifications, 'transport') as transport:
            with notifications.BuildNotification(Path('D:/fixture'), None, enabled=False) as notice:
                notice.start({'id': 'ticket'})
            transport.assert_not_called()
            self.assertEqual(notice.result['state'], 'disabled')

    def test_completion_waits_for_inflight_submission_then_removes_own_ticket(self):
        entered, proceed = threading.Event(), threading.Event()
        actions = []

        def transport(action, payload):
            actions.append((action, payload['tag']))
            if action == 'show':
                entered.set()
                proceed.wait()
            return {'state': 'submitted' if action == 'show' else 'removed'}

        with patch.object(notifications, 'transport', side_effect=transport):
            notice = notifications.BuildNotification(Path('D:/fixture'), 'Task', thread_name='Real thread')
            notice.start({'id': 'our-ticket'})
            entered.wait()
            self.assertEqual(actions, [('show', 'our-ticket')])
            proceed.set()
            notice.finish()
        self.assertEqual(actions, [('show', 'our-ticket'), ('remove', 'our-ticket')])
        self.assertEqual(notice.result['removal']['state'], 'removed')

    def test_submission_uses_thread_name_not_project(self):
        with patch.object(notifications, 'transport', return_value={'state': 'disabled_by_windows'}) as transport:
            with notifications.BuildNotification(Path('D:/not-a-title'), 'Compile app',
                                                 thread_name='Real thread') as notice:
                notice.start({'id': 'our-ticket'})
        text = [node.text for node in ET.fromstring(transport.call_args.args[1]['xml']).findall('.//text')]
        self.assertIn('Thread Name: Real thread', text)
        self.assertFalse(any('not-a-title' in line for line in text))

    def test_cli_routes_owner_and_optout(self):
        cli = importlib.import_module('agent_toolbelt_gradle_build_gate.cli')
        with patch.object(gate, 'run_build', return_value={'exit_code': 0}) as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['run', '--project', 'D:/fixture', '--owner-task', 'Our task',
                                       '--thread-name', 'Our conversation', '--no-notify', '--', 'test']), 0)
        self.assertEqual(run.call_args.kwargs['owner_task'], 'Our task')
        self.assertEqual(run.call_args.kwargs['thread_name'], 'Our conversation')
        self.assertFalse(run.call_args.kwargs['notify'])

    @unittest.skipUnless(os.name == 'nt', 'Windows notification transport')
    def test_transport_uses_json_stdin_and_isolates_diagnostic_timeout(self):
        message = notifications.payload(Path('D:/A & B'), 'our-ticket', 'Task; $(do not execute)')
        with patch.object(notifications.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout='{"state":"submitted"}')) as run:
            self.assertEqual(notifications.transport('show', message)['state'], 'submitted')
        self.assertNotIn('Task;', ' '.join(run.call_args.args[0]))
        self.assertEqual(json.loads(run.call_args.kwargs['input'])['xml'], message['xml'])
        self.assertEqual(run.call_args.kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)
        with patch.object(notifications.subprocess, 'run', side_effect=subprocess.TimeoutExpired('notification', 15)):
            self.assertEqual(notifications.transport('show', message)['failure_kind'], 'notification_transport_timeout')

    def test_disabled_windows_notifications_do_not_attempt_removal(self):
        with patch.object(notifications, 'transport', return_value={'state': 'disabled_by_windows'}) as transport:
            with notifications.BuildNotification(Path('D:/fixture'), 'Task') as notice:
                notice.start({'id': 'our-ticket'})
        self.assertEqual(notice.result['state'], 'disabled_by_windows')
        self.assertEqual([call.args[0] for call in transport.call_args_list], ['show'])

    def test_exceptional_completion_removes_the_notification(self):
        with patch.object(notifications, 'transport', side_effect=lambda action, payload: {
                'state': 'submitted' if action == 'show' else 'removed'}) as transport:
            with self.assertRaisesRegex(RuntimeError, 'preflight failed'):
                with notifications.BuildNotification(Path('D:/fixture'), 'Task') as notice:
                    notice.start({'id': 'our-ticket'})
                    raise RuntimeError('preflight failed')
        self.assertEqual([call.args[0] for call in transport.call_args_list], ['show', 'remove'])

    def test_notification_errors_do_not_change_failed_build_or_gate_result(self):
        mutex = MagicMock(); mutex.abandoned = False; mutex.__enter__.return_value = mutex
        with temporary_workspace() as root:
            project = Path(root); (project / 'gradlew.bat').touch()
            with patch('agent_toolbelt_gradle_build_gate.queue.TicketQueue', return_value=ExecutionTicket()), \
                 patch.object(gate, 'NamedMutex', return_value=mutex), \
                 patch.object(gate, 'LifecycleObserver'), \
                 patch.object(gate, 'inspect_activity', return_value={'safe_to_start': True, 'processes': []}), \
                 patch('agent_toolbelt_gradle_build_gate.usage.record_project', return_value={'ok': True}), \
                 patch.object(gate, 'make_profile', return_value={}), \
                 patch.object(gate, 'execute_wrapper', return_value={'exit_code': 7}), \
                 patch.object(notifications, 'transport', side_effect=OSError('private transport detail')):
                result = gate.run_build(project, ['test'], retire_daemons='none', tray=False)
        self.assertEqual(result['exit_code'], 7)
        self.assertTrue(result['gate_acquired'])
        self.assertEqual(result['desktop_notification']['state'], 'unavailable')
        self.assertEqual(result['desktop_notification']['removal']['state'], 'unavailable')
        self.assertNotIn('private transport detail', json.dumps(result))
        mutex.__exit__.assert_called_once()

    def test_acquisition_failure_does_not_notify_queued_request(self):
        mutex = MagicMock(); mutex.__enter__.side_effect = RuntimeError('not acquired')
        with temporary_workspace() as root:
            project = Path(root); (project / 'gradlew.bat').touch()
            with patch('agent_toolbelt_gradle_build_gate.queue.TicketQueue', return_value=ExecutionTicket()), \
                 patch.object(gate, 'NamedMutex', return_value=mutex), \
                 patch.object(gate, 'make_profile', return_value={}), \
                 patch.object(notifications, 'transport') as transport:
                with self.assertRaisesRegex(RuntimeError, 'not acquired'):
                    gate.run_build(project, ['test'], retire_daemons='none', tray=False)
        transport.assert_not_called()

    @unittest.skipUnless(os.name == 'nt' and os.getenv('GRADLE_GATE_NOTIFICATION_SMOKE') == '1',
                         'Opt-in standard silent Windows notification; no Gradle build')
    def test_native_submission_content_and_ticket_scoped_removal(self):
        message = notifications.payload(Path('D:/Downloads/Public/agent-toolbelt'), 'gate-native-test',
                                        'Notification smoke test - no Gradle build running')
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        probe = '''$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
$items = [Windows.UI.Notifications.ToastNotificationManager]::History.GetHistory('Darka.GradleBuildGate')
ConvertTo-Json -InputObject @($items | Where-Object { $_.Tag -eq 'gate-native-test' } | ForEach-Object {
    @{ tag=$_.Tag; group=$_.Group; xml=$_.Content.GetXml() }
}) -Depth 4 -Compress
'''

        def history():
            result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand',
                                     base64.b64encode(probe.encode('utf-16le')).decode('ascii')],
                                    capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return json.loads(result.stdout)

        try:
            self.assertEqual(notifications.transport('show', message)['state'], 'submitted')
            items = history()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]['group'], message['group'])
            xml = ET.fromstring(items[0]['xml'])
            self.assertEqual(xml.find('audio').get('silent'), 'true')
            self.assertIn('Task: Notification smoke test - no Gradle build running',
                          [node.text for node in xml.findall('.//text')])
        finally:
            removal = notifications.transport('remove', message)
        self.assertEqual(removal['state'], 'removed')
        self.assertEqual(history(), [])

    def test_notification_starts_after_acquisition_and_finishes_after_gate_release(self):
        events = []
        mutex = MagicMock(); mutex.abandoned = False
        mutex.__enter__.side_effect = lambda *a: events.append('acquire') or mutex
        mutex.__exit__.side_effect = lambda *a: events.append('release')
        observer = MagicMock()
        observer.__enter__.return_value = observer
        observer.pids = None
        observer.wait.side_effect = lambda: events.append('wait')
        snapshots = iter([{'safe_to_start': False, 'processes': []},
                          {'safe_to_start': True, 'processes': []}])
        notice = MagicMock(); notice.__enter__.return_value = notice
        notice.start.side_effect = lambda ticket: events.append('notify')
        notice.__exit__.side_effect = lambda *a: events.append('notification_finish')
        notice.result = {'state': 'submitted'}
        with temporary_workspace() as root:
            project = Path(root); (project / 'gradlew.bat').touch()
            with patch('agent_toolbelt_gradle_build_gate.queue.TicketQueue', return_value=ExecutionTicket(events)), \
                 patch.object(gate, 'NamedMutex', return_value=mutex), \
                 patch.object(gate, 'LifecycleObserver', return_value=observer), \
                 patch.object(gate, 'inspect_activity', side_effect=lambda *a: events.append('inspect') or next(snapshots)), \
                 patch('agent_toolbelt_gradle_build_gate.usage.record_project', return_value={'ok': True}), \
                 patch.object(gate, 'make_profile', return_value={}), \
                 patch.object(gate, 'execute_wrapper', side_effect=lambda *a: events.append('build') or {'exit_code': 7}), \
                 patch.object(notifications, 'BuildNotification', return_value=notice):
                result = gate.run_build(project, ['test'], retire_daemons='none', owner_task='Our task', tray=False)
        self.assertEqual(events, ['ticket_turn', 'acquire', 'notify', 'inspect', 'wait', 'inspect',
                                  'build', 'release', 'ticket_release', 'notification_finish'])
        self.assertEqual(result['exit_code'], 7)
        self.assertFalse(result['ok'])
        self.assertEqual(result['desktop_notification']['state'], 'submitted')
