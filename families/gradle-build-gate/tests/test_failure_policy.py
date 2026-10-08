import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import unittest
from unittest.mock import patch

from test_gate import temporary_workspace


class FailurePolicy(unittest.TestCase):
    def setUp(self):
        self.gate = importlib.import_module('agent_toolbelt_gradle_build_gate.gate')
        self.cli = importlib.import_module('agent_toolbelt_gradle_build_gate.cli')

    def test_default_and_explicit_collection_are_invocation_local(self):
        with temporary_workspace() as root, patch.dict(os.environ, {'GRADLE_GATE_COLLECT_ALL_FAILURES': 'true'}):
            for collect in (False, True):
                profile = self.gate.make_profile(Path(root), ['test'], [], collect_all_failures=collect)
                self.assertEqual(profile['test_fail_fast'], not collect)
                self.assertEqual(profile['environment']['GRADLE_GATE_COLLECT_ALL_FAILURES'], str(collect).lower())
                self.assertFalse(profile['test_ignore_failures'])
            self.assertEqual(os.environ['GRADLE_GATE_COLLECT_ALL_FAILURES'], 'true')

    def test_conflicting_options_cannot_disable_default(self):
        with temporary_workspace() as root:
            for option in ('--continue', '--continue=true', '--no-fail-fast', '--fail-fast'):
                with self.subTest(option=option), self.assertRaises(ValueError):
                    self.gate.make_profile(Path(root), ['test', option], [])
            profile = self.gate.make_profile(Path(root), ['test', '--continue'], [], collect_all_failures=True)
            self.assertIn('--continue', profile['arguments'])
            self.gate.make_profile(Path(root), ['test', '-m'], [])

    def test_cli_routes_collection_and_keeps_failed_exit(self):
        for options, collect in (([], False), (['--collect-all-failures'], True)):
            with patch.object(self.gate, 'run_build', return_value={'exit_code': 1}) as run, contextlib.redirect_stdout(io.StringIO()):
                exit_code = self.cli.main(['run', '--project', 'D:/fixture', *options, '--', 'test'])
            self.assertEqual(exit_code, 1)
            self.assertEqual(run.call_args.kwargs['collect_all_failures'], collect)

    def test_init_script_uses_native_failure_not_output_matching(self):
        script = (self.gate.ASSETS / 'profile.init.gradle').read_text()
        self.assertIn('task.failFast =', script)
        self.assertIn('task.ignoreFailures = false', script)
        self.assertIn('GRADLE_GATE_COLLECT_ALL_FAILURES', script)
        self.assertIn('fail_fast: task.failFast', script)

    def test_failure_result_releases_gate_only_after_wrapper_returns(self):
        from test_gate import ExecutionTicket
        from unittest.mock import MagicMock
        events = []
        mutex = MagicMock()
        mutex.abandoned = False
        mutex.__enter__.side_effect = lambda: events.append('acquire') or mutex
        mutex.__exit__.side_effect = lambda *a: events.append('release')
        with temporary_workspace() as root:
            project = Path(root)
            (project / 'gradlew.bat').touch()
            with patch('agent_toolbelt_gradle_build_gate.queue.TicketQueue', return_value=ExecutionTicket(events)), \
                 patch.object(self.gate, 'NamedMutex', return_value=mutex), \
                 patch.object(self.gate, 'LifecycleObserver'), \
                 patch('agent_toolbelt_gradle_build_gate.usage.record_project', return_value={'ok': True}), \
                 patch.object(self.gate, 'inspect_activity', return_value={'safe_to_start': True, 'processes': []}), \
                 patch.object(self.gate, 'execute_wrapper', side_effect=lambda *a: events.append('failed_wrapper_exit') or {'exit_code': 1}):
                result = self.gate.run_build(project, ['test'], retire_daemons='none')
        self.assertEqual(events, ['ticket_turn', 'acquire', 'failed_wrapper_exit', 'release', 'ticket_release'])
        self.assertFalse(result['ok'])
        self.assertTrue(result['gate_acquired'])

    @unittest.skipUnless(os.name == 'nt', 'Windows batch fixture')
    def test_error_text_is_harmless_and_failed_result_is_reported(self):
        with temporary_workspace() as root:
            project = Path(root)
            (project / 'gradlew.bat').write_text('@echo off\necho ERROR: intentional negative test\necho SampleTest ^> broken FAILED\nexit /b 7\n', encoding='ascii')
            profile = self.gate.make_profile(project, ['test'], [])
            result = self.gate.execute_wrapper(project, profile, project / 'failed.log')
            self.assertEqual(result['exit_code'], 7)
            self.assertEqual(result['failure_output_evidence'], ['SampleTest > broken FAILED'])
            self.assertFalse(result['test_failure_policy_verified'])
            (project / 'gradlew.bat').write_text('@echo off\necho ERROR: intentional negative test\nexit /b 0\n', encoding='ascii')
            result = self.gate.execute_wrapper(project, profile, project / 'passing.log')
            self.assertEqual(result['exit_code'], 0)
            self.assertEqual(result['failure_output_evidence'], [])

    @unittest.skipUnless(os.name == 'nt' and os.getenv('GRADLE_GATE_NATIVE_SMOKE') == '1',
                         'Opt-in real Gradle verification uses the production FIFO/mutex')
    def test_native_gradle_stops_early_and_opt_out_collects_failures(self):
        home = Path.home() / '.gradle'
        distributions = list((home / 'wrapper/dists/gradle-9.8.0-bin').glob('*/gradle-9.8.0'))
        junit = list((home / 'caches/modules-2/files-2.1/junit/junit/4.13.2').glob('*/*.jar'))
        hamcrest = list((home / 'caches/modules-2/files-2.1/org.hamcrest/hamcrest-core/1.3').glob('*/*.jar'))
        self.assertTrue(distributions and junit and hamcrest, 'Local offline Gradle/JUnit fixture dependencies required')
        with temporary_workspace(prefix='gate-native-failure-') as root:
            project = Path(root)
            (project / 'gradlew.bat').write_text('@echo off\ncall "' + str(distributions[0] / 'bin/gradle.bat') + '" %*\n', encoding='ascii')
            props = project / 'gradle/wrapper/gradle-wrapper.properties'
            props.parent.mkdir(parents=True)
            props.write_text('distributionUrl=https://services.gradle.org/distributions/gradle-9.8.0-bin.zip\n')
            (project / 'settings.gradle').write_text("rootProject.name = 'failure-policy-fixture'\n")
            jars = ', '.join(repr(p.as_posix()) for p in (junit[0], hamcrest[0]))
            (project / 'build.gradle').write_text("plugins { id 'java' }\ndependencies { testImplementation files(" + jars + ") }\ntest { useJUnit(); maxHeapSize = '128m'; ignoreFailures = true }\n")
            sources = project / 'src/test/java'
            sources.mkdir(parents=True)
            # Separate classes exercise scheduling: native fail-fast need not
            # interrupt methods already dispatched within a single fast class.
            for i in range(51):
                name = f'Failure{i:02d}Test'
                (sources / f'{name}.java').write_text('import org.junit.*;\npublic class ' + name +
                    ' { @Test public void fails() { Assert.fail("intentional native failure"); } }\n')
            totals = []
            # Only catalog attribution is mocked; queue, mutex, observer and native
            # Gradle execution are real. A disposable fixture is not a known project.
            with patch('agent_toolbelt_gradle_build_gate.usage.record_project', return_value={'ok': True, 'fixture': True}):
                for collect in (False, True):
                    result = self.gate.run_build(project, ['clean', 'test', '--offline', '--no-daemon',
                                                         '--no-configuration-cache', '--console=plain'],
                                                 retire_daemons='none', collect_all_failures=collect,
                                                 log_path=project / f'build-{collect}.log')
                    self.assertEqual(result['exit_code'], 1)
                    self.assertTrue(result['gate_acquired'])
                    self.assertTrue(result['test_failure_policy_verified'])
                    self.assertTrue(result['failure_output_evidence'])
                    reports = [ET.parse(p).getroot() for p in (project / 'build/test-results/test').glob('TEST-*.xml')]
                    totals.append(sum(int(r.attrib['tests']) - int(r.attrib.get('skipped', 0)) for r in reports))
                    self.assertEqual(sum(int(r.attrib['failures']) for r in reports), totals[-1])
                    print(json.dumps({'collect_all_failures': collect, 'executed': totals[-1]}), flush=True)
            self.assertLess(totals[0], totals[1])
            self.assertEqual(totals[1], 51)
            print(json.dumps({'native_fail_fast_test_counts': totals, 'gate_acquired': True,
                              'exit_codes': [1, 1]}))


if __name__ == '__main__':
    unittest.main()
