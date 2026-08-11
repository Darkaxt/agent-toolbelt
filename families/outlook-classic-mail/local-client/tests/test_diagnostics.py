import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from outlook_classic_mail_client import cli, client


@contextlib.contextmanager
def fake_queue():
    yield {
        "used": True,
        "waited_seconds": 0.0,
        "position_at_enqueue": 1,
        "depth_at_enqueue": 1,
        "timeout_seconds": 900,
    }


@contextlib.contextmanager
def fake_lock():
    yield


def install_fake_com(*, dispatch_error=None, session_error=None):
    pythoncom = types.ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: None

    class FakeApplication:
        @property
        def Session(self):
            if session_error:
                raise session_error
            return object()

    win32com = types.ModuleType("win32com")
    win32com_client = types.ModuleType("win32com.client")

    def dispatch(name):
        if dispatch_error:
            raise dispatch_error
        return FakeApplication()

    win32com_client.Dispatch = dispatch
    win32com.client = win32com_client
    sys.modules["pythoncom"] = pythoncom
    sys.modules["win32com"] = win32com
    sys.modules["win32com.client"] = win32com_client


def remove_fake_com():
    for name in ("pythoncom", "win32com", "win32com.client"):
        sys.modules.pop(name, None)


class OutlookDiagnosticsTests(unittest.TestCase):
    def run_cli(self, argv):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cli.main(argv)
        return exit_code, json.loads(stdout.getvalue())

    def patch_runtime(self, *, log_path):
        originals = {
            "queue": client.outlook_operation_queue,
            "lock": client.outlook_com_lock,
            "log_path": client.DEFAULT_DIAGNOSTICS_LOG_PATH,
            "connect": client.connect_outlook,
            "runtime_state": client.outlook_runtime_state,
        }
        client.outlook_operation_queue = lambda *args, **kwargs: fake_queue()
        client.outlook_com_lock = lambda *args, **kwargs: fake_lock()
        client.DEFAULT_DIAGNOSTICS_LOG_PATH = log_path
        client.outlook_runtime_state = lambda: {
            "process_running": True,
            "visible_window": True,
        }
        return originals

    def restore_runtime(self, originals):
        client.outlook_operation_queue = originals["queue"]
        client.outlook_com_lock = originals["lock"]
        client.DEFAULT_DIAGNOSTICS_LOG_PATH = originals["log_path"]
        client.connect_outlook = originals["connect"]
        client.outlook_runtime_state = originals["runtime_state"]
        remove_fake_com()

    def test_dispatch_failure_returns_and_logs_structured_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            originals = self.patch_runtime(log_path=log_path)
            install_fake_com(dispatch_error=RuntimeError("Outlook profile unavailable for msg-SECRET query=alpha"))
            try:
                exit_code, payload = self.run_cli(["accounts"])
            finally:
                self.restore_runtime(originals)

            self.assertEqual(exit_code, 74)
            self.assertFalse(payload["ok"])
            diagnostics = payload["client_diagnostics"]
            self.assertEqual(diagnostics["failure_kind"], "outlook_dispatch_failed")
            self.assertEqual(diagnostics["com_stages"]["dispatch_outlook_application"], "failed")
            self.assertEqual(diagnostics["exception"]["type"], "RuntimeError")
            self.assertIn("Outlook profile unavailable", diagnostics["exception"]["message"])

            events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 1)
            event_text = json.dumps(events[0])
            self.assertIn("outlook_dispatch_failed", event_text)
            self.assertNotIn("msg-SECRET", event_text)
            self.assertNotIn("query=alpha", event_text)

    def test_session_failure_is_classified_after_dispatch_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            originals = self.patch_runtime(log_path=log_path)
            install_fake_com(session_error=RuntimeError("Session unavailable"))
            try:
                exit_code, payload = self.run_cli(["accounts"])
            finally:
                self.restore_runtime(originals)

            self.assertEqual(exit_code, 74)
            self.assertEqual(payload["client_diagnostics"]["failure_kind"], "outlook_session_unavailable")
            self.assertEqual(payload["client_diagnostics"]["com_stages"]["session_access"], "failed")

    def test_diagnostics_probe_does_not_dispatch_mail_operation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            originals = self.patch_runtime(log_path=log_path)
            original_dispatch = client.dispatch_operation
            client.dispatch_operation = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mail dispatch should not run"))
            install_fake_com()
            try:
                exit_code, payload = self.run_cli(["diagnostics-probe"])
            finally:
                client.dispatch_operation = original_dispatch
                self.restore_runtime(originals)

            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["operation"], "diagnostics-probe")
            self.assertTrue(payload["result"]["com_available"])
            self.assertEqual(payload["client_diagnostics"]["failure_kind"], None)
            self.assertTrue(log_path.exists())

    def test_diagnostics_log_reads_recent_events_without_queue_or_com(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "events.jsonl"
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps({"invocation_id": "old", "created_at": "2026-04-26T00:00:00Z"}),
                        json.dumps({"invocation_id": "new", "created_at": "2026-04-26T01:00:00Z"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            originals = self.patch_runtime(log_path=log_path)
            client.outlook_operation_queue = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("queue should not run"))
            client.connect_outlook = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("COM should not run"))
            try:
                exit_code, payload = self.run_cli(["diagnostics-log", "--limit", "1"])
            finally:
                self.restore_runtime(originals)

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["operation"], "diagnostics-log")
            self.assertEqual(payload["result"]["events"][0]["invocation_id"], "new")

    def test_draft_create_missing_body_fails_before_com_queue(self):
        def fail_queue(*args, **kwargs):
            raise AssertionError("queue should not be used for malformed draft creation")

        original_queue = client.outlook_operation_queue
        client.outlook_operation_queue = fail_queue
        try:
            exit_code, payload = self.run_cli(
                [
                    "draft-reply",
                    "--account",
                    "demo@example.com",
                    "--message-id",
                    "msg-1",
                    "--instruction",
                    "Use this as guidance, not body.",
                    "--create-draft",
                    "--confirm",
                ]
            )
        finally:
            client.outlook_operation_queue = original_queue

        self.assertEqual(exit_code, 2)
        self.assertFalse(payload["ok"])
        self.assertIn("--body with the final draft text", payload["stderr"])
        self.assertIsNone(payload["queue"])

    def test_invocation_diagnostics_include_session_and_desktop_fields(self):
        diagnostics = client.build_client_diagnostics(operation="accounts")

        self.assertEqual(diagnostics["operation"], "accounts")
        self.assertIn("invocation_id", diagnostics)
        self.assertIn("process_session_id", diagnostics)
        self.assertIn("active_console_session_id", diagnostics)
        self.assertIn("input_desktop_accessible", diagnostics)
        self.assertIn("outlook_process_running", diagnostics)

    def test_interactive_command_launches_desktop_outlook_before_com_dispatch(self):
        events = []
        diagnostics = client.build_client_diagnostics(operation="accounts")

        original_state = client.outlook_runtime_state
        original_allowed = client.interactive_outlook_launch_allowed
        original_launch = client.launch_outlook_desktop
        try:
            client.outlook_runtime_state = lambda: {
                "process_running": False,
                "visible_window": False,
            }
            client.interactive_outlook_launch_allowed = lambda: True
            client.launch_outlook_desktop = lambda: events.append("launch") or {
                "executable": r"C:\Program Files\Microsoft Office\Root\Office16\OUTLOOK.EXE",
                "pid": 4321,
            }

            install_fake_com()
            original_dispatch = sys.modules["win32com.client"].Dispatch
            sys.modules["win32com.client"].Dispatch = lambda name: events.append("dispatch") or original_dispatch(name)
            application, session = client.connect_outlook(diagnostics=diagnostics)
        finally:
            client.outlook_runtime_state = original_state
            client.interactive_outlook_launch_allowed = original_allowed
            client.launch_outlook_desktop = original_launch
            remove_fake_com()

        self.assertIsNotNone(application)
        self.assertIsNotNone(session)
        self.assertEqual(events, ["launch", "dispatch"])
        self.assertEqual(diagnostics["outlook_startup"]["action"], "desktop_launch_requested")
        self.assertEqual(diagnostics["outlook_startup"]["launch_pid"], 4321)

    def test_interactive_command_promotes_existing_hidden_outlook_without_killing_it(self):
        diagnostics = client.build_client_diagnostics(operation="search")
        launch_calls = []

        original_state = client.outlook_runtime_state
        original_allowed = client.interactive_outlook_launch_allowed
        original_launch = client.launch_outlook_desktop
        try:
            client.outlook_runtime_state = lambda: {
                "process_running": True,
                "visible_window": False,
            }
            client.interactive_outlook_launch_allowed = lambda: True
            client.launch_outlook_desktop = lambda: launch_calls.append("promote") or {
                "executable": r"C:\Program Files\Microsoft Office\Root\Office16\OUTLOOK.EXE",
                "pid": 9876,
            }
            install_fake_com()
            client.connect_outlook(diagnostics=diagnostics)
        finally:
            client.outlook_runtime_state = original_state
            client.interactive_outlook_launch_allowed = original_allowed
            client.launch_outlook_desktop = original_launch
            remove_fake_com()

        self.assertEqual(launch_calls, ["promote"])
        self.assertTrue(diagnostics["outlook_startup"]["process_running_before"])
        self.assertFalse(diagnostics["outlook_startup"]["visible_window_before"])
        self.assertEqual(diagnostics["outlook_startup"]["action"], "desktop_promotion_requested")

    def test_diagnostics_probe_does_not_launch_outlook_when_process_is_absent(self):
        diagnostics = client.build_client_diagnostics(operation="diagnostics-probe")
        launch_calls = []

        original_state = client.outlook_runtime_state
        original_allowed = client.interactive_outlook_launch_allowed
        original_launch = client.launch_outlook_desktop
        try:
            client.outlook_runtime_state = lambda: {
                "process_running": False,
                "visible_window": False,
            }
            client.interactive_outlook_launch_allowed = lambda: True
            client.launch_outlook_desktop = lambda: launch_calls.append("launch")
            with self.assertRaises(client.OutlookComUnavailableError) as raised:
                client.connect_outlook(diagnostics=diagnostics)
        finally:
            client.outlook_runtime_state = original_state
            client.interactive_outlook_launch_allowed = original_allowed
            client.launch_outlook_desktop = original_launch

        self.assertEqual(launch_calls, [])
        self.assertEqual(raised.exception.failure_kind, "outlook_not_running")
        self.assertEqual(diagnostics["outlook_startup"]["action"], "probe_no_launch")

    def test_background_command_does_not_launch_outlook_when_process_is_absent(self):
        diagnostics = client.build_client_diagnostics(operation="accounts")
        launch_calls = []

        original_state = client.outlook_runtime_state
        original_allowed = client.interactive_outlook_launch_allowed
        original_launch = client.launch_outlook_desktop
        try:
            client.outlook_runtime_state = lambda: {
                "process_running": False,
                "visible_window": False,
            }
            client.interactive_outlook_launch_allowed = lambda: False
            client.launch_outlook_desktop = lambda: launch_calls.append("launch")
            with self.assertRaises(client.OutlookComUnavailableError) as raised:
                client.connect_outlook(diagnostics=diagnostics)
        finally:
            client.outlook_runtime_state = original_state
            client.interactive_outlook_launch_allowed = original_allowed
            client.launch_outlook_desktop = original_launch

        self.assertEqual(launch_calls, [])
        self.assertEqual(raised.exception.failure_kind, "outlook_interactive_session_required")
        self.assertEqual(diagnostics["outlook_startup"]["action"], "background_no_launch")

    def test_desktop_launch_does_not_inherit_wrapper_stdio(self):
        executable = Path(r"C:\Program Files\Microsoft Office\Root\Office16\OUTLOOK.EXE")
        fake_process = mock.Mock(pid=2468)

        with mock.patch.object(client, "resolve_outlook_executable", return_value=executable):
            with mock.patch.object(client.subprocess, "Popen", return_value=fake_process) as popen:
                result = client.launch_outlook_desktop()

        self.assertEqual(result["pid"], 2468)
        popen.assert_called_once_with(
            [str(executable)],
            cwd=str(executable.parent),
            close_fds=True,
            stdin=client.subprocess.DEVNULL,
            stdout=client.subprocess.DEVNULL,
            stderr=client.subprocess.DEVNULL,
        )


if __name__ == "__main__":
    unittest.main()
