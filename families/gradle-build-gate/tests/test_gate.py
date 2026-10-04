import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import tempfile
import unittest
import uuid
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


def temporary_workspace(prefix="gradle-gate-test-"):
    preferred = Path("D:/Temp")
    return tempfile.TemporaryDirectory(prefix=prefix, dir=preferred if preferred.is_dir() else None)


class ExecutionTicket:
    ticket = {"number": 7, "id": "synthetic"}
    def __init__(self, events=None): self.events = events
    def __enter__(self):
        if self.events is not None: self.events.append("ticket_turn")
        return self
    def __exit__(self, *args):
        if self.events is not None: self.events.append("ticket_release")


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

    def test_retirement_selects_only_incompatible_idle_daemons(self):
        rows = [{"pid": 1, "state": "idle", "version": "8.13", "max_heap": "-xmx3g"},
                {"pid": 2, "state": "idle", "version": "8.12.1", "max_heap": "-xmx3g"},
                {"pid": 3, "state": "idle", "version": "8.13", "max_heap": "-xmx8g"}]
        selected = self.gate.retirement_candidates({"safe_to_start": True, "processes": rows}, "8.13", "-Xmx3g", "incompatible")
        self.assertEqual([p["pid"] for p in selected], [2, 3])
        self.assertEqual(selected[0]["retirement_reason"], "different_version")
        self.assertEqual(selected[1]["retirement_reason"], "different_heap")
        self.assertEqual(self.gate.retirement_candidates({"safe_to_start": True, "processes": [rows[0]]}, "8.13", "-Xmx3072m", "incompatible"), [])
        self.assertEqual(len(self.gate.retirement_candidates({"safe_to_start": True, "processes": rows}, "8.13", "-Xmx3g", "all-idle")), 3)
        self.assertEqual(self.gate.retirement_candidates({"safe_to_start": False, "processes": rows}, "8.13", "-Xmx3g", "none"), [])

    def test_retirement_rejects_busy_ambiguous_and_unknown_version(self):
        for state in ("active", "ambiguous"):
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.gate.retirement_candidates({"safe_to_start": False, "processes": [{"state": state}]}, "8.13", "-Xmx3g", "incompatible")
        with self.assertRaises(ValueError):
            self.gate.retirement_candidates({"safe_to_start": True, "processes": [{"state": "idle"}]}, "8.13", "-Xmx3g", "incompatible")

    def test_wrapper_version_is_pinned_without_a_gradle_launch(self):
        with temporary_workspace() as root:
            project = Path(root)
            props = project / "gradle/wrapper/gradle-wrapper.properties"
            props.parent.mkdir(parents=True)
            props.write_text("distributionUrl=https\\://services.gradle.org/distributions/gradle-8.13-bin.zip\n")
            self.assertEqual(self.gate.wrapper_version(project), "8.13")
            props.write_text("distributionUrl=https://example.invalid/custom.zip\n")
            with self.assertRaises(ValueError):
                self.gate.wrapper_version(project)

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
        with patch("agent_toolbelt_gradle_build_gate.queue.TicketQueue", return_value=ExecutionTicket(events)), \
             patch.object(self.gate, "NamedMutex", return_value=Mutex()), \
             patch.object(self.gate, "LifecycleObserver", return_value=Observer()), \
             patch.object(self.gate, "inspect_activity", side_effect=inspect), \
             patch.object(self.gate, "execute_wrapper", side_effect=lambda *args: events.append("execute") or {"exit_code": 0}), \
             patch.object(self.gate, "make_profile", return_value={"arguments": [], "environment": {}}):
            with temporary_workspace() as root:
                (Path(root) / "gradlew.bat").touch()
                result = self.gate.run_build(Path(root), ["test"], retire_daemons="none")
        self.assertEqual(events, ["ticket_turn", "acquire", "subscribe", "inspect", "wait", "inspect", "execute", "unsubscribe", "release", "ticket_release"])
        self.assertEqual(result["queue_ticket"]["number"], 7)

    def test_retirement_is_held_under_gate_and_rechecked_before_build(self):
        events = []
        candidate = {"pid": 2, "created": 100, "state": "idle", "version": "8.12.1", "max_heap": "-xmx3g"}
        snapshots = iter([{"safe_to_start": True, "processes": [candidate]},
                          {"safe_to_start": True, "processes": [candidate]},
                          {"safe_to_start": True, "processes": []}])
        class Mutex:
            abandoned = False
            def __enter__(self): events.append("acquire"); return self
            def __exit__(self, *args): events.append("release")
        class Observer:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with temporary_workspace() as root:
            project = Path(root); (project / "gradlew.bat").touch()
            with patch("agent_toolbelt_gradle_build_gate.queue.TicketQueue", return_value=ExecutionTicket(events)), \
                 patch.object(self.gate, "NamedMutex", return_value=Mutex()), \
                 patch.object(self.gate, "LifecycleObserver", return_value=Observer()), \
                 patch.object(self.gate, "wrapper_version", return_value="8.13"), \
                 patch.object(self.gate, "inspect_activity", side_effect=lambda *a: events.append("inspect") or next(snapshots)), \
                 patch.object(self.gate, "make_profile", return_value={"gradle_jvmargs": "-Xmx3g"}), \
                 patch.object(self.gate, "retire_daemon", side_effect=lambda p: events.append("retire") or {"process_exit_verified": True}), \
                 patch.object(self.gate, "execute_wrapper", side_effect=lambda *a: events.append("build") or {"exit_code": 0}):
                result = self.gate.run_build(project, ["test"])
        self.assertEqual(events, ["ticket_turn", "acquire", "inspect", "inspect", "retire", "inspect", "build", "release", "ticket_release"])
        self.assertTrue(result["daemon_retirement"]["retired"][0]["process_exit_verified"])

    def test_new_activity_before_retirement_cannot_be_stopped(self):
        candidate = {"pid": 2, "created": 100, "state": "idle", "version": "8.12", "max_heap": "-xmx3g"}
        idle = {"safe_to_start": True, "processes": [candidate]}
        busy = {"safe_to_start": False, "processes": [{**candidate, "state": "active"}]}
        class Mutex:
            abandoned = False
            def __enter__(self): return self
            def __exit__(self, *args): pass
        class Observer:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def wait(self): raise RuntimeError("external build still active")
        with temporary_workspace() as root:
            (Path(root) / "gradlew.bat").touch()
            with patch("agent_toolbelt_gradle_build_gate.queue.TicketQueue", return_value=ExecutionTicket()), \
                 patch.object(self.gate, "NamedMutex", return_value=Mutex()), \
                 patch.object(self.gate, "LifecycleObserver", return_value=Observer()), \
                 patch.object(self.gate, "wrapper_version", return_value="8.13"), \
                 patch.object(self.gate, "make_profile", return_value={"gradle_jvmargs": "-Xmx3g"}), \
                 patch.object(self.gate, "inspect_activity", side_effect=[idle, busy, busy]), \
                 patch.object(self.gate, "retire_daemon") as retire, patch.object(self.gate, "execute_wrapper") as build:
                with self.assertRaisesRegex(RuntimeError, "still active"):
                    self.gate.run_build(Path(root), ["test"])
                retire.assert_not_called(); build.assert_not_called()

    def test_daemon_metadata_handles_quoted_distribution_path(self):
        row = {"command": 'java -Xmx3072m -cp "D:\\Tools with spaces\\gradle-8.13\\lib\\gradle-launcher-8.13.jar" org.gradle.launcher.daemon.bootstrap.GradleDaemon 8.13',
               "executable": "java.exe"}
        result = self.gate.daemon_details(row)
        self.assertEqual(result["version"], "8.13")
        self.assertEqual(result["distribution"], str(Path(r"D:\Tools with spaces\gradle-8.13")))

    @unittest.skipUnless(os.name == "nt", "Windows daemon identity")
    def test_real_graceful_protocol_handshake_and_exit(self):
        distributions = list((Path.home() / ".gradle/wrapper/dists").glob("gradle-8.13-bin/*/gradle-8.13"))
        java = shutil.which("java")
        if not distributions or not java:
            self.skipTest("Local Gradle 8.13/JDK protocol fixture unavailable")
        with temporary_workspace() as root:
            registry = Path(root) / "registry.bin"
            server = subprocess.Popen([java, "-Xmx128m", "--class-path", str(distributions[0] / "lib/*"),
                                       str(SRC.parent / "tests/fixtures/SyntheticDaemon.java"), str(registry), "Idle"],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                      creationflags=self.gate.NO_WINDOW)
            try:
                ready = server.stdout.readline()
                if not ready:
                    self.fail(server.stderr.read())
                identity = json.loads(ready)
                candidate = {"pid": identity["pid"], "created": identity["created"] / 1000,
                             "version": "8.13", "distribution": str(distributions[0]), "java_executable": java,
                             "daemon_log": str(Path(root) / "daemon.out.log"), "retirement_reason": "test_fixture"}
                self.assertEqual(self.gate.retire_daemon(candidate, inspect_only=True)["outcome"], "registry_idle_verified")
                with self.assertRaises(RuntimeError):
                    self.gate.retire_daemon({**candidate, "created": candidate["created"] - 10}, inspect_only=True)
                result = self.gate.retire_daemon(candidate)
                self.assertTrue(result["process_exit_verified"])
                self.assertEqual(server.wait(), 0, server.stderr.read())
            finally:
                if server.poll() is None:
                    server.terminate()  # Our synthetic protocol process only.
                server.wait(); server.stdout.close(); server.stderr.close()

    @unittest.skipUnless(os.name == "nt", "Windows daemon identity")
    def test_live_busy_registry_fixture_is_not_stopped(self):
        distributions = list((Path.home() / ".gradle/wrapper/dists").glob("gradle-8.13-bin/*/gradle-8.13"))
        java = shutil.which("java")
        if not distributions or not java:
            self.skipTest("Local Gradle 8.13/JDK protocol fixture unavailable")
        with temporary_workspace() as root:
            server = subprocess.Popen([java, "-Xmx128m", "--class-path", str(distributions[0] / "lib/*"),
                                       str(SRC.parent / "tests/fixtures/SyntheticDaemon.java"), str(Path(root) / "registry.bin"), "Busy"],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=self.gate.NO_WINDOW)
            try:
                ready = server.stdout.readline()
                if not ready:
                    self.fail(server.stderr.read())
                identity = json.loads(ready)
                candidate = {"pid": identity["pid"], "created": identity["created"] / 1000, "version": "8.13",
                             "distribution": str(distributions[0]), "java_executable": java,
                             "daemon_log": str(Path(root) / "daemon.out.log")}
                with self.assertRaises(RuntimeError):
                    self.gate.retire_daemon(candidate)
                self.assertIsNone(server.poll(), "Busy protocol fixture must remain alive")
            finally:
                if server.poll() is None:
                    server.terminate()  # Our synthetic process, never a real daemon.
                server.wait(); server.stdout.close(); server.stderr.close()

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
            active = json.loads((runtime / "active.json").read_text())
            self.assertTrue((runtime / "releases" / active["release"] / "agent_toolbelt_gradle_build_gate/assets/RetireDaemon.java").is_file())
            env = dict(os.environ)
            env.pop("AGENT_TOOLBELT_HOME", None)
            env["GRADLE_BUILD_GATE_HOME"] = str(runtime)
            call = subprocess.run([sys.executable, "-B", str(skills / "gradle-build-gate/scripts/invoke_gradle_build_gate.py"), "--help"],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(call.returncode, 0, call.stderr)
            self.assertIn("status", call.stdout)
            call = subprocess.run([sys.executable, "-B", str(skills / "gradle-build-gate/scripts/invoke_gradle_build_gate.py"), "run", "--help"],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(call.returncode, 0, call.stderr)
            self.assertIn("--retire-daemons", call.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows kernel mutex")
    def test_real_mutex_across_processes_and_abandonment(self):
        # Kernel semantics do not require occupying the live host build gate.
        test_name = "Local\\Darka.GradleGateTest." + uuid.uuid4().hex
        patcher = patch.object(self.gate, "MUTEX_NAME", test_name)
        patcher.start(); self.addCleanup(patcher.stop)
        # Parent owns the production mutex; a child cannot acquire it until release.
        prefix = 'from agent_toolbelt_gradle_build_gate import gate; gate.MUTEX_NAME=' + repr(test_name) + '; from agent_toolbelt_gradle_build_gate.gate import NamedMutex; '
        code = prefix + 'import sys; print("ready",flush=True); m=NamedMutex(); m.__enter__(); print("acquired",flush=True); sys.stdin.readline(); m.__exit__(None,None,None)'
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
        code = prefix + 'import os; m=NamedMutex(); m.__enter__(); os._exit(0)'
        # Keep an open handle so abandonment remains observable after owner death.
        m = self.gate.NamedMutex()
        child = subprocess.Popen([sys.executable, "-B", "-c", code], env=env)
        self.assertEqual(child.wait(), 0)
        with m:
            self.assertTrue(m.abandoned)


if __name__ == "__main__":
    unittest.main()
