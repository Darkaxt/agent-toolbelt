import io
import importlib.util
import json
import os
import runpy
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "codex-thread-recall" / "src"
SKILL_SCRIPTS = REPO_ROOT / "families" / "codex-thread-recall" / "codex" / "skills" / "codex-thread-recall" / "scripts"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_codex_thread_recall import cli, thread_recall  # noqa: E402


THREAD_ID = "019-thread-test"


def make_entry(timestamp: str, entry_type: str, payload: dict) -> dict:
    return {"timestamp": timestamp, "type": entry_type, "payload": payload}


def load_skill_script_module(name: str):
    script_path = SKILL_SCRIPTS / name
    if not script_path.is_file():
        raise AssertionError(f"Missing skill script: {script_path}")
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load skill script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_repo_bundle(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[tool.uv.workspace]\nmembers=[]\n", encoding="utf-8")
    for relative in (
        Path("packages") / "core" / "src",
        Path("families") / "codex-thread-recall" / "src",
        Path("families") / "codex-thread-recall" / "codex" / "skills" / "codex-thread-recall" / "scripts",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    return root / "families" / "codex-thread-recall" / "codex" / "skills" / "codex-thread-recall" / "scripts" / "invoke_codex_thread_recall.py"


def make_runtime_python(codex_home: Path) -> Path:
    runtime_python = codex_home / "tools" / "codex-thread-recall" / ".venv" / "Scripts" / "python.exe"
    runtime_python.parent.mkdir(parents=True, exist_ok=True)
    runtime_python.write_text("", encoding="utf-8")
    return runtime_python


def make_active_runtime(codex_home: Path, *, release_name: str = "20260425-000000Z") -> tuple[Path, Path, Path]:
    release_root = codex_home / "tools" / "codex-thread-recall" / "releases" / release_name
    runtime_python = release_root / ".venv" / "Scripts" / "python.exe"
    runtime_python.parent.mkdir(parents=True, exist_ok=True)
    runtime_python.write_text("", encoding="utf-8")
    active_manifest = codex_home / "tools" / "codex-thread-recall" / "active.json"
    active_manifest.parent.mkdir(parents=True, exist_ok=True)
    active_manifest.write_text(
        json.dumps(
            {
                "family": "codex-thread-recall",
                "release_root": str(release_root),
                "python": str(runtime_python),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return release_root, runtime_python, active_manifest


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
            r"\\?\D:\Workspace\Projects\recall-sandbox",
            str(rollout_path),
            1777077000,
            1777077300,
        ),
    )
    conn.commit()
    conn.close()
    return codex_home, rollout_path


class ThreadRecallTests(unittest.TestCase):
    def with_env(self, codex_home: Path, *, thread_id: str = THREAD_ID):
        class _Env:
            def __enter__(inner_self):
                inner_self.original_env = dict(os.environ)
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_THREAD_ID"] = thread_id
                return inner_self

            def __exit__(inner_self, exc_type, exc, tb):
                os.environ.clear()
                os.environ.update(inner_self.original_env)
                return False

        return _Env()

    def test_status_resolves_current_thread_from_env(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.status()

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
            with self.with_env(codex_home):
                payload = thread_recall.recall()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "rollout_missing")

    def test_recall_extracts_decisions_commands_paths_blockers_and_evidence(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Please implement the thread recall helper."}),
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
                    "arguments": json.dumps({"command": "git -C D:\\Workspace\\Projects\\toolbelt status --short --branch"}),
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
                            "stdout": "M src/recall/thread_recall.py",
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
                    "text": "Touched D:\\Workspace\\Projects\\toolbelt\\src\\recall\\thread_recall.py and keep unrelated existing repo changes untouched. Open question: should this stay Codex-only?",
                },
            ),
            make_entry("2026-04-25T08:05:00Z", "compacted", {"type": "context_compacted"}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.recall()

        self.assertTrue(payload["ok"])
        recall = payload["recall"]
        self.assertIn("CODEX_THREAD_ID", recall["summary"])
        self.assertTrue(any("fail closed" in item.lower() for item in recall["decisions"]))
        self.assertTrue(any("git -C D:\\Workspace\\Projects\\toolbelt status --short --branch" in item for item in recall["commands"]))
        self.assertIn(
            r"D:\Workspace\Projects\toolbelt\src\recall\thread_recall.py",
            recall["touched_paths"],
        )
        self.assertTrue(any("Permission denied" in item for item in recall["blockers"]))
        self.assertTrue(any("should this stay Codex-only" in item for item in recall["open_questions"]))
        self.assertGreaterEqual(len(recall["evidence"]), 3)
        self.assertTrue(any(item["entry_type"] == "compacted" for item in recall["evidence"]))
        self.assertTrue(payload["index"]["used"])

    def test_recall_builds_and_reuses_index_then_rebuilds_when_rollout_changes(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Plan the timeline helper."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: fail closed."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = thread_recall.recall()
                second = thread_recall.recall()
                more_entries = entries + [
                    make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": "Published `codex-thread-recall`."})
                ]
                rollout_path.write_text(
                    "\n".join(json.dumps(entry, ensure_ascii=False) for entry in more_entries) + "\n",
                    encoding="utf-8",
                )
                third = thread_recall.recall()

        self.assertTrue(first["index"]["built"])
        self.assertFalse(first["index"]["stale"])
        self.assertFalse(second["index"]["built"])
        self.assertFalse(second["index"]["stale"])
        self.assertTrue(third["index"]["built"])
        self.assertTrue(third["index"]["stale"])
        self.assertGreater(third["index"]["entry_count"], second["index"]["entry_count"])

    def test_cache_schema_tracks_append_state_and_normalized_facet_tables(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt` with PR `#11`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.recall(profile="shipping")

            self.assertTrue(payload["ok"])
            cache_db = codex_home / "cache" / "codex-thread-recall" / "index.sqlite"
            conn = sqlite3.connect(cache_db)
            try:
                rollout_columns = {
                    row[1] for row in conn.execute("pragma table_info(rollout_indexes)").fetchall()
                }
                table_names = {
                    row[0] for row in conn.execute("select name from sqlite_master where type = 'table'").fetchall()
                }
            finally:
                conn.close()

        self.assertTrue({"schema_version", "last_indexed_offset", "last_indexed_line", "last_indexed_entry"}.issubset(rollout_columns))
        self.assertTrue(
            {
                "entry_paths",
                "entry_blockers",
                "entry_retry_signals",
                "entry_questions",
                "entry_entities",
                "entry_repos",
                "entry_pr_numbers",
                "entry_commit_oids",
                "entry_qualified_ids",
                "entry_event_kinds",
            }.issubset(table_names)
        )

    def test_append_only_indexes_new_complete_lines_and_ignores_partial_line(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Start thread recall."}),
        ]
        appended_entry = make_entry(
            "2026-04-25T08:01:00Z",
            "event_msg",
            {"type": "agent_message", "text": "Published `artifact-alpha`."},
        )
        pending_entry = make_entry(
            "2026-04-25T08:02:00Z",
            "event_msg",
            {"type": "agent_message", "text": "Merged PR `#12` for `artifact-alpha`."},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = thread_recall.recall()
                with rollout_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(appended_entry, ensure_ascii=False) + "\n")
                    handle.write(json.dumps(pending_entry, ensure_ascii=False))
                second = thread_recall.recall(profile="shipping")
                with rollout_path.open("a", encoding="utf-8") as handle:
                    handle.write("\n")
                third = thread_recall.recall(profile="shipping")

        self.assertTrue(first["index"]["built"])
        self.assertEqual(first["index"]["appended_entries"], 0)
        self.assertTrue(second["index"]["built"])
        self.assertTrue(second["index"]["stale"])
        self.assertEqual(second["index"]["entry_count"], 2)
        self.assertEqual(second["index"]["appended_entries"], 1)
        self.assertIn("artifact-alpha", second["recall"]["shipped_entities"])
        self.assertEqual(third["index"]["entry_count"], 3)
        self.assertEqual(third["index"]["appended_entries"], 1)
        self.assertIn(12, third["recall"]["pr_numbers"])

    def test_rollout_truncation_forces_full_rebuild(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Start thread recall."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha`."}),
        ]
        replacement_entries = [
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "agent_message", "text": "Reset to `artifact-beta` only."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = thread_recall.recall(profile="shipping")
                rollout_path.write_text(
                    "\n".join(json.dumps(entry, ensure_ascii=False) for entry in replacement_entries) + "\n",
                    encoding="utf-8",
                )
                second = thread_recall.recall(profile="shipping")

        self.assertTrue(first["ok"])
        self.assertTrue(second["index"]["built"])
        self.assertTrue(second["index"]["stale"])
        self.assertEqual(second["index"]["entry_count"], 1)
        self.assertEqual(second["index"]["appended_entries"], 0)
        self.assertIn("artifact-beta", second["recall"]["known_facts"][0])

    def test_inconsistent_thread_cache_rebuilds_cleanly(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Start thread recall."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = thread_recall.recall(profile="shipping")
                cache_db = codex_home / "cache" / "codex-thread-recall" / "index.sqlite"
                conn = sqlite3.connect(cache_db)
                try:
                    conn.execute("delete from rollout_indexes where thread_id = ?", (THREAD_ID,))
                    conn.commit()
                finally:
                    conn.close()
                second = thread_recall.recall(profile="shipping")

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["index"]["built"])
        self.assertTrue(second["index"]["stale"])
        self.assertEqual(second["index"]["last_rebuild_reason"], "orphaned-thread-cache")

    def test_mtime_only_drift_does_not_trigger_rebuild(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Start thread recall."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = thread_recall.recall()
                stat = rollout_path.stat()
                os.utime(rollout_path, ns=(stat.st_atime_ns + 10_000, stat.st_mtime_ns + 10_000))
                second = thread_recall.recall()

        self.assertTrue(first["index"]["built"])
        self.assertFalse(second["index"]["built"])
        self.assertFalse(second["index"]["stale"])
        self.assertEqual(second["index"]["entry_count"], first["index"]["entry_count"])

    def test_status_includes_runtime_and_cache_diagnostics(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["runtime"]["mode"], "direct")
        self.assertEqual(payload["cache"]["schema_version"], thread_recall.CACHE_SCHEMA_VERSION)
        self.assertIn("index.sqlite", payload["cache"]["path"])
        self.assertIn(payload["cache"]["lock_state"]["state"], {"unlocked", "not-needed", "acquired"})

    def test_live_index_lock_waits_briefly_then_succeeds(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            lock_path = thread_recall.thread_lock_path(codex_home, THREAD_ID)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(
                    {
                        "thread_id": THREAD_ID,
                        "rollout_path": "rollout.jsonl",
                        "pid": os.getpid(),
                        "started_at": datetime.now(tz=thread_recall.UTC).isoformat(),
                    }
                ),
                encoding="utf-8",
            )

            original_wait = thread_recall.INDEX_LOCK_WAIT_SECONDS
            original_poll = thread_recall.INDEX_LOCK_POLL_SECONDS
            original_sleep = thread_recall.time.sleep
            try:
                thread_recall.INDEX_LOCK_WAIT_SECONDS = 1.0
                thread_recall.INDEX_LOCK_POLL_SECONDS = 0.05
                cleared = {"done": False}

                def fake_sleep(_seconds: float) -> None:
                    if not cleared["done"]:
                        cleared["done"] = True
                        lock_path.unlink(missing_ok=True)

                thread_recall.time.sleep = fake_sleep
                with self.with_env(codex_home):
                    payload = thread_recall.recall()
            finally:
                thread_recall.INDEX_LOCK_WAIT_SECONDS = original_wait
                thread_recall.INDEX_LOCK_POLL_SECONDS = original_poll
                thread_recall.time.sleep = original_sleep

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["index"]["lock_state"]["state"], "waited")

    def test_stale_index_lock_is_reclaimed(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            lock_path = thread_recall.thread_lock_path(codex_home, THREAD_ID)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(
                    {
                        "thread_id": THREAD_ID,
                        "rollout_path": "rollout.jsonl",
                        "pid": 999999,
                        "started_at": "2026-04-24T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            with self.with_env(codex_home):
                payload = thread_recall.recall()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["index"]["lock_state"]["state"], "reclaimed-stale")

    def test_live_index_lock_times_out_with_structured_busy_failure(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            lock_path = thread_recall.thread_lock_path(codex_home, THREAD_ID)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(
                    {
                        "thread_id": THREAD_ID,
                        "rollout_path": "rollout.jsonl",
                        "pid": os.getpid(),
                        "started_at": datetime.now(tz=thread_recall.UTC).isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            original_wait = thread_recall.INDEX_LOCK_WAIT_SECONDS
            original_poll = thread_recall.INDEX_LOCK_POLL_SECONDS
            original_sleep = thread_recall.time.sleep
            original_monotonic = thread_recall.time.monotonic
            try:
                thread_recall.INDEX_LOCK_WAIT_SECONDS = 0.15
                thread_recall.INDEX_LOCK_POLL_SECONDS = 0.05
                ticks = iter([0.0, 0.1, 0.2, 0.3])
                thread_recall.time.monotonic = lambda: next(ticks)
                thread_recall.time.sleep = lambda _seconds: None
                with self.with_env(codex_home):
                    payload = thread_recall.recall()
            finally:
                thread_recall.INDEX_LOCK_WAIT_SECONDS = original_wait
                thread_recall.INDEX_LOCK_POLL_SECONDS = original_poll
                thread_recall.time.sleep = original_sleep
                thread_recall.time.monotonic = original_monotonic

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "index_busy")
        self.assertEqual(payload["cache"]["lock_state"]["state"], "busy")

    def test_timeline_groups_ship_events_by_entity_and_tracks_revisits_without_repo_specific_heuristics(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Please ship `artifact-alpha`."}),
            make_entry(
                "2026-04-25T08:05:00Z",
                "event_msg",
                {
                    "type": "agent_message",
                    "text": r"Working in D:\Work\Projects\artifact-alpha\README.md and repo `example/toolbelt`.",
                },
            ),
            make_entry(
                "2026-04-25T08:10:00Z",
                "event_msg",
                {
                    "type": "agent_message",
                    "text": "Published and installed. PR `#11` was merged with commit `ed7982b`. Enabled `artifact-alpha@example-market`.",
                },
            ),
            make_entry(
                "2026-04-25T09:00:00Z",
                "event_msg",
                {"type": "agent_message", "text": "Follow-up fix merged as PR `#12` for `artifact-alpha` in `example/toolbelt`."},
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.timeline(kind="shipped", group="entity", limit=10)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["group"], "entity")
        self.assertEqual(len(payload["timeline"]), 1)
        item = payload["timeline"][0]
        self.assertEqual(item["entity"], "artifact-alpha")
        self.assertEqual(item["first_seen_at"], "2026-04-25T08:00:00Z")
        self.assertEqual(item["first_ship_at"], "2026-04-25T08:10:00Z")
        self.assertEqual(item["last_ship_at"], "2026-04-25T09:00:00Z")
        self.assertEqual(item["elapsed_to_first_ship_seconds"], 600)
        self.assertEqual(item["elapsed_to_last_ship_seconds"], 3600)
        self.assertEqual(item["revisit_count"], 1)
        self.assertIn("example/toolbelt", item["repos"])
        self.assertIn(11, item["pr_numbers"])
        self.assertIn(12, item["pr_numbers"])
        self.assertIn("ed7982b", item["commit_oids"])
        self.assertIn("artifact-alpha@example-market", item["qualified_ids"])
        self.assertEqual(len(item["ship_events"]), 3)

    def test_timeline_ignores_email_addresses_as_entities(self):
        entries = [
            make_entry(
                "2026-04-25T08:10:00Z",
                "event_msg",
                {
                    "type": "agent_message",
                    "text": "Published after confirming with michael@example.com and `artifact-beta`.",
                },
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.timeline(kind="published", group="entity", limit=10)

        self.assertTrue(payload["ok"])
        self.assertEqual([item["entity"] for item in payload["timeline"]], ["artifact-beta"])

    def test_timeline_none_returns_flat_events(self):
        entries = [
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-theta`."}),
            make_entry("2026-04-25T08:15:00Z", "event_msg", {"type": "agent_message", "text": "Merged PR `#14` for `artifact-theta`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.timeline(kind="all", group="none", limit=10)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["group"], "none")
        self.assertEqual([event["kind"] for event in payload["timeline"]], ["published", "merged"])

    def test_recall_shipping_profile_surfaces_ship_context_and_filters_noise(self):
        noisy_blob = "<skills_instructions> " + ("x " * 2000)
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-gamma` and `artifact-delta`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Published and installed `artifact-gamma`. PR `#11` merged in `example/toolbelt`."}),
            make_entry("2026-04-25T08:06:00Z", "event_msg", {"type": "agent_message", "text": "PR `#12` merged as a follow-up fix for `artifact-gamma`."}),
            make_entry("2026-04-25T08:07:00Z", "response_item", {"type": "message", "role": "developer", "content": [{"type": "output_text", "text": noisy_blob}]}),
            make_entry("2026-04-25T08:08:00Z", "response_item", {"type": "function_call_output", "output": json.dumps({"stdout": noisy_blob, "stderr": ""})}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.recall(profile="shipping", evidence_limit=10)

        self.assertTrue(payload["ok"])
        self.assertGreater(payload["index"]["noise_filtered_count"], 0)
        recall = payload["recall"]
        self.assertEqual(recall["profile"], "shipping")
        self.assertIn("artifact-gamma", recall["shipped_entities"])
        self.assertIn("example/toolbelt", recall["repos_touched"])
        self.assertIn(11, recall["pr_numbers"])
        self.assertIn(12, recall["pr_numbers"])
        self.assertTrue(any("follow-up" in item.lower() for item in recall["follow_up_fixes"]))
        self.assertFalse(any("<skills_instructions>" in item.get("excerpt", "") for item in recall["evidence"]))

    def test_recall_debug_profile_prioritizes_failures_and_retries(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "response_item", {"type": "function_call", "arguments": json.dumps({"command": "uv run test-suite"})}),
            make_entry("2026-04-25T08:01:00Z", "response_item", {"type": "function_call_output", "output": json.dumps({"stdout": "", "stderr": "Permission denied"})}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": "Retrying with a narrower command after timeout."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.recall(profile="debug")

        self.assertTrue(payload["ok"])
        recall = payload["recall"]
        self.assertEqual(recall["profile"], "debug")
        self.assertTrue(any("Permission denied" in item for item in recall["failure_events"]))
        self.assertTrue(any("Retrying" in item for item in recall["retry_signals"]))
        self.assertTrue(any("uv run test-suite" in item for item in recall["commands"]))

    def test_grep_returns_bounded_evidence_and_matched_facets(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Use CODEX_THREAD_ID first."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "CODEX_THREAD_ID is present in this shell for `artifact-epsilon`."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": "No heuristic fallback in v1."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(pattern="CODEX_THREAD_ID", limit=1)

        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["results"]), 1)
        self.assertIn("CODEX_THREAD_ID", payload["results"][0]["excerpt"])
        self.assertIn("artifact-epsilon", payload["results"][0]["matched_facets"]["entities"])

    def test_grep_structured_filters_and_include_noise_toggle(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "PLEASE IMPLEMENT THIS PLAN: ship `artifact-zeta`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-zeta` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:02:00Z", "response_item", {"type": "function_call_output", "output": json.dumps({"stdout": "<skills_instructions> PLEASE IMPLEMENT THIS PLAN", "stderr": ""})}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                filtered = thread_recall.grep_rollout(
                    pattern="artifact-zeta",
                    role="assistant",
                    entry_type="event_msg",
                    after="2026-04-25T08:00:30Z",
                    before="2026-04-25T08:01:30Z",
                    limit=10,
                )
                no_noise = thread_recall.grep_rollout(pattern="PLEASE IMPLEMENT THIS PLAN", limit=10)
                with_noise = thread_recall.grep_rollout(pattern="PLEASE IMPLEMENT THIS PLAN", include_noise=True, limit=10)

        self.assertTrue(filtered["ok"])
        self.assertEqual(len(filtered["results"]), 1)
        self.assertEqual(filtered["results"][0]["role"], "assistant")
        self.assertEqual(filtered["results"][0]["entry_type"], "event_msg")
        self.assertEqual(len(no_noise["results"]), 0)
        self.assertGreater(len(with_noise["results"]), 0)

    def test_recall_skips_malformed_jsonl_with_warning(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries, malformed_line="{not-json")
            with self.with_env(codex_home):
                payload = thread_recall.recall()

        self.assertTrue(payload["ok"])
        self.assertTrue(any("malformed JSONL" in warning for warning in payload["warnings"]))

    def test_compacted_entries_are_indexed_as_markers_without_replaying_replacement_history(self):
        compacted = thread_recall.normalize_entry(
            {
                "timestamp": "2026-04-25T08:05:00Z",
                "type": "compacted",
                "payload": {
                    "message": "",
                    "replacement_history": [
                        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Published `artifact-lambda`."}]}
                    ],
                },
            },
            7,
            42,
        )

        self.assertEqual(compacted["raw_text"], "Context compacted.")
        self.assertEqual(compacted["excerpt"], "Context compacted.")
        self.assertEqual(compacted["noise_reason"], "compaction-marker")
        self.assertEqual(compacted["entities"], [])
        self.assertEqual(compacted["event_kinds"], [])

    def test_oversized_entries_use_bounded_storage_but_keep_tail_blockers(self):
        huge_output = ("alpha " * 2000) + "Permission denied"
        oversized = thread_recall.normalize_entry(
            {
                "timestamp": "2026-04-25T08:06:00Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": json.dumps({"stdout": huge_output, "stderr": ""}),
                },
            },
            8,
            43,
        )

        self.assertTrue(any("Permission denied" in item for item in oversized["blockers"]))

    def test_oversized_noise_entries_use_bounded_storage(self):
        huge_output = ("alpha " * 4000) + "artifact-omega"
        oversized = thread_recall.normalize_entry(
            {
                "timestamp": "2026-04-25T08:07:00Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": json.dumps({"stdout": huge_output, "stderr": ""}),
                },
            },
            9,
            44,
        )

        self.assertTrue(oversized["is_noise"])
        self.assertEqual(oversized["noise_reason"], "oversized-output")
        self.assertLess(len(oversized["raw_text"]), len(huge_output))


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

    def test_grep_cli_passes_filters(self):
        original_grep = cli.thread_recall.grep_rollout
        cli.thread_recall.grep_rollout = lambda **kwargs: {
            "ok": True,
            "pattern": kwargs["pattern"],
            "results": [],
            "warnings": [],
            "role": kwargs.get("role"),
            "include_noise": kwargs.get("include_noise"),
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["grep", "--pattern", "fail closed", "--role", "assistant", "--include-noise"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.grep_rollout = original_grep

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["pattern"], "fail closed")
        self.assertEqual(payload["role"], "assistant")
        self.assertTrue(payload["include_noise"])

    def test_timeline_cli_passes_kind_and_group(self):
        original_timeline = cli.thread_recall.timeline
        cli.thread_recall.timeline = lambda **kwargs: {
            "ok": True,
            "kind": kwargs["kind"],
            "group": kwargs["group"],
            "timeline": [],
            "warnings": [],
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["timeline", "--kind", "shipped", "--group", "entity"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.timeline = original_timeline

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["kind"], "shipped")
        self.assertEqual(payload["group"], "entity")

    def test_recall_cli_accepts_profile_and_escapes_unicode_for_windows_console_safety(self):
        original_recall = cli.thread_recall.recall
        cli.thread_recall.recall = lambda **kwargs: {
            "ok": True,
            "thread": {"id": "demo"},
            "recall": {"profile": kwargs["profile"], "summary": "【unicode evidence】"},
            "warnings": [],
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["recall", "--profile", "shipping"])
                rendered = buffer.getvalue()
                payload = json.loads(rendered)
        finally:
            cli.thread_recall.recall = original_recall

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["recall"]["profile"], "shipping")
        self.assertIn("\\u3010unicode evidence\\u3011", rendered)

    def test_cli_module_runs_when_invoked_with_python_m(self):
        original_status = cli.thread_recall.status
        original_cli_module = sys.modules.pop("agent_toolbelt_codex_thread_recall.cli", None)
        cli.thread_recall.status = lambda **kwargs: {"ok": True, "thread": {"id": "demo"}, "warnings": []}
        original_argv = list(sys.argv)
        try:
            sys.argv = ["agent_toolbelt_codex_thread_recall.cli", "status"]
            with io.StringIO() as buffer, redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_module("agent_toolbelt_codex_thread_recall.cli", run_name="__main__")
                rendered = buffer.getvalue()
        finally:
            sys.argv = original_argv
            cli.thread_recall.status = original_status
            if original_cli_module is not None:
                sys.modules["agent_toolbelt_codex_thread_recall.cli"] = original_cli_module

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn('"id": "demo"', rendered)


class ThreadRecallRuntimeTests(unittest.TestCase):
    def test_runtime_bootstrap_prefers_agent_toolbelt_home_override_over_installed_runtime(self):
        module = load_skill_script_module("runtime_bootstrap.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo_root = temp_root / "dev-repo"
            script_path = make_repo_bundle(repo_root)
            codex_home = temp_root / "codex-home"
            make_active_runtime(codex_home)

            target = module.resolve_execution_target(
                script_path=script_path,
                env={
                    "AGENT_TOOLBELT_HOME": str(repo_root),
                    "CODEX_HOME": str(codex_home),
                },
            )

        self.assertEqual(target["mode"], "repo")
        self.assertEqual(Path(target["repo_root"]), repo_root.resolve())

    def test_runtime_bootstrap_uses_repo_relative_bundle_when_present(self):
        module = load_skill_script_module("runtime_bootstrap.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo-bundle"
            script_path = make_repo_bundle(repo_root)

            target = module.resolve_execution_target(script_path=script_path, env={})

        self.assertEqual(target["mode"], "repo")
        self.assertEqual(Path(target["repo_root"]), repo_root.resolve())

    def test_runtime_bootstrap_uses_active_release_by_default(self):
        module = load_skill_script_module("runtime_bootstrap.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            codex_home = temp_root / "codex-home"
            release_root, runtime_python, active_manifest = make_active_runtime(codex_home)
            script_path = temp_root / "installed-skill" / "scripts" / "invoke_codex_thread_recall.py"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("", encoding="utf-8")

            target = module.resolve_execution_target(
                script_path=script_path,
                env={"CODEX_HOME": str(codex_home)},
            )

        self.assertEqual(target["mode"], "runtime")
        self.assertEqual(Path(target["runtime_python"]), runtime_python.resolve())
        self.assertEqual(Path(target["release_root"]), release_root.resolve())
        self.assertEqual(Path(target["active_manifest"]), active_manifest.resolve())

    def test_runtime_bootstrap_falls_back_to_legacy_runtime_when_active_manifest_is_absent(self):
        module = load_skill_script_module("runtime_bootstrap.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            codex_home = temp_root / "codex-home"
            runtime_python = make_runtime_python(codex_home)
            script_path = temp_root / "installed-skill" / "scripts" / "invoke_codex_thread_recall.py"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("", encoding="utf-8")

            target = module.resolve_execution_target(
                script_path=script_path,
                env={"CODEX_HOME": str(codex_home)},
            )

        self.assertEqual(target["mode"], "runtime")
        self.assertEqual(Path(target["runtime_python"]), runtime_python.resolve())
        self.assertTrue(target["legacy_runtime"])

    def test_runtime_bootstrap_fails_closed_when_no_runtime_or_repo_exists(self):
        module = load_skill_script_module("runtime_bootstrap.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            codex_home = temp_root / "codex-home"
            script_path = temp_root / "installed-skill" / "scripts" / "invoke_codex_thread_recall.py"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("", encoding="utf-8")

            with self.assertRaises(RuntimeError) as ctx:
                module.resolve_execution_target(
                    script_path=script_path,
                    env={"CODEX_HOME": str(codex_home)},
                )

        self.assertIn("AGENT_TOOLBELT_HOME", str(ctx.exception))
        self.assertIn("releases", str(ctx.exception))

    def test_runtime_installer_plans_staged_release_commands(self):
        module = load_skill_script_module("install_codex_thread_recall_runtime.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo_root = temp_root / "repo"
            make_repo_bundle(repo_root)
            release_root = temp_root / "codex-home" / "tools" / "codex-thread-recall" / "releases" / "release-1"
            commands = module.build_install_commands(
                repo_root=repo_root,
                release_root=release_root,
                python_executable=Path("C:/Python312/python.exe"),
            )

        flattened = [" ".join(str(part) for part in command) for command in commands]
        self.assertTrue(any(" -m venv " in f" {command} " for command in flattened))
        self.assertTrue(any("agent-toolbelt-core" in command for command in flattened))
        self.assertTrue(any("agent-toolbelt-codex-thread-recall" in command for command in flattened))
        self.assertTrue(any("--no-cache-dir" in command for command in flattened))
        self.assertTrue(any(str(release_root / ".venv") in command for command in flattened))

    def test_runtime_installer_only_flips_active_manifest_after_validation(self):
        module = load_skill_script_module("install_codex_thread_recall_runtime.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo_root = temp_root / "repo"
            make_repo_bundle(repo_root)
            codex_home = temp_root / "codex-home"
            observed: dict[str, Any] = {"commands": []}

            def runner(command, env=None):
                observed["commands"].append((list(command), env))
                return None

            def validator(*, release_root, runner):
                active_manifest = codex_home / "tools" / "codex-thread-recall" / "active.json"
                self.assertFalse(active_manifest.exists())
                self.assertTrue((release_root / "release.json").is_file())
                return None

            manifest_path = module.install_runtime(
                repo_root=repo_root,
                codex_home=codex_home,
                python_executable=Path("C:/Python312/python.exe"),
                runner=runner,
                validator=validator,
                release_stamp="release-1",
            )
            self.assertEqual(manifest_path, codex_home / "tools" / "codex-thread-recall" / "active.json")
            active_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                Path(active_payload["release_root"]),
                codex_home / "tools" / "codex-thread-recall" / "releases" / "release-1",
            )
            self.assertEqual(len(observed["commands"]), 3)

    def test_runtime_installer_accepts_agent_toolbelt_home_env_override(self):
        module = load_skill_script_module("install_codex_thread_recall_runtime.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            make_repo_bundle(repo_root)
            original_env = dict(os.environ)
            try:
                os.environ["AGENT_TOOLBELT_HOME"] = str(repo_root)
                resolved = module.resolve_repo_root()
            finally:
                os.environ.clear()
                os.environ.update(original_env)

        self.assertEqual(resolved, repo_root.resolve())


if __name__ == "__main__":
    unittest.main()
