import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "codex-thread-recall" / "src"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_codex_thread_recall import cli, thread_recall  # noqa: E402


THREAD_ID = "019-thread-test"


def make_entry(timestamp: str, entry_type: str, payload: dict) -> dict:
    return {"timestamp": timestamp, "type": entry_type, "payload": payload}


def make_codex_home(
    temp_dir: str,
    *,
    thread_id: str = THREAD_ID,
    rollout_entries: list[dict] | None = None,
    malformed_line: str | None = None,
    missing_rollout: bool = False,
) -> tuple[Path, Path]:
    codex_home = Path(temp_dir) / "codex-home"
    codex_home.mkdir(parents=True, exist_ok=True)
    rollout_path = codex_home / "sessions" / "2026" / "04" / "25" / f"rollout-{thread_id}.jsonl"
    rollout_path.parent.mkdir(parents=True, exist_ok=True)

    if not missing_rollout:
        lines = [json.dumps(entry, ensure_ascii=False) for entry in (rollout_entries or [])]
        if malformed_line is not None:
            lines.insert(1, malformed_line)
        rollout_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    conn = sqlite3.connect(codex_home / "state_5.sqlite")
    conn.execute(
        """
        create table threads (
            id text primary key,
            title text,
            cwd text,
            rollout_path text,
            created_at integer,
            updated_at integer
        )
        """
    )
    conn.execute(
        "insert into threads (id, title, cwd, rollout_path, created_at, updated_at) values (?, ?, ?, ?, ?, ?)",
        (
            thread_id,
            "Thread Recall Test",
            r"\\?\D:\Downloads\Public\agent-toolbelt",
            str(rollout_path),
            1777077000,
            1777077300,
        ),
    )
    conn.commit()
    conn.close()
    return codex_home, rollout_path


class ThreadRecallTests(unittest.TestCase):
    def test_status_resolves_current_thread_from_env(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            original_env = dict(os.environ)
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_THREAD_ID"] = THREAD_ID
                payload = thread_recall.status()
            finally:
                os.environ.clear()
                os.environ.update(original_env)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["thread"]["id"], THREAD_ID)
        self.assertEqual(payload["thread"]["rollout_path"], str(rollout_path))

    def test_thread_override_is_used_when_provided(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, thread_id="override-thread", rollout_entries=entries)
            original_env = dict(os.environ)
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                payload = thread_recall.status(thread_id="override-thread")
            finally:
                os.environ.clear()
                os.environ.update(original_env)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["thread"]["id"], "override-thread")

    def test_missing_thread_env_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir)
            original_env = dict(os.environ)
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ.pop("CODEX_THREAD_ID", None)
                payload = thread_recall.status()
            finally:
                os.environ.clear()
                os.environ.update(original_env)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "thread_unavailable")

    def test_missing_rollout_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, missing_rollout=True)
            original_env = dict(os.environ)
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_THREAD_ID"] = THREAD_ID
                payload = thread_recall.recall()
            finally:
                os.environ.clear()
                os.environ.update(original_env)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "rollout_missing")

    def test_recall_extracts_decisions_commands_paths_blockers_and_evidence(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Please implement codex-thread-recall."}),
            make_entry(
                "2026-04-25T08:01:00Z",
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Decision: use CODEX_THREAD_ID and fail closed if exact resolution fails."}
                    ],
                },
            ),
            make_entry(
                "2026-04-25T08:02:00Z",
                "response_item",
                {
                    "type": "function_call",
                    "name": "shell_command",
                    "arguments": json.dumps({"command": "git -C D:\\Downloads\\Public\\agent-toolbelt status --short --branch"}),
                },
            ),
            make_entry(
                "2026-04-25T08:03:00Z",
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": json.dumps(
                        {
                            "stdout": "M families/codex-thread-recall/src/agent_toolbelt_codex_thread_recall/thread_recall.py",
                            "stderr": "[Errno 13] Permission denied",
                        }
                    ),
                },
            ),
            make_entry(
                "2026-04-25T08:04:00Z",
                "event_msg",
                {
                    "type": "agent_message",
                    "text": "Touched D:\\Downloads\\Public\\agent-toolbelt\\families\\codex-thread-recall\\src\\agent_toolbelt_codex_thread_recall\\thread_recall.py and keep unrelated existing repo changes untouched. Open question: should this stay Codex-only?",
                },
            ),
            make_entry("2026-04-25T08:05:00Z", "compacted", {"type": "context_compacted"}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            original_env = dict(os.environ)
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_THREAD_ID"] = THREAD_ID
                payload = thread_recall.recall()
            finally:
                os.environ.clear()
                os.environ.update(original_env)

        self.assertTrue(payload["ok"])
        recall = payload["recall"]
        self.assertIn("CODEX_THREAD_ID", recall["summary"])
        self.assertTrue(any("fail closed" in item.lower() for item in recall["decisions"]))
        self.assertTrue(any("git -C D:\\Downloads\\Public\\agent-toolbelt status --short --branch" in item for item in recall["commands"]))
        self.assertIn(
            r"D:\Downloads\Public\agent-toolbelt\families\codex-thread-recall\src\agent_toolbelt_codex_thread_recall\thread_recall.py",
            recall["touched_paths"],
        )
        self.assertTrue(any("Permission denied" in item for item in recall["blockers"]))
        self.assertTrue(any("should this stay Codex-only" in item for item in recall["open_questions"]))
        self.assertGreaterEqual(len(recall["evidence"]), 3)
        self.assertTrue(any(item["entry_type"] == "compacted" for item in recall["evidence"]))

    def test_grep_returns_bounded_evidence(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Use CODEX_THREAD_ID first."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "CODEX_THREAD_ID is present in this shell."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": "No heuristic fallback in v1."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            original_env = dict(os.environ)
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_THREAD_ID"] = THREAD_ID
                payload = thread_recall.grep_rollout(pattern="CODEX_THREAD_ID", limit=1)
            finally:
                os.environ.clear()
                os.environ.update(original_env)

        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["results"]), 1)
        self.assertIn("CODEX_THREAD_ID", payload["results"][0]["excerpt"])

    def test_recall_skips_malformed_jsonl_with_warning(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries, malformed_line="{not-json")
            original_env = dict(os.environ)
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_THREAD_ID"] = THREAD_ID
                payload = thread_recall.recall()
            finally:
                os.environ.clear()
                os.environ.update(original_env)

        self.assertTrue(payload["ok"])
        self.assertTrue(any("malformed JSONL" in warning for warning in payload["warnings"]))


class ThreadRecallCliTests(unittest.TestCase):
    def test_status_cli_prints_json(self):
        original_status = cli.thread_recall.status
        cli.thread_recall.status = lambda **kwargs: {"ok": True, "thread": {"id": "demo"}, "warnings": []}
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["status"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.status = original_status

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["thread"]["id"], "demo")

    def test_grep_cli_passes_pattern(self):
        original_grep = cli.thread_recall.grep_rollout
        cli.thread_recall.grep_rollout = lambda **kwargs: {
            "ok": True,
            "pattern": kwargs["pattern"],
            "results": [],
            "warnings": [],
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["grep", "--pattern", "fail closed"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.grep_rollout = original_grep

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["pattern"], "fail closed")

    def test_recall_cli_escapes_unicode_for_windows_console_safety(self):
        original_recall = cli.thread_recall.recall
        cli.thread_recall.recall = lambda **kwargs: {
            "ok": True,
            "thread": {"id": "demo"},
            "recall": {"summary": "【unicode evidence】"},
            "warnings": [],
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["recall"])
                rendered = buffer.getvalue()
        finally:
            cli.thread_recall.recall = original_recall

        self.assertEqual(exit_code, 0)
        self.assertIn("\\u3010unicode evidence\\u3011", rendered)


if __name__ == "__main__":
    unittest.main()
