from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "families/codex-thread-recall/src"))
sys.path.insert(0, str(ROOT / "packages/core/src"))
from agent_toolbelt_codex_thread_recall import thread_recall as recall

ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class RecallRetirementTests(unittest.TestCase):
    def test_retired_cache_is_purged_with_facets_but_other_thread_survives(self):
        with tempfile.TemporaryDirectory(dir="D:/Temp") as root:
            home = Path(root)
            with closing(sqlite3.connect(home / "state_5.sqlite")) as state:
                state.execute("CREATE TABLE threads(id TEXT)")
                state.execute("INSERT INTO threads VALUES (?)", (OTHER,))
                state.commit()
            with closing(recall.connect_cache(home)) as conn:
                recall.ensure_cache_schema(conn)
                conn.execute("INSERT INTO rollout_paths(id,path) VALUES (1,'fixture')")
                for tid in (ID, OTHER):
                    conn.execute("INSERT INTO entries(thread_id,rollout_path_id,entry_index,rollout_line,byte_start,byte_end,is_noise,content_class) VALUES (?,1,0,1,0,10,0,'work')", (tid,))
                conn.execute("INSERT INTO entry_facts(entry_id,fact) VALUES (1,'retired fact')")
                conn.commit()
            result = recall.purge_retired_thread_cache(thread_id=ID, confirm_thread_id=ID, codex_home=home)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["deleted_entries"], 1)
            with closing(recall.connect_existing_cache(home)) as conn:
                self.assertEqual(conn.execute("SELECT thread_id FROM entries").fetchall()[0][0], OTHER)
                self.assertEqual(conn.execute("SELECT count(*) FROM entry_facts").fetchone()[0], 0)
            refused = recall.purge_retired_thread_cache(thread_id=OTHER, confirm_thread_id=OTHER, codex_home=home)
            self.assertFalse(refused["ok"])
