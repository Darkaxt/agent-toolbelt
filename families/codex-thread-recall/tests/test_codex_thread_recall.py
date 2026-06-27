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
    title: str = "Thread Recall Test",
    created_at: int = 1777077000,
    updated_at: int = 1777077300,
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
            title,
            r"\\?\D:\Workspace\Projects\recall-sandbox",
            str(rollout_path),
            created_at,
            updated_at,
        ),
    )
    conn.commit()
    conn.close()
    return codex_home, rollout_path


def add_thread_to_codex_home(
    codex_home: Path,
    *,
    thread_id: str,
    rollout_entries: list[dict] | None = None,
    cwd: str = r"\\?\D:\Workspace\Projects\recall-sandbox",
    title: str = "Thread Recall Test",
    missing_rollout: bool = False,
    created_at: int = 1777077600,
    updated_at: int = 1777077900,
) -> Path:
    rollout_path = codex_home / "sessions" / "2026" / "04" / "25" / f"rollout-{thread_id}.jsonl"
    rollout_path.parent.mkdir(parents=True, exist_ok=True)
    if not missing_rollout:
        lines = [json.dumps(entry, ensure_ascii=False) for entry in (rollout_entries or [])]
        rollout_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    conn = sqlite3.connect(codex_home / "state_5.sqlite")
    try:
        conn.execute(
            "insert into threads (id, title, cwd, rollout_path, created_at, updated_at) values (?, ?, ?, ?, ?, ?)",
            (thread_id, title, cwd, str(rollout_path), created_at, updated_at),
        )
        conn.commit()
    finally:
        conn.close()
    return rollout_path


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

    def warm_status(self) -> dict:
        collector = thread_recall.collect(thread_source="current")
        self.assertTrue(collector["ok"], collector)
        return thread_recall.status()

    def test_status_resolves_current_thread_from_env(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["thread"]["id"], THREAD_ID)
        self.assertEqual(payload["thread"]["rollout_path"], str(rollout_path))

    def test_status_does_not_build_index_by_default(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            cache_db = codex_home / "cache" / "codex-thread-recall" / "index.sqlite"
            with self.with_env(codex_home):
                payload = thread_recall.status()

        self.assertTrue(payload["ok"])
        self.assertFalse(cache_db.exists())
        self.assertEqual(payload["cache"]["freshness"]["state"], "not_indexed")
        self.assertEqual(payload["cache"]["entry_count"], 0)
        self.assertIsNone(payload["episodes"]["current"])

    def test_collect_current_builds_index_and_status_reports_fresh(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-alpha`."})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                collected = thread_recall.collect(thread_source="current")
                payload = thread_recall.status()

        self.assertTrue(collected["ok"], collected)
        self.assertEqual(collected["collector"]["thread_source"]["applied"], "current")
        self.assertEqual(collected["collector"]["threads"][0]["result"], "rebuilt")
        self.assertEqual(payload["cache"]["freshness"]["state"], "fresh")
        self.assertEqual(payload["cache"]["entry_count"], 1)

    def test_collect_append_tail_rebuild_handles_large_tail_slice(self):
        entries = [
            make_entry(
                f"2026-04-25T08:{index % 60:02d}:00Z",
                "event_msg",
                {"type": "agent_message", "text": f"Validated `artifact-alpha` step {index}."},
            )
            for index in range(thread_recall.SQLITE_PARAM_CHUNK_SIZE * 3)
        ]
        appended_entry = make_entry(
            "2026-04-25T10:00:00Z",
            "event_msg",
            {"type": "agent_message", "text": "Validated `artifact-alpha` after append."},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = thread_recall.collect(thread_source="current")
                with rollout_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(appended_entry, ensure_ascii=False) + "\n")
                second = thread_recall.collect(thread_source="current")
                payload = thread_recall.status()

        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["collector"]["threads"][0]["result"], "appended")
        self.assertEqual(payload["cache"]["freshness"]["state"], "fresh")
        self.assertEqual(payload["cache"]["entry_count"], len(entries) + 1)

    def test_collect_recent_selects_newest_readable_threads(self):
        now = int(datetime.now(tz=UTC).timestamp())
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(
                temp_dir,
                thread_id="current-thread",
                rollout_entries=entries,
                updated_at=now - 60,
            )
            add_thread_to_codex_home(
                codex_home,
                thread_id="newer-readable",
                rollout_entries=entries,
                updated_at=now - 30,
            )
            add_thread_to_codex_home(
                codex_home,
                thread_id="too-old",
                rollout_entries=entries,
                updated_at=now - 72 * 3600,
            )
            add_thread_to_codex_home(
                codex_home,
                thread_id="missing-rollout",
                rollout_entries=entries,
                missing_rollout=True,
                updated_at=now - 10,
            )
            with self.with_env(codex_home, thread_id="current-thread"):
                payload = thread_recall.collect(
                    thread_source="recent",
                    max_threads=2,
                    updated_within_hours=48,
                )

        self.assertTrue(payload["ok"], payload)
        included_ids = [item["thread_id"] for item in payload["collector"]["threads"]]
        skipped = {item["thread_id"]: item["reason"] for item in payload["collector"]["skipped_threads"]}
        self.assertEqual(included_ids, ["newer-readable", "current-thread"])
        self.assertEqual(skipped["missing-rollout"], "rollout_missing")
        self.assertEqual(skipped["too-old"], "updated_before_window")

    def test_collect_jsonl_log_omits_thread_titles(self):
        now = int(datetime.now(tz=UTC).timestamp())
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "hello"})]
        sensitive_title = "PRIVATE MESSAGE BODY SHOULD NOT BE IN JSONL"
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(
                temp_dir,
                rollout_entries=entries,
                title=sensitive_title,
                updated_at=now - 60,
            )
            json_log = Path(temp_dir) / "collector.jsonl"
            with self.with_env(codex_home):
                payload = thread_recall.collect(thread_source="current", json_log=json_log)
            log_line = json_log.read_text(encoding="utf-8")
            log_payload = json.loads(log_line)
            last_run_payload = json.loads(thread_recall.collector_last_run_path(codex_home).read_text(encoding="utf-8"))

        def contains_key(value: object, key: str) -> bool:
            if isinstance(value, dict):
                return key in value or any(contains_key(item, key) for item in value.values())
            if isinstance(value, list):
                return any(contains_key(item, key) for item in value)
            return False

        self.assertTrue(payload["ok"], payload)
        self.assertIn(sensitive_title, json.dumps(payload))
        self.assertNotIn(sensitive_title, log_line)
        self.assertFalse(contains_key(log_payload, "thread_title"))
        self.assertFalse(contains_key(last_run_payload, "thread_title"))
        self.assertNotIn(sensitive_title, json.dumps(last_run_payload))

    def test_collector_task_installer_prefers_no_console_pythonw(self):
        installer = (
            SKILL_SCRIPTS / "install_codex_thread_recall_collector_task.ps1"
        ).read_text(encoding="utf-8")

        self.assertLess(installer.index("pythonw.exe"), installer.index("python.exe"))
        self.assertIn("no_console", installer)

    def test_collect_skips_live_lock_without_waiting_for_full_lock_budget(self):
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
            with self.with_env(codex_home):
                payload = thread_recall.collect(thread_source="current", max_run_seconds=10)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["collector"]["threads"][0]["result"], "busy")
        self.assertEqual(payload["collector"]["threads"][0]["lock_state"]["state"], "locked")

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
                entry_columns = {
                    row[1] for row in conn.execute("pragma table_info(entries)").fetchall()
                }
                fts_columns = {
                    row[1] for row in conn.execute("pragma table_info(entries_fts)").fetchall()
                }
                table_names = {
                    row[0] for row in conn.execute("select name from sqlite_master where type = 'table'").fetchall()
                }
            finally:
                conn.close()

        self.assertTrue({"schema_version", "rollout_path_id", "last_indexed_offset", "last_indexed_line", "last_indexed_entry"}.issubset(rollout_columns))
        self.assertTrue({"rollout_path_id", "byte_start", "byte_end", "excerpt"}.issubset(entry_columns))
        self.assertNotIn("raw_text", entry_columns)
        self.assertNotIn("search_text", entry_columns)
        self.assertEqual({"entry_id", "thread_id", "search_text"}, fts_columns)
        self.assertTrue(
            {
                "rollout_paths",
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
                "entry_entity_mentions",
            }.issubset(table_names)
        )

    def test_legacy_episode_schema_is_dropped_before_rebuild(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            cache_db = codex_home / "cache" / "codex-thread-recall" / "index.sqlite"
            cache_db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(cache_db)
            try:
                conn.executescript(
                    """
                    create table rollout_indexes (
                        thread_id text primary key,
                        schema_version integer not null,
                        rollout_path text not null,
                        rollout_size integer not null,
                        rollout_mtime_ns integer not null,
                        last_indexed_offset integer not null,
                        last_indexed_line integer not null,
                        last_indexed_entry integer not null,
                        built_at text not null,
                        entry_count integer not null,
                        noise_filtered_count integer not null,
                        last_rebuild_reason text
                    );
                    create table entries (
                        id integer primary key,
                        thread_id text not null,
                        entry_index integer not null,
                        rollout_line integer not null,
                        timestamp text,
                        entry_type text,
                        payload_type text,
                        role text,
                        command text,
                        raw_text text,
                        search_text text,
                        excerpt text,
                        is_noise integer not null,
                        noise_reason text,
                        content_class text not null
                    );
                    create table episodes (
                        id integer primary key,
                        thread_id text not null,
                        episode_index integer not null,
                        started_entry_index integer not null,
                        ended_entry_index integer not null,
                        started_at text,
                        ended_at text,
                        entry_count integer not null,
                        work_entry_count integer not null,
                        boundary_reason text
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            with self.with_env(codex_home):
                payload = self.warm_status()

            conn = sqlite3.connect(cache_db)
            try:
                episode_columns = {
                    row[1] for row in conn.execute("pragma table_info(episodes)").fetchall()
                }
            finally:
                conn.close()

        self.assertTrue(payload["ok"])
        self.assertIn("substantive_entry_count", episode_columns)

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

    def test_episode_tail_rebuild_seed_uses_first_episode_when_only_one_episode_exists(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-alpha`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-alpha` active."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()
                conn = thread_recall.connect_cache(codex_home)
                try:
                    seed = thread_recall.episode_tail_rebuild_seed(conn, thread_id=THREAD_ID)
                finally:
                    conn.close()

        self.assertTrue(payload["ok"])
        self.assertEqual(seed["start_episode_index"], 1)
        self.assertEqual(seed["start_entry_index"], 1)
        self.assertEqual(seed["boundary_reason"], "thread-start")

    def test_episode_tail_rebuild_seed_uses_last_two_episodes_when_available(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-beta` active."}),
            make_entry("2026-04-25T08:04:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-gamma`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-gamma` active."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()
                conn = thread_recall.connect_cache(codex_home)
                try:
                    seed = thread_recall.episode_tail_rebuild_seed(conn, thread_id=THREAD_ID)
                finally:
                    conn.close()

        self.assertTrue(payload["ok"])
        self.assertEqual(seed["start_episode_index"], 2)
        self.assertEqual(seed["start_entry_index"], 3)
        self.assertEqual(seed["boundary_reason"], "post-ship-user-request")

    def test_append_growth_uses_tail_rebuild_instead_of_full_episode_rebuild(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-beta` active."}),
            make_entry("2026-04-25T08:04:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-gamma`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-gamma` active."}),
        ]
        appended_entry = make_entry(
            "2026-04-25T08:06:00Z",
            "event_msg",
            {"type": "agent_message", "text": "Validated `artifact-gamma` after wiring the release."},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = self.warm_status()
                original_full_rebuild = thread_recall.rebuild_thread_episodes
                try:
                    thread_recall.rebuild_thread_episodes = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                        AssertionError("append growth should not use full episode rebuild")
                    )
                    with rollout_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(appended_entry, ensure_ascii=False) + "\n")
                    second = self.warm_status()
                finally:
                    thread_recall.rebuild_thread_episodes = original_full_rebuild

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["episodes"]["total"], 3)
        self.assertEqual(second["episodes"]["current"]["dominant_entities"], ["artifact-gamma"])

    def test_append_growth_falls_back_to_full_rebuild_when_tail_rebuild_fails(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-beta` active."}),
            make_entry("2026-04-25T08:04:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-gamma`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-gamma` active."}),
        ]
        appended_entry = make_entry(
            "2026-04-25T08:06:00Z",
            "event_msg",
            {"type": "agent_message", "text": "Validated `artifact-gamma` after wiring the release."},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = self.warm_status()
                original_tail_rebuild = thread_recall.rebuild_tail_thread_episodes
                original_full_rebuild = thread_recall.rebuild_thread_episodes
                full_rebuild_called = {"value": False}

                def wrapped_full_rebuild(*args, **kwargs):
                    full_rebuild_called["value"] = True
                    return original_full_rebuild(*args, **kwargs)

                def failing_tail_rebuild(*_args, **_kwargs):
                    raise thread_recall.TailEpisodeRebuildError("boom")

                try:
                    thread_recall.rebuild_tail_thread_episodes = failing_tail_rebuild
                    thread_recall.rebuild_thread_episodes = wrapped_full_rebuild
                    with rollout_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(appended_entry, ensure_ascii=False) + "\n")
                    second = self.warm_status()
                finally:
                    thread_recall.rebuild_tail_thread_episodes = original_tail_rebuild
                    thread_recall.rebuild_thread_episodes = original_full_rebuild

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertTrue(full_rebuild_called["value"])
        self.assertEqual(second["episodes"]["current"]["dominant_entities"], ["artifact-gamma"])

    def test_append_growth_rebuilds_single_episode_from_episode_one_checkpoint(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-alpha`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-alpha` active."}),
        ]
        appended_entry = make_entry(
            "2026-04-25T08:02:00Z",
            "event_msg",
            {"type": "agent_message", "text": "Validated `artifact-alpha` after wiring the release."},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = self.warm_status()
                original_full_rebuild = thread_recall.rebuild_thread_episodes
                try:
                    thread_recall.rebuild_thread_episodes = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                        AssertionError("single-episode append should rebuild from episode one without full rebuild")
                    )
                    with rollout_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(appended_entry, ensure_ascii=False) + "\n")
                    second = self.warm_status()
                finally:
                    thread_recall.rebuild_thread_episodes = original_full_rebuild

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["episodes"]["total"], 1)
        self.assertEqual(second["episodes"]["current"]["dominant_entities"], ["artifact-alpha"])

    def test_append_growth_starts_new_episode_for_disjoint_user_goal(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
        ]
        appended_entries = [
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-beta` active."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = self.warm_status()
                with rollout_path.open("a", encoding="utf-8") as handle:
                    for entry in appended_entries:
                        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                second = self.warm_status()

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["episodes"]["total"], 2)
        self.assertEqual(second["episodes"]["last_boundary_reason"], "post-ship-user-request")
        self.assertEqual(second["episodes"]["current"]["dominant_entities"], ["artifact-beta"])

    def test_append_growth_rebuilds_cleanly_when_tail_episode_checkpoint_is_corrupt(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-beta` active."}),
            make_entry("2026-04-25T08:04:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-gamma`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-gamma` active."}),
        ]
        appended_entry = make_entry(
            "2026-04-25T08:06:00Z",
            "event_msg",
            {"type": "agent_message", "text": "Validated `artifact-gamma` after wiring the release."},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, rollout_path = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = self.warm_status()
                cache_db = codex_home / "cache" / "codex-thread-recall" / "index.sqlite"
                conn = sqlite3.connect(cache_db)
                try:
                    conn.execute(
                        "update episodes set started_entry_index = 999 where thread_id = ? and episode_index = 3",
                        (THREAD_ID,),
                    )
                    conn.commit()
                finally:
                    conn.close()
                with rollout_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(appended_entry, ensure_ascii=False) + "\n")
                second = self.warm_status()
                conn = sqlite3.connect(cache_db)
                try:
                    repaired_starts = [
                        row[0]
                        for row in conn.execute(
                            "select started_entry_index from episodes where thread_id = ? order by episode_index",
                            (THREAD_ID,),
                        ).fetchall()
                    ]
                finally:
                    conn.close()

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["episodes"]["current"]["dominant_entities"], ["artifact-gamma"])
        self.assertTrue(all(value < 999 for value in repaired_starts))

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
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["runtime"]["mode"], "direct")
        self.assertEqual(payload["cache"]["schema_version"], thread_recall.CACHE_SCHEMA_VERSION)
        self.assertIn("index.sqlite", payload["cache"]["path"])
        self.assertIn(payload["cache"]["lock_state"]["state"], {"unlocked", "not-needed", "acquired"})

    def test_status_reports_fts_health_and_collector_self_heals_missing_fts_rows(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Plan `artifact-health`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: index `artifact-health`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                first = self.warm_status()
                cache_path = thread_recall.cache_db_path(Path(codex_home))
                conn = sqlite3.connect(cache_path)
                try:
                    conn.execute("delete from entries_fts where entry_id = (select min(id) from entries)")
                    conn.commit()
                finally:
                    conn.close()
                stale = thread_recall.status()
                collector = thread_recall.collect(thread_source="current")
                healed = thread_recall.status()

        self.assertTrue(first["ok"])
        self.assertTrue(first["search"]["fts_available"])
        self.assertEqual(first["search"]["fts_indexed_entry_count"], 2)
        self.assertTrue(stale["cache"]["health"]["rebuild_recommended"])
        self.assertEqual(stale["search"]["fts_missing_entry_count"], 1)
        self.assertTrue(collector["ok"], collector)
        self.assertTrue(healed["ok"], healed)
        self.assertTrue(healed["cache"]["health"]["ok"])
        self.assertEqual(healed["search"]["fts_missing_entry_count"], 0)
        self.assertEqual(healed["search"]["fts_indexed_entry_count"], 2)
        self.assertIn("fts", healed["search"]["query_modes"])

    def test_status_reports_current_episode_diagnostics(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "user_message", "text": "Now refine `artifact-beta`."}),
            make_entry("2026-04-25T08:12:00Z", "event_msg", {"type": "agent_message", "text": "Decision: use episode scope for `artifact-beta`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["total"], 2)
        self.assertEqual(payload["episodes"]["last_boundary_reason"], "post-ship-user-request")
        self.assertEqual(payload["episodes"]["current"]["dominant_entities"], ["artifact-beta"])

    def test_assistant_only_validation_tail_stays_in_same_episode(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: use `artifact-beta` as the active work item."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": r"Touched D:\Work\artifact-beta\README.md."}),
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "agent_message", "text": "Validated the release wiring for `thread_recall`."}),
            make_entry("2026-04-25T08:04:00Z", "event_msg", {"type": "agent_message", "text": "Merged follow-up checks for `thread_recall`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["total"], 1)
        self.assertEqual(payload["episodes"]["current"]["dominant_entities"], ["artifact-beta"])
        self.assertEqual(payload["episodes"]["current"]["selection_reason"], "latest-substantive-episode")
        self.assertGreaterEqual(payload["episodes"]["current"]["substantive_entry_count"], 3)

    def test_repo_only_churn_does_not_split_episode(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-beta` as the current work slice."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": "Working in repo `example/toolbelt`."}),
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "user_message", "text": "Keep using repo `example/other-repo` but continue `artifact-beta`."}),
            make_entry("2026-04-25T08:04:00Z", "event_msg", {"type": "agent_message", "text": "Updated repo notes for `artifact-beta`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["total"], 1)
        self.assertEqual(payload["episodes"]["current"]["dominant_entities"], ["artifact-beta"])

    def test_post_ship_user_follow_up_without_new_strong_anchor_stays_in_same_episode(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:06:00Z", "event_msg", {"type": "user_message", "text": "Please verify the shipping output again."}),
            make_entry("2026-04-25T08:07:00Z", "event_msg", {"type": "agent_message", "text": "Validated `artifact-alpha` and the shipping output."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["total"], 1)
        self.assertEqual(payload["episodes"]["current"]["dominant_entities"], ["artifact-alpha"])

    def test_user_row_with_disjoint_strong_anchor_starts_new_episode(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: use `artifact-alpha` for the first pass."}),
            make_entry("2026-04-25T08:06:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:20:00Z", "event_msg", {"type": "user_message", "text": "Now implement `artifact-beta`."}),
            make_entry("2026-04-25T08:21:00Z", "event_msg", {"type": "agent_message", "text": "Decision: use `artifact-beta` as the active slice."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["total"], 2)
        self.assertEqual(payload["episodes"]["last_boundary_reason"], "post-ship-user-request")
        self.assertEqual(payload["episodes"]["current"]["dominant_entities"], ["artifact-beta"])

    def test_tiny_assistant_only_trailing_episode_merges_back_into_prior_work(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: use `artifact-beta` as the active work item."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": r"Touched D:\Work\artifact-beta\README.md."}),
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "agent_message", "text": "Validated `thread_recall`."}),
            make_entry("2026-04-25T08:04:00Z", "event_msg", {"type": "agent_message", "text": "Installed `thread_recall`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["total"], 1)
        self.assertEqual(payload["episodes"]["current"]["dominant_entities"], ["artifact-beta"])

    def test_time_gap_episode_does_not_merge_back(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: use `artifact-beta` as the active work item."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": r"Touched D:\Work\artifact-beta\README.md."}),
            make_entry("2026-04-25T10:30:00Z", "event_msg", {"type": "agent_message", "text": "Validated `thread_recall` after the long pause."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["total"], 2)
        self.assertEqual(payload["episodes"]["last_boundary_reason"], "time-gap")

    def test_current_falls_back_from_thin_empty_tail_to_previous_substantive_episode(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-beta`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-beta` as the active work item."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": r"Touched D:\Work\artifact-beta\README.md."}),
            make_entry("2026-04-25T08:20:00Z", "event_msg", {"type": "user_message", "text": "Now implement `artifact-gamma`."}),
            make_entry("2026-04-25T08:21:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-gamma` as the active work item."}),
            make_entry("2026-04-25T08:22:00Z", "event_msg", {"type": "agent_message", "text": r"Touched D:\Work\artifact-gamma\README.md."}),
            make_entry("2026-04-25T08:30:00Z", "response_item", {"type": "function_call_output", "output": json.dumps({"stdout": "done", "stderr": ""})}),
            make_entry("2026-04-25T08:31:00Z", "event_msg", {"type": "agent_message", "text": "ok"}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["current"]["dominant_entities"], ["artifact-gamma"])
        self.assertEqual(payload["episodes"]["current"]["selection_reason"], "latest-substantive-episode")
        self.assertGreaterEqual(payload["episodes"]["current"]["substantive_entry_count"], 3)

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
            original_pid_is_running = thread_recall.pid_is_running
            try:
                thread_recall.INDEX_LOCK_WAIT_SECONDS = 1.0
                thread_recall.INDEX_LOCK_POLL_SECONDS = 0.05
                thread_recall.pid_is_running = lambda _pid: True
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
                thread_recall.pid_is_running = original_pid_is_running

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
            original_pid_is_running = thread_recall.pid_is_running
            try:
                thread_recall.pid_is_running = lambda _pid: False
                with self.with_env(codex_home):
                    payload = thread_recall.recall()
            finally:
                thread_recall.pid_is_running = original_pid_is_running

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
            original_pid_is_running = thread_recall.pid_is_running
            try:
                thread_recall.INDEX_LOCK_WAIT_SECONDS = 0.15
                thread_recall.INDEX_LOCK_POLL_SECONDS = 0.05
                thread_recall.pid_is_running = lambda _pid: True
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
                thread_recall.pid_is_running = original_pid_is_running

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
                payload = thread_recall.timeline(kind="shipped", group="entity", limit=10, scope="thread")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scope"]["applied"], "thread")
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

    def test_timeline_entity_grouping_uses_primary_ranked_entity_only(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Please ship `artifact-beta`."}),
            make_entry(
                "2026-04-25T08:02:00Z",
                "event_msg",
                {"type": "agent_message", "text": "Decision: keep `artifact-beta` inside `thread_recall` while wiring the release."},
            ),
            make_entry(
                "2026-04-25T08:05:00Z",
                "event_msg",
                {"type": "agent_message", "text": "Published `artifact-beta` from `thread_recall` with PR `#22`."},
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.timeline(kind="published", group="entity", limit=10, scope="thread")

        self.assertTrue(payload["ok"])
        self.assertEqual([item["entity"] for item in payload["timeline"]], ["artifact-beta"])
        self.assertEqual(payload["timeline"][0]["first_seen_at"], "2026-04-25T08:00:00Z")

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

    def test_path_entity_candidates_ignore_runtime_tools_and_fallback_from_helper_scripts(self):
        self.assertEqual(
            thread_recall.entity_candidates_from_path(r"C:\Program Files\PowerShell\7\pwsh.exe"),
            [],
        )
        self.assertEqual(
            thread_recall.entity_candidates_from_path(r"D:\Work\Projects\artifact-beta\scripts\invoke_refresh_runtime.py"),
            ["artifact-beta"],
        )

    def test_entity_extraction_ignores_env_vars_bare_filenames_and_runtime_modules(self):
        self.assertEqual(
            thread_recall.extract_entities("Use `PATH`, `SKILL.md`, `__main__`, `pathlib`, and `artifact-beta`."),
            ["artifact-beta"],
        )

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

    def test_timeline_defaults_to_current_episode_scope_and_hides_meta_noise(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry(
                "2026-04-25T08:07:00Z",
                "response_item",
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "output_text", "text": "Installed `sandbox_mode` with `danger-full-access`."}],
                },
            ),
            make_entry(
                "2026-04-25T08:08:00Z",
                "response_item",
                {
                    "type": "function_call_output",
                    "output": json.dumps(
                        {
                            "stdout": '1:{"timestamp":"2026-04-25T08:05:00Z","type":"event_msg","payload":{"type":"agent_message","text":"Published `artifact-dump`."}}',
                            "stderr": "",
                        }
                    ),
                },
            ),
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "user_message", "text": "Now ship `artifact-beta`."}),
            make_entry("2026-04-25T08:12:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-beta` in `example/toolbelt`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                current_payload = thread_recall.timeline(kind="shipped", group="entity", limit=10)
                thread_payload = thread_recall.timeline(kind="shipped", group="entity", limit=10, scope="thread")

        self.assertTrue(current_payload["ok"])
        self.assertEqual(current_payload["scope"]["requested"], "current")
        self.assertEqual(current_payload["scope"]["applied"], "episode")
        self.assertEqual([item["entity"] for item in current_payload["timeline"]], ["artifact-beta"])
        self.assertEqual(
            sorted(item["entity"] for item in thread_payload["timeline"]),
            ["artifact-alpha", "artifact-beta"],
        )

    def test_status_current_episode_prefers_semantic_artifact_entities_over_wrapper_paths(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:20:00Z", "event_msg", {"type": "user_message", "text": "Now refine `artifact-beta`."}),
            make_entry(
                "2026-04-25T08:21:00Z",
                "event_msg",
                {"type": "agent_message", "text": "Decision: keep `artifact-beta` as the current work slice."},
            ),
            make_entry(
                "2026-04-25T08:22:00Z",
                "response_item",
                {
                    "type": "function_call",
                    "arguments": json.dumps(
                        {
                            "command": r"C:\Program Files\PowerShell\7\pwsh.exe -File D:\Work\Projects\artifact-beta\scripts\invoke_refresh_runtime.py"
                        }
                    ),
                },
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["current"]["dominant_entities"], ["artifact-beta"])

    def test_status_current_episode_keeps_ranked_artifact_dominant_after_generic_chatter(self):
        entries = [
            make_entry("2026-04-25T08:20:00Z", "event_msg", {"type": "user_message", "text": "Please refine `artifact-beta`."}),
            make_entry(
                "2026-04-25T08:21:00Z",
                "event_msg",
                {"type": "agent_message", "text": "Decision: keep `artifact-beta` as the main work item inside `thread_recall`."},
            ),
            make_entry("2026-04-25T08:22:00Z", "event_msg", {"type": "agent_message", "text": "Validated `thread_recall`."}),
            make_entry("2026-04-25T08:23:00Z", "event_msg", {"type": "agent_message", "text": "Merged follow-up checks for `thread_recall`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = self.warm_status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["episodes"]["current"]["dominant_entities"], ["artifact-beta"])

    def test_timeline_include_meta_restores_suppressed_meta_events(self):
        entries = [
            make_entry(
                "2026-04-25T08:00:00Z",
                "response_item",
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "output_text", "text": "Installed `artifact-meta` in `example/toolbelt`."}],
                },
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                hidden = thread_recall.timeline(kind="installed", group="entity", limit=10)
                restored = thread_recall.timeline(kind="installed", group="entity", limit=10, include_meta=True, scope="thread")

        self.assertTrue(hidden["ok"])
        self.assertEqual(hidden["timeline"], [])
        self.assertEqual([item["entity"] for item in restored["timeline"]], ["artifact-meta"])

    def test_timeline_ignores_shipped_markers_that_only_appear_in_command_output(self):
        entries = [
            make_entry(
                "2026-04-25T08:00:00Z",
                "response_item",
                {
                    "type": "function_call_output",
                    "output": json.dumps({"stdout": "Published `artifact-noise` in `example/toolbelt`.", "stderr": ""}),
                },
            ),
            make_entry(
                "2026-04-25T08:01:00Z",
                "event_msg",
                {"type": "agent_message", "text": "Published `artifact-real` in `example/toolbelt`."},
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.timeline(kind="published", group="entity", limit=10, scope="thread")

        self.assertTrue(payload["ok"])
        self.assertEqual([item["entity"] for item in payload["timeline"]], ["artifact-real"])

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

    def test_recall_shipping_ranks_real_artifact_above_generic_identifier(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-gamma`."}),
            make_entry(
                "2026-04-25T08:01:00Z",
                "event_msg",
                {"type": "agent_message", "text": "Decision: keep `artifact-gamma` inside `thread_recall` for the release."},
            ),
            make_entry(
                "2026-04-25T08:05:00Z",
                "event_msg",
                {"type": "agent_message", "text": "Published `artifact-gamma` from `thread_recall` with PR `#11`."},
            ),
            make_entry(
                "2026-04-25T08:06:00Z",
                "event_msg",
                {"type": "agent_message", "text": "Merged follow-up checks for `thread_recall`."},
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.recall(profile="shipping", evidence_limit=10, scope="thread")

        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(len(payload["recall"]["shipped_entities"]), 1)
        self.assertEqual(payload["recall"]["shipped_entities"][0], "artifact-gamma")

    def test_recall_general_defaults_to_current_episode_and_uses_scoped_semantic_facts(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: use `artifact-alpha` for the first pass."}),
            make_entry("2026-04-25T08:06:00Z", "event_msg", {"type": "agent_message", "text": r"Working in D:\Work\artifact-alpha\README.md."}),
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."}),
            make_entry("2026-04-25T08:20:00Z", "event_msg", {"type": "user_message", "text": "Please implement scoped recall for `artifact-beta`."}),
            make_entry("2026-04-25T08:21:00Z", "event_msg", {"type": "agent_message", "text": "Decision: use current episode scope by default and fail closed on missing episode ids."}),
            make_entry("2026-04-25T08:22:00Z", "event_msg", {"type": "agent_message", "text": r"Touched D:\Work\artifact-beta\README.md and repo `example/toolbelt`."}),
            make_entry("2026-04-25T08:23:00Z", "response_item", {"type": "function_call_output", "output": json.dumps({"stdout": "", "stderr": "Permission denied"})}),
            make_entry("2026-04-25T08:24:00Z", "event_msg", {"type": "agent_message", "text": "Open question: should grep stay thread-wide by default?"}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.recall(profile="general")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scope"]["requested"], "current")
        self.assertEqual(payload["scope"]["applied"], "episode")
        recall = payload["recall"]
        self.assertIn("artifact-beta", recall["current_goal"])
        self.assertTrue(any("current episode scope" in item.lower() for item in recall["decisions"]))
        self.assertTrue(any(r"D:\Work\artifact-beta\README.md" in item for item in recall["touched_paths"]))
        self.assertTrue(any("Permission denied" in item for item in recall["blockers"]))
        self.assertTrue(any("grep stay thread-wide" in item for item in recall["open_questions"]))
        self.assertFalse(any("artifact-alpha" in item for item in recall["decisions"]))
        self.assertFalse(any("artifact-alpha" in item for item in recall["known_facts"]))

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

    def test_grep_reports_total_matches_truncation_and_supports_time_sort(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-epsilon`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Merged PR `#11` for `artifact-epsilon`."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": "Installed `artifact-epsilon`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(pattern="artifact-epsilon", role="assistant", limit=2, sort="time-desc")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total_matches"], 3)
        self.assertEqual(payload["returned_matches"], 2)
        self.assertTrue(payload["truncated"])
        self.assertEqual([item["timestamp"] for item in payload["results"]], ["2026-04-25T08:02:00Z", "2026-04-25T08:01:00Z"])

    def test_grep_all_returns_all_logical_matches_and_collapses_mirrors(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-epsilon`."}),
            make_entry(
                "2026-04-25T08:00:00Z",
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Published `artifact-epsilon`."}],
                },
            ),
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "task_complete", "summary": "Published `artifact-epsilon`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(pattern="artifact-epsilon", all_matches=True, sort="time-asc")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total_matches"], 1)
        self.assertEqual(payload["returned_matches"], 1)
        self.assertFalse(payload["truncated"])
        self.assertEqual(payload["collapsed_mirror_matches"], 2)
        self.assertEqual(payload["results"][0]["payload_type"], "agent_message")

    def test_grep_scope_current_restricts_results_but_thread_default_stays_global(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Ship `artifact-alpha` with CODEX_THREAD_ID notes."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "CODEX_THREAD_ID helps `artifact-alpha` resolve."}),
            make_entry("2026-04-25T08:20:00Z", "event_msg", {"type": "user_message", "text": "Now ship `artifact-beta`."}),
            make_entry("2026-04-25T08:21:00Z", "event_msg", {"type": "agent_message", "text": "Scoped recall keeps `artifact-beta` focused."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                thread_payload = thread_recall.grep_rollout(pattern="artifact", limit=10)
                current_payload = thread_recall.grep_rollout(pattern="artifact", limit=10, scope="current")

        self.assertTrue(thread_payload["ok"])
        self.assertEqual(thread_payload["scope"]["applied"], "thread")
        self.assertGreaterEqual(len(thread_payload["results"]), 2)
        self.assertEqual(current_payload["scope"]["applied"], "episode")
        self.assertTrue(all("artifact-beta" in item["excerpt"] for item in current_payload["results"]))

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

    def test_grep_include_noise_reads_raw_rollout_source_without_cached_raw_text(self):
        raw_only_marker = "RAW-SOURCE-ONLY-MARKER-1199"
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-visible`."}),
            make_entry(
                "2026-04-25T08:01:00Z",
                "response_item",
                {
                    "type": "function_call_output",
                    "output": json.dumps({"stdout": ("noise " * 3000) + raw_only_marker, "stderr": ""}),
                },
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(pattern=raw_only_marker, include_noise=True, limit=10)

            cache_db = codex_home / "cache" / "codex-thread-recall" / "index.sqlite"
            conn = sqlite3.connect(cache_db)
            try:
                entry_columns = {
                    row[1] for row in conn.execute("pragma table_info(entries)").fetchall()
                }
                fts_columns = {
                    row[1] for row in conn.execute("pragma table_info(entries_fts)").fetchall()
                }
            finally:
                conn.close()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["returned_matches"], 1)
        self.assertIn(raw_only_marker, payload["results"][0]["match"]["snippet"])
        self.assertNotIn("raw_text", entry_columns)
        self.assertNotIn("raw_text", fts_columns)

    def test_grep_fts_mode_supports_boolean_prefix_and_match_metadata(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Plan `artifact-search` audit search support."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: implement audit search snippets for `artifact-search`."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": "Unrelated mention of audit logs."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(
                    pattern='"audit search" AND artifact*',
                    query_mode="fts",
                    limit=10,
                    sort="relevance",
                )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["query_mode"], "fts")
        self.assertEqual(payload["total_matches"], 2)
        self.assertTrue(all(result["entry_ref"].startswith(f"{THREAD_ID}#") for result in payload["results"]))
        self.assertTrue(all(result["match"]["query_mode"] == "fts" for result in payload["results"]))
        self.assertTrue(all(isinstance(result["match"].get("fts_rank"), (int, float)) for result in payload["results"]))
        self.assertTrue(any("[[audit" in result["match"]["snippet"].lower() for result in payload["results"]))

    def test_grep_invalid_fts_query_fails_closed(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-search`."})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(pattern='"unterminated phrase', query_mode="fts")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "invalid_query")

    def test_grep_context_returns_scoped_neighbor_evidence(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "agent_message", "text": "Prepare `artifact-context`."}),
            make_entry("2026-04-25T08:01:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep `artifact-context` scoped."}),
            make_entry("2026-04-25T08:02:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-context`."}),
            make_entry("2026-04-25T08:03:00Z", "event_msg", {"type": "agent_message", "text": "Validated `artifact-context`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(pattern="Published", context=1, limit=1)

        self.assertTrue(payload["ok"])
        result = payload["results"][0]
        self.assertEqual(result["entry_index"], 3)
        self.assertEqual([item["entry_index"] for item in result["context"]["before"]], [2])
        self.assertEqual([item["entry_index"] for item in result["context"]["after"]], [4])
        self.assertNotIn("context", result["context"]["before"][0])

    def test_grep_context_limit_is_bounded(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-context`."})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(pattern="artifact-context", context=6)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "invalid_request")

    def test_timeline_none_reports_total_matches_sort_and_collapses_mirrors(self):
        entries = [
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-theta`."}),
            make_entry(
                "2026-04-25T08:10:00Z",
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Published `artifact-theta`."}],
                },
            ),
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "task_complete", "summary": "Published `artifact-theta`."}),
            make_entry("2026-04-25T08:15:00Z", "event_msg", {"type": "agent_message", "text": "Merged PR `#14` for `artifact-theta`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.timeline(kind="all", group="none", limit=10, sort="time-desc", scope="thread")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total_matches"], 2)
        self.assertEqual(payload["returned_matches"], 2)
        self.assertEqual(payload["collapsed_mirror_matches"], 2)
        self.assertEqual([event["kind"] for event in payload["timeline"]], ["merged", "published"])

    def test_worklog_returns_span_and_excludes_incidental_by_default(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Please implement `artifact-iota`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: use `artifact-iota`."}),
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-iota`."}),
            make_entry(
                "2026-04-25T08:20:00Z",
                "response_item",
                {"type": "function_call_output", "output": json.dumps({"stdout": "M families/artifact-iota/README.md", "stderr": ""})},
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.worklog(patterns=["artifact-iota"])
                incidental = thread_recall.worklog(patterns=["artifact-iota"], include_incidental=True)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["started_at"], "2026-04-25T08:00:00Z")
        self.assertEqual(payload["ended_at"], "2026-04-25T08:10:00Z")
        self.assertEqual(payload["matched_entries"], 3)
        self.assertEqual(payload["raw_matches"], 3)
        self.assertEqual(incidental["ended_at"], "2026-04-25T08:20:00Z")
        self.assertEqual(incidental["raw_matches"], 4)

    def test_worklog_supports_or_patterns(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Plan `artifact-kappa`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: build `artifact-kappa`."}),
            make_entry("2026-04-25T08:30:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-lambda`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.worklog(patterns=["artifact-kappa", "artifact-lambda"])

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["started_at"], "2026-04-25T08:00:00Z")
        self.assertEqual(payload["ended_at"], "2026-04-25T08:30:00Z")
        self.assertEqual(payload["matched_entries"], 3)

    def test_worklog_fts_mode_adds_match_metadata_to_boundary_evidence(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement audit search for `artifact-mu`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep audit search for `artifact-mu` literal-compatible."}),
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "agent_message", "text": "Published audit search for `artifact-mu`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            with self.with_env(codex_home):
                payload = thread_recall.worklog(patterns=['"audit search" AND artifact*'], query_mode="fts")

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["query_mode"], "fts")
        self.assertEqual(payload["started_at"], "2026-04-25T08:00:00Z")
        self.assertEqual(payload["ended_at"], "2026-04-25T08:10:00Z")
        self.assertEqual(payload["evidence_start"]["match"]["query_mode"], "fts")
        self.assertIn("[[audit", payload["evidence_start"]["match"]["snippet"].lower())
        self.assertTrue(payload["evidence_end"]["entry_ref"].startswith(f"{THREAD_ID}#"))

    def test_workspace_thread_source_includes_same_cwd_threads_and_coerces_current_scope(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-main`."}),
        ]
        other_entries = [
            make_entry("2026-04-25T09:00:00Z", "event_msg", {"type": "agent_message", "text": "Merged PR `#15` for `artifact-main`."}),
        ]
        different_cwd_entries = [
            make_entry("2026-04-25T10:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-foreign`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            add_thread_to_codex_home(codex_home, thread_id="019-thread-other", rollout_entries=other_entries, updated_at=1777078800)
            add_thread_to_codex_home(
                codex_home,
                thread_id="019-thread-foreign",
                rollout_entries=different_cwd_entries,
                cwd=r"\\?\D:\Workspace\Projects\other-sandbox",
                updated_at=1777079400,
            )
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(
                    pattern="artifact-main",
                    all_matches=True,
                    scope="current",
                    thread_source="workspace",
                    sort="time-asc",
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scope"]["applied"], "thread")
        self.assertEqual(payload["thread_source"]["applied"], "workspace")
        self.assertEqual(len(payload["thread_source"]["included_threads"]), 2)
        self.assertEqual({item["thread_id"] for item in payload["results"]}, {THREAD_ID, "019-thread-other"})
        self.assertTrue(all("thread_cwd" in item for item in payload["results"]))

    def test_workspace_episode_scope_fails_closed(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-main`."})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            add_thread_to_codex_home(codex_home, thread_id="019-thread-other", rollout_entries=entries, updated_at=1777078800)
            with self.with_env(codex_home):
                payload = thread_recall.grep_rollout(
                    pattern="artifact-main",
                    scope="episode",
                    episode_id="episode-1",
                    thread_source="workspace",
                )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "scope_unavailable")

    def test_workspace_recall_merges_shipping_context_and_source_thread_evidence(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-alpha` in `example/toolbelt`."})]
        other_entries = [make_entry("2026-04-25T09:00:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-beta` in `example/toolbelt`."})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            add_thread_to_codex_home(codex_home, thread_id="019-thread-other", rollout_entries=other_entries, updated_at=1777078800)
            with self.with_env(codex_home):
                payload = thread_recall.recall(profile="shipping", scope="thread", thread_source="workspace")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["thread_source"]["applied"], "workspace")
        self.assertIn("artifact-alpha", payload["recall"]["shipped_entities"])
        self.assertIn("artifact-beta", payload["recall"]["shipped_entities"])
        self.assertTrue(any(item.get("thread_id") == "019-thread-other" for item in payload["recall"]["evidence"]))

    def test_memory_export_import_list_show_search_and_forget_are_opt_in(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement portable memory for `artifact-memory`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: export distilled facts for `artifact-memory` only."}),
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "agent_message", "text": "Published `artifact-memory` in `example/toolbelt`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            bundle_path = Path(temp_dir) / "artifact-memory.bundle.json"
            with self.with_env(codex_home):
                exported = thread_recall.memory_export(scope="thread", output_path=bundle_path)
                imported = thread_recall.memory_import(bundle_path=bundle_path)
                imported_again = thread_recall.memory_import(bundle_path=bundle_path)
                listed = thread_recall.memory_list()
                shown = thread_recall.memory_show(bundle_id=exported["bundle_id"])
                searched = thread_recall.memory_search(pattern="artifact-memory", limit=10)
                recalled = thread_recall.recall(scope="thread")
                forgotten = thread_recall.memory_forget(bundle_id=exported["bundle_id"])
                searched_after_forget = thread_recall.memory_search(pattern="artifact-memory", limit=10)
                bundle_file_exists = bundle_path.is_file()

        self.assertTrue(exported["ok"], exported)
        self.assertEqual(exported["bundle"]["format"], "codex-thread-recall.memory_bundle.v1")
        self.assertEqual(exported["bundle_id"], exported["bundle"]["bundle_id"])
        self.assertTrue(bundle_file_exists)
        self.assertNotIn("raw_text", json.dumps(exported["bundle"]).lower())
        self.assertTrue(imported["ok"], imported)
        self.assertTrue(imported["imported"])
        self.assertTrue(imported_again["ok"], imported_again)
        self.assertFalse(imported_again["imported"])
        self.assertEqual(listed["bundles"][0]["bundle_id"], exported["bundle_id"])
        self.assertEqual(shown["bundle"]["bundle_id"], exported["bundle_id"])
        self.assertGreaterEqual(searched["total_matches"], 1)
        self.assertIn("[[artifact-memory]]", searched["results"][0]["match"]["snippet"])
        self.assertEqual(searched["results"][0]["bundle_id"], exported["bundle_id"])
        self.assertTrue(recalled["ok"])
        self.assertNotIn("memory_bundles", recalled)
        self.assertTrue(forgotten["forgotten"])
        self.assertEqual(searched_after_forget["total_matches"], 0)

    def test_memory_import_rejects_tampered_or_oversized_bundles(self):
        entries = [make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement `artifact-memory`."})]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            bundle_path = Path(temp_dir) / "memory.bundle.json"
            tampered_path = Path(temp_dir) / "tampered.bundle.json"
            oversized_path = Path(temp_dir) / "oversized.bundle.json"
            oversized_path.write_text("x" * (thread_recall.MEMORY_BUNDLE_MAX_BYTES + 1), encoding="utf-8")
            with self.with_env(codex_home):
                exported = thread_recall.memory_export(scope="thread", output_path=bundle_path)
                tampered = json.loads(bundle_path.read_text(encoding="utf-8"))
                tampered["items"][0]["text"] = "tampered content"
                tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
                tampered_payload = thread_recall.memory_import(bundle_path=tampered_path)
                oversized_payload = thread_recall.memory_import(bundle_path=oversized_path)

        self.assertTrue(exported["ok"])
        self.assertFalse(tampered_payload["ok"])
        self.assertEqual(tampered_payload["error"], "invalid_memory_bundle")
        self.assertFalse(oversized_payload["ok"])
        self.assertEqual(oversized_payload["error"], "memory_bundle_too_large")

    def test_memory_search_fts_and_unavailable_fallback_are_explicit(self):
        entries = [
            make_entry("2026-04-25T08:00:00Z", "event_msg", {"type": "user_message", "text": "Implement audit bundle for `artifact-memory`."}),
            make_entry("2026-04-25T08:05:00Z", "event_msg", {"type": "agent_message", "text": "Decision: keep audit bundle searchable for `artifact-memory`."}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home, _ = make_codex_home(temp_dir, rollout_entries=entries)
            bundle_path = Path(temp_dir) / "memory.bundle.json"
            with self.with_env(codex_home):
                exported = thread_recall.memory_export(scope="thread", output_path=bundle_path)
                imported = thread_recall.memory_import(bundle_path=bundle_path)
                fts_payload = thread_recall.memory_search(pattern='"audit bundle" AND artifact*', query_mode="fts", limit=10)
                original_probe = thread_recall.sqlite_fts5_available
                try:
                    thread_recall.sqlite_fts5_available = lambda conn: False
                    literal_payload = thread_recall.memory_search(pattern="artifact-memory", query_mode="literal", limit=10)
                    unavailable_payload = thread_recall.memory_search(pattern="artifact-memory", query_mode="fts", limit=10)
                finally:
                    thread_recall.sqlite_fts5_available = original_probe

        self.assertTrue(exported["ok"])
        self.assertTrue(imported["ok"])
        self.assertTrue(fts_payload["ok"], fts_payload)
        self.assertGreaterEqual(fts_payload["total_matches"], 1)
        self.assertEqual(fts_payload["results"][0]["match"]["query_mode"], "fts")
        self.assertTrue(literal_payload["ok"])
        self.assertGreaterEqual(literal_payload["total_matches"], 1)
        self.assertFalse(unavailable_payload["ok"])
        self.assertEqual(unavailable_payload["error"], "fts_unavailable")

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

        self.assertNotIn("raw_text", compacted)
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

    def test_oversized_noise_entries_do_not_store_raw_text(self):
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
        self.assertNotIn("raw_text", oversized)
        self.assertEqual(oversized["search_text"], "")

    def test_transcript_dump_rows_are_classified_and_suppressed_by_default(self):
        transcript_dump = thread_recall.normalize_entry(
            {
                "timestamp": "2026-04-25T08:07:00Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": json.dumps(
                        {
                            "stdout": '\n'.join(
                                [
                                    '1:{"timestamp":"2026-04-25T08:00:00Z","type":"event_msg","payload":{"type":"user_message","text":"Start `artifact-noise`"}}',
                                    '2:{"timestamp":"2026-04-25T08:01:00Z","type":"event_msg","payload":{"type":"agent_message","text":"Published `artifact-noise`"}}',
                                ]
                            ),
                            "stderr": "",
                        }
                    ),
                },
            },
            10,
            45,
        )

        self.assertTrue(transcript_dump["is_noise"])
        self.assertEqual(transcript_dump["content_class"], "transcript_dump")


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
            "scope": kwargs.get("scope"),
            "query_mode": kwargs.get("query_mode"),
            "context": kwargs.get("context"),
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main([
                    "grep",
                    "--pattern",
                    "fail closed",
                    "--role",
                    "assistant",
                    "--include-noise",
                    "--scope",
                    "current",
                    "--query-mode",
                    "fts",
                    "--context",
                    "2",
                ])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.grep_rollout = original_grep

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["pattern"], "fail closed")
        self.assertEqual(payload["role"], "assistant")
        self.assertTrue(payload["include_noise"])
        self.assertEqual(payload["scope"], "current")
        self.assertEqual(payload["query_mode"], "fts")
        self.assertEqual(payload["context"], 2)

    def test_worklog_cli_passes_query_mode(self):
        original_worklog = cli.thread_recall.worklog
        cli.thread_recall.worklog = lambda **kwargs: {
            "ok": True,
            "patterns": kwargs["patterns"],
            "query_mode": kwargs.get("query_mode"),
            "warnings": [],
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["worklog", "--pattern", "audit search", "--query-mode", "fts"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.worklog = original_worklog

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["patterns"], ["audit search"])
        self.assertEqual(payload["query_mode"], "fts")

    def test_collect_cli_passes_scheduler_options(self):
        original_collect = cli.thread_recall.collect
        cli.thread_recall.collect = lambda **kwargs: {
            "ok": True,
            "collector": {
                "thread_source": {"applied": kwargs["thread_source"]},
                "max_threads": kwargs["max_threads"],
                "updated_within_hours": kwargs["updated_within_hours"],
                "max_run_seconds": kwargs["max_run_seconds"],
                "json_log": kwargs["json_log"],
            },
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(
                    [
                        "collect",
                        "--thread-source",
                        "recent",
                        "--max-threads",
                        "7",
                        "--updated-within-hours",
                        "24",
                        "--max-run-seconds",
                        "30",
                        "--json-log",
                        "collector.jsonl",
                    ]
                )
                payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.collect = original_collect

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["collector"]["thread_source"]["applied"], "recent")
        self.assertEqual(payload["collector"]["max_threads"], 7)
        self.assertEqual(payload["collector"]["updated_within_hours"], 24)
        self.assertEqual(payload["collector"]["max_run_seconds"], 30)
        self.assertEqual(payload["collector"]["json_log"], "collector.jsonl")

    def test_memory_cli_routes_export_import_and_search(self):
        calls: list[tuple[str, dict]] = []
        original_export = cli.thread_recall.memory_export
        original_import = cli.thread_recall.memory_import
        original_search = cli.thread_recall.memory_search
        cli.thread_recall.memory_export = lambda **kwargs: calls.append(("export", kwargs)) or {"ok": True, "bundle_id": "bundle-1"}
        cli.thread_recall.memory_import = lambda **kwargs: calls.append(("import", kwargs)) or {"ok": True, "bundle_id": "bundle-1"}
        cli.thread_recall.memory_search = lambda **kwargs: calls.append(("search", kwargs)) or {"ok": True, "results": []}
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                self.assertEqual(cli.main(["memory", "export", "--scope", "thread", "--output", "bundle.json"]), 0)
                export_payload = json.loads(buffer.getvalue())
            with io.StringIO() as buffer, redirect_stdout(buffer):
                self.assertEqual(cli.main(["memory", "import", "--path", "bundle.json"]), 0)
                import_payload = json.loads(buffer.getvalue())
            with io.StringIO() as buffer, redirect_stdout(buffer):
                self.assertEqual(cli.main(["memory", "search", "--pattern", "artifact", "--query-mode", "fts", "--limit", "5"]), 0)
                search_payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.memory_export = original_export
            cli.thread_recall.memory_import = original_import
            cli.thread_recall.memory_search = original_search

        self.assertEqual(export_payload["bundle_id"], "bundle-1")
        self.assertEqual(import_payload["bundle_id"], "bundle-1")
        self.assertEqual(search_payload["results"], [])
        self.assertEqual(calls[0], ("export", {"thread_id": None, "codex_home": None, "scope": "thread", "episode_id": None, "output_path": "bundle.json"}))
        self.assertEqual(calls[1], ("import", {"codex_home": None, "bundle_path": "bundle.json"}))
        self.assertEqual(calls[2][0], "search")
        self.assertEqual(calls[2][1]["query_mode"], "fts")
        self.assertEqual(calls[2][1]["limit"], 5)

    def test_timeline_cli_passes_kind_and_group(self):
        original_timeline = cli.thread_recall.timeline
        cli.thread_recall.timeline = lambda **kwargs: {
            "ok": True,
            "kind": kwargs["kind"],
            "group": kwargs["group"],
            "scope": kwargs["scope"],
            "include_meta": kwargs["include_meta"],
            "timeline": [],
            "warnings": [],
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["timeline", "--kind", "shipped", "--group", "entity", "--scope", "episode", "--episode-id", "episode-2", "--include-meta"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.timeline = original_timeline

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["kind"], "shipped")
        self.assertEqual(payload["group"], "entity")
        self.assertEqual(payload["scope"], "episode")
        self.assertTrue(payload["include_meta"])

    def test_recall_cli_accepts_profile_and_escapes_unicode_for_windows_console_safety(self):
        original_recall = cli.thread_recall.recall
        cli.thread_recall.recall = lambda **kwargs: {
            "ok": True,
            "thread": {"id": "demo"},
            "recall": {"profile": kwargs["profile"], "summary": "【unicode evidence】"},
            "warnings": [],
            "scope": kwargs["scope"],
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["recall", "--profile", "shipping", "--scope", "current"])
                rendered = buffer.getvalue()
                payload = json.loads(rendered)
        finally:
            cli.thread_recall.recall = original_recall

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["recall"]["profile"], "shipping")
        self.assertEqual(payload["scope"], "current")
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

    def test_runtime_bootstrap_runtime_mode_terminates_child_tree_on_keyboard_interrupt(self):
        module = load_skill_script_module("runtime_bootstrap.py")
        calls: list[tuple[str, int]] = []

        class FakeProcess:
            pid = 4242
            returncode = None

            def wait(self):
                raise KeyboardInterrupt()

        original_popen = module.subprocess.Popen
        original_terminate = module.terminate_process_tree
        module.subprocess.Popen = lambda *_args, **_kwargs: FakeProcess()
        module.terminate_process_tree = lambda process: calls.append(("terminate", process.pid))
        try:
            with self.assertRaises(KeyboardInterrupt):
                module.execute_cli(
                    {"mode": "runtime", "runtime_python": "C:/Python/python.exe"},
                    ["status"],
                )
        finally:
            module.subprocess.Popen = original_popen
            module.terminate_process_tree = original_terminate

        self.assertEqual(calls, [("terminate", 4242)])

    def test_runtime_bootstrap_runtime_mode_returns_structured_timeout_when_configured(self):
        module = load_skill_script_module("runtime_bootstrap.py")
        calls: list[tuple[str, int]] = []

        class FakeProcess:
            pid = 4243
            returncode = None

            def wait(self, timeout=None):
                raise module.subprocess.TimeoutExpired(["python"], timeout)

        original_popen = module.subprocess.Popen
        original_terminate = module.terminate_process_tree
        module.subprocess.Popen = lambda *_args, **_kwargs: FakeProcess()
        module.terminate_process_tree = lambda process: calls.append(("terminate", process.pid))
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = module.execute_cli(
                    {"mode": "runtime", "runtime_python": "C:/Python/python.exe"},
                    ["status"],
                    env={"CODEX_THREAD_RECALL_WRAPPER_TIMEOUT_SEC": "1"},
                )
                payload = json.loads(buffer.getvalue())
        finally:
            module.subprocess.Popen = original_popen
            module.terminate_process_tree = original_terminate

        self.assertEqual(exit_code, 124)
        self.assertEqual(payload["error"], "wrapper_timeout")
        self.assertEqual(calls, [("terminate", 4243)])


if __name__ == "__main__":
    unittest.main()
