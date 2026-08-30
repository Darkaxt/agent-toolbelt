from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_SRC = REPO_ROOT / "families" / "context-transfer" / "src"
if str(FAMILY_SRC) not in sys.path:
    sys.path.insert(0, str(FAMILY_SRC))

from agent_toolbelt_context_transfer import retirement


TEMP_ROOT = Path(r"D:\Temp")
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class RetirementFixture:
    def __init__(self, root: Path):
        self.root = root
        self.codex_home = root / "codex-home"
        self.sessions = self.codex_home / "sessions"
        self.sessions.mkdir(parents=True)
        self.root_rollout = self.sessions / "root.jsonl"
        self.child_rollout = self.sessions / "child.jsonl"
        self.root_rollout.write_bytes(b"root rollout")
        self.child_rollout.write_bytes(b"child rollout")
        self.unlisted = self.sessions / "new.jsonl"
        self.unlisted.write_bytes(b"new concurrent file")
        self.state_db = self.codex_home / "state_5.sqlite"
        self.state_db.write_bytes(b"sqlite remains")

        self.transaction = root / "transaction"
        self.transaction.mkdir()
        self.archive_path = self.transaction / "thread-tree.7z"
        self.archive_path.write_bytes(b"verified archive")
        self.handoff_path = self.transaction / "CONTEXT_TRANSFER.md"
        self.handoff_path.write_text("# accepted handoff\n", encoding="utf-8")
        self.manifest_path = self.transaction / "manifest.json"
        rollouts = []
        for thread_id, path in (("root", self.root_rollout), ("child", self.child_rollout)):
            stat_result = path.stat()
            rollouts.append(
                {
                    "thread_id": thread_id,
                    "original_path": str(path),
                    "archive_path": f"sessions/{path.name}",
                    "size": stat_result.st_size,
                    "mtime_ns": stat_result.st_mtime_ns,
                    "sha256": digest(path),
                }
            )
        self.manifest = {
            "schema": "agent_toolbelt_context_transfer.archive_manifest.v1",
            "source_thread_id": "root",
            "destination_thread_id": "destination",
            "codex_home": str(self.codex_home),
            "handoff_sha256": digest(self.handoff_path),
            "rollouts": rollouts,
        }
        write_json(self.manifest_path, self.manifest)
        write_json(
            self.transaction / "threads.json",
            [{"thread_id": "root"}, {"thread_id": "child"}],
        )
        write_json(
            self.transaction / "spawn-edges.json",
            [
                {
                    "parent_thread_id": "root",
                    "child_thread_id": "child",
                    "status": "closed",
                }
            ],
        )
        self.verification_path = self.transaction / "verification.json"
        self.verification = {
            "schema": "agent_toolbelt_context_transfer.verification.v1",
            "ok": True,
            "archive_path": str(self.archive_path),
            "archive_sha256": digest(self.archive_path),
            "manifest_sha256": digest(self.manifest_path),
            "handoff_sha256": digest(self.handoff_path),
            "archive_test_passed": True,
        }
        write_json(self.verification_path, self.verification)

        self.acceptance_path = root / "destination-acceptance.json"
        self.acceptance = {
            "schema": "agent_toolbelt_context_transfer.destination_acceptance.v1",
            "source_thread_id": "root",
            "destination_thread_id": "destination",
            "handoff_ready": True,
            "mapped_active_requirements": ["continue Apollo"],
            "evidence_sources_inspected": ["rollout offsets", "live repository"],
            "repository_state_verified": [{"path": "D:/repo", "commit": "abcdef1"}],
            "unresolved_uncertainties": [],
            "critical_unmapped_objectives": [],
            "first_continuation_action": "Continue Stage 4.",
            "handoff_sha256": digest(self.handoff_path),
        }
        write_json(self.acceptance_path, self.acceptance)

        self.archived_state_path = root / "archived-state.json"
        self.archived_state = {
            "schema": "agent_toolbelt_context_transfer.archived_state.v1",
            "source_thread_id": "root",
            "archived": True,
            "verified_at": "2026-08-31T13:00:00Z",
            "evidence_source": "codex_task_api",
        }
        write_json(self.archived_state_path, self.archived_state)

    def issue(self, *, confirm: bool = True) -> dict:
        with mock.patch.object(
            retirement.archive,
            "verify_recovery_archive",
            return_value={"ok": True, "archive_sha256": digest(self.archive_path)},
        ):
            return retirement.issue_deletion_ticket(
                verification_path=self.verification_path,
                acceptance_path=self.acceptance_path,
                archived_state_path=self.archived_state_path,
                confirm_live_retirement=confirm,
            )


class RetirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.fixture = RetirementFixture(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_ticket_issue_requires_explicit_live_retirement_confirmation(self):
        with self.assertRaises(retirement.RetirementError) as raised:
            self.fixture.issue(confirm=False)

        self.assertEqual(raised.exception.kind, "live_retirement_confirmation_required")
        self.assertFalse((self.fixture.transaction / "deletion-ticket.json").exists())

    def test_ticket_requires_verified_archived_state(self):
        state = dict(self.fixture.archived_state)
        state["archived"] = False
        write_json(self.fixture.archived_state_path, state)

        with self.assertRaises(retirement.RetirementError) as raised:
            self.fixture.issue()

        self.assertEqual(raised.exception.kind, "source_not_archived")

    def test_ticket_rejects_unmapped_objective(self):
        acceptance = dict(self.fixture.acceptance)
        acceptance["critical_unmapped_objectives"] = ["release"]
        write_json(self.fixture.acceptance_path, acceptance)

        with self.assertRaises(retirement.RetirementError) as raised:
            self.fixture.issue()

        self.assertEqual(raised.exception.kind, "acceptance_incomplete")

    def test_ticket_binds_archive_handoff_threads_and_exact_files(self):
        result = self.fixture.issue()
        ticket_path = Path(result["ticket_path"])
        ticket = json.loads(ticket_path.read_text(encoding="utf-8"))

        self.assertEqual(ticket["source_thread_id"], "root")
        self.assertEqual(ticket["thread_ids"], ["child", "root"])
        self.assertEqual(ticket["archive_sha256"], digest(self.fixture.archive_path))
        self.assertEqual(ticket["handoff_sha256"], digest(self.fixture.handoff_path))
        self.assertEqual(len(ticket["files"]), 2)
        self.assertTrue(ticket["nonce"])
        self.assertTrue(ticket["ticket_id"])
        self.assertEqual(ticket["cache_files"], [])
        self.assertEqual(ticket["cache_ownership"], "none_proven")

    def test_apply_deletes_only_unchanged_ticket_files_and_leaves_sqlite_and_new_files(self):
        db_before = digest(self.fixture.state_db)
        ticket = self.fixture.issue()

        result = retirement.apply_deletion_ticket(
            ticket_path=ticket["ticket_path"],
            ticket_id=ticket["ticket_id"],
            confirm_delete=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "complete")
        self.assertFalse(self.fixture.root_rollout.exists())
        self.assertFalse(self.fixture.child_rollout.exists())
        self.assertTrue(self.fixture.unlisted.is_file())
        self.assertEqual(digest(self.fixture.state_db), db_before)
        self.assertEqual(result["residual_file_count"], 0)
        self.assertTrue(Path(result["consumed_marker_path"]).is_file())

    def test_changed_file_is_skipped_and_ticket_is_consumed(self):
        ticket = self.fixture.issue()
        self.fixture.child_rollout.write_bytes(b"changed concurrently")

        result = retirement.apply_deletion_ticket(
            ticket_path=ticket["ticket_path"],
            ticket_id=ticket["ticket_id"],
            confirm_delete=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "partial")
        self.assertFalse(self.fixture.root_rollout.exists())
        self.assertTrue(self.fixture.child_rollout.is_file())
        self.assertEqual(result["residual_file_count"], 1)
        self.assertEqual(result["files"][1]["status"], "changed_skipped")

        with self.assertRaises(retirement.RetirementError) as raised:
            retirement.apply_deletion_ticket(
                ticket_path=ticket["ticket_path"],
                ticket_id=ticket["ticket_id"],
                confirm_delete=True,
            )
        self.assertEqual(raised.exception.kind, "ticket_already_used")

    def test_tampered_ticket_fails_before_deletion(self):
        issued = self.fixture.issue()
        ticket_path = Path(issued["ticket_path"])
        ticket = json.loads(ticket_path.read_text(encoding="utf-8"))
        ticket["files"][0]["original_path"] = str(self.fixture.unlisted)
        write_json(ticket_path, ticket)

        with self.assertRaises(retirement.RetirementError) as raised:
            retirement.apply_deletion_ticket(
                ticket_path=ticket_path,
                ticket_id=issued["ticket_id"],
                confirm_delete=True,
            )

        self.assertEqual(raised.exception.kind, "ticket_integrity_failed")
        self.assertTrue(self.fixture.root_rollout.is_file())
        self.assertTrue(self.fixture.child_rollout.is_file())

    def test_outside_codex_rollout_root_is_rejected_even_with_recomputed_ticket_id(self):
        issued = self.fixture.issue()
        ticket_path = Path(issued["ticket_path"])
        ticket = json.loads(ticket_path.read_text(encoding="utf-8"))
        outside = self.root / "outside.txt"
        outside.write_bytes(b"outside")
        stat_result = outside.stat()
        ticket["files"][0] = {
            "thread_id": "root",
            "original_path": str(outside),
            "size": stat_result.st_size,
            "mtime_ns": stat_result.st_mtime_ns,
            "sha256": digest(outside),
        }
        ticket["ticket_id"] = retirement.compute_ticket_id(ticket)
        write_json(ticket_path, ticket)

        with self.assertRaises(retirement.RetirementError) as raised:
            retirement.apply_deletion_ticket(
                ticket_path=ticket_path,
                ticket_id=ticket["ticket_id"],
                confirm_delete=True,
            )

        self.assertEqual(raised.exception.kind, "unsafe_ticket_path")
        self.assertTrue(outside.is_file())

    def test_wrong_reviewed_ticket_id_fails_before_deletion(self):
        issued = self.fixture.issue()

        with self.assertRaises(retirement.RetirementError) as raised:
            retirement.apply_deletion_ticket(
                ticket_path=issued["ticket_path"],
                ticket_id="0" * 64,
                confirm_delete=True,
            )

        self.assertEqual(raised.exception.kind, "ticket_id_mismatch")
        self.assertTrue(self.fixture.root_rollout.is_file())

    def test_retirement_module_has_no_recursive_or_sqlite_deletion_path(self):
        source = (
            FAMILY_SRC
            / "agent_toolbelt_context_transfer"
            / "retirement.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("rmtree(", source)
        self.assertNotIn("sqlite3", source)
        self.assertNotIn(".glob(", source)
        self.assertNotIn(".rglob(", source)


if __name__ == "__main__":
    unittest.main()
