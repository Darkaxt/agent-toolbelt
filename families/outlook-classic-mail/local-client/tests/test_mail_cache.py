import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from outlook_classic_mail_client import mail_cache


class MailCacheFolderInventoryTests(unittest.TestCase):
    def test_schema_migrates_existing_folder_state_with_folder_entry_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mail_cache.sqlite"
            conn = sqlite3.connect(path)
            try:
                conn.execute(
                    """
                    CREATE TABLE folder_state (
                        store_id TEXT NOT NULL,
                        account TEXT NOT NULL,
                        store TEXT NOT NULL,
                        folder_selector TEXT NOT NULL,
                        folder_path TEXT NOT NULL,
                        high_watermark TEXT,
                        refreshed_at TEXT NOT NULL,
                        message_count INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY(store_id, folder_selector)
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            cache = mail_cache.MailCache(path)
            cache.ensure_schema()
            with cache.connection() as conn:
                columns = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(folder_state)").fetchall()
                }

        self.assertIn("folder_entry_id", columns)

    def test_folder_inventory_can_be_persisted_and_searched(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = mail_cache.MailCache(Path(temp_dir) / "mail_cache.sqlite")
            cache.upsert_folder_identity(
                {
                    "store_id": "store-1",
                    "account": "demo@example.com",
                    "store": "Demo",
                    "folder_selector": "custom:Inbox/Rules/Legitimate Spam",
                    "folder_path": r"\Demo\Inbox\Rules\Legitimate Spam",
                    "folder_entry_id": "folder-spam",
                }
            )

            rows = cache.search_folder_inventory(
                query="legitimate spam",
                account="demo@example.com",
                limit=10,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["folder_entry_id"], "folder-spam")
        self.assertEqual(rows[0]["folder_selector"], "custom:Inbox/Rules/Legitimate Spam")

    def test_folder_message_entry_ids_support_identity_backfill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = mail_cache.MailCache(Path(temp_dir) / "mail_cache.sqlite")
            cache.upsert_message(
                {
                    "account": "demo@example.com",
                    "store": "Demo",
                    "store_id": "store-1",
                    "folder_selector": "custom:Inbox/Projects",
                    "folder_path": r"\Demo\Inbox\Projects",
                    "entry_id": "message-1",
                    "message_date": "2026-08-28T12:00:00",
                }
            )

            entry_ids = cache.folder_message_entry_ids(
                store_id="store-1",
                folder_selector="custom:Inbox/Projects",
                limit=5,
            )

        self.assertEqual(entry_ids, ["message-1"])


if __name__ == "__main__":
    unittest.main()
