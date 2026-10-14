import contextlib
import io
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))
from agent_toolbelt_windows_elevation_gate import engine
from agent_toolbelt_windows_elevation_gate.native import Mutex
from agent_toolbelt_windows_elevation_gate.queue import Queue, atomic_json


def queue_child(root, namespace, connection, release, phase="explaining", abandon=False):
    try:
        queue = Queue(root, namespace)
        ticket = queue.register({"task": "Queue test", "thread_name": "Fixture"})
        connection.send(("registered", ticket))
        queue.wait_turn()
        with Mutex(namespace + ".Prompt", queue.n):
            queue.phase(phase)
            connection.send(("entered", ticket["number"]))
            if abandon:
                return
            release.wait()
            queue.release("fixture_complete")
    except Exception as exc:
        connection.send(("error", str(exc)))
    finally:
        connection.close()


@unittest.skipUnless(os.name == "nt", "Windows native event/process tests")
class ElevationFlowTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get("ELEVATION_TEST_TEMP", "D:/Temp"))
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="elevation-gate-test-", dir=scratch)
        self.root = Path(self.temp.name)
        self.namespace = "Local\\Darka.ElevationTest." + self.root.name
        self.queue = Queue(self.root / "state", self.namespace)
        self.request = engine.prepare([sys.executable, "-c", "print('read-only fixture')"],
                                      cwd=str(self.root), task="Read identity", thread_name="Fixture task",
                                      reason="Verify elevation transport", changes="No system changes",
                                      targets=["Current process identity"])

    def tearDown(self):
        self.temp.cleanup()

    def run_flow(self, dialog, launcher):
        with contextlib.redirect_stderr(io.StringIO()):
            return engine.run(self.request, queue=self.queue, dialog=dialog, launcher=launcher)

    def test_cancel_returns_feedback_without_launching_and_releases_queue(self):
        def forbidden(*args):
            self.fail("Cancel must not launch anything")
        result = self.run_flow(lambda request: {"accepted": False, "feedback": "Wrong target; do not proceed"}, forbidden)
        self.assertEqual(result["failure_kind"], "user_declined")
        self.assertEqual(result["feedback"], "Wrong target; do not proceed")
        self.assertEqual(self.queue.status()["pending"], 0)
        self.assertEqual(list((self.queue.root / "requests").iterdir()), [])

    def test_accept_keeps_command_unchanged_and_releases_before_job_wait(self):
        original = list(self.request["command"])
        testcase = self

        class Child:
            def wait(self):
                testcase.assertEqual(testcase.queue.status()["pending"], 0)
                return 0

        def launch(path, digest, host):
            request = json.loads(path.read_text())
            self.assertEqual(request["command"], original)
            atomic_json(path.with_suffix(".result.json"), {
                "ok": True, "request_sha256": digest, "command_exit_code": 0, "elevated": True,
                "request_id": request["request_id"],
            })
            return Child()

        result = self.run_flow(lambda request: {"accepted": True, "feedback": "Do not change the target"}, launch)
        self.assertTrue(result["ok"])
        self.assertEqual(result["feedback"], "Do not change the target")
        self.assertTrue(result["prompt_gate_released"])

    def test_uac_decline_is_distinct_and_never_retried(self):
        calls = []
        def launch(*args):
            calls.append(args)
            raise engine.ElevationDenied("fixture denial")
        result = self.run_flow(lambda request: {"accepted": True, "feedback": ""}, launch)
        self.assertEqual(result["failure_kind"], "uac_declined")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.queue.status()["pending"], 0)

    def test_definite_native_launch_failure_releases_prompt_without_retry(self):
        def launch(*args):
            raise engine.ElevationLaunchFailed("Native launch failed before a worker started")
        result = self.run_flow(lambda request: {"accepted": True, "feedback": ""}, launch)
        self.assertEqual(result["failure_kind"], "elevation_launch_failed")
        self.assertFalse(result["launched"])
        self.assertEqual(self.queue.status()["pending"], 0)

    def test_preview_rating_cannot_become_execution_consent(self):
        from agent_toolbelt_windows_elevation_gate.dialog import ExplanationDialog
        for preview in (True, False):
            dialog = ExplanationDialog.__new__(ExplanationDialog)
            dialog.preview, dialog.answer = preview, {}
            dialog.feedback = SimpleNamespace(get=lambda *args: "Readable now")
            dialog.root = SimpleNamespace(destroy=lambda: None)
            dialog.finish(True)
            self.assertEqual(dialog.answer["accepted"], not preview)
            if preview:
                self.assertTrue(dialog.answer["preview_approved"])
            self.assertEqual(dialog.answer["feedback"], "Readable now")

    def test_changed_script_after_dialog_cannot_execute(self):
        script = self.root / "payload.py"
        script.write_text("print('original')")
        self.request = engine.prepare([sys.executable, str(script)], cwd=str(self.root),
            task="Read fixture", thread_name="Fixture", reason="Test binding", changes="None", targets=[str(script)])
        def dialog(request):
            script.write_text("print('changed')")
            return {"accepted": True, "feedback": ""}
        result = self.run_flow(dialog, lambda *args: self.fail("Changed input launched"))
        self.assertIn("input_changed", result["error"])
        self.assertEqual(self.queue.status()["pending"], 0)

    def test_changed_request_bytes_after_dialog_fail_closed(self):
        def dialog(request):
            path = self.queue.root / "requests" / (request["request_id"] + ".json")
            path.write_text("{}")
            return {"accepted": True, "feedback": ""}
        result = self.run_flow(dialog, lambda *args: self.fail("Changed request launched"))
        self.assertIn("input_changed", result["error"])

    def test_native_two_process_fifo_holds_one_prompt_slot(self):
        context = mp.get_context("spawn")
        release_a, release_b = context.Event(), context.Event()
        parent_a, child_a = context.Pipe()
        parent_b, child_b = context.Pipe()
        a = context.Process(target=queue_child, args=(self.queue.root, self.namespace, child_a, release_a))
        b = context.Process(target=queue_child, args=(self.queue.root, self.namespace, child_b, release_b))
        a.start(); child_a.close()
        first = parent_a.recv()
        self.assertEqual(first[0], "registered")
        self.assertEqual(parent_a.recv(), ("entered", 1))
        b.start(); child_b.close()
        second = parent_b.recv()
        self.assertEqual(second[0], "registered")
        self.assertEqual(second[1]["number"], 2)
        status = self.queue.status()
        self.assertEqual([t["phase"] for t in status["tickets"]], ["explaining", "queued"])
        self.assertFalse(parent_b.poll())
        release_a.set()
        self.assertEqual(parent_b.recv(), ("entered", 2))
        release_b.set()
        a.join(); b.join()
        self.assertEqual((a.exitcode, b.exitcode), (0, 0))
        self.assertEqual(self.queue.status()["pending"], 0)
        parent_a.close(); parent_b.close()

    def test_dead_uac_owner_requires_explicit_recovery(self):
        context = mp.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(target=queue_child,
            args=(self.queue.root, self.namespace, child, context.Event(), "uac", True))
        process.start(); child.close()
        ticket = parent.recv()[1]
        self.assertEqual(parent.recv()[0], "entered")
        process.join(); parent.close()
        status = self.queue.status()
        self.assertTrue(status["tickets"][0]["recovery_required"])
        with self.assertRaises(ValueError):
            self.queue.recover(ticket["id"], False)
        self.assertTrue(self.queue.recover(ticket["id"], True)["ok"])
        self.assertEqual(self.queue.status()["pending"], 0)

        path = self.queue.root / "requests" / (ticket["id"] + ".json")
        atomic_json(path, {**self.request, "request_id": ticket["id"],
                           "owner": {"pid": ticket["pid"], "ticks": ticket["ticks"]}})
        atomic_json(path.with_suffix(".worker.json"), {"pid": ticket["pid"], "ticks": ticket["ticks"]})
        atomic_json(path.with_suffix(".result.json"), {"request_sha256": engine.sha256(path), "ok": False})
        self.assertTrue(engine.finalize(ticket["id"], self.queue)["ok"])
        self.assertFalse(path.exists())

    def test_visual_preview_never_queues_or_elevates(self):
        from agent_toolbelt_windows_elevation_gate import cli
        args = ["preview", "--show-dialog", "--owner-task", "UI inspection", "--thread-name", "Fixture",
                "--reason", "Readability check", "--changes", "None", "--target", "Visual preview",
                "--cwd", str(self.root), "--", sys.executable, "-c", "print('not executed')"]
        with patch.object(engine, "run", side_effect=AssertionError("Preview attempted execution")):
            with patch.object(cli.broker, "preview", return_value={"preview_approved": False, "feedback": "Clearer", "launched": False}) as dialog:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(cli.main(args), 0)
        result = json.loads(output.getvalue())
        self.assertFalse(result["launched"])
        self.assertEqual(result["dialog"]["feedback"], "Clearer")
        self.assertEqual(dialog.call_args.args[0]["thread_name"], "Fixture")
        self.assertEqual(self.queue.status()["pending"], 0)

    def test_active_owner_cannot_be_recovered(self):
        ticket = self.queue.register(self.request)
        self.queue.phase("uac")
        try:
            with self.assertRaises(ValueError):
                self.queue.recover(ticket["id"], True)
        finally:
            self.queue.release("fixture_cancelled")

    def test_direct_process_execution_is_bounded_and_reports_exit(self):
        result = engine.execute([sys.executable, "-c", "print('x'*100000); raise SystemExit(7)"], str(self.root))
        self.assertFalse(result["ok"])
        self.assertEqual(result["command_exit_code"], 7)
        self.assertTrue(result["stdout_truncated"])
        self.assertLessEqual(len(result["stdout"]), engine.OUTPUT_LIMIT)

    def test_shell_alias_and_relative_executable_are_rejected(self):
        with self.assertRaises(ValueError):
            engine.prepare(["powershell", "-Command", "whoami"], cwd=str(self.root), task="Test",
                thread_name="Fixture", reason="Test", changes="None", targets=["identity"])


if __name__ == "__main__":
    unittest.main()
