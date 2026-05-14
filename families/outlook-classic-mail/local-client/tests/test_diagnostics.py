import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


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
        }
        client.outlook_operation_queue = lambda *args, **kwargs: fake_queue()
        client.outlook_com_lock = lambda *args, **kwargs: fake_lock()
        client.DEFAULT_DIAGNOSTICS_LOG_PATH = log_path
        return originals

    def restore_runtime(self, originals):
        client.outlook_operation_queue = originals["queue"]
        client.outlook_com_lock = originals["lock"]
        client.DEFAULT_DIAGNOSTICS_LOG_PATH = originals["log_path"]
        client.connect_outlook = originals["connect"]
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


if __name__ == "__main__":
    unittest.main()
