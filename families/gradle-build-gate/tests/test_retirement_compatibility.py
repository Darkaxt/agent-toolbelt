import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


class Compatibility(unittest.TestCase):
    def setUp(self):
        self.gate = importlib.import_module("agent_toolbelt_gradle_build_gate.gate")

    @unittest.skipUnless(os.name == "nt", "Installed Windows Gradle distributions")
    def test_adapter_compiles_against_installed_distributions_without_shutdown(self):
        java = shutil.which("java")
        distributions = sorted((Path.home() / ".gradle/wrapper/dists").glob("gradle-*/*/gradle-*/lib"))
        if not java or not distributions:
            self.skipTest("No local JDK/Gradle distributions")
        for lib in distributions:
            with self.subTest(version=lib.parent.name):
                result = subprocess.run([java, "-Xmx128m", "--class-path", str(lib / "*"),
                                         str(self.gate.ASSETS / "RetireDaemon.java"), "inspect",
                                         str(lib / "nonexistent-registry"), "2147483647", "0"],
                                        capture_output=True, text=True, creationflags=self.gate.NO_WINDOW)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "already_exited")

    def test_compiler_failure_is_actionable_and_sanitized(self):
        from types import SimpleNamespace
        diagnostic = ('C:/private/path/RetireDaemon.java:14: error: cannot find symbol\n'
                      ' symbol: class DaemonState\n'
                      ' location: package org.gradle.launcher.daemon.server.api\n'
                      'RetireDaemon$2 is not abstract and does not override abstract method '
                      'start(long,Action<FileLockReleasedSignal>) in FileLockContentionHandler\n'
                      'token=super-secret auth bytes [11, 12, 13]\n')
        child = SimpleNamespace(returncode=1, communicate=lambda: ("", diagnostic), wait=lambda: 1,
                                stdout=SimpleNamespace(close=lambda: None), stderr=SimpleNamespace(close=lambda: None))
        with tempfile.TemporaryDirectory(dir="D:/Temp" if Path("D:/Temp").is_dir() else None) as root:
            path = Path(root); (path / "lib").mkdir(); (path / "registry.bin").touch()
            java = path / "java.exe"; java.touch()
            candidate = {"java_executable": str(java), "distribution": str(path),
                         "daemon_log": str(path / "daemon.out.log"), "pid": 10, "created": 100, "version": "8.6"}
            with patch.object(self.gate.subprocess, "Popen", return_value=child):
                with self.assertRaises(RuntimeError) as error:
                    self.gate.retire_daemon(candidate)
            self.assertEqual(error.exception.failure_kind, "adapter_compilation_failure")
            text = str(error.exception)
            self.assertIn("DaemonState", text)
            self.assertIn("Action<FileLockReleasedSignal>", text)
            self.assertNotIn("super-secret", text)
            self.assertNotIn("private/path", text)

    def test_cli_preserves_structured_sanitized_failure(self):
        import contextlib
        import io
        cli = importlib.import_module("agent_toolbelt_gradle_build_gate.cli")
        failure = self.gate.RetirementFailure({"pid": 10, "version": "8.6"}, 1,
                                             ["cannot find symbol", "symbol: class DaemonState"], True)
        output = io.StringIO()
        with patch.object(self.gate, "run_build", side_effect=failure), contextlib.redirect_stdout(output):
            result = cli.main(["run", "--project", "D:/fixture", "--", "test"])
        payload = json.loads(output.getvalue())
        self.assertEqual(result, 2)
        self.assertEqual(payload["failure_kind"], "adapter_compilation_failure")
        self.assertEqual(payload["retirement_diagnostics"]["target_version"], "8.6")
        self.assertFalse(payload["safe_to_continue"])

    @unittest.skipUnless(os.name == "nt", "Native Gradle 8.6 protocol")
    def test_86_graceful_exit_busy_rejection_and_racing_work(self):
        java = shutil.which("java")
        distributions = list((Path.home() / ".gradle/wrapper/dists").glob("gradle-8.6-bin/*/gradle-8.6"))
        if not java or not distributions:
            self.skipTest("No local Gradle 8.6/JDK")
        for state, race in (("Idle", False), ("Busy", False), ("Idle", True)):
            with self.subTest(state=state, race=race), tempfile.TemporaryDirectory(dir="D:/Temp" if Path("D:/Temp").is_dir() else None) as root:
                server = subprocess.Popen([java, "-Xmx128m", "--class-path", str(distributions[0] / "lib/*"),
                                           str(SRC.parent / "tests/fixtures/SyntheticDaemon86.java"),
                                           str(Path(root) / "registry.bin"), state, "race" if race else "normal"],
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True, creationflags=self.gate.NO_WINDOW)
                worker = None
                try:
                    ready = server.stdout.readline()
                    self.assertTrue(ready, server.stderr.read() if not ready else "")
                    identity = json.loads(ready)
                    candidate = {"pid": identity["pid"], "created": identity["created"] / 1000,
                                 "version": "8.6", "distribution": str(distributions[0]), "java_executable": java,
                                 "daemon_log": str(Path(root) / "daemon.out.log")}
                    if state == "Busy":
                        with self.assertRaisesRegex(RuntimeError, "daemon_not_idle"):
                            self.gate.retire_daemon(candidate)
                        self.assertIsNone(server.poll(), "Busy target must remain alive")
                    elif not race:
                        self.assertTrue(self.gate.retire_daemon(candidate)["process_exit_verified"])
                        self.assertEqual(server.wait(), 0, server.stderr.read())
                    else:
                        code = ('import json,sys; from agent_toolbelt_gradle_build_gate.gate import retire_daemon; '
                                'print(json.dumps(retire_daemon(json.loads(sys.argv[1]))),flush=True)')
                        worker = subprocess.Popen([sys.executable, "-B", "-c", code, json.dumps(candidate)],
                                                  env={**os.environ, "PYTHONPATH": str(SRC)}, stdout=subprocess.PIPE,
                                                  stderr=subprocess.PIPE, text=True, creationflags=self.gate.NO_WINDOW)
                        self.assertEqual(server.stdout.readline().strip(), "racing_work_preserved")
                        self.assertIsNone(worker.poll(), "Must supervise actual exit, not just shutdown reply")
                        self.assertIsNone(server.poll(), "Racing work must not be cancelled")
                        server.stdin.write("work_complete\n"); server.stdin.flush()
                        result = json.loads(worker.stdout.readline())
                        self.assertTrue(result["process_exit_verified"])
                        self.assertEqual(worker.wait(), 0, worker.stderr.read())
                        self.assertEqual(server.wait(), 0, server.stderr.read())
                finally:
                    for child in (worker, server):
                        if child is None:
                            continue
                        if child.poll() is None:
                            child.terminate()  # Isolated owned fixture/supervisor only.
                        child.wait()
                        for stream in (child.stdin, child.stdout, child.stderr):
                            if stream:
                                stream.close()


if __name__ == "__main__":
    unittest.main()
