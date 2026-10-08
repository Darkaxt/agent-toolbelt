import copy
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from test_gate import temporary_workspace

support = importlib.import_module("agent_toolbelt_gradle_build_gate.support")


class OwnerContracts(unittest.TestCase):
    def test_reply_requires_live_current_unanswered_request_and_reason(self):
        state = {"status": "running", "revision": 7,
                 "request": {"id": "request", "revision": 7, "response": None}}
        support.validate_response(state, "request", "continue", "Thread dump shows expected IO")
        for changed, request, decision, reason in [
            ({"status": "wrapper_exited"}, "request", "cancel", "diagnosed"),
            ({"revision": 8}, "request", "cancel", "diagnosed"),
            ({}, "different", "cancel", "diagnosed"),
            ({}, "request", "cancel", " "),
            ({}, "request", "kill", "diagnosed"),
            ({"request": {"id": "request", "response": {}}}, "request", "cancel", "diagnosed"),
        ]:
            with self.subTest(changed=changed, request=request, decision=decision):
                with self.assertRaises(ValueError):
                    support.validate_response({**copy.deepcopy(state), **changed}, request, decision, reason)

    def test_owned_processes_exclude_reused_root_and_unrelated_java(self):
        root = {"pid": 1, "created_ticks": 100, "parent_pid": 0}
        child = {"pid": 2, "created_ticks": 101, "parent_pid": 1}
        unrelated = {"pid": 3, "created_ticks": 90, "parent_pid": 0}
        stale_child = {"pid": 4, "created_ticks": 99, "parent_pid": 1}
        self.assertEqual(support.owned_processes([root, child, unrelated, stale_child], root), [root, child])
        self.assertEqual(support.owned_processes([root, child], {"pid": 1, "created_ticks": 99}), [])

    def test_reused_daemon_needs_reciprocal_client_connection(self):
        wrapper = {"pid": 1, "created_ticks": 100, "parent_pid": 0}
        client = {"pid": 2, "created_ticks": 101, "parent_pid": 1, "gradle_client": True}
        daemon = {"pid": 3, "created_ticks": 50, "parent_pid": 0, "gradle_daemon": True}
        worker = {"pid": 4, "created_ticks": 102, "parent_pid": 3}
        one = {"pid": 2, "local_address": "127.0.0.1", "local_port": 4000,
               "remote_address": "127.0.0.1", "remote_port": 5000}
        other = {"pid": 3, "local_address": "127.0.0.1", "local_port": 5000,
                 "remote_address": "127.0.0.1", "remote_port": 4000}
        rows = [wrapper, client, daemon, worker]
        self.assertEqual(len(support.owned_processes(rows, wrapper, [one])), 2)
        self.assertEqual(len(support.owned_processes(rows, wrapper, [one, other])), 4)

    @unittest.skipUnless(os.name == "nt", "Windows exact process snapshot")
    def test_native_diagnostics_bind_exact_wrapper_start_time(self):
        with temporary_workspace() as folder:
            native = support.NativeWait()
            handle, ticks = native.process(os.getpid())
            native.k.CloseHandle(handle)
            result = support.diagnostics({"pid": os.getpid(), "created_ticks": ticks}, Path(folder))
            self.assertEqual(result["state"], "captured", result)
            self.assertIn({"pid": os.getpid(), "created_ticks": ticks},
                          [{"pid": row["pid"], "created_ticks": row["created_ticks"]} for row in result["processes"]])

    def test_cli_cancel_requires_current_request_and_routes_decision(self):
        cli = importlib.import_module("agent_toolbelt_gradle_build_gate.cli")
        from contextlib import redirect_stdout
        with patch.object(support, "respond", return_value={"ok": True}) as response, redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["cancel", "--ticket", "a" * 32, "--request", "current", "--reason", "diagnosed"]), 0)
        response.assert_called_once_with("a" * 32, "current", "cancel", "diagnosed")

    @unittest.skipUnless(os.name == "nt", "Windows metadata mutex")
    def test_capture_update_cannot_overwrite_independent_owner_response(self):
        with temporary_workspace() as folder:
            native = support.NativeWait()
            handle, ticks = native.process(os.getpid())
            native.k.CloseHandle(handle)
            ticket = {"id": "c" * 32, "pid": os.getpid(), "created_ticks": ticks}
            monitor = support.BuildSupport(ticket, folder, Path(folder) / "build.log", root=folder)
            request = {"id": "request", "revision": 0, "response": None}
            monitor.update(request=request)
            stale_copy = dict(request)
            try:
                support.respond(ticket["id"], "request", "continue", "verified progress", folder)
                monitor.update(request={**stale_copy, "diagnostics": {"state": "captured"}})
                self.assertEqual(support.read(ticket["id"], folder)["request"]["response"]["decision"], "continue")
            finally:
                monitor.finish(0)

    def test_ticket_path_rejects_traversal(self):
        for value in ("../other", "", "A" * 32):
            with self.assertRaises(ValueError):
                support.ticket_path(value, Path("unused"))

    def test_notification_is_not_acknowledgement_and_failure_is_visible(self):
        with patch.object(support, "codex_message", return_value={"state": "unavailable"}), \
                patch("sys.stderr", new_callable=io.StringIO) as output:
            result = support.notify("owner", {"id": "ticket"}, {"id": "request"}, Path("record.json"))
            self.assertEqual(result["state"], "unavailable")
            event = json.loads(output.getvalue())
            self.assertEqual(event["state"], "owner_support_requested")
            self.assertEqual(event["request_id"], "request")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(support.codex_message("owner", "message")["state"], "unavailable")

    @unittest.skipUnless(os.name == "nt", "Windows native identity/event contract")
    def test_response_roundtrip_and_duplicate_rejection(self):
        with temporary_workspace() as folder:
            native = support.NativeWait()
            handle, ticks = native.process(os.getpid())
            native.k.CloseHandle(handle)
            ticket = {"id": "a" * 32, "pid": os.getpid(), "created_ticks": ticks}
            state = {"schema": 1, "ticket": ticket, "status": "running", "revision": 1,
                     "request": {"id": "request", "revision": 1, "response": None}}
            support.save(support.ticket_path(ticket["id"], folder), state)
            result = support.respond(ticket["id"], "request", "continue", "expected long compile", folder)
            self.assertEqual(result["state"], "response_submitted")
            self.assertFalse(result["completion_verified"])
            self.assertEqual(support.read(ticket["id"], folder)["request"]["response"]["decision"], "continue")
            with self.assertRaises(ValueError):
                support.respond(ticket["id"], "request", "cancel", "duplicate", folder)

    @unittest.skipUnless(os.name == "nt", "Windows private-console Ctrl+C")
    def test_private_console_cancel_does_not_signal_other_process(self):
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        code = ("import signal,time; "
                "signal.signal(signal.SIGINT, lambda *args: (print('cancel_handled', flush=True), exit(23))); "
                "print('ready', flush=True); time.sleep(600)")
        child = subprocess.Popen([sys.executable, "-B", "-c", code], startupinfo=startup,
                                 creationflags=subprocess.CREATE_NEW_CONSOLE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                 text=True)
        untouched = subprocess.Popen([sys.executable, "-B", "-c", "import time; print('ready',flush=True); time.sleep(600)"],
                                     creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "ready")
            self.assertEqual(untouched.stdout.readline().strip(), "ready")
            native = support.NativeWait()
            handle, ticks = native.process(child.pid)
            native.k.CloseHandle(handle)
            wrong = support.request_console_cancel({"pid": child.pid, "created_ticks": ticks + 1})
            self.assertEqual(wrong["state"], "cancel_not_delivered")
            self.assertIsNone(child.poll())
            result = support.request_console_cancel({"pid": child.pid, "created_ticks": ticks})
            self.assertEqual(result["state"], "ctrl_c_requested")
            self.assertEqual(child.wait(timeout=15), 23)
            self.assertIn("cancel_handled", child.stdout.read())
            self.assertIsNone(untouched.poll())
        finally:
            for fixture in (child, untouched):
                if fixture.poll() is None:
                    fixture.kill()  # Harmless fixture only; never a Gradle process.
                fixture.wait()
                fixture.stdout.close(); fixture.stderr.close()

    @unittest.skipUnless(os.name == "nt", "Windows support event and observer")
    def test_quiet_alert_requires_owner_reply_and_no_cancellation_from_age(self):
        with temporary_workspace() as folder:
            native = support.NativeWait()
            handle, ticks = native.process(os.getpid())
            native.k.CloseHandle(handle)
            ticket = {"id": "b" * 32, "pid": os.getpid(), "created_ticks": ticks}
            ready = threading.Event()
            def notification(*args):
                ready.set()
                return {"state": "accepted_unacknowledged"}
            with patch.object(support, "notify", side_effect=notification), \
                    patch.object(support, "diagnostics", return_value={"state": "captured"}), \
                    patch.object(support, "request_console_cancel") as cancel, \
                    patch("sys.stderr", new_callable=io.StringIO):
                monitor = support.BuildSupport(ticket, folder, Path(folder) / "build.log",
                                               quiet_seconds=0.01, root=folder)
                monitor.start(type("Child", (), {"pid": os.getpid()})())
                try:
                    self.assertTrue(ready.wait(5))  # Test assertion bound, not build control.
                    state = support.read(ticket["id"], folder)
                    self.assertEqual(state["request"]["response"], None)
                    cancel.assert_not_called()
                    support.respond(ticket["id"], state["request"]["id"], "continue", "expected work", folder)
                finally:
                    monitor.finish(0)
                cancel.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows diagnostic review event")
    def test_continue_rearms_review_without_faking_progress(self):
        with temporary_workspace() as folder:
            native = support.NativeWait()
            handle, ticks = native.process(os.getpid())
            native.k.CloseHandle(handle)
            ticket = {"id": "d" * 32, "pid": os.getpid(), "created_ticks": ticks}
            reviewed_again = threading.Event()
            requests = []
            def notification(owner, ticket, request, path):
                requests.append(request["id"])
                if len(requests) == 1:
                    support.respond(ticket["id"], request["id"], "continue", "reviewed expected work", folder)
                else:
                    reviewed_again.set()
                return {"state": "tool_session_emitted_unacknowledged"}
            with patch.object(support, "notify", side_effect=notification), \
                    patch.object(support, "diagnostics", return_value={"state": "captured"}), \
                    patch("sys.stderr", new_callable=io.StringIO):
                monitor = support.BuildSupport(ticket, folder, Path(folder) / "build.log",
                                               quiet_seconds=0.05, root=folder)
                monitor.start(type("Child", (), {"pid": os.getpid()})())
                try:
                    self.assertTrue(reviewed_again.wait(5))
                    self.assertEqual(monitor.revision, 0)
                    self.assertNotEqual(requests[0], requests[1])
                    self.assertIsNone(monitor.state["cancellation"])
                finally:
                    monitor.finish(0)

    def test_cancel_retains_gate_until_live_daemon_becomes_idle(self):
        from test_gate import ExecutionTicket
        from unittest.mock import MagicMock
        gate = importlib.import_module("agent_toolbelt_gradle_build_gate.gate")
        events = []
        mutex = MagicMock()
        mutex.abandoned = False
        mutex.__enter__.side_effect = lambda: events.append("acquire") or mutex
        mutex.__exit__.side_effect = lambda *a: events.append("release")
        observer = MagicMock()
        observer.__enter__.return_value.pids = {42}
        observer.__enter__.return_value.wait.side_effect = lambda: events.append("daemon_exit_wait")
        inspections = [{"safe_to_start": True, "processes": []},
                       {"safe_to_start": False, "processes": [{"pid": 42, "state": "active"}]},
                       {"safe_to_start": True, "processes": []}]
        with temporary_workspace() as root:
            project = Path(root)
            (project / "gradlew.bat").touch()
            with patch("agent_toolbelt_gradle_build_gate.queue.TicketQueue", return_value=ExecutionTicket(events)), \
                    patch.object(gate, "NamedMutex", return_value=mutex), \
                    patch.object(gate, "LifecycleObserver", return_value=observer), \
                    patch.object(gate, "inspect_activity", side_effect=inspections), \
                    patch("agent_toolbelt_gradle_build_gate.usage.record_project", return_value={"ok": True}), \
                    patch.object(gate, "execute_wrapper", side_effect=lambda *a: events.append("wrapper_exit") or {
                        "exit_code": 1, "owner_support": {"cancellation": {"state": "ctrl_c_requested"}}}):
                result = gate.run_build(project, ["test"], retire_daemons="none")
        self.assertEqual(events, ["ticket_turn", "acquire", "wrapper_exit", "daemon_exit_wait", "release", "ticket_release"])
        self.assertTrue(result["owner_support"]["completion_verified"])

    @unittest.skipUnless(os.name == "nt" and os.getenv("GRADLE_GATE_SUPPORT_SMOKE") == "1",
                         "Opt-in native Gradle cancellation through production FIFO")
    def test_native_hanging_test_owner_cancel_and_verified_gate_release(self):
        gate = importlib.import_module("agent_toolbelt_gradle_build_gate.gate")
        home = Path.home() / ".gradle"
        distributions = list((home / "wrapper/dists/gradle-9.8.0-bin").glob("*/gradle-9.8.0"))
        junit = list((home / "caches/modules-2/files-2.1/junit/junit/4.13.2").glob("*/*.jar"))
        hamcrest = list((home / "caches/modules-2/files-2.1/org.hamcrest/hamcrest-core/1.3").glob("*/*.jar"))
        self.assertTrue(distributions and junit and hamcrest)
        with temporary_workspace(prefix="gate-native-support-") as root:
            project = Path(root)
            (project / "gradlew.bat").write_text('@echo off\ncall "' + str(distributions[0] / 'bin/gradle.bat') + '" %*\n', encoding="ascii")
            (project / "settings.gradle").write_text("rootProject.name = 'owner-support-fixture'\n")
            jars = ", ".join(repr(p.as_posix()) for p in (junit[0], hamcrest[0]))
            (project / "build.gradle").write_text("plugins { id 'java' }\ndependencies { testImplementation files(" + jars + ") }\ntest { useJUnit(); maxHeapSize = '128m' }\n")
            source = project / "src/test/java/HangingTest.java"
            source.parent.mkdir(parents=True)
            source.write_text("import org.junit.Test; public class HangingTest { @Test public void waitsForOwner() throws Exception { Thread.sleep(Long.MAX_VALUE); } }\n")
            captured = []
            real_diagnostics = support.diagnostics
            def owner_reply(owner, ticket, request, path):
                state = json.loads(path.read_text())
                observed = state["progress"].get("test") or ""
                if "waitsForOwner" not in observed:
                    support.respond(ticket["id"], request["id"], "continue", "Fixture setup still making progress")
                return {"state": "fixture_owner_notified"}
            def diagnose_and_reply(wrapper, directory):
                evidence = real_diagnostics(wrapper, directory)
                state = support.read(directory.parent.name)
                request = state["request"]
                if ("waitsForOwner" in (state["progress"].get("test") or "")
                        and request["id"] == directory.name and request["response"] is None
                        and request["revision"] == state["revision"]):
                    captured.append(evidence)
                    support.respond(state["ticket"]["id"], state["request"]["id"], "cancel",
                                    "Intentional hanging-test fixture; diagnostics captured")
                return evidence
            with patch.object(support, "notify", side_effect=owner_reply), \
                    patch.object(support, "diagnostics", side_effect=diagnose_and_reply), \
                    patch("agent_toolbelt_gradle_build_gate.usage.record_project", return_value={"ok": True, "fixture": True}):
                result = gate.run_build(project, ["test", "--offline", "--no-daemon", "--no-configuration-cache", "--console=plain"],
                                        retire_daemons="none", diagnostic_quiet_seconds=2, log_path=project / "build.log")
            self.assertTrue(result["gate_acquired"])
            self.assertNotEqual(result["exit_code"], 0)
            self.assertEqual(result["owner_support"]["cancellation"]["state"], "ctrl_c_requested")
            self.assertTrue(result["owner_support"]["completion_verified"])
            self.assertTrue(captured)
            self.assertEqual(captured[-1]["state"], "captured", captured[-1])
            self.assertTrue(any(dump.get("exit_code") == 0 for dump in captured[-1]["thread_dumps"]), captured[-1])
            print(json.dumps({"native_owner_support": result["owner_support"],
                              "gate_acquired": result["gate_acquired"], "exit_code": result["exit_code"]}), flush=True)


if __name__ == "__main__":
    unittest.main()
