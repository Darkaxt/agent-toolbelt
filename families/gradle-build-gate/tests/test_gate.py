import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


def temporary_workspace(prefix="gradle-gate-test-"):
    preferred = Path("D:/Temp")
    return tempfile.TemporaryDirectory(prefix=prefix, dir=preferred if preferred.is_dir() else None)


class Contracts(unittest.TestCase):
    def setUp(self):
        self.gate = importlib.import_module("agent_toolbelt_gradle_build_gate.gate")

    def test_daemon_requires_log_identity_idle_and_no_client_connection(self):
        classify = self.gate.classify_process
        p = {"pid": 10, "created": 100, "name": "java.exe",
             "command": "org.gradle.launcher.daemon.bootstrap.GradleDaemon"}
        self.assertEqual(classify(p, "Marking the daemon as idle", 101, False, True), "idle")
        self.assertEqual(classify(p, "Marking the daemon as idle", 99, False, True), "ambiguous")
        self.assertEqual(classify(p, "Marking the daemon as idle", 101, True, True), "active")
        self.assertEqual(classify(p, "Marking the daemon as idle", 101, False, False), "ambiguous")
        self.assertEqual(classify(p, "", 101, False, True), "ambiguous")

    def test_latest_lifecycle_not_cpu_or_sleep_message(self):
        p = {"pid": 10, "created": 100, "name": "java.exe",
             "command": "org.gradle.launcher.daemon.bootstrap.GradleDaemon"}
        log = "Marking the daemon as idle\nMarking the daemon as busy\ndaemon is running. Sleeping until state changes."
        self.assertEqual(self.gate.classify_process(p, log, 101, False, True), "active")
        self.assertEqual(self.gate.classify_process(p, log + "\nMarking the daemon as idle", 101, False, True), "idle")

    def test_idle_marker_must_not_disappear_behind_periodic_log_noise(self):
        with temporary_workspace() as folder:
            p = Path(folder) / "daemon-10.out.log"
            p.write_text("Marking the daemon as idle\n" + "health check\n" * 30000, encoding="utf-8")
            self.assertEqual(self.gate.daemon_lifecycle(p), "Marking the daemon as idle")
            with p.open("a", encoding="utf-8") as handle:
                handle.write("Marking the daemon as busy\n")
            self.assertEqual(self.gate.daemon_lifecycle(p), "Marking the daemon as busy")

    def test_client_and_inaccessible_java_block(self):
        for command in ("org.gradle.wrapper.GradleWrapperMain test", "org.gradle.launcher.GradleMain test"):
            p = {"pid": 10, "created": 100, "name": "java.exe", "command": command}
            self.assertEqual(self.gate.classify_process(p), "active")
        self.assertEqual(self.gate.classify_process({"name": "java.exe", "command": None}), "ambiguous")
        self.assertEqual(self.gate.classify_process({"name": "java.exe", "command": "com.example.Other"}), "unrelated")

    def test_profile_preserves_other_arguments_and_removes_duplicate_heap(self):
        self.assertEqual(self.gate.heap_args('-Xms256m -Xmx8g -Dfile.encoding=UTF-8 --add-opens=java.base/java.lang=ALL-UNNAMED', 3),
                         '-Xms256m -Dfile.encoding=UTF-8 --add-opens=java.base/java.lang=ALL-UNNAMED -Xmx3g')

    def test_profile_reads_user_overrides_and_native_budget(self):
        with temporary_workspace() as root:
            project = Path(root) / "project"; project.mkdir()
            home = Path(root) / "gradle-home"; home.mkdir()
            (project / "gradle.properties").write_text("org.gradle.jvmargs=-Dproject=kept -Xmx8g\n")
            (home / "gradle.properties").write_text("org.gradle.jvmargs=-Duser=kept -XX:+UseG1GC -Xmx5g\nkotlin.daemon.jvmargs=-Xms512m -Xmx6g\n")
            profile = self.gate.make_profile(project, ["test", "-g", str(home)], [home])
            self.assertEqual(profile["gradle_jvmargs"], "-Duser=kept -XX:+UseG1GC -Xmx3g")
            self.assertEqual(profile["kotlin_daemon_jvmargs"], "-Xms512m -Xmx3g")
            self.assertEqual(profile["environment"]["CMAKE_BUILD_PARALLEL_LEVEL"], "2")
            self.assertNotIn("kotlin.compiler.execution.strategy", " ".join(profile["arguments"]))
            with self.assertRaises(ValueError):
                self.gate.make_profile(project, ["test"], [home], gradle_heap=4)

    @unittest.skipUnless(os.name == "nt", "Windows lifecycle subscriptions")
    def test_real_watcher_observes_log_change_without_sleep(self):
        with temporary_workspace() as root:
            log = Path(root) / "daemon/9/daemon-10.out.log"
            log.parent.mkdir(parents=True)
            log.write_text("initial\n")
            with self.gate.LifecycleObserver([Path(root)]) as watcher:
                with log.open("a") as handle:
                    handle.write("Marking the daemon as idle\n")
                watcher.wait()

    @unittest.skipUnless(os.name == "nt", "Windows batch wrapper")
    def test_synthetic_wrapper_exit_and_space_quoting(self):
        with temporary_workspace(prefix="gate test ") as root:
            project = Path(root)
            (project / "gradlew.bat").write_text('@echo off\necho %*\nexit /b 7\n', encoding="ascii")
            profile = self.gate.make_profile(project, ["test", "-Pnote=two words"], [])
            result = self.gate.execute_wrapper(project, profile, project / "build.log")
            self.assertEqual(result["exit_code"], 7)
            self.assertFalse(result["gradle_profile_verified"])
            self.assertIn("two words", (project / "build.log").read_text())

    def test_command_profile_cannot_be_silently_overridden(self):
        for args in (["--parallel"], ["--max-workers=8"], ["--stop"], ["assembleDebug", "&", "whoami"], ["-Dorg.gradle.parallel=true"]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.gate.validate_arguments(args)

    def test_inherited_jvm_heap_override_is_not_silently_accepted(self):
        with temporary_workspace() as root, patch.dict(os.environ, {"_JAVA_OPTIONS": "-Xmx12g"}):
            with self.assertRaisesRegex(ValueError, "_JAVA_OPTIONS"):
                self.gate.make_profile(Path(root), ["test"], [])

    def test_java_properties_continuations_and_unicode(self):
        with temporary_workspace() as folder:
            p = Path(folder) / "gradle.properties"
            p.write_text('org.gradle.jvmargs=-Dnote=hello\\u0020world ' + '\\' + '\n -XX:+HeapDumpOnOutOfMemoryError\n', encoding="utf-8")
            value = self.gate.read_properties(p)["org.gradle.jvmargs"]
            self.assertIn("hello world", value)
            self.assertIn("HeapDumpOnOutOfMemoryError", value)

    def test_gate_before_observation_and_held_through_exit(self):
        events = []
        class Mutex:
            abandoned = False
            def __enter__(self): events.append("acquire"); return self
            def __exit__(self, *args): events.append("release")
        class Observer:
            def __enter__(self): events.append("subscribe"); return self
            def __exit__(self, *args): events.append("unsubscribe")
            def wait(self): events.append("wait")
        inspections = iter([{"safe_to_start": False, "processes": [{"state": "ambiguous"}]},
                            {"safe_to_start": True, "processes": []}])
        def inspect(*args): events.append("inspect"); return next(inspections)
        with patch.object(self.gate, "NamedMutex", return_value=Mutex()), \
             patch.object(self.gate, "LifecycleObserver", return_value=Observer()), \
             patch.object(self.gate, "inspect_activity", side_effect=inspect), \
             patch.object(self.gate, "execute_wrapper", side_effect=lambda *args: events.append("execute") or {"exit_code": 0}), \
             patch.object(self.gate, "make_profile", return_value={"arguments": [], "environment": {}}):
            with temporary_workspace() as root:
                (Path(root) / "gradlew.bat").touch()
                self.gate.run_build(Path(root), ["test"])
        self.assertEqual(events, ["acquire", "subscribe", "inspect", "wait", "inspect", "execute", "unsubscribe", "release"])

    @unittest.skipUnless(os.name == "nt", "Windows batch argument forwarding")
    def test_required_jvm_quotes_and_spaces_reach_wrapper_unchanged(self):
        with temporary_workspace(prefix="gate spaces ") as root:
            project = Path(root)
            (project / "capture.py").write_text('import json, sys\nprint(json.dumps(sys.argv[1:]))\n')
            (project / "gradlew.bat").write_text('@echo off\n"' + sys.executable + '" -B "%~dp0capture.py" %*\n', encoding="ascii")
            (project / "gradle.properties").write_text('org.gradle.jvmargs=-Dnote="two words" -XX:+UseG1GC -Xmx8g\n')
            profile = self.gate.make_profile(project, ["test"], [])
            result = self.gate.execute_wrapper(project, profile, project / "build.log")
            self.assertEqual(result["exit_code"], 0)
            args = json.loads((project / "build.log").read_text())
            self.assertIn('-Dorg.gradle.jvmargs=-Dnote="two words" -XX:+UseG1GC -Xmx3g', args)

    def test_installer_works_without_repository_bootstrap(self):
        spec = importlib.util.spec_from_file_location("gradle_install", SRC.parent / "scripts/install.py")
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        with temporary_workspace() as root:
            runtime = Path(root) / "runtime"
            skills = Path(root) / "skills"
            installer.install(runtime, [skills])
            env = dict(os.environ)
            env.pop("AGENT_TOOLBELT_HOME", None)
            env["GRADLE_BUILD_GATE_HOME"] = str(runtime)
            call = subprocess.run([sys.executable, "-B", str(skills / "gradle-build-gate/scripts/invoke_gradle_build_gate.py"), "--help"],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(call.returncode, 0, call.stderr)
            self.assertIn("status", call.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows kernel mutex")
    def test_real_mutex_across_processes_and_abandonment(self):
        # Parent owns the production mutex; a child cannot acquire it until release.
        code = 'from agent_toolbelt_gradle_build_gate.gate import NamedMutex; import sys; print("ready",flush=True); m=NamedMutex(); m.__enter__(); print("acquired",flush=True); sys.stdin.readline(); m.__exit__(None,None,None)'
        env = {**os.environ, "PYTHONPATH": str(SRC)}
        with self.gate.NamedMutex():
            child = subprocess.Popen([sys.executable, "-B", "-u", "-c", code], env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            self.assertEqual(child.stdout.readline().strip(), "ready")
            self.assertIsNone(child.poll())
        self.assertEqual(child.stdout.readline().strip(), "acquired")
        child.stdin.write("done\n"); child.stdin.flush()
        self.assertEqual(child.wait(), 0)
        child.stdin.close(); child.stdout.close()
        code = 'from agent_toolbelt_gradle_build_gate.gate import NamedMutex; import os; m=NamedMutex(); m.__enter__(); os._exit(0)'
        # Keep an open handle so abandonment remains observable after owner death.
        m = self.gate.NamedMutex()
        child = subprocess.Popen([sys.executable, "-B", "-c", code], env=env)
        self.assertEqual(child.wait(), 0)
        with m:
            self.assertTrue(m.abandoned)


if __name__ == "__main__":
    unittest.main()
