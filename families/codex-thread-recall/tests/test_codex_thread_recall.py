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
                    "text": "Published and installed. PR `#11` was merged with commit `ed7982b`. Enabled `artifact-alpha@local-market`.",
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
        self.assertIn("artifact-alpha@local-market", item["qualified_ids"])
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
            make_entry("2026-04-25T08:10:00Z", "event_msg", {"type": "agent_message", "text": "Published `codex-thread-recall`."}),
            make_entry("2026-04-25T08:15:00Z", "event_msg", {"type": "agent_message", "text": "Merged PR `#14` for `codex-thread-recall`."}),
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


if __name__ == "__main__":
    unittest.main()
