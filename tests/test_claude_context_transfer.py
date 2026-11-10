import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "families/claude-context-transfer/codex/skills/claude-context-transfer/scripts/claude_context_transfer.py"
SPEC = importlib.util.spec_from_file_location("claude_context_transfer", HELPER)
cct = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cct)

SRC = "11111111-1111-4111-8111-111111111111"
DST = "22222222-2222-4222-8222-222222222222"
HAS_7Z = bool(shutil.which("7z.exe") or shutil.which("7z"))


def line(**record):
    return json.dumps(record) + "\n"


class ClaudeContextTransferTests(unittest.TestCase):
    def setUp(self):
        base = os.environ.get("CLAUDE_TRANSFER_TEST_ROOT") or None
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self._tmp.name)
        self.home = self.root / "claude"
        project = self.home / "projects" / "C--work"
        (project / SRC / "subagents").mkdir(parents=True)
        self.main = project / f"{SRC}.jsonl"
        self.main.write_text(
            line(type="custom-title", customTitle="Old work", sessionId=SRC)
            + line(type="user", sessionId=SRC, message={"role": "user", "content": "Implement the parser"})
            + line(type="custom-title", customTitle="Old work", sessionId=SRC)
            + line(type="user", sessionId=SRC, message={"role": "user", "content": "<task-notification>done</task-notification>"})
            + line(type="assistant", sessionId=SRC, message={"content": [{"type": "text", "text": "Decision: use streaming"}]}),
            encoding="utf-8")
        (project / SRC / "subagents" / "agent-abc.jsonl").write_text(
            line(type="assistant", sessionId=SRC, message={"content": [{"type": "text", "text": "child result"}]}), encoding="utf-8")
        (self.home / "file-history" / SRC).mkdir(parents=True)
        (self.home / "file-history" / SRC / "f@v1").write_text("old file", encoding="utf-8")
        (project / f"{DST}.jsonl").write_text(line(type="user", sessionId=DST, message={"content": "continue"}), encoding="utf-8")
        self.reframe = self.root / "state.json"
        self.reframe.write_text(json.dumps({"sessions": {"t1": {"id": "t1", "claudeSessionId": SRC, "name": "Tile"}}}), encoding="utf-8")
        self.work = self.root / "work"
        self.work.mkdir()
        patcher = patch.object(cct, "running_processes", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def inspect(self):
        result = cct.inspect(self.home, SRC, DST, self.root / "archives", self.reframe)
        path = cct.write_json(self.work / "inspection.json", result)
        return result, path

    def handoff(self, manifest, drop=None, child=True):
        body = []
        for name in cct.REQUIRED_SECTIONS:
            if name == drop:
                continue
            text = "- agent-abc: produced child result" if (name == "Subagent Contribution Map" and child) else "content"
            body.append(f"## {name}\n\n{text}\n")
        path = self.work / "CONTEXT_TRANSFER.md"
        path.write_text("# Transfer\n\n" + "\n".join(body), encoding="utf-8")
        return path

    def acceptance(self, handoff, **override):
        payload = {"schema": f"{cct.PREFIX}.destination_acceptance.v1", "source_session_id": SRC,
                   "destination_session_id": DST, "handoff_ready": True,
                   "handoff_sha256": hashlib.sha256(handoff.read_bytes()).hexdigest(),
                   "mapped_active_requirements": ["parser"], "evidence_sources_inspected": ["catalog"],
                   "repository_state_verified": ["git status"], "unresolved_uncertainties": [],
                   "critical_unmapped_objectives": [], "first_continuation_action": "run tests", **override}
        return cct.write_json(self.work / "acceptance.json", payload)

    def test_inspect_inventories_owned_members_and_reframe_tiles(self):
        result, _ = self.inspect()
        relatives = sorted(m["relative"] for m in result["members"])
        self.assertEqual(relatives, [f"file-history/{SRC}/f@v1", f"projects/C--work/{SRC}.jsonl",
                                     f"projects/C--work/{SRC}/subagents/agent-abc.jsonl"])
        self.assertEqual(result["subagent_ids"], ["agent-abc"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["source_titles"]["custom_title"], "Old work")
        self.assertEqual(result["reframe_tile_references"][0]["tile_id"], "t1")
        self.assertFalse(result["mutations_performed"])

    def test_inspect_blockers(self):
        with self.assertRaises(cct.TransferError):
            cct.inspect(self.home, SRC, SRC, self.root, None)
        with self.assertRaises(cct.TransferError):
            cct.inspect(self.home, SRC[:8], DST, self.root, None)
        dst = self.home / "projects" / "C--work" / f"{DST}.jsonl"
        dst.write_text(dst.read_text() + line(type="user", sessionId=SRC), encoding="utf-8")
        (self.home / "sessions").mkdir()
        (self.home / "sessions" / "1.json").write_text(json.dumps({"pid": 77, "sessionId": SRC}), encoding="utf-8")
        with patch.object(cct, "running_processes", return_value=[{"ProcessId": 77, "Name": "claude.exe"}]):
            result = cct.inspect(self.home, SRC, DST, self.root, None)
        self.assertEqual(set(result["blockers"]), {"source_live", "destination_is_history_dependent"})
        self.assertFalse(result["retirement_ready"])

    def test_catalog_dedupes_titles_and_labels_automation(self):
        result, _ = self.inspect()
        entries = cct.catalog(result, 10, 10, 10, 100)["transcripts"][0]["entries"]
        self.assertEqual([e["kind"] for e in entries], ["title", "user", "automated_event", "assistant"])

    def test_handoff_and_acceptance_contract(self):
        result, _ = self.inspect()
        with self.assertRaises(cct.TransferError) as missing:
            cct.validate_handoff(result, self.handoff(result, drop="Current Objective"))
        self.assertIn("Current Objective", missing.exception.details["missing_sections"])
        with self.assertRaises(cct.TransferError) as unmapped:
            cct.validate_handoff(result, self.handoff(result, child=False))
        self.assertEqual(unmapped.exception.details["unmapped_subagents"], ["agent-abc"])
        handoff = self.handoff(result)
        self.assertTrue(cct.validate_handoff(result, handoff)["ok"])
        with self.assertRaises(cct.TransferError):
            cct.validate_acceptance(result, handoff, self.acceptance(handoff, handoff_sha256="0" * 64))
        with self.assertRaises(cct.TransferError):
            cct.validate_acceptance(result, handoff, self.acceptance(handoff, critical_unmapped_objectives=["x"]))
        self.assertTrue(cct.validate_acceptance(result, handoff, self.acceptance(handoff))["ok"])

    @unittest.skipUnless(HAS_7Z, "7-Zip required")
    def test_pack_verify_gate_restore_and_completion(self):
        result, manifest = self.inspect()
        handoff = self.handoff(result)
        acceptance = self.acceptance(handoff)
        transfer = self.root / "archives" / "2026" / "2026-11-10-old-work"
        packed = cct.pack(manifest, handoff, str(transfer), None)
        archive = Path(packed["archive"])
        self.assertFalse((archive.parent / ".staging").exists())
        verification = cct.verify(archive, None)
        self.assertEqual(verification["members_verified"], 3)
        self.assertTrue((transfer / "Records" / "verification.json").is_file())

        plan = {"schema": "thread_cleanup.plan.v1", "system": "claude", "protected_ids": [],
                "snapshot": {"id": SRC, "files": [{"path": m["path"], "sha256": m["sha256"]} for m in result["members"]]}}
        plan_path = cct.write_json(self.work / "plan.json", plan)
        verification_path = archive.parent / "verification.json"
        with self.assertRaises(cct.TransferError) as unprotected:
            cct.retirement_check(manifest, handoff, acceptance, verification_path, plan_path)
        self.assertEqual(unprotected.exception.kind, "destination_unprotected")
        plan["protected_ids"] = [DST]
        plan["snapshot"]["files"].append({"path": str(self.home / "debug" / f"{SRC}.txt"), "sha256": "1" * 64})
        cct.write_json(plan_path, plan)
        with self.assertRaises(cct.TransferError) as unarchived:
            cct.retirement_check(manifest, handoff, acceptance, verification_path, plan_path)
        self.assertEqual(unarchived.exception.kind, "unarchived_members")
        plan["snapshot"]["files"].pop()
        cct.write_json(plan_path, plan)
        self.assertTrue(cct.retirement_check(manifest, handoff, acceptance, verification_path, plan_path)["ok"])

        # Simulated retirement, then recovery from the archive.
        originals = {m["path"]: m["sha256"] for m in result["members"]}
        for path in originals:
            Path(path).unlink()
        restored = cct.restore(archive, None)
        self.assertEqual(len(restored["restored"]), 3)
        self.assertTrue(all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in originals.items()))
        Path(next(iter(originals))).write_text("changed", encoding="utf-8")
        with self.assertRaises(cct.TransferError) as conflict:
            cct.restore(archive, None)
        self.assertEqual(conflict.exception.kind, "restore_conflict")

        records = transfer / "Records"
        cct.write_json(records / "acceptance-validation.json", cct.validate_acceptance(result, handoff, acceptance))
        with self.assertRaises(cct.TransferError):
            cct.validate_completion(transfer)
        dst = self.home / "projects" / "C--work" / f"{DST}.jsonl"
        dst.write_text(dst.read_text() + line(type="custom-title", customTitle="Old work", sessionId=DST), encoding="utf-8")
        cct.write_json(records / "title-status.json", cct.title_status(self.home, DST, "Old work", None))
        cct.write_json(records / "retirement-result.json", {"ok": True, "result": {"complete": False}})
        with self.assertRaises(cct.TransferError):
            cct.validate_completion(transfer)
        # Exact thread-cleanup CLI envelope.
        cct.write_json(records / "retirement-result.json", {"ok": True, "result": {"complete": True}})
        self.assertEqual(cct.validate_completion(transfer)["endpoint"], "takeover_retired")

    @unittest.skipUnless(HAS_7Z, "7-Zip required")
    def test_pack_refuses_changed_source(self):
        result, manifest = self.inspect()
        handoff = self.handoff(result)
        self.main.write_text(self.main.read_text() + line(type="user", sessionId=SRC), encoding="utf-8")
        with self.assertRaises(cct.TransferError) as changed:
            cct.pack(manifest, handoff, str(self.root / "archives" / "x"), None)
        self.assertEqual(changed.exception.kind, "source_changed")


if __name__ == "__main__":
    unittest.main()
