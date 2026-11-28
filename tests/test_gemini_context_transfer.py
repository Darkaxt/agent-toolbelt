import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "families/gemini-context-transfer/codex/skills/gemini-context-transfer/scripts/gemini_context_transfer.py"
SPEC = importlib.util.spec_from_file_location("gemini_context_transfer", HELPER)
gct = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gct)

SRC = "11111111-1111-4111-8111-111111111111"
OTHER = "33333333-3333-4333-8333-333333333333"
DST = "22222222-2222-4222-8222-222222222222"
HAS_7Z = bool(shutil.which("7z.exe") or shutil.which("7z"))


def line(**record):
    return json.dumps(record) + "\n"


class GeminiContextTransferTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=os.environ.get("GEMINI_TRANSFER_TEST_ROOT") or None)
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.home = self.root / "gemini"
        hook = "D:/Tools/Reframe/profiles/ClaudeGPT/hooks/abc-agy"
        meta = {"conversations": {
            SRC: {"summary": {"ID": SRC, "Title": "Doodle Work", "NumSteps": 5, "UpdatedAt": "2026-11-23T00:00:00Z",
                              "WorkspaceURIs": ["file:///C:/work", f"file:///{hook}"]}},
            OTHER: {"summary": {"ID": OTHER, "Title": "Other", "NumSteps": 1, "UpdatedAt": "2026-11-01T00:00:00Z"}}}}
        (self.home / "cache").mkdir(parents=True)
        (self.home / "cache" / "conversation_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.home / "history.jsonl").write_text(line(id=SRC), encoding="utf-8")
        (self.home / "conversation_summaries.db").write_bytes(b"SQLite shared")
        logs = self.home / "brain" / SRC / ".system_generated" / "logs"
        logs.mkdir(parents=True)
        self.transcript = logs / "transcript.jsonl"
        self.transcript.write_text(
            line(step_index=0, source="USER_EXPLICIT", type="USER_INPUT", created_at="t0",
                 content="<USER_REQUEST>\nExtract the APK\n</USER_REQUEST>\n<ADDITIONAL_METADATA>x</ADDITIONAL_METADATA>")
            + line(step_index=1, source="MODEL", type="PLANNER_RESPONSE", content="Plan: use adb",
                   tool_calls=[{"name": "run_command", "args": {"CommandLine": "git clone https://github.com/acme/tool.git"}},
                               {"name": "view_file", "args": {"AbsolutePath": "D:/proj/a.py"}}])
            + line(step_index=2, source="MODEL", type="GENERIC", content="cloned ok")
            + line(step_index=3, source="SYSTEM", type="CHECKPOINT", content="# Resuming from a compaction")
            + line(step_index=4, source="MODEL", type="PLANNER_RESPONSE", content="Released v1.2.3, done"),
            encoding="utf-8")
        (logs / "transcript_full.jsonl").write_text("full\n", encoding="utf-8")
        (self.home / "brain" / SRC / ".system_generated" / "subagents" / "sub-1").mkdir(parents=True)
        (self.home / "brain" / SRC / ".system_generated" / "subagents" / "sub-1" / "out.txt").write_text("child", encoding="utf-8")
        (self.home / "brain" / SRC / "task-7").mkdir()
        (self.home / "brain" / SRC / "task-7" / "notes.md").write_text("task", encoding="utf-8")
        (self.home / "conversations").mkdir()
        (self.home / "conversations" / f"{SRC}.db").write_bytes(b"db-bytes")
        (self.home / "conversations" / f"{OTHER}.db").write_bytes(b"other")
        (self.home / "annotations").mkdir()
        (self.home / "annotations" / f"{SRC}.pbtxt").write_text("a: 1", encoding="utf-8")
        self.claude = self.root / "claude"
        (self.claude / "projects" / "C--x").mkdir(parents=True)
        (self.claude / "projects" / "C--x" / f"{DST}.jsonl").write_text(line(type="user"), encoding="utf-8")
        self.records = self.root / "transfer" / "Records"
        self.records.mkdir(parents=True)
        for target, value in (("running_processes", []), ("refuse_c_drive", None)):
            patcher = patch.object(gct, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def inspect(self):
        result = gct.inspect(self.home, SRC, DST, self.root / "archives", self.claude)
        return result, gct.write_json(self.records / "inspection.json", result)

    def handoff(self, manifest):
        body = "\n\n".join(f"## {name}\ncontent" for name in gct.REQUIRED_SECTIONS
                           if name != "Gemini Subagent And Task Map")
        body += "\n\n## Gemini Subagent And Task Map\n- sub-1: child\n- task-7: notes\n"
        path = self.records / "CONTEXT_TRANSFER.md"
        path.write_text(body, encoding="utf-8")
        return path

    def acceptance(self, manifest, handoff):
        payload = {"schema": f"{gct.PREFIX}.destination_acceptance.v1", "source_conversation_id": SRC,
                   "destination_session_id": DST, "handoff_ready": True, "handoff_sha256": gct.sha256(handoff),
                   "mapped_active_requirements": ["r"], "evidence_sources_inspected": ["catalog"],
                   "repository_state_verified": ["repo"], "unresolved_uncertainties": [],
                   "critical_unmapped_objectives": [], "first_continuation_action": "continue"}
        path = self.records / "destination-acceptance.json"
        gct.write_json(path, payload)
        gct.write_json(self.records / "acceptance-validation.json", gct.validate_acceptance(manifest, handoff, path))
        return path

    def test_list_and_ids(self):
        result = gct.list_conversations(self.home)
        self.assertEqual([r["id"] for r in result["conversations"]], [SRC, OTHER])
        self.assertGreater(result["conversations"][0]["sizes"]["brain"], 0)
        with self.assertRaises(gct.TransferError):
            gct.inspect(self.home, "Doodle Work", DST, self.root, self.claude)
        with self.assertRaises(gct.TransferError):
            gct.inspect(self.home, SRC, SRC, self.root, self.claude)

    def test_inspect_inventory_blockers_and_refs(self):
        result, _ = self.inspect()
        rels = {m["relative"] for m in result["members"]}
        self.assertIn(f"conversations/{SRC}.db", rels)
        self.assertIn(f"annotations/{SRC}.pbtxt", rels)
        self.assertNotIn(f"conversations/{OTHER}.db", rels)
        self.assertTrue(all(len(m["sha256"]) == 64 for m in result["members"]))
        self.assertEqual(result["title"], "Doodle Work")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["reframe_tile_references"][0]["hook_id"], "abc-agy")
        self.assertEqual(result["subagent_ids"], ["sub-1"])
        self.assertEqual(result["task_directories"], ["task-7"])
        residual = {Path(r["path"]).name for r in result["shared_index_residuals"]}
        self.assertTrue({"conversation_metadata.json", "history.jsonl", "conversation_summaries.db"} <= residual)
        with patch.object(gct, "running_processes", return_value=[{"Name": "agy.exe", "ProcessId": 4}]):
            self.assertIn("source_live", gct.inspect(self.home, SRC, DST, self.root, self.claude)["blockers"])
        self.assertIn("destination_transcript_missing",
                      gct.inspect(self.home, SRC, OTHER, self.root, self.claude)["blockers"])

    def test_catalog_search_show(self):
        result, _ = self.inspect()
        cat = gct.catalog(result, 15, 30, 150, 600)
        self.assertEqual(cat["user_requests"][0]["excerpt"], "Extract the APK")
        self.assertEqual(len(cat["checkpoints"]), 1)
        self.assertEqual(cat["final_assistant_messages"][-1]["excerpt"], "Released v1.2.3, done")
        self.assertEqual(cat["files_touched"][0]["path"], "D:/proj/a.py")
        self.assertIn("acme/tool", cat["git_repositories"])
        self.assertIn("v1.2.3", cat["releases_and_prs"])
        self.assertTrue(cat["commands_recent"][0].startswith("git clone"))
        found = gct.search(self.home, SRC, "git clone", None, True, 5, 100, False)
        self.assertEqual(found["matches"][0]["kind"], "tool_use")
        self.assertEqual(gct.search(self.home, SRC, "apk", {"user"}, False, 5, 100, False)["total_matches"], 1)
        self.assertIn("Plan: use adb", gct.show(self.home, SRC, 2, 1000, 0)["text"])

    def test_handoff_and_acceptance(self):
        result, _ = self.inspect()
        handoff = self.handoff(result)
        self.assertTrue(gct.validate_handoff(result, handoff)["ok"])
        handoff.write_text("## Current Objective\nx\n", encoding="utf-8")
        with self.assertRaises(gct.TransferError) as caught:
            gct.validate_handoff(result, handoff)
        self.assertIn("sub-1", caught.exception.details["unmapped_subagents_or_tasks"])
        handoff = self.handoff(result)
        path = self.acceptance(result, handoff)
        payload = json.loads(path.read_text())
        payload["critical_unmapped_objectives"] = ["x"]
        gct.write_json(path, payload)
        with self.assertRaises(gct.TransferError):
            gct.validate_acceptance(result, handoff, path)

    def test_pack_refuses_changed_source_and_missing_root(self):
        result, manifest = self.inspect()
        handoff = self.handoff(result)
        (self.home / "annotations" / f"{SRC}.pbtxt").write_text("changed", encoding="utf-8")
        with self.assertRaises(gct.TransferError) as caught:
            gct.pack(manifest, handoff, str(self.root / "transfer"), None)
        self.assertEqual(caught.exception.kind, "source_changed")
        result, manifest = self.inspect()
        data = json.loads(manifest.read_text())
        data["archive_root"] = "Q:\\NoSuchDrive\\Root"
        gct.write_json(manifest, data)
        with self.assertRaises(gct.TransferError) as caught:
            gct.pack(manifest, handoff, None, None)
        self.assertEqual(caught.exception.kind, "archive_root_unavailable")

    def test_refuse_c_drive(self):
        patch.stopall()
        with self.assertRaises(gct.TransferError):
            gct.refuse_c_drive(Path("C:\\Archives\\x"))
        gct.refuse_c_drive(Path("D:\\Archives\\x"))

    @unittest.skipUnless(HAS_7Z, "7-Zip required")
    def test_end_to_end_pack_verify_retire_restore(self):
        result, manifest = self.inspect()
        handoff = self.handoff(result)
        acceptance = self.acceptance(result, handoff)
        packed = gct.pack(manifest, handoff, str(self.root / "transfer"), None)
        archive = Path(packed["archive"])
        self.assertEqual(archive.name, "conversation-tree.7z")
        verified = gct.verify(archive, None)
        self.assertTrue((self.records / "verification.json").is_file())
        verification = self.records / "verification.json"
        with patch.object(gct, "running_processes", return_value=[{"Name": "language_server_windows_x64.exe"}]):
            with self.assertRaises(gct.TransferError):
                gct.retire(manifest, handoff, acceptance, verification, True, None, None)
        dry = gct.retire(manifest, handoff, acceptance, verification, True, None, None)
        self.assertTrue(dry["dry_run"])
        self.assertTrue((self.home / "brain" / SRC).exists())
        with self.assertRaises(gct.TransferError):
            gct.retire(manifest, handoff, acceptance, verification, False, "0" * 64, None)
        output = self.records / "retirement-result.json"
        done = gct.retire(manifest, handoff, acceptance, verification, False, dry["plan_sha256"], output)
        self.assertTrue(done["complete"])
        self.assertEqual(done["bytes_reclaimed"], result["total_bytes"])
        self.assertFalse((self.home / "brain" / SRC).exists())
        self.assertFalse((self.home / "conversations" / f"{SRC}.db").exists())
        self.assertTrue((self.home / "conversations" / f"{OTHER}.db").exists())
        self.assertTrue((self.home / "cache" / "conversation_metadata.json").read_text().count(SRC))
        self.assertTrue((self.home / "history.jsonl").exists())
        self.assertTrue(gct.validate_completion(self.root / "transfer")["ok"])
        restored = gct.restore(archive, None)
        self.assertEqual(len(restored["restored"]), result["member_count"])
        self.assertEqual(gct.sha256(self.home / "conversations" / f"{SRC}.db"),
                         gct.sha256(self.home / "conversations" / f"{SRC}.db"))
        (self.home / "annotations" / f"{SRC}.pbtxt").write_text("conflict", encoding="utf-8")
        with self.assertRaises(gct.TransferError) as caught:
            gct.restore(archive, None)
        self.assertEqual(caught.exception.kind, "restore_conflict")
        self.assertTrue(verified["ok"])

    def test_cli_list_prints_json(self):
        with patch("sys.stdout") as out:
            self.assertEqual(gct.main(["list", "--gemini-home", str(self.home)]), 0)
        self.assertIn(SRC, "".join(c.args[0] for c in out.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
