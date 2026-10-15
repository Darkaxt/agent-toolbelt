from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_toolbelt_context_transfer import database_evidence as db


class DatabaseEvidenceTests(unittest.TestCase):
    def test_inherited_chain_requires_independent_destination(self):
        from agent_toolbelt_context_transfer import context_transfer
        from test_archive import ArchiveFixture

        with tempfile.TemporaryDirectory(dir="D:/Temp") as value:
            root = Path(value)
            fixture = ArchiveFixture(root)
            for tid, parent in (("ancestor", None), ("source", "ancestor"),
                                ("fork", "source"), ("sibling", "ancestor"),
                                ("independent", None)):
                fixture.add_thread(tid, (json.dumps({"type": "session_meta", "payload": {
                    "id": tid, "forked_from_id": parent,
                    "forked_from_ordinal_exclusive": 12}}) + "\n").encode(), tid)
            ancestors = db.history_ancestors(fixture.codex_home, "fork")
            self.assertEqual([item["thread_id"] for item in ancestors], ["source", "ancestor"])
            for destination in ("fork", "sibling", "ancestor"):
                result = context_transfer.inventory_thread_tree(
                    source_thread_id="source", destination_thread_id=destination,
                    codex_home=fixture.codex_home, archive_root=root / "archives")
                self.assertIn("destination_is_history_dependent", result["blockers"])
            result = context_transfer.inventory_thread_tree(
                source_thread_id="source", destination_thread_id="independent",
                codex_home=fixture.codex_home, archive_root=root / "archives")
            self.assertNotIn("destination_is_history_dependent", result["blockers"])
            self.assertIn("surviving_fork_history_references", result["blockers"])

    def test_scoped_preservation_including_database_only_evidence(self):
        with tempfile.TemporaryDirectory(dir="D:/Temp") as value:
            root = Path(value)
            with closing(sqlite3.connect(root / "thread_history_1.sqlite")) as c:
                c.execute("CREATE TABLE thread_items(thread_id TEXT,item_json TEXT)")
                c.executemany("INSERT INTO thread_items VALUES (?,?)", [("selected", '{"text":"database only"}'), ("unrelated", "private unrelated")])
                c.commit()
            before = (root / "thread_history_1.sqlite").read_bytes()
            inventory = db.database_inventory(root, ["selected"])
            self.assertEqual(inventory[0]["tables"][0]["rows"], 1)
            receipt = db.export_database_evidence(root, ["selected"], root / "evidence.jsonl")
            rows = [json.loads(line) for line in (root / "evidence.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["row"]["item_json"], '{"text":"database only"}')
            self.assertNotIn("unrelated", (root / "evidence.jsonl").read_text())
            self.assertEqual((root / "thread_history_1.sqlite").read_bytes(), before)
            self.assertFalse(receipt["live_databases_mutated"])

    def test_unknown_non_thread_tables_are_not_exported(self):
        with tempfile.TemporaryDirectory(dir="D:/Temp") as value:
            root = Path(value)
            with closing(sqlite3.connect(root / "state_5.sqlite")) as c:
                c.execute("CREATE TABLE account(secret TEXT)")
                c.execute("INSERT INTO account VALUES ('do not copy')")
                c.commit()
            receipt = db.export_database_evidence(root, ["selected"], root / "evidence.jsonl")
            self.assertEqual(receipt["tables"], [])
            self.assertEqual(receipt["size"], 0)
