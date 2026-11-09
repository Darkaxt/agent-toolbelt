"""Different chat owners share one SQLite writer without losing an operation."""
import multiprocessing
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_toolbelt_codex_thread_recall.cache_write_lock import connect_cache_database


def hold_writer(path, acquired, release):
    with closing(connect_cache_database(path, timeout=0)) as conn:
        conn.execute("begin immediate")
        conn.execute("insert into observations values ('first')")
        acquired.set()
        release.wait()
        conn.commit()


def next_writer(path, queued, entered):
    queued.set()
    with closing(connect_cache_database(path, timeout=0)) as conn:
        entered.set()
        conn.execute("insert into observations values ('second')")
        conn.commit()


class CacheWriteLockTests(unittest.TestCase):
    def test_different_process_waits_for_original_writer_and_read_only_inspection_stays_available(self):
        with tempfile.TemporaryDirectory(prefix="recall-writer-") as scratch:
            path = str(Path(scratch) / "index.sqlite")
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("pragma journal_mode=wal")
                conn.execute("create table observations (value text)")
            context = multiprocessing.get_context("spawn")
            acquired, release, queued, entered = (context.Event() for _ in range(4))
            first = context.Process(target=hold_writer, args=(path, acquired, release))
            second = context.Process(target=next_writer, args=(path, queued, entered))
            first.start()
            started_second = False
            try:
                self.assertTrue(acquired.wait(10), "diagnostic watchdog: first writer did not start")
                second.start(); started_second = True
                self.assertTrue(queued.wait(10), "diagnostic watchdog: waiting process did not start")
                self.assertFalse(entered.wait(0.05), "a competing writer cannot enter SQLite before ownership transfers")
                with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)) as reader:
                    self.assertEqual(reader.execute("select * from observations").fetchall(), [])
            finally:
                release.set()
                first.join()
                if started_second:
                    second.join()
            self.assertEqual(first.exitcode, 0); self.assertEqual(second.exitcode, 0)
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute("select value from observations order by rowid").fetchall(), [("first",), ("second",)])

    def test_failed_write_rolls_back_before_releasing_the_next_writer(self):
        with tempfile.TemporaryDirectory(prefix="recall-writer-") as scratch:
            path=Path(scratch) / "index.sqlite"
            with self.assertRaises(ValueError):
                with closing(connect_cache_database(path)) as conn:
                    conn.execute("create table observations (value text)")
                    conn.execute("insert into observations values ('uncommitted')")
                    raise ValueError("fixture failure")
            with closing(connect_cache_database(path,timeout=0)) as conn:
                self.assertFalse(conn.in_transaction)
                self.assertEqual(conn.execute("select * from observations").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
