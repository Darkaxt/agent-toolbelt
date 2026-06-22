import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from outlook_classic_mail_client import queueing


class OutlookQueueTests(unittest.TestCase):
    def test_fifo_queue_serializes_three_waiters(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "outlook_queue.sqlite"
            events: list[tuple[str, str]] = []
            errors: list[BaseException] = []

            def worker(name: str) -> None:
                try:
                    with queueing.acquire_queue_turn(
                        "search",
                        path=queue_path,
                        timeout_sec=2,
                        poll_interval_sec=0.01,
                        lease_sec=60,
                    ) as meta:
                        events.append(("enter", name))
                        if name == "one":
                            self.assertEqual(meta["position_at_enqueue"], 1)
                        time.sleep(0.03)
                        events.append(("exit", name))
                except BaseException as exc:  # pragma: no cover - test captures failures
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(name,)) for name in ("one", "two", "three")]
            for thread in threads:
                thread.start()
                time.sleep(0.05)
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            self.assertEqual(
                [name for kind, name in events if kind == "enter"],
                ["one", "two", "three"],
            )

    def test_queue_timeout_when_turn_never_arrives(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "outlook_queue.sqlite"
            holder_entered = threading.Event()

            def holder() -> None:
                with queueing.acquire_queue_turn(
                    "search",
                    path=queue_path,
                    timeout_sec=2,
                    poll_interval_sec=0.01,
                    lease_sec=60,
                ):
                    holder_entered.set()
                    time.sleep(0.2)

            thread = threading.Thread(target=holder)
            thread.start()
            self.assertTrue(holder_entered.wait(1))
            try:
                with self.assertRaises(queueing.QueueTimeoutError):
                    with queueing.acquire_queue_turn(
                        "search",
                        path=queue_path,
                        timeout_sec=0.05,
                        poll_interval_sec=0.01,
                        lease_sec=60,
                    ):
                        self.fail("Queue turn should not be acquired before timeout.")
            finally:
                thread.join()

    def test_prunes_stale_running_ticket_before_claim(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "outlook_queue.sqlite"
            store = queueing.QueueStore(queue_path)
            store.ensure_schema()
            with store.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO queue_tickets(pid, operation, status, created_at, updated_at, lease_expires_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (999, "search", "running", 0.0, 0.0, 1.0),
                )

            with queueing.acquire_queue_turn(
                "search",
                path=queue_path,
                timeout_sec=0.2,
                poll_interval_sec=0.01,
                lease_sec=60,
                monotonic_func=lambda: 10.0,
                wall_time_func=lambda: 10.0,
            ) as meta:
                self.assertEqual(meta["position_at_enqueue"], 1)

    def test_retry_transient_state_operation_uses_backoff(self):
        attempts = {"count": 0}
        sleeps: list[float] = []

        def flaky() -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        result = queueing.run_with_state_retries(flaky, sleep_func=sleeps.append)

        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 3)
        self.assertEqual(sleeps, [0.1, 0.3])


if __name__ == "__main__":
    unittest.main()
