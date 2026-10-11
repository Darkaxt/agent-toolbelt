import contextlib
import importlib
import json
import os
from pathlib import Path
import sys
import subprocess
import threading
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock

from test_gate import temporary_workspace

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))


class TelemetryContracts(unittest.TestCase):
    def setUp(self):
        self.tray = importlib.import_module('agent_toolbelt_gradle_build_gate.tray')
        self.folder = temporary_workspace('gradle-tray-test-')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.ticket = {'id': 'a' * 32, 'number': 1, 'pid': 123, 'created_ticks': 456}

    def store(self):
        return self.tray.TelemetryStore(self.root, lock=lambda: contextlib.nullcontext(),
                                        identity=lambda ticket: 'live')

    def test_phases_statistics_and_duplicate_completion(self):
        store = self.store()
        row = {**self.ticket, 'owner_task': 'Task A', 'project': 'D:/Project', 'queued_at': 100}
        store.update(row, 'queued', now=100)
        self.assertEqual(store.read()['live'][self.ticket['id']]['phase'], 'queued')
        store.update(row, 'preflight', now=110, acquired_at=110)
        store.update(row, 'running', now=115, build_started_at=115)
        store.update(row, 'finished', now=135, exit_code=1, queue_seconds=10,
                     gate_seconds=25, build_seconds=20)
        store.update(row, 'finished', now=135, exit_code=1, queue_seconds=10,
                     gate_seconds=25, build_seconds=20)
        data = store.read()
        self.assertEqual(data['live'], {})
        self.assertEqual(data['stats']['builds'], 1)
        self.assertEqual(data['stats']['failures'], 1)
        self.assertEqual(data['stats']['gate_seconds'], 25)
        self.assertEqual(data['stats']['queue_seconds'], 10)
        self.assertEqual(data['recent'][0]['build_seconds'], 20)
        self.assertNotIn('arguments', json.dumps(data))

    def test_history_is_bounded_and_corruption_not_silently_reset(self):
        store = self.store()
        data = store.read()
        data['recent'] = [{'id': f'{number:032x}', 'phase': 'finished'} for number in range(104)]
        data['stats']['builds'] = 104
        (self.root / 'telemetry.json').write_text(json.dumps(data), encoding='utf-8')
        store.update(self.ticket, 'queued')
        store.update(self.ticket, 'finished', exit_code=0, gate_seconds=1, build_seconds=1, queue_seconds=0)
        self.assertEqual(len(store.read()['recent']), 100)
        self.assertEqual(store.read()['stats']['builds'], 105)
        (self.root / 'telemetry.json').write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            store.update(self.ticket, 'queued')
        self.assertEqual((self.root / 'telemetry.json').read_text(), '{broken')

    def test_dead_identity_is_not_counted_as_success_unknown_identity_preserved(self):
        states = {123: 'live', 124: 'unknown'}
        store = self.tray.TelemetryStore(self.root, lock=lambda: contextlib.nullcontext(),
                                        identity=lambda row: states[row['pid']])
        store.update(self.ticket, 'preflight')
        other = {**self.ticket, 'id': 'b' * 32, 'pid': 124}
        store.update(other, 'queued')
        states[123] = 'exited'
        store.update(other, 'queued')
        data = store.read()
        self.assertNotIn(self.ticket['id'], data['live'])
        self.assertIn(other['id'], data['live'])
        self.assertEqual(data['stats']['abandoned'], 1)
        self.assertEqual(data['stats']['builds'], 0)

    def test_optional_worker_is_async_and_finishes_without_changing_exception(self):
        entered, proceed = threading.Event(), threading.Event()
        events = []
        class SlowStore:
            def update(self, row, phase, **fields):
                entered.set(); proceed.wait(); events.append((phase, fields))
        observer = self.tray.BuildTelemetry(Path('D:/Project'), 'A task', store=SlowStore(), autostart=False)
        with self.assertRaisesRegex(RuntimeError, 'build problem'):
            with observer:
                observer.registered(self.ticket)
                entered.wait()
                observer.phase(self.ticket, 'preflight')
                observer.phase(self.ticket, 'running')
                proceed.set()
                raise RuntimeError('build problem')
        self.assertEqual([p for p, _ in events], ['queued', 'preflight', 'running', 'finished'])
        self.assertIsNone(events[-1][1]['exit_code'])

    def test_disabled_and_failed_telemetry_are_not_build_authority(self):
        with patch.object(self.tray, 'start') as start, patch.object(self.tray, 'TelemetryStore') as store:
            with self.tray.BuildTelemetry(Path('D:/Project'), enabled=False) as observer:
                observer.registered(self.ticket)
                observer.phase(self.ticket, 'running')
                observer.completed(7)
            start.assert_not_called(); store.assert_not_called()
        class BrokenStore:
            def update(self, *args, **kwargs):
                raise OSError('private error details')
        with self.tray.BuildTelemetry(Path('D:/Project'), store=BrokenStore(), autostart=False) as observer:
            observer.registered(self.ticket)
            observer.completed(7)
        self.assertEqual(observer.result['state'], 'unavailable')
        self.assertNotIn('private error', json.dumps(observer.result))

    def test_final_durations_exclude_post_release_notification_cleanup(self):
        store = self.store()
        observer = self.tray.BuildTelemetry(Path('D:/Project'), store=store, autostart=False)
        with patch.object(self.tray.time, 'monotonic', side_effect=[10, 15, 40, 45, 100]):
            with observer:
                observer.registered(self.ticket)
                observer.phase(self.ticket, 'preflight')
                observer.phase(self.ticket, 'running')
                observer.completed(0)
                observer.released()
        row = store.read()['recent'][0]
        self.assertEqual(row['gate_seconds'], 35)
        self.assertEqual(row['build_seconds'], 25)

    def test_build_integration_releases_gate_before_telemetry_collection(self):
        from agent_toolbelt_gradle_build_gate import gate
        from test_gate import ExecutionTicket
        events = []
        mutex = MagicMock(); mutex.abandoned = False
        mutex.__enter__.side_effect = lambda *a: events.append('acquired') or mutex
        mutex.__exit__.side_effect = lambda *a: events.append('gate_released')
        telemetry = MagicMock(); telemetry.__enter__.return_value = telemetry
        telemetry.phase.side_effect = lambda ticket, phase: events.append(phase)
        telemetry.completed.side_effect = lambda code: events.append(('exit', code))
        telemetry.released.side_effect = lambda: events.append('release_observed')
        telemetry.__exit__.side_effect = lambda *a: events.append('telemetry_collected')
        telemetry.result = {'state': 'recorded'}
        project = self.root / 'project'; project.mkdir(); (project / 'gradlew.bat').touch()
        with patch('agent_toolbelt_gradle_build_gate.queue.TicketQueue', return_value=ExecutionTicket(events)), \
             patch.object(gate, 'NamedMutex', return_value=mutex), \
             patch.object(gate, 'LifecycleObserver'), \
             patch.object(gate, 'inspect_activity', return_value={'safe_to_start': True, 'processes': []}), \
             patch('agent_toolbelt_gradle_build_gate.usage.record_project', return_value={'ok': True}), \
             patch.object(gate, 'make_profile', return_value={}), \
             patch.object(gate, 'execute_wrapper', return_value={'exit_code': 7}), \
             patch.object(self.tray, 'BuildTelemetry', return_value=telemetry):
            result = gate.run_build(project, ['test'], retire_daemons='none', notify=False)
        self.assertEqual(events, ['ticket_turn', 'acquired', 'preflight', 'running', ('exit', 7),
                                  'verifying_completion', 'gate_released', 'release_observed',
                                  'ticket_release', 'telemetry_collected'])
        self.assertEqual(result['exit_code'], 7)

    def test_queue_observation_failure_does_not_prevent_fifo_turn_or_release(self):
        if os.name != 'nt':
            self.skipTest('Native Windows queue')
        from agent_toolbelt_gradle_build_gate.queue import TicketQueue
        import uuid
        namespace = r'Local\Darka.GradleTrayQueueTest.' + uuid.uuid4().hex
        with TicketQueue(self.root, namespace, on_registered=lambda ticket: (_ for _ in ()).throw(
                OSError('optional observer failure'))) as request:
            self.assertEqual(request.ticket['number'], 1)
        self.assertEqual(json.loads((self.root / 'queue.json').read_text())['tickets'], [])

    def test_cli_routes_observer_and_optout_independently_of_toasts(self):
        from agent_toolbelt_gradle_build_gate import cli, gate
        import io
        with patch.object(gate, 'run_build', return_value={'exit_code': 0}) as run, contextlib.redirect_stdout(io.StringIO()):
            cli.main(['run', '--project', 'D:/Project', '--owner-task', 'Task', '--no-tray', '--', 'test'])
        self.assertFalse(run.call_args.kwargs['tray'])
        self.assertTrue(run.call_args.kwargs['notify'])
        with patch.object(self.tray, 'status', return_value={'state': 'idle'}) as snapshot, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['tray', 'status']), 0)
        snapshot.assert_called_once_with()


@unittest.skipUnless(os.name == 'nt', 'Native Windows tray observer')
class NativeTrayContracts(unittest.TestCase):
    store = TelemetryContracts.store

    def setUp(self):
        TelemetryContracts.setUp(self)
        from agent_toolbelt_gradle_build_gate.queue import NativeWait
        native = NativeWait()
        handle, ticks = native.process(os.getpid()); native.k.CloseHandle(handle)
        self.ticket.update(pid=os.getpid(), created_ticks=ticks)

    def snapshot(self, tickets):
        from agent_toolbelt_gradle_build_gate.support import save
        save(self.root / 'queue.json', {'schema': 1, 'next_number': 10, 'tickets': tickets})
        return self.tray.status(self.root)

    def test_native_snapshot_hover_content_identity_and_read_only_behavior(self):
        store = self.store()
        row = {**self.ticket, 'owner_task': 'A long human task title & symbols', 'project': 'D:/Exact Project'}
        store.update(row, 'queued')
        store.update(row, 'preflight', acquired_at=100)
        store.update(row, 'running', build_started_at=110)
        data = self.snapshot([self.ticket])
        before = (self.root / 'queue.json').read_bytes(), (self.root / 'telemetry.json').read_bytes()
        self.assertEqual(data['state'], 'busy')
        self.assertEqual(data['waiting'], 0)
        self.assertEqual(data['owner']['project'], 'D:/Exact Project')
        self.assertIn('A long human task title & symbols', data['text'])
        self.assertIn('Average queue wait', data['text'])
        self.assertEqual(data['icon_style'], 'local_gradle_elephant')
        self.assertLessEqual(len(data['tooltip']), 63)
        second = {**self.ticket, 'id': 'b' * 32, 'number': 2}
        self.assertEqual(self.snapshot([self.ticket, second])['waiting'], 1)
        self.assertEqual((self.root / 'telemetry.json').read_bytes(), before[1])
        stale = {**self.ticket, 'created_ticks': self.ticket['created_ticks'] + 1}
        data = self.snapshot([stale])
        self.assertIsNone(data['owner']); self.assertEqual(data['waiting'], 0)
        self.assertEqual((self.root / 'telemetry.json').read_bytes(), before[1])
        (self.root / 'telemetry.json').unlink()
        data = self.snapshot([self.ticket])
        self.assertEqual(data['state'], 'uncertain')
        self.assertIsNone(data['owner'])
        self.assertIsNone(data['waiting'])
        self.assertEqual(data['registered_requests'], 1)
        self.assertIn('older helper', data['text'])
        (self.root / 'queue.json').write_text('{broken')
        self.assertEqual(self.tray.status(self.root)['state'], 'uncertain')

    def test_native_singleton_stop_only_observer(self):
        from agent_toolbelt_gradle_build_gate.queue import NativeWait
        self.assertFalse(self.tray.running(self.root))
        result = self.tray.start(self.root)
        native = NativeWait()
        process, _ = native.process(result['pid'])
        try:
            self.assertEqual(result['state'], 'started')
            self.assertTrue(self.tray.running(self.root))
            self.assertEqual(self.tray.start(self.root)['state'], 'already_running')
            self.assertFalse((self.root / 'queue.json').exists())
            self.assertEqual(self.tray.stop(self.root)['state'], 'stopped')
            self.assertEqual(native.k.WaitForSingleObject(process, 15000), 0,
                             'UI stop diagnostic failed; no Gradle process is involved')
            self.assertFalse(self.tray.running(self.root))
        finally:
            self.tray.stop(self.root)
            if process: native.k.CloseHandle(process)

    def test_native_concurrent_telemetry_writers_keep_distinct_results(self):
        from concurrent.futures import ThreadPoolExecutor
        store = self.tray.TelemetryStore(self.root)
        def write(number):
            row = {**self.ticket, 'id': f'{number:032x}', 'number': number}
            store.update(row, 'queued')
            store.update(row, 'finished', exit_code=0, queue_seconds=0, gate_seconds=0, build_seconds=1)
        with ThreadPoolExecutor(max_workers=3) as workers:
            list(workers.map(write, [1, 2, 3]))
        self.assertEqual(store.read()['stats']['builds'], 3)
        self.assertEqual(len(store.read()['recent']), 3)

    def test_observer_survives_launcher_exit_and_external_stop_is_ticket_free(self):
        from agent_toolbelt_gradle_build_gate.queue import NativeWait
        code = ('import json,sys; from pathlib import Path; '
                'from agent_toolbelt_gradle_build_gate.tray import start; '
                'print(json.dumps(start(Path(sys.argv[1]))))')
        launched = subprocess.run([sys.executable, '-B', '-c', code, str(self.root)],
                                  env={**os.environ, 'PYTHONPATH': str(SRC)}, capture_output=True,
                                  text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        outcome = json.loads(launched.stdout)
        native = NativeWait()
        process, _ = native.process(outcome['pid'])
        try:
            self.assertEqual(outcome['state'], 'started')
            self.assertTrue(self.tray.running(self.root))
            self.assertEqual(self.tray.stop(self.root)['state'], 'stop_requested')
            self.assertEqual(native.k.WaitForSingleObject(process, 15000), 0)
            self.assertFalse((self.root / 'queue.json').exists())
        finally:
            self.tray.stop(self.root)
            if process: native.k.CloseHandle(process)


if __name__ == '__main__':
    unittest.main()
