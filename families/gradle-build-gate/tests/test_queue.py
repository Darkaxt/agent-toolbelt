import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


@unittest.skipUnless(os.name == "nt", "Native Windows execution tickets")
class TicketContracts(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("agent_toolbelt_gradle_build_gate.queue")
        self.temp = tempfile.TemporaryDirectory(prefix="gradle-ticket-test-", dir="D:/Temp" if Path("D:/Temp").is_dir() else None)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.namespace = "Local\\Darka.GradleTicketTest." + uuid.uuid4().hex
        self.children = []
        self.addCleanup(self.close_children)

    def close_children(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()  # Owned queue-test Python process only.
            child.wait()
            for stream in (child.stdin, child.stdout):
                stream.close()

    def child(self, stay_alive=False):
        code = ('from pathlib import Path; from agent_toolbelt_gradle_build_gate.queue import TicketQueue; import json,sys; '
                'q=TicketQueue(Path(' + repr(str(self.root)) + '), ' + repr(self.namespace) + '); '
                'q.register(); print(json.dumps(q.ticket),flush=True); q.wait_turn(); '
                'print("acquired",flush=True); sys.stdin.readline(); q.release(); print("released",flush=True)' +
                ('; sys.stdin.readline()' if stay_alive else ''))
        child = subprocess.Popen([sys.executable, "-B", "-u", "-c", code],
                                 env={**os.environ, "PYTHONPATH": str(SRC)}, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self.children.append(child)
        return child, json.loads(child.stdout.readline())

    def test_native_fifo_and_completion_wakeup(self):
        with self.module.TicketQueue(self.root, self.namespace) as first:
            child2, ticket2 = self.child()
            child3, ticket3 = self.child()
            self.assertLess(first.ticket["number"], ticket2["number"])
            self.assertLess(ticket2["number"], ticket3["number"])
            self.assertIsNone(child2.poll()); self.assertIsNone(child3.poll())
        self.assertEqual(child2.stdout.readline().strip(), "acquired")
        self.assertIsNone(child3.poll())
        child2.stdin.write("finish\n"); child2.stdin.flush()
        self.assertEqual(child2.stdout.readline().strip(), "released")
        self.assertEqual(child3.stdout.readline().strip(), "acquired")
        child3.stdin.write("finish\n"); child3.stdin.flush()
        self.assertEqual(child3.stdout.readline().strip(), "released")
        self.assertEqual(child2.wait(), 0); self.assertEqual(child3.wait(), 0)
        self.assertEqual(self.module.queue_status(self.root)["pending"], 0)

    def test_dead_head_reclaimed_without_age_or_timeout(self):
        head, first = self.child()
        self.assertEqual(head.stdout.readline().strip(), "acquired")
        next_child, second = self.child()
        head.terminate(); head.wait()
        self.assertEqual(next_child.stdout.readline().strip(), "acquired")
        next_child.stdin.write("finish\n"); next_child.stdin.flush()
        self.assertEqual(next_child.stdout.readline().strip(), "released")
        self.assertEqual(next_child.wait(), 0)
        self.assertGreater(second["number"], first["number"])

    def test_corrupt_queue_is_not_reset(self):
        self.root.mkdir(exist_ok=True)
        (self.root / "queue.json").write_text('{"schema":1,"next_number":0,"tickets":[]}')
        with self.assertRaises(ValueError):
            with self.module.TicketQueue(self.root, self.namespace):
                self.fail("Invalid queue must not grant a turn")

    def test_released_owner_stays_alive_then_new_head_dies(self):
        head, _ = self.child(stay_alive=True)
        self.assertEqual(head.stdout.readline().strip(), "acquired")
        second, _ = self.child()
        third, _ = self.child()
        head.stdin.write("release\n"); head.stdin.flush()
        self.assertEqual(head.stdout.readline().strip(), "released")
        self.assertEqual(second.stdout.readline().strip(), "acquired")
        self.assertIsNone(head.poll())
        second.terminate(); second.wait()
        self.assertEqual(third.stdout.readline().strip(), "acquired")
        third.stdin.write("finish\n"); third.stdin.flush()
        self.assertEqual(third.stdout.readline().strip(), "released")
        self.assertEqual(third.wait(), 0)
        head.stdin.write("exit\n"); head.stdin.flush()
        self.assertEqual(head.wait(), 0)

    def test_pid_identity_mismatch_is_reclaimed_but_unknown_identity_is_not(self):
        q = self.module.TicketQueue(self.root, self.namespace)
        handle, ticks = q.native.process(os.getpid())
        q.native.k.CloseHandle(handle)
        stale = {"id": uuid.uuid4().hex, "number": 1, "pid": os.getpid(), "created_ticks": ticks + 1}
        q.save({"schema": 1, "next_number": 2, "tickets": [stale]})
        with q:
            self.assertEqual(q.ticket["number"], 2)
            self.assertEqual(self.module.queue_status(self.root)["pending"], 1)
        q.save({"schema": 1, "next_number": 2, "tickets": [stale]})
        original = q.native.process
        def deny_stale(pid, created_ticks=None):
            if created_ticks is not None:
                raise PermissionError("identity unavailable")
            return original(pid, created_ticks)
        with patch.object(q.native, "process", side_effect=deny_stale), self.assertRaises(PermissionError):
            q.register()
        self.assertEqual(self.module.queue_status(self.root)["tickets"], [stale])
        self.assertIsNone(q.event)

    def test_cancel_wait_removes_only_own_ticket_and_status_does_not_mutate(self):
        head, first = self.child()
        self.assertEqual(head.stdout.readline().strip(), "acquired")
        q = self.module.TicketQueue(self.root, self.namespace)
        with patch.object(q, "wait_turn", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            with q:
                self.fail("Canceled wait must not enter")
        before = (self.root / "queue.json").read_bytes()
        self.assertEqual(self.module.queue_status(self.root)["tickets"], [first])
        self.assertEqual(before, (self.root / "queue.json").read_bytes())
        head.stdin.write("finish\n"); head.stdin.flush()
        self.assertEqual(head.stdout.readline().strip(), "released")
        self.assertEqual(head.wait(), 0)


if __name__ == "__main__":
    unittest.main()
