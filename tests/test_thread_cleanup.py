import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "families/thread-cleanup/codex/skills/thread-cleanup/scripts/invoke_thread_cleanup.py"
SPEC = importlib.util.spec_from_file_location("thread_cleanup", HELPER)
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)
ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
EXE = Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"


class CleanupTests(unittest.TestCase):
    def test_short_and_noncanonical_ids_rejected(self):
        for value in ("aaaaaaaa", "../history", ID.upper()):
            with self.assertRaises((cleanup.CleanupError, ValueError)):
                cleanup.exact_id(value)

    def test_protected_and_current_thread_cannot_be_planned(self):
        with patch.dict(os.environ, {"CODEX_THREAD_ID": ID}):
            with self.assertRaises(cleanup.CleanupError):
                cleanup.plan("codex", "does-not-exist", ID)
        with self.assertRaises(cleanup.CleanupError):
            cleanup.plan("claude", "does-not-exist", ID, [ID])

    def test_claude_plan_is_exact_and_does_not_copy_other_sessions(self):
        with tempfile.TemporaryDirectory(dir="D:/Temp") as value:
            home = Path(value)
            project = home / "projects/example"
            project.mkdir(parents=True)
            (project / f"{ID}.jsonl").write_text('{"sessionId":"' + ID + '"}\n')
            (project / f"{OTHER}.jsonl").write_text("preserve")
            children = project / ID / "subagents"
            children.mkdir(parents=True)
            (children / "agent-1.jsonl").write_text("owned child history")
            packet = cleanup.plan("claude", home, ID, [OTHER])
            self.assertEqual(len(packet["snapshot"]["files"]), 2)
            self.assertFalse(any(OTHER in p["path"] for p in packet["snapshot"]["files"]))
            self.assertTrue((project / f"{OTHER}.jsonl").exists())

    def test_codex_delete_blocks_missing_activity_before_rpc(self):
        packet = {"schema": "thread_cleanup.plan.v1", "system": "codex", "home": "unused",
                  "snapshot": {"id": ID}, "protected_ids": []}
        with patch.object(cleanup, "CodexRPC") as rpc:
            with self.assertRaises(cleanup.CleanupError):
                cleanup.delete_codex(packet, "unused", {"thread_id": ID, "status": "active"})
            rpc.assert_not_called()

    @unittest.skipUnless(EXE.exists(), "Installed Codex app-server required for isolated lifecycle test")
    def test_real_app_server_deletes_rollout_and_database_rows(self):
        with tempfile.TemporaryDirectory(dir="D:/Temp", delete=False, prefix="thread-cleanup-fixture-") as value:
            print(f"Fixture cleanup required: {value}", flush=True)
            home = Path(value) / "codex-home"
            home.mkdir()
            rpc = cleanup.CodexRPC(EXE, home)
            try:
                started = rpc.request("thread/start", {"cwd": value})
                tid = started["thread"]["id"]
                rpc.request("thread/archive", {"threadId": tid})
            finally:
                rpc.close()
            # Synthetic database-only item: must be removed by the supported API.
            with closing(sqlite3.connect(home / "thread_history_1.sqlite")) as c:
                c.execute("CREATE TABLE IF NOT EXISTS deletion_fixture(thread_id TEXT,value TEXT)")
                c.execute("INSERT INTO deletion_fixture VALUES (?,?)", (OTHER, "unrelated"))
                c.execute("INSERT INTO thread_turns(thread_id,turn_id,rollout_ordinal,status) VALUES (?,?,?,?)", (tid, "fixture-turn", 0, "completed"))
                c.execute("INSERT INTO thread_items(thread_id,turn_id,item_id,rollout_ordinal,created_at_ms,item_json) VALUES (?,?,?,?,?,?)",
                          (tid, "fixture-turn", "fixture-item", 0, 0, '{"type":"agentMessage","text":"database-only fixture"}'))
                c.commit()
            with closing(sqlite3.connect(home / "memories_1.sqlite")) as c:
                c.execute("INSERT INTO stage1_outputs(thread_id,source_updated_at,raw_memory,rollout_summary,generated_at) VALUES (?,0,'fixture memory','fixture summary',0)", (tid,))
                c.commit()
            with closing(sqlite3.connect(home / "queue_1.sqlite")) as c:
                c.execute("INSERT INTO queued_thread_revisions(thread_id) VALUES (?)", (tid,))
                c.commit()
            earlier = home / "archived_sessions" / f"rollout-earlier-{tid}.jsonl"
            earlier.write_text(json.dumps({"type": "session_meta", "payload": {"id": tid}}) + "\n")
            packet = cleanup.plan("codex", home, tid)
            self.assertTrue(any(r["table"] == "thread_items" and r["rows"] == 1 for r in packet["snapshot"]["database_rows"]))
            result = cleanup.delete_codex(packet, EXE, {"source": "codex_task_api", "thread_id": tid, "status": "notLoaded"})
            self.assertTrue(result["application_delete_completed"])
            self.assertEqual(result["file_residuals"], [])
            self.assertEqual(result["database_residuals"], [])
            with closing(cleanup.readonly(home / "thread_history_1.sqlite")) as c:
                self.assertEqual(c.execute("SELECT value FROM deletion_fixture").fetchone()[0], "unrelated")

    def test_claude_exact_deletion_preserves_other_history_and_index_rows(self):
        with tempfile.TemporaryDirectory(dir="D:/Temp") as value:
            home = Path(value)
            project = home / "projects/example"
            project.mkdir(parents=True)
            (project / f"{ID}.jsonl").write_text('{"sessionId":"' + ID + '"}\n')
            (project / f"{OTHER}.jsonl").write_text("unrelated history")
            history = home / "history.jsonl"
            history.write_text(json.dumps({"sessionId": ID, "display": "remove"}) + "\n" +
                               json.dumps({"sessionId": OTHER, "display": "preserve"}) + "\n")
            packet = cleanup.plan("claude", home, ID, [OTHER])
            with patch.object(cleanup, "live_claude_ids", return_value=[]):
                result = cleanup.delete_claude(packet)
            self.assertTrue(result["complete"], result)
            self.assertFalse((project / f"{ID}.jsonl").exists())
            self.assertEqual((project / f"{OTHER}.jsonl").read_text(), "unrelated history")
            self.assertEqual(json.loads(history.read_text())["sessionId"], OTHER)

    def test_claude_live_registration_blocks_before_deletion(self):
        packet = {"schema": "thread_cleanup.plan.v1", "system": "claude", "home": "unused",
                  "snapshot": {"id": ID}, "protected_ids": []}
        with patch.object(cleanup, "live_claude_ids", return_value=[ID]):
            with self.assertRaises(cleanup.CleanupError):
                cleanup.delete_claude(packet)

    def test_claude_hardlinked_history_name_does_not_delete_other_link(self):
        with tempfile.TemporaryDirectory(dir="D:/Temp") as value:
            home = Path(value)
            project = home / "projects/example"
            project.mkdir(parents=True)
            (project / f"{ID}.jsonl").write_text("fixture")
            original = home / "unrelated-original.txt"
            original.write_text("preserve original")
            saved = home / "file-history" / ID
            saved.mkdir(parents=True)
            os.link(original, saved / "saved@v1")
            packet = cleanup.plan("claude", home, ID)
            with patch.object(cleanup, "live_claude_ids", return_value=[]):
                result = cleanup.delete_claude(packet)
            self.assertTrue(result["complete"], result)
            self.assertEqual(original.read_text(), "preserve original")

    def test_live_detection_ignores_the_cleanup_shells_own_uuid_arguments(self):
        import subprocess
        processes = [{"Name": "pwsh.exe", "ProcessId": 1, "CommandLine": f"python C:/.claude/skills/thread-cleanup/script.py --confirm-thread-id {ID}"},
                     {"Name": "claude.exe", "ProcessId": 2, "CommandLine": f"claude --resume {OTHER}"}]
        with tempfile.TemporaryDirectory(dir="D:/Temp") as value:
            completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(processes))
            with patch.object(cleanup.subprocess, "run", return_value=completed):
                self.assertEqual(cleanup.live_claude_ids(Path(value)), [OTHER])

    def test_fork_dependencies_are_not_confused_with_spawn_edges(self):
        with tempfile.TemporaryDirectory(dir="D:/Temp") as value:
            home = Path(value)
            rollout = home / "dependent.jsonl"
            rollout.write_text(json.dumps({"type": "session_meta", "payload": {"id": OTHER, "forked_from_id": ID, "forked_from_ordinal_exclusive": 42}}) + "\n")
            with closing(sqlite3.connect(home / "state_5.sqlite")) as c:
                c.execute("CREATE TABLE threads(id TEXT,rollout_path TEXT)")
                c.execute("INSERT INTO threads VALUES (?,?)", (OTHER, str(rollout)))
                c.commit()
            found = cleanup.fork_dependents(home, ID)
            self.assertEqual(found[0]["thread_id"], OTHER)
            self.assertEqual(found[0]["fork_boundary"], 42)


if __name__ == "__main__":
    unittest.main()
