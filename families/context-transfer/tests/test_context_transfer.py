from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_SRC = REPO_ROOT / "families" / "context-transfer" / "src"
if str(FAMILY_SRC) not in sys.path:
    sys.path.insert(0, str(FAMILY_SRC))

from agent_toolbelt_context_transfer import context_transfer


TEMP_ROOT = Path(r"D:\Temp")
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CodexFixture:
    def __init__(self, root: Path):
        self.codex_home = root / "codex-home"
        self.sessions = self.codex_home / "sessions" / "2026" / "08" / "31"
        self.sessions.mkdir(parents=True)
        self.db_path = self.codex_home / "state_5.sqlite"
        self.connection = sqlite3.connect(self.db_path)
        self.connection.executescript(
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
                sandbox_policy TEXT NOT NULL,
                approval_mode TEXT NOT NULL,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                has_user_event INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                archived_at INTEGER,
                git_sha TEXT,
                git_branch TEXT,
                git_origin_url TEXT,
                cli_version TEXT NOT NULL DEFAULT '',
                first_user_message TEXT NOT NULL DEFAULT '',
                agent_nickname TEXT,
                agent_role TEXT,
                name TEXT
            );
            CREATE TABLE thread_spawn_edges (
                parent_thread_id TEXT NOT NULL,
                child_thread_id TEXT PRIMARY KEY,
                status TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def add_thread(
        self,
        thread_id: str,
        content: bytes,
        *,
        rollout_path: Path | None = None,
        archived: bool = False,
        title: str | None = None,
    ) -> Path:
        path = rollout_path or self.sessions / f"rollout-{thread_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.connection.execute(
            """
            INSERT INTO threads (
                id, rollout_path, created_at, updated_at, source, model_provider,
                cwd, title, sandbox_policy, approval_mode, archived, git_sha,
                git_branch, git_origin_url, name
            ) VALUES (?, ?, 1, 2, 'app', 'openai', ?, ?, 'full', 'never', ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                str(path),
                str(path.parent),
                title or thread_id,
                int(archived),
                "a" * 40,
                "main",
                "https://example.invalid/repo.git",
                title,
            ),
        )
        self.connection.commit()
        return path

    def add_edge(self, parent: str, child: str, status: str = "closed") -> None:
        self.connection.execute(
            "INSERT INTO thread_spawn_edges VALUES (?, ?, ?)",
            (parent, child, status),
        )
        self.connection.commit()


class InventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.fixture = CodexFixture(self.root)
        self.archive_root = self.root / "archive-does-not-exist"

    def tearDown(self) -> None:
        self.fixture.close()
        self.temp.cleanup()

    def inventory(self, source: str = "root", destination: str = "destination") -> dict:
        return context_transfer.inventory_thread_tree(
            source_thread_id=source,
            destination_thread_id=destination,
            codex_home=self.fixture.codex_home,
            archive_root=self.archive_root,
        )

    def test_recursively_inventories_complete_closed_tree(self):
        root_path = self.fixture.add_thread("root", b"root-data")
        child_path = self.fixture.add_thread("child", b"child-data")
        grandchild_path = self.fixture.add_thread("grandchild", b"grandchild-data")
        self.fixture.add_edge("root", "child")
        self.fixture.add_edge("child", "grandchild")

        result = self.inventory()

        self.assertEqual(result["source_thread_id"], "root")
        self.assertEqual(result["thread_count"], 3)
        self.assertEqual(result["edge_count"], 2)
        self.assertEqual(result["total_rollout_bytes"], 9 + 10 + 15)
        self.assertEqual([item["thread_id"] for item in result["threads"]], ["root", "child", "grandchild"])
        self.assertEqual([item["depth"] for item in result["threads"]], [0, 1, 2])
        self.assertEqual(result["terminal_status_counts"], {"closed": 2})
        self.assertTrue(result["retirement_ready"])
        self.assertFalse(self.archive_root.exists())
        records = {item["thread_id"]: item for item in result["threads"]}
        self.assertEqual(records["root"]["sha256"], sha256(root_path))
        self.assertEqual(records["child"]["sha256"], sha256(child_path))
        self.assertEqual(records["grandchild"]["sha256"], sha256(grandchild_path))

    def test_inspection_does_not_modify_sqlite_database(self):
        self.fixture.add_thread("root", b"root")
        before = sha256(self.fixture.db_path)

        self.inventory()

        self.assertEqual(sha256(self.fixture.db_path), before)

    def test_rejects_source_equal_to_destination(self):
        self.fixture.add_thread("root", b"root")

        with self.assertRaises(context_transfer.ContextTransferError) as raised:
            self.inventory(source="root", destination="root")

        self.assertEqual(raised.exception.kind, "source_is_destination")

    def test_missing_source_is_structured_failure(self):
        with self.assertRaises(context_transfer.ContextTransferError) as raised:
            self.inventory(source="missing")

        self.assertEqual(raised.exception.kind, "source_thread_not_found")

    def test_active_child_blocks_retirement_but_remains_visible(self):
        self.fixture.add_thread("root", b"root")
        self.fixture.add_thread("child", b"child")
        self.fixture.add_edge("root", "child", status="running")

        result = self.inventory()

        self.assertFalse(result["retirement_ready"])
        self.assertIn("non_terminal_children", result["blockers"])
        self.assertEqual(result["terminal_status_counts"], {"running": 1})

    def test_missing_child_row_blocks_retirement(self):
        self.fixture.add_thread("root", b"root")
        self.fixture.add_edge("root", "missing-child")

        result = self.inventory()

        self.assertFalse(result["retirement_ready"])
        self.assertIn("missing_thread_rows", result["blockers"])
        self.assertEqual(result["missing_thread_ids"], ["missing-child"])

    def test_missing_rollout_blocks_retirement(self):
        path = self.fixture.add_thread("root", b"root")
        path.unlink()

        result = self.inventory()

        self.assertFalse(result["retirement_ready"])
        self.assertIn("missing_rollouts", result["blockers"])
        self.assertEqual(result["threads"][0]["file_state"], "missing")

    def test_rollout_outside_codex_home_is_rejected(self):
        outside = self.root / "outside.jsonl"
        self.fixture.add_thread("root", b"root", rollout_path=outside)

        result = self.inventory()

        self.assertFalse(result["retirement_ready"])
        self.assertIn("unsafe_rollout_paths", result["blockers"])
        self.assertEqual(result["threads"][0]["file_state"], "unsafe_path")

    def test_cycle_is_reported_without_recursing_forever(self):
        self.fixture.add_thread("root", b"root")
        self.fixture.add_thread("child", b"child")
        self.fixture.add_edge("root", "child")
        self.fixture.add_edge("child", "root")

        result = self.inventory()

        self.assertFalse(result["retirement_ready"])
        self.assertIn("spawn_cycle", result["blockers"])
        self.assertEqual(result["cycle_paths"], [["root", "child", "root"]])

    def test_duplicate_rollout_path_blocks_retirement(self):
        shared = self.sessions_path / "shared.jsonl"
        self.fixture.add_thread("root", b"shared", rollout_path=shared)
        self.fixture.add_thread("child", b"shared", rollout_path=shared)
        self.fixture.add_edge("root", "child")

        result = self.inventory()

        self.assertFalse(result["retirement_ready"])
        self.assertIn("duplicate_rollout_paths", result["blockers"])

    @property
    def sessions_path(self) -> Path:
        return self.fixture.sessions

    def test_manifest_is_json_serializable_and_excludes_first_user_message(self):
        self.fixture.add_thread("root", b"root")

        result = self.inventory()
        encoded = json.dumps(result, sort_keys=True)

        self.assertNotIn("first_user_message", encoded)
        self.assertIn("git_branch", result["threads"][0]["metadata"])


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.fixture = CodexFixture(self.root)
        self.fixture.add_thread("root", b"root")
        self.archive_root = self.root / "archive-does-not-exist"

    def tearDown(self) -> None:
        self.fixture.close()
        self.temp.cleanup()

    def run_cli(self, *arguments: str, environment: dict[str, str] | None = None) -> tuple[int, dict]:
        from agent_toolbelt_context_transfer import cli

        output = io.StringIO()
        with mock.patch.dict(os.environ, environment or {}, clear=True), redirect_stdout(output):
            exit_code = cli.main(list(arguments))
        return exit_code, json.loads(output.getvalue())

    def test_inspect_uses_environment_defaults_and_does_not_create_archive_root(self):
        exit_code, payload = self.run_cli(
            "inspect",
            "--source-thread-id",
            "root",
            "--archive-root",
            str(self.archive_root),
            environment={
                "CODEX_HOME": str(self.fixture.codex_home),
                "CODEX_THREAD_ID": "destination",
            },
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "inspect")
        self.assertEqual(payload["result"]["destination_thread_id"], "destination")
        self.assertFalse(self.archive_root.exists())

    def test_inspect_explicit_destination_overrides_environment(self):
        exit_code, payload = self.run_cli(
            "inspect",
            "--source-thread-id",
            "root",
            "--destination-thread-id",
            "explicit-destination",
            "--codex-home",
            str(self.fixture.codex_home),
            "--archive-root",
            str(self.archive_root),
            environment={"CODEX_THREAD_ID": "environment-destination"},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["result"]["destination_thread_id"], "explicit-destination")

    def test_inspect_requires_destination_identity(self):
        exit_code, payload = self.run_cli(
            "inspect",
            "--source-thread-id",
            "root",
            "--codex-home",
            str(self.fixture.codex_home),
            "--archive-root",
            str(self.archive_root),
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["kind"], "destination_thread_required")

    def test_inspect_returns_structured_inventory_error(self):
        exit_code, payload = self.run_cli(
            "inspect",
            "--source-thread-id",
            "missing",
            "--destination-thread-id",
            "destination",
            "--codex-home",
            str(self.fixture.codex_home),
            "--archive-root",
            str(self.archive_root),
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["operation"], "inspect")
        self.assertEqual(payload["error"]["kind"], "source_thread_not_found")
        self.assertFalse(self.archive_root.exists())

    def test_inspect_writes_manifest_only_when_output_is_explicit(self):
        output_path = self.root / "inspection.json"

        exit_code, payload = self.run_cli(
            "inspect",
            "--source-thread-id",
            "root",
            "--destination-thread-id",
            "destination",
            "--codex-home",
            str(self.fixture.codex_home),
            "--archive-root",
            str(self.archive_root),
            "--output",
            str(output_path),
        )

        self.assertEqual(exit_code, 0)
        written = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(written["schema"], "agent_toolbelt_context_transfer.inventory.v1")
        self.assertEqual(payload["output_path"], str(output_path.resolve()))

    def test_pack_cli_forwards_reviewed_inputs(self):
        from agent_toolbelt_context_transfer import cli

        with mock.patch.object(
            cli.archive,
            "pack_recovery",
            return_value={"ok": True, "archive_path": "E:/archive.7z"},
        ) as pack_recovery:
            exit_code, payload = self.run_cli(
                "pack",
                "--manifest",
                "D:/inspection.json",
                "--handoff",
                "D:/CONTEXT_TRANSFER.md",
                "--archive-root",
                "E:/Codex/ThreadArchives",
                "--seven-zip-path",
                "D:/Tools/7z.exe",
                "--dictionary-mib",
                "768",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "pack")
        pack_recovery.assert_called_once_with(
            inspection_manifest_path="D:/inspection.json",
            handoff_path="D:/CONTEXT_TRANSFER.md",
            archive_root="E:/Codex/ThreadArchives",
            seven_zip_path="D:/Tools/7z.exe",
            dictionary_mib=768,
        )

    def test_verify_cli_returns_structured_archive_failure(self):
        from agent_toolbelt_context_transfer import archive, cli

        with mock.patch.object(
            cli.archive,
            "verify_recovery_archive",
            side_effect=archive.ArchiveError("archive_test_failed", "bad archive"),
        ):
            exit_code, payload = self.run_cli(
                "verify",
                "--archive",
                "E:/broken.7z",
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["error"]["kind"], "archive_test_failed")

    def test_catalog_cli_writes_only_explicit_bounded_output(self):
        from agent_toolbelt_context_transfer import cli

        output_path = self.root / "catalog.json"
        with mock.patch.object(
            cli.handoff,
            "build_evidence_catalog",
            return_value={"schema": "catalog", "entry_count": 3},
        ) as build_catalog:
            exit_code, payload = self.run_cli(
                "catalog",
                "--manifest",
                "D:/inspection.json",
                "--max-entries-per-thread",
                "8",
                "--max-total-entries",
                "500",
                "--excerpt-chars",
                "400",
                "--output",
                str(output_path),
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_path.is_file())
        self.assertEqual(payload["output_path"], str(output_path.resolve()))
        build_catalog.assert_called_once_with(
            inspection_manifest_path="D:/inspection.json",
            max_entries_per_thread=8,
            max_total_entries=500,
            excerpt_chars=400,
        )

    def test_validate_handoff_cli_forwards_inputs(self):
        from agent_toolbelt_context_transfer import cli

        with mock.patch.object(
            cli.handoff,
            "validate_handoff",
            return_value={"ok": True, "handoff_sha256": "abc"},
        ) as validate:
            exit_code, payload = self.run_cli(
                "validate-handoff",
                "--manifest",
                "D:/inspection.json",
                "--handoff",
                "D:/CONTEXT_TRANSFER.md",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "validate-handoff")
        validate.assert_called_once_with(
            handoff_path="D:/CONTEXT_TRANSFER.md",
            inspection_manifest_path="D:/inspection.json",
        )

    def test_validate_acceptance_cli_returns_structured_failure(self):
        from agent_toolbelt_context_transfer import cli, handoff

        with mock.patch.object(
            cli.handoff,
            "validate_destination_acceptance",
            side_effect=handoff.HandoffError("acceptance_incomplete", "missing evidence"),
        ):
            exit_code, payload = self.run_cli(
                "validate-acceptance",
                "--manifest",
                "D:/inspection.json",
                "--handoff",
                "D:/CONTEXT_TRANSFER.md",
                "--acceptance",
                "D:/destination-acceptance.json",
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["error"]["kind"], "acceptance_incomplete")

    def test_issue_deletion_ticket_cli_requires_and_forwards_confirmation(self):
        from agent_toolbelt_context_transfer import cli

        with mock.patch.object(
            cli.retirement,
            "issue_deletion_ticket",
            return_value={"ok": True, "ticket_path": "E:/deletion-ticket.json"},
        ) as issue:
            exit_code, payload = self.run_cli(
                "issue-deletion-ticket",
                "--verification",
                "E:/verification.json",
                "--acceptance",
                "E:/destination-acceptance.json",
                "--archived-state",
                "E:/archived-state.json",
                "--confirm-live-retirement",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "issue-deletion-ticket")
        issue.assert_called_once_with(
            verification_path="E:/verification.json",
            acceptance_path="E:/destination-acceptance.json",
            archived_state_path="E:/archived-state.json",
            confirm_live_retirement=True,
        )

    def test_apply_deletion_cli_returns_structured_failure(self):
        from agent_toolbelt_context_transfer import cli, retirement

        with mock.patch.object(
            cli.retirement,
            "apply_deletion_ticket",
            side_effect=retirement.RetirementError("ticket_already_used", "used"),
        ):
            exit_code, payload = self.run_cli(
                "apply-deletion",
                "--ticket",
                "E:/deletion-ticket.json",
                "--ticket-id",
                "a" * 64,
                "--confirm-delete",
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["error"]["kind"], "ticket_already_used")

    def test_module_invocation_executes_cli(self):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, (str(FAMILY_SRC), environment.get("PYTHONPATH")))
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_toolbelt_context_transfer.cli",
                "inspect",
                "--source-thread-id",
                "root",
                "--destination-thread-id",
                "destination",
                "--codex-home",
                str(self.fixture.codex_home),
                "--archive-root",
                str(self.archive_root),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["thread_count"], 1)


if __name__ == "__main__":
    unittest.main()
