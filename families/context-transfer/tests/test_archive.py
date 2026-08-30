from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_SRC = REPO_ROOT / "families" / "context-transfer" / "src"
if str(FAMILY_SRC) not in sys.path:
    sys.path.insert(0, str(FAMILY_SRC))

from agent_toolbelt_context_transfer import archive, context_transfer


TEMP_ROOT = Path(r"D:\Temp")
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
SEVEN_ZIP = shutil.which("7z.exe") or shutil.which("7z")


class ArchiveFixture:
    def __init__(self, root: Path):
        self.codex_home = root / "codex-home"
        self.sessions = self.codex_home / "sessions" / "2026" / "08" / "31"
        self.sessions.mkdir(parents=True)
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
            connection.commit()

    def add_thread(self, thread_id: str, content: bytes, title: str) -> Path:
        path = self.sessions / f"rollout-{thread_id}.jsonl"
        path.write_bytes(content)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, 1, 2, 'app', 'openai', ?, ?, 0)",
                (thread_id, str(path), str(self.sessions), title),
            )
            connection.commit()
        return path

    def add_edge(self, parent: str, child: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT INTO thread_spawn_edges VALUES (?, ?, 'closed')",
                (parent, child),
            )
            connection.commit()


class ArchivePolicyTests(unittest.TestCase):
    def test_compression_arguments_are_maximum_lzma2_solid_without_timeout(self):
        arguments = archive.compression_arguments(768)

        self.assertEqual(
            arguments,
            [
                "-t7z",
                "-mx=9",
                "-m0=lzma2",
                "-md=768m",
                "-mfb=273",
                "-ms=on",
                "-mmt=on",
            ],
        )
        self.assertFalse(any("timeout" in value.casefold() for value in arguments))

    def test_dictionary_selection_uses_largest_safe_supported_candidate(self):
        self.assertEqual(
            archive.select_dictionary_mib(
                total_memory_bytes=64 * 1024**3,
                available_memory_bytes=24 * 1024**3,
            ),
            1024,
        )
        self.assertEqual(
            archive.select_dictionary_mib(
                total_memory_bytes=8 * 1024**3,
                available_memory_bytes=2 * 1024**3,
            ),
            64,
        )


@unittest.skipUnless(SEVEN_ZIP, "7-Zip is required for archive integration tests")
class ArchiveIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.fixture = ArchiveFixture(self.root)
        self.root_rollout = self.fixture.add_thread(
            "root",
            b'{"type":"root"}\n',
            "Apollo installation troubleshooting",
        )
        self.child_rollout = self.fixture.add_thread(
            "child",
            b'{"type":"child"}\n',
            "worker",
        )
        self.fixture.add_edge("root", "child")
        self.archive_root = self.root / "archives"
        self.handoff_path = self.root / "CONTEXT_TRANSFER.md"
        self.handoff_path.write_text("# Continuation\n\nVerified handoff.\n", encoding="utf-8")
        self.inventory = context_transfer.inventory_thread_tree(
            source_thread_id="root",
            destination_thread_id="destination",
            codex_home=self.fixture.codex_home,
            archive_root=self.archive_root,
        )
        self.manifest_path = self.root / "inspection.json"
        self.manifest_path.write_text(json.dumps(self.inventory), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def pack(self) -> dict:
        return archive.pack_recovery(
            inspection_manifest_path=self.manifest_path,
            handoff_path=self.handoff_path,
            archive_root=self.archive_root,
            seven_zip_path=SEVEN_ZIP,
            dictionary_mib=16,
            now=lambda: datetime(2026, 8, 31, 12, 34, 56, tzinfo=timezone.utc),
        )

    def test_pack_builds_verified_transaction_without_large_staging_copy(self):
        result = self.pack()

        transaction_root = Path(result["transaction_root"])
        archive_path = Path(result["archive_path"])
        self.assertTrue(result["ok"])
        self.assertTrue(archive_path.is_file())
        self.assertEqual(archive_path.name, "thread-tree.7z")
        self.assertFalse((transaction_root / "thread-tree.7z.partial").exists())
        self.assertTrue((transaction_root / "manifest.json").is_file())
        self.assertTrue((transaction_root / "CONTEXT_TRANSFER.md").is_file())
        self.assertTrue((transaction_root / "threads.json").is_file())
        self.assertTrue((transaction_root / "spawn-edges.json").is_file())
        self.assertTrue((transaction_root / "verification.json").is_file())
        self.assertFalse((transaction_root / ".payload").exists())
        self.assertFalse((transaction_root / ".verification-staging").exists())

        manifest = json.loads((transaction_root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["rollouts"]), 2)
        self.assertTrue(all(item["archive_path"].startswith("sessions/") for item in manifest["rollouts"]))
        self.assertTrue(all(Path(item["original_path"]).is_absolute() for item in manifest["rollouts"]))
        self.assertEqual(result["compression"]["arguments"], archive.compression_arguments(16))
        self.assertEqual(result["representative_extractions_verified"], 2)

    def test_verify_rechecks_archive_hash_internal_metadata_and_representatives(self):
        packed = self.pack()

        verified = archive.verify_recovery_archive(
            packed["archive_path"],
            seven_zip_path=SEVEN_ZIP,
        )

        self.assertTrue(verified["ok"])
        self.assertTrue(verified["archive_test_passed"])
        self.assertTrue(verified["internal_manifest_matches"])
        self.assertTrue(verified["internal_handoff_matches"])
        self.assertEqual(verified["representative_extractions_verified"], 2)

    def test_changed_source_fails_before_transaction_creation(self):
        self.root_rollout.write_bytes(b"changed")

        with self.assertRaises(archive.ArchiveError) as raised:
            self.pack()

        self.assertEqual(raised.exception.kind, "source_file_changed")
        self.assertFalse(self.archive_root.exists())

    def test_inventory_blocker_prevents_pack(self):
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        payload["retirement_ready"] = False
        payload["blockers"] = ["non_terminal_children"]
        self.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(archive.ArchiveError) as raised:
            self.pack()

        self.assertEqual(raised.exception.kind, "inspection_not_ready")
        self.assertFalse(self.archive_root.exists())

    def test_external_handoff_tamper_is_detected(self):
        packed = self.pack()
        transaction_root = Path(packed["transaction_root"])
        (transaction_root / "CONTEXT_TRANSFER.md").write_text("tampered", encoding="utf-8")

        with self.assertRaises(archive.ArchiveError) as raised:
            archive.verify_recovery_archive(
                packed["archive_path"],
                seven_zip_path=SEVEN_ZIP,
            )

        self.assertEqual(raised.exception.kind, "handoff_hash_mismatch")

    def test_corrupt_archive_is_rejected(self):
        packed = self.pack()
        archive_path = Path(packed["archive_path"])
        with archive_path.open("r+b") as handle:
            handle.seek(0)
            handle.write(b"not-7z!")

        with self.assertRaises(archive.ArchiveError) as raised:
            archive.verify_recovery_archive(archive_path, seven_zip_path=SEVEN_ZIP)

        self.assertIn(raised.exception.kind, {"archive_hash_mismatch", "archive_test_failed"})

    def test_downgraded_compression_evidence_is_rejected(self):
        packed = self.pack()
        verification_path = Path(packed["transaction_root"]) / "verification.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        verification["compression"]["arguments"][1] = "-mx=5"
        verification_path.write_text(json.dumps(verification), encoding="utf-8")

        with self.assertRaises(archive.ArchiveError) as raised:
            archive.verify_recovery_archive(
                packed["archive_path"],
                seven_zip_path=SEVEN_ZIP,
            )

        self.assertEqual(raised.exception.kind, "compression_policy_mismatch")

    def test_missing_metadata_export_is_rejected_as_incomplete(self):
        packed = self.pack()
        transaction_root = Path(packed["transaction_root"])
        (transaction_root / "threads.json").unlink()

        with self.assertRaises(archive.ArchiveError) as raised:
            archive.verify_recovery_archive(
                packed["archive_path"],
                seven_zip_path=SEVEN_ZIP,
            )

        self.assertEqual(raised.exception.kind, "recovery_artifact_missing")


if __name__ == "__main__":
    unittest.main()
