import contextlib
import importlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_gradle_build_gate import cli, gate


class DaemonLifecycleTests(unittest.TestCase):
    def test_profile_disables_daemon_reuse_by_default_and_preserves_budgets(self):
        with tempfile.TemporaryDirectory(dir='D:/Temp') as root:
            profile = gate.make_profile(Path(root), ['help'], [])
        self.assertIn('--no-daemon', profile['arguments'])
        self.assertEqual(profile['daemon_lifecycle'], 'single_use')
        self.assertIn('-Xmx3g', profile['gradle_jvmargs'])
        self.assertEqual(profile['kotlin_strategy'], 'project_default')

    def test_reuse_requires_explicit_opt_out_and_conflicts_are_rejected(self):
        with tempfile.TemporaryDirectory(dir='D:/Temp') as root:
            project = Path(root)
            keep = gate.make_profile(project, ['help'], [], keep_daemon=True)
            self.assertIn('--daemon', keep['arguments'])
            explicit = gate.make_profile(project, ['help', '--no-daemon'], [])
            self.assertEqual(explicit['arguments'].count('--no-daemon'), 1)
            for args in (['help', '--daemon'], ['help', '-Dorg.gradle.daemon=true'],
                         ['help', '-Porg.gradle.daemon=true']):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    gate.make_profile(project, args, [])
            with self.assertRaises(ValueError):
                gate.make_profile(project, ['help', '--no-daemon'], [], keep_daemon=True)

    def test_cli_defaults_to_all_idle_retirement_and_forwards_opt_out(self):
        with patch.object(gate, 'run_build', return_value={'exit_code': 0}) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            cli.main(['run', '--project', 'D:/fixture', '--keep-daemon', '--', 'help'])
        self.assertEqual(run.call_args.kwargs['retire_daemons'], 'all-idle')
        self.assertTrue(run.call_args.kwargs['keep_daemon'])

    def test_completion_waits_for_activity_then_retires_idle_until_exit(self):
        events = []
        idle = {'pid': 22, 'created': 123, 'state': 'idle', 'version': '8.6', 'max_heap': '-xmx3g'}
        snapshots = [
            {'safe_to_start': False, 'processes': [{**idle, 'state': 'active'}]},
            {'safe_to_start': True, 'processes': [idle]},
            {'safe_to_start': True, 'processes': [idle]},
            {'safe_to_start': True, 'processes': []}]
        observer = MagicMock()
        observer.__enter__.return_value = observer
        observer.pids = None
        observer.wait.side_effect = lambda: events.append('wait')
        with patch.object(gate, 'LifecycleObserver', return_value=observer), \
                patch.object(gate, 'inspect_activity', side_effect=snapshots), \
                patch.object(gate, 'retire_daemon', side_effect=lambda p: events.append('retire') or
                             {'pid': p['pid'], 'process_exit_verified': True}) as retire:
            result = gate.finish_daemon_lifecycle([], lambda: events.append('phase'))
        self.assertEqual(events, ['phase', 'wait', 'retire'])
        self.assertTrue(result['exit_verified'])
        self.assertEqual(retire.call_args.args[0]['pid'], 22)

    def test_new_build_before_retirement_is_not_cancelled(self):
        idle = {'pid': 22, 'created': 123, 'state': 'idle', 'version': '8.6', 'max_heap': '-xmx3g'}
        observer = MagicMock(); observer.__enter__.return_value = observer; observer.pids = None
        observer.wait.side_effect = RuntimeError('external work remains active')
        with patch.object(gate, 'LifecycleObserver', return_value=observer), \
                patch.object(gate, 'inspect_activity', side_effect=[
                    {'safe_to_start': True, 'processes': [idle]},
                    {'safe_to_start': False, 'processes': [{**idle, 'state': 'active'}]},
                    {'safe_to_start': False, 'processes': [{**idle, 'state': 'active'}]}]), \
                patch.object(gate, 'retire_daemon') as retire:
            with self.assertRaisesRegex(RuntimeError, 'external work'):
                gate.finish_daemon_lifecycle([], lambda: None)
        retire.assert_not_called()

    def test_post_build_retirement_finishes_before_mutex_release_on_failed_build(self):
        events = []
        mutex = MagicMock(); mutex.abandoned = False; mutex.__enter__.return_value = mutex
        mutex.__enter__.side_effect = lambda *a: events.append('acquire') or mutex
        mutex.__exit__.side_effect = lambda *a: events.append('release')
        queue = MagicMock(); queue.__enter__.return_value = queue; queue.ticket = {'id': 'fixture', 'number': 1}
        with tempfile.TemporaryDirectory(dir='D:/Temp') as root:
            project = Path(root); (project / 'gradlew.bat').touch()
            with patch('agent_toolbelt_gradle_build_gate.queue.TicketQueue', return_value=queue), \
                    patch('agent_toolbelt_gradle_build_gate.usage.record_project', return_value={'ok': True}), \
                    patch.object(gate, 'NamedMutex', return_value=mutex), \
                    patch.object(gate, 'LifecycleObserver'), \
                    patch.object(gate, 'inspect_activity', return_value={'safe_to_start': True, 'processes': []}), \
                    patch.object(gate, 'wrapper_version', return_value='8.6'), \
                    patch.object(gate, 'execute_wrapper', side_effect=lambda *a: events.append('build') or {'exit_code': 7}), \
                    patch.object(gate, 'finish_daemon_lifecycle', side_effect=lambda *a:
                                 events.append('retire') or {'exit_verified': True, 'retired': []}):
                result = gate.run_build(project, ['help'], notify=False, tray=False)
        self.assertEqual(events, ['acquire', 'build', 'retire', 'release'])
        self.assertEqual(result['exit_code'], 7)
        self.assertEqual(result['build_exit_code'], 7)
        self.assertTrue(result['post_build_daemons']['exit_verified'])

    def test_retirement_failure_does_not_claim_success_or_lose_build_result(self):
        queue = MagicMock(); queue.__enter__.return_value = queue; queue.ticket = {'id': 'fixture', 'number': 1}
        with tempfile.TemporaryDirectory(dir='D:/Temp') as root:
            project = Path(root); (project / 'gradlew.bat').touch()
            with patch('agent_toolbelt_gradle_build_gate.queue.TicketQueue', return_value=queue), \
                    patch('agent_toolbelt_gradle_build_gate.usage.record_project', return_value={'ok': True}), \
                    patch.object(gate, 'NamedMutex'), patch.object(gate, 'LifecycleObserver'), \
                    patch.object(gate, 'inspect_activity', return_value={'safe_to_start': True, 'processes': []}), \
                    patch.object(gate, 'wrapper_version', return_value='8.6'), \
                    patch.object(gate, 'execute_wrapper', return_value={'exit_code': 0}), \
                    patch.object(gate, 'finish_daemon_lifecycle', side_effect=gate.RetirementFailure(
                        {'pid': 22, 'version': '8.6'}, 1, ['cannot find symbol'], True)):
                result = gate.run_build(project, ['help'], notify=False, tray=False)
        self.assertFalse(result['ok'])
        self.assertEqual(result['exit_code'], 2)
        self.assertEqual(result['build_exit_code'], 0)
        self.assertEqual(result['post_build_daemons']['failure_kind'], 'adapter_compilation_failure')
        self.assertFalse(result['post_build_daemons']['exit_verified'])
