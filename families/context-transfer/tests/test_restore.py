from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_SRC = REPO_ROOT / "families" / "context-transfer" / "src"
if str(FAMILY_SRC) not in sys.path:
    sys.path.insert(0, str(FAMILY_SRC))

from agent_toolbelt_context_transfer import archive, context_transfer, restore


TEMP_ROOT = Path(r"D:\Temp")
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
SEVEN_ZIP = shutil.which("7z.exe") or shutil.which("7z")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(SEVEN_ZIP, "7-Zip is required for restore integration tests")
class RestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.codex_home = self.root / "codex-home"
        self.sessions = self.codex_home / "sessions" / "2026" / "08" / "31"
        self.sessions.mkdir(parents=True)
        self.root_rollout = self.sessions / "root.jsonl"
        self.child_rollout = self.sessions / "child.jsonl"
        self.root_rollout.write_bytes(b"root restore content")
        self.child_rollout.write_bytes(b"child restore content")
        self.expected_hashes = {
            self.root_rollout: digest(self.root_rollout),
            self.child_rollout: digest(self.child_rollout),
        }
        self.db_path = self.codex_home / "state_5.sqlite"
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    rollout_path TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    model_provider TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    title TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE thread_spawn_edges (
                    parent_thread_id TEXT NOT NULL,
                    child_thread_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL
                );
                """
            )
            for thread_id, path in (("root", self.root_rollout), ("child", self.child_rollout)):
                connection.execute(
                    "INSERT INTO threads VALUES (?, ?, 1, 2, 'app', 'openai', ?, ?, 1)",
                    (thread_id, str(path), str(self.sessions), thread_id),
                )
            connection.execute(
                "INSERT INTO thread_spawn_edges VALUES ('root', 'child', 'closed')"
            )
            connection.commit()
        self.archive_root = self.root / "archives"
        inventory = context_transfer.inventory_thread_tree(
            source_thread_id="root",
            destination_thread_id="destination",
            codex_home=self.codex_home,
            archive_root=self.archive_root,
        )
        self.inspection_path = self.root / "inspection.json"
        self.inspection_path.write_text(json.dumps(inventory), encoding="utf-8")
        self.handoff_path = self.root / "CONTEXT_TRANSFER.md"
        self.handoff_path.write_text(
            """# Context Transfer

## Current Objective
Restore the task.

## Authoritative Specifications And Plans
Use the accepted restore specification.

## Completed Work With Evidence
Archive tests passed.

## Active Stage And Exact Next Actions
Restore exact rollouts.

## Unresolved Blockers And Required Deferrals
No blockers or deferrals.

## Durable Decisions And User Constraints
Never overwrite conflicts.

## Failed Approaches Not To Repeat
Do not restore with wildcards.

## Repositories Branches And Artifacts
No repository mutation.

## Child-Agent Contribution Map
child: restore fixture.

## Uncertainties Requiring Verification
None.
""",
            encoding="utf-8",
        )
        self.packed = archive.pack_recovery(
            inspection_manifest_path=self.inspection_path,
            handoff_path=self.handoff_path,
            archive_root=self.archive_root,
            seven_zip_path=SEVEN_ZIP,
            dictionary_mib=16,
            now=lambda: datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def remove_rollouts(self) -> None:
        self.root_rollout.unlink()
        self.child_rollout.unlink()

    def test_round_trip_restores_absent_files_and_preserves_sqlite(self):
        self.remove_rollouts()
        database_before = digest(self.db_path)

        result = restore.restore_recovery_archive(
            archive_path=self.packed["archive_path"],
            seven_zip_path=SEVEN_ZIP,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["restored_file_count"], 2)
        self.assertEqual(result["identical_file_count"], 0)
        self.assertEqual(result["conflict_file_count"], 0)
        self.assertEqual(digest(self.db_path), database_before)
        for path, expected_hash in self.expected_hashes.items():
            self.assertEqual(digest(path), expected_hash)
        self.assertFalse((Path(self.packed["transaction_root"]) / ".restore-staging").exists())

    def test_identical_existing_file_is_skipped(self):
        self.child_rollout.unlink()

        result = restore.restore_recovery_archive(
            archive_path=self.packed["archive_path"],
            seven_zip_path=SEVEN_ZIP,
        )

        statuses = {item["thread_id"]: item["status"] for item in result["files"]}
        self.assertEqual(statuses, {"root": "identical_existing", "child": "restored"})

    def test_conflict_fails_before_restoring_any_absent_file(self):
        self.root_rollout.write_bytes(b"conflicting newer content")
        self.child_rollout.unlink()

        with self.assertRaises(restore.RestoreError) as raised:
            restore.restore_recovery_archive(
                archive_path=self.packed["archive_path"],
                seven_zip_path=SEVEN_ZIP,
            )

        self.assertEqual(raised.exception.kind, "restore_conflict")
        self.assertFalse(self.child_rollout.exists())
        self.assertEqual(self.root_rollout.read_bytes(), b"conflicting newer content")

    def test_insufficient_space_fails_before_extraction(self):
        self.remove_rollouts()
        disk_usage = shutil._ntuple_diskusage(total=100, used=100, free=0)

        with mock.patch.object(restore.shutil, "disk_usage", return_value=disk_usage):
            with self.assertRaises(restore.RestoreError) as raised:
                restore.restore_recovery_archive(
                    archive_path=self.packed["archive_path"],
                    seven_zip_path=SEVEN_ZIP,
                )

        self.assertEqual(raised.exception.kind, "insufficient_restore_space")
        self.assertFalse(self.root_rollout.exists())

    def test_missing_metadata_row_is_reported_without_sqlite_write(self):
        self.remove_rollouts()
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("DELETE FROM threads WHERE id = 'child'")
            connection.commit()
        database_before = digest(self.db_path)

        result = restore.restore_recovery_archive(
            archive_path=self.packed["archive_path"],
            seven_zip_path=SEVEN_ZIP,
        )

        self.assertEqual(result["missing_metadata_thread_ids"], ["child"])
        self.assertEqual(digest(self.db_path), database_before)
        self.assertFalse(result["sqlite_mutation_performed"])

    def test_corrupt_archive_fails_without_creating_rollouts(self):
        self.remove_rollouts()
        archive_path = Path(self.packed["archive_path"])
        with archive_path.open("ab") as handle:
            handle.write(b"corruption")

        with self.assertRaises(restore.RestoreError):
            restore.restore_recovery_archive(
                archive_path=archive_path,
                seven_zip_path=SEVEN_ZIP,
            )

        self.assertFalse(self.root_rollout.exists())
        self.assertFalse(self.child_rollout.exists())


if __name__ == "__main__":
    unittest.main()
