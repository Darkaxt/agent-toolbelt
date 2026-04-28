import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from whatsapp_wacli_agent import agent  # noqa: E402


class FakeRunner:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.commands = []
        self.envs = []

    def __call__(self, command, *, timeout_sec, env=None):
        self.commands.append(command)
        self.envs.append(env or {})
        payload = self.payloads.pop(0)
        return agent.ProcessResult(
            returncode=payload.get("returncode", 0),
            stdout=json.dumps(payload.get("stdout", {})),
            stderr=payload.get("stderr", ""),
        )


class WhatsAppWacliAgentTests(unittest.TestCase):
    def make_config(self, temp_dir):
        root = Path(temp_dir)
        fake_wacli = root / "wacli.exe"
        fake_wacli.write_text("", encoding="utf-8")
        store = root / "store"
        store.mkdir()
        return agent.Config(wacli_path=fake_wacli, store_dir=store)

    def write_lid_mapping(self, store_dir, *, lid, pn):
        conn = sqlite3.connect(store_dir / "session.db")
        try:
            conn.execute("create table if not exists whatsmeow_lid_map (lid text primary key, pn text not null)")
            conn.execute("insert or replace into whatsmeow_lid_map (lid, pn) values (?, ?)", (lid, pn))
            conn.commit()
        finally:
            conn.close()

    def write_session_contacts(self, store_dir, rows):
        conn = sqlite3.connect(store_dir / "session.db")
        try:
            conn.execute(
                """
                create table if not exists whatsmeow_contacts (
                    our_jid text,
                    their_jid text,
                    first_name text,
                    full_name text,
                    push_name text,
                    business_name text,
                    redacted_phone text
                )
                """
            )
            conn.executemany(
                """
                insert into whatsmeow_contacts (
                    our_jid,
                    their_jid,
                    first_name,
                    full_name,
                    push_name,
                    business_name,
                    redacted_phone
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def write_message_counts(self, store_dir, counts):
        conn = sqlite3.connect(store_dir / "wacli.db")
        try:
            conn.execute("create table messages (chat_jid text not null)")
            for jid, count in counts.items():
                conn.executemany(
                    "insert into messages (chat_jid) values (?)",
                    [(jid,) for _ in range(count)],
                )
            conn.commit()
        finally:
            conn.close()

    def write_chat_rows(self, store_dir, rows):
        conn = sqlite3.connect(store_dir / "wacli.db")
        try:
            conn.execute(
                "create table chats (jid text primary key, kind text not null, name text, last_message_ts integer)"
            )
            conn.executemany(
                "insert into chats (jid, kind, name, last_message_ts) values (?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def write_chat_message_times(self, store_dir, *, jid, message_timestamps, chat_last_message_ts):
        conn = sqlite3.connect(store_dir / "wacli.db")
        try:
            conn.execute(
                "create table messages (chat_jid text not null, ts integer not null)"
            )
            conn.execute(
                "create table chats (jid text primary key, kind text not null, name text, last_message_ts integer)"
            )
            conn.executemany(
                "insert into messages (chat_jid, ts) values (?, ?)",
                [(jid, ts) for ts in message_timestamps],
            )
            conn.execute(
                "insert into chats (jid, kind, name, last_message_ts) values (?, ?, ?, ?)",
                (jid, "contact", "Demo Contact", chat_last_message_ts),
            )
            conn.commit()
        finally:
            conn.close()

    def write_media_message_metadata(
        self,
        store_dir,
        *,
        chat_jid,
        msg_id,
        media_type="image",
        media_caption="db caption",
        filename="receipt.jpg",
        mime_type="image/jpeg",
        file_length=12345,
        local_path="C:\\tmp\\media\\receipt.jpg",
        downloaded_at="2026-04-28T13:00:00Z",
    ):
        conn = sqlite3.connect(store_dir / "wacli.db")
        try:
            conn.execute(
                """
                create table messages (
                    chat_jid text not null,
                    msg_id text not null,
                    media_type text,
                    media_caption text,
                    filename text,
                    mime_type text,
                    file_length integer,
                    local_path text,
                    downloaded_at text,
                    media_key text,
                    direct_path text,
                    file_sha256 text,
                    file_enc_sha256 text
                )
                """
            )
            conn.execute(
                """
                insert into messages (
                    chat_jid,
                    msg_id,
                    media_type,
                    media_caption,
                    filename,
                    mime_type,
                    file_length,
                    local_path,
                    downloaded_at,
                    media_key,
                    direct_path,
                    file_sha256,
                    file_enc_sha256
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_jid,
                    msg_id,
                    media_type,
                    media_caption,
                    filename,
                    mime_type,
                    file_length,
                    local_path,
                    downloaded_at,
                    "secret-key",
                    "https://mmg.whatsapp.net/private",
                    "sha",
                    "enc-sha",
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def test_builds_argument_list_without_shell_passthrough(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = agent.Config(
                wacli_path=Path(temp_dir) / "wacli.exe",
                store_dir=Path(temp_dir) / "store",
            )
            command = agent.build_wacli_command(cfg, ["messages", "list", "--limit", "2"])

        self.assertIsInstance(command, list)
        self.assertIn("--json", command)
        self.assertIn("--store", command)
        self.assertEqual(command[-4:], ["messages", "list", "--limit", "2"])

    def test_default_runner_forces_utf8_decoding_with_replacement(self):
        completed = agent.subprocess.CompletedProcess(
            args=["wacli"],
            returncode=0,
            stdout='{"ok": true}',
            stderr="",
        )

        with patch.object(agent.subprocess, "run", return_value=completed) as run:
            result = agent.default_runner(["wacli"], timeout_sec=5)

        self.assertEqual(result.stdout, '{"ok": true}')
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")

    def test_resolve_config_prefers_path_before_local_tools_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_wacli = root / "Tools" / "wacli" / "wacli.exe"
            path_wacli = root / "path-bin" / "wacli.exe"
            local_wacli.parent.mkdir(parents=True)
            path_wacli.parent.mkdir(parents=True)
            local_wacli.write_text("legacy fallback", encoding="utf-8")
            path_wacli.write_text("path tool", encoding="utf-8")

            original_local_appdata = agent.os.environ.get("LOCALAPPDATA")
            original_path = agent.os.environ.get("PATH")
            agent.os.environ.pop(agent.WACLI_PATH_ENV, None)
            agent.os.environ.pop(agent.WACLI_STORE_ENV, None)
            agent.os.environ["LOCALAPPDATA"] = str(root)
            agent.os.environ["PATH"] = str(path_wacli.parent)
            try:
                with patch.object(agent.shutil, "which", side_effect=lambda name: str(path_wacli) if name == "wacli.exe" else None):
                    cfg = agent.resolve_config()
            finally:
                if original_local_appdata is None:
                    agent.os.environ.pop("LOCALAPPDATA", None)
                else:
                    agent.os.environ["LOCALAPPDATA"] = original_local_appdata
                if original_path is None:
                    agent.os.environ.pop("PATH", None)
                else:
                    agent.os.environ["PATH"] = original_path

        self.assertEqual(cfg.wacli_path, path_wacli.resolve())

    def test_find_chat_resolves_single_match(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "chats": [
                            {"jid": "123@s.whatsapp.net", "name": "Demo Contact"}
                        ]
                    }
                }
            ]
        )

        result = agent.find_chat("Demo", runner=runner)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["chat"]["jid"], "123@s.whatsapp.net")

    def test_find_chat_handles_wacli_data_shape_and_uppercase_jid(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": [
                            {
                                "JID": "15557654321@s.whatsapp.net",
                                "Name": "Demo Contact",
                            }
                        ],
                    }
                }
            ]
        )

        result = agent.find_chat("Demo Contact", runner=runner)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["chat"]["jid"], "15557654321@s.whatsapp.net")
        self.assertEqual(result["result"]["chat"]["name"], "Demo Contact")

    def test_latest_uses_normalized_jid_from_chat_resolution(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": [
                            {
                                "JID": "15557654321@s.whatsapp.net",
                                "Name": "Demo Contact",
                            }
                        ],
                    }
                },
                {"stdout": {"success": True, "data": []}},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            result = agent.latest(
                "Demo Contact",
                runner=runner,
                config=cfg,
                auto_backfill=False,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(runner.commands[1][-4:], ["--chat", "15557654321@s.whatsapp.net", "--limit", "20"])

    def test_find_chat_refuses_ambiguous_matches(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "chats": [
                            {"jid": "1@s.whatsapp.net", "name": "Demo A"},
                            {"jid": "2@s.whatsapp.net", "name": "Demo B"},
                        ]
                    }
                }
            ]
        )

        result = agent.find_chat("Demo", runner=runner)

        self.assertFalse(result["ok"])
        self.assertIn("ambiguous_chat", result["warnings"])

    def test_find_chat_falls_back_to_contact_search(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
                {
                    "stdout": {
                        "success": True,
                        "data": [
                            {
                                "JID": "15551234567@s.whatsapp.net",
                                "Phone": "15551234567",
                                "Name": "Profile Alias",
                                "Alias": "",
                            }
                        ],
                    }
                },
            ]
        )

        result = agent.find_chat("Profile Alias", runner=runner)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["chat"]["jid"], "15551234567@s.whatsapp.net")
        self.assertEqual(result["result"]["chat"]["name"], "Profile Alias")
        self.assertEqual(result["result"]["chat"]["source"], "contact")
        self.assertIn("contacts", runner.commands[1])

    def test_find_chat_falls_back_to_local_chat_metadata_for_non_contact_chat(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_chat_rows(
                cfg.store_dir,
                [("123@lid", "unknown", "Non Contact Chat", 1777380000)],
            )
            result = agent.find_chat("Non Contact", runner=runner, config=cfg)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["chat"]["jid"], "123@lid")
        self.assertEqual(result["result"]["chat"]["source"], "local_chat")
        self.assertEqual(len(runner.commands), 1)

    def test_find_chat_uses_archived_store_alias_when_fresh_store_keeps_only_jid_name(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
                {"stdout": {"success": True, "data": []}},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_message_counts(cfg.store_dir, {"123@lid": 2})
            archived_store = cfg.store_dir.parent / "store-stale-20260428-152530"
            archived_store.mkdir()
            self.write_chat_rows(
                archived_store,
                [("123@lid", "unknown", "Archived Alias", 1777370000)],
            )

            result = agent.find_chat("Archived Alias", runner=runner, config=cfg)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["chat"]["jid"], "123@lid")
        self.assertEqual(result["result"]["chat"]["source"], "archived_chat_alias:store-stale-20260428-152530")
        self.assertIn("resolved_from_archived_store_alias", result["warnings"])
        self.assertIn("contacts", runner.commands[1])

    def test_find_chat_resolves_non_contact_from_live_session_push_name(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_lid_mapping(cfg.store_dir, lid="193793236189416", pn="35799041717")
            self.write_message_counts(cfg.store_dir, {"193793236189416@lid": 3})
            self.write_session_contacts(
                cfg.store_dir,
                [
                    (
                        "34610895060:47@s.whatsapp.net",
                        "35799041717@s.whatsapp.net",
                        None,
                        None,
                        "Monzer",
                        None,
                        None,
                    )
                ],
            )

            result = agent.find_chat("Monzer", runner=runner, config=cfg)

        self.assertTrue(result["ok"])
        chat = result["result"]["chat"]
        self.assertEqual(chat["jid"], "193793236189416@lid")
        self.assertEqual(chat["source"], "live_session_contact")
        self.assertEqual(chat["resolved_jid"], "193793236189416@lid")
        self.assertEqual(chat["contact_jid"], "35799041717@s.whatsapp.net")
        self.assertEqual(chat["phone"], "35799041717")
        self.assertEqual(chat["phone_jid"], "35799041717@s.whatsapp.net")
        self.assertEqual(chat["display_label"], "Monzer")
        self.assertEqual(len(runner.commands), 1)

    def test_find_chat_resolves_phone_fragments_through_live_session_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_lid_mapping(cfg.store_dir, lid="193793236189416", pn="35799041717")
            self.write_message_counts(cfg.store_dir, {"193793236189416@lid": 3})
            self.write_session_contacts(
                cfg.store_dir,
                [
                    (
                        "34610895060:47@s.whatsapp.net",
                        "35799041717@s.whatsapp.net",
                        None,
                        None,
                        "Monzer",
                        None,
                        None,
                    )
                ],
            )

            for query in ("+357 99 041717", "+35799041717", "99041717", "041717"):
                with self.subTest(query=query):
                    runner = FakeRunner([{"stdout": {"success": True, "data": []}}])
                    result = agent.find_chat(query, runner=runner, config=cfg)

                    self.assertTrue(result["ok"])
                    self.assertEqual(result["result"]["chat"]["jid"], "193793236189416@lid")
                    self.assertEqual(result["result"]["chat"]["source"], "live_session_contact")

    def test_live_session_metadata_beats_archived_alias(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_lid_mapping(cfg.store_dir, lid="193793236189416", pn="35799041717")
            self.write_message_counts(cfg.store_dir, {"193793236189416@lid": 3})
            self.write_session_contacts(
                cfg.store_dir,
                [
                    (
                        "34610895060:47@s.whatsapp.net",
                        "35799041717@s.whatsapp.net",
                        None,
                        None,
                        "Monzer",
                        None,
                        None,
                    )
                ],
            )
            archived_store = cfg.store_dir.parent / "store-stale-20260428-152530"
            archived_store.mkdir()
            self.write_chat_rows(
                archived_store,
                [("193793236189416@lid", "unknown", "Monzer", 1777370000)],
            )

            result = agent.find_chat("Monzer", runner=runner, config=cfg)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["chat"]["source"], "live_session_contact")
        self.assertNotIn("resolved_from_archived_store_alias", result.get("warnings", []))

    def test_ambiguous_phone_fragment_fails_closed(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_lid_mapping(cfg.store_dir, lid="111", pn="35799041717")
            self.write_lid_mapping(cfg.store_dir, lid="222", pn="44777041717")
            self.write_message_counts(cfg.store_dir, {"111@lid": 1, "222@lid": 1})

            result = agent.find_chat("041717", runner=runner, config=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("ambiguous_chat", result["warnings"])

    def test_too_short_phone_fragment_does_not_match_live_lid_map(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
                {"stdout": {"success": True, "data": []}},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_lid_mapping(cfg.store_dir, lid="193793236189416", pn="35799041717")
            self.write_message_counts(cfg.store_dir, {"193793236189416@lid": 3})

            result = agent.find_chat("1717", runner=runner, config=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("chat_not_found", result["warnings"])

    def test_is_jid_accepts_lid_jids(self):
        self.assertTrue(agent.is_jid("900001234567@lid"))

    def test_phone_number_jid_maps_to_lid_from_session_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_lid_mapping(cfg.store_dir, lid="900001234567", pn="15551234567")

            resolved = agent.lid_jid_for_phone_jid(cfg, "15551234567@s.whatsapp.net")

        self.assertEqual(resolved, "900001234567@lid")

    def test_latest_prefers_chat_jid_when_message_store_is_keyed_by_phone_jid(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
                {
                    "stdout": {
                        "success": True,
                        "data": [
                            {
                                "JID": "15551234567@s.whatsapp.net",
                                "Phone": "15551234567",
                                "Name": "Profile Alias",
                            }
                        ],
                    }
                },
                {"stdout": {"success": True, "data": {"messages": [{"MsgID": "m1"}]}}},
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_lid_mapping(cfg.store_dir, lid="900001234567", pn="15551234567")
            self.write_message_counts(
                cfg.store_dir,
                {
                    "15551234567@s.whatsapp.net": 5,
                    "900001234567@lid": 0,
                },
            )

            result = agent.latest("Profile Alias", limit=1, runner=runner, config=cfg)

        self.assertTrue(result["ok"])
        self.assertEqual(runner.commands[2][-4:], ["--chat", "15551234567@s.whatsapp.net", "--limit", "1"])
        self.assertEqual(result["result"]["resolution"]["contact_jid"], "15551234567@s.whatsapp.net")
        self.assertEqual(result["result"]["resolution"]["resolved_jid"], "900001234567@lid")
        self.assertEqual(result["result"]["resolution"]["resolution_source"], "pn_lid_map")

    def test_invoke_history_read_retries_alternate_jid_when_messages_are_null(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": {"messages": None}}},
                {"stdout": {"success": True, "data": {"messages": [{"MsgID": "m1"}]}}},
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            response, used_jid, attempted_jids = agent.invoke_history_read(
                operation="latest",
                jids=["900001234567@lid", "15551234567@s.whatsapp.net"],
                command_builder=lambda jid: ["messages", "list", "--chat", jid, "--limit", "1"],
                runner=runner,
                config=cfg,
                timeout_sec=agent.DEFAULT_TIMEOUT_SEC,
            )

        self.assertTrue(response["ok"])
        self.assertEqual(used_jid, "15551234567@s.whatsapp.net")
        self.assertEqual(attempted_jids, ["900001234567@lid", "15551234567@s.whatsapp.net"])
        self.assertEqual(runner.commands[0][-4:], ["--chat", "900001234567@lid", "--limit", "1"])
        self.assertEqual(runner.commands[1][-4:], ["--chat", "15551234567@s.whatsapp.net", "--limit", "1"])
        self.assertEqual(len(response["result"]["payload"]["data"]["messages"]), 1)
        self.assertIn("jid_fallback_used", response["warnings"])

    def test_latest_normalizes_null_messages_when_no_alternate_jid_exists(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": {"messages": None}}},
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)

            result = agent.latest(
                "15551234567@s.whatsapp.net",
                limit=1,
                runner=runner,
                config=cfg,
                auto_backfill=False,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["payload"]["data"]["messages"], [])
        self.assertIn("messages_null_normalized", result["warnings"])

    def test_latest_fails_closed_when_chat_metadata_is_newer_than_message_store(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {"MsgID": "m2", "Timestamp": 1776711328},
                                {"MsgID": "m1", "Timestamp": 1776620000},
                            ]
                        },
                    }
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_chat_message_times(
                cfg.store_dir,
                jid="193793236189416@lid",
                message_timestamps=[1776620000, 1776711328],
                chat_last_message_ts=1777376212,
            )

            result = agent.latest("193793236189416@lid", limit=2, runner=runner, config=cfg)

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("message_store_lag", result["warnings"])
        self.assertIn("recreat", result["stderr"].lower())
        self.assertEqual(result["result"]["backfill"]["reason"], "requested_limit_satisfied")
        freshness = result["result"]["message_store_freshness"]
        self.assertTrue(freshness["stale"])
        self.assertEqual(freshness["chat_last_message_at"], "2026-04-28T11:36:52Z")
        self.assertEqual(freshness["latest_readable_message_at"], "2026-04-20T18:55:28Z")
        self.assertEqual(freshness["gap_seconds"], 664884)
        self.assertEqual(freshness["recovery"]["recommended_action"], "recreate_session")
        self.assertIn("fresh store", freshness["recovery"]["message"])
        self.assertEqual(len(result["result"]["payload"]["data"]["messages"]), 2)

    def test_latest_no_backfill_still_reports_message_store_lag(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {"messages": [{"MsgID": "m1", "Timestamp": 1776711328}]},
                    }
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_chat_message_times(
                cfg.store_dir,
                jid="193793236189416@lid",
                message_timestamps=[1776711328],
                chat_last_message_ts=1777376212,
            )

            result = agent.latest(
                "193793236189416@lid",
                limit=20,
                runner=runner,
                config=cfg,
                auto_backfill=False,
            )

        self.assertFalse(result["ok"])
        self.assertIn("message_store_lag", result["warnings"])
        self.assertEqual(result["result"]["backfill"]["backfill_attempted"], False)
        self.assertTrue(result["result"]["message_store_freshness"]["stale"])
        self.assertEqual(
            result["result"]["message_store_freshness"]["recovery"]["recommended_action"],
            "recreate_session",
        )

    def test_latest_stays_ok_when_message_store_reaches_chat_metadata(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {"messages": [{"MsgID": "m1", "Timestamp": 1777376212}]},
                    }
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_chat_message_times(
                cfg.store_dir,
                jid="193793236189416@lid",
                message_timestamps=[1777376212],
                chat_last_message_ts=1777376212,
            )

            result = agent.latest(
                "193793236189416@lid",
                limit=20,
                runner=runner,
                config=cfg,
                auto_backfill=False,
            )

        self.assertTrue(result["ok"])
        self.assertNotIn("message_store_lag", result["warnings"])
        self.assertFalse(result["result"]["message_store_freshness"]["stale"])

    def test_backfill_prefers_chat_jid_when_message_store_is_keyed_by_phone_jid(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
                {
                    "stdout": {
                        "success": True,
                        "data": [
                            {
                                "JID": "15551234567@s.whatsapp.net",
                                "Phone": "15551234567",
                                "Name": "Profile Alias",
                            }
                        ],
                    }
                },
                {"stdout": {"success": True, "data": {"messages_added": 5}}},
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_lid_mapping(cfg.store_dir, lid="900001234567", pn="15551234567")
            self.write_message_counts(
                cfg.store_dir,
                {
                    "15551234567@s.whatsapp.net": 1,
                    "900001234567@lid": 0,
                },
            )

            result = agent.backfill("Profile Alias", count=20, requests=1, wait_sec=5, runner=runner, config=cfg)

        self.assertTrue(result["ok"])
        self.assertIn("15551234567@s.whatsapp.net", runner.commands[2])
        self.assertEqual(result["result"]["chat"]["contact_jid"], "15551234567@s.whatsapp.net")
        self.assertEqual(result["result"]["chat"]["resolved_jid"], "900001234567@lid")

    def test_search_prefers_chat_jid_when_message_store_is_keyed_by_phone_jid(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
                {
                    "stdout": {
                        "success": True,
                        "data": [
                            {
                                "JID": "15551234567@s.whatsapp.net",
                                "Phone": "15551234567",
                                "Name": "Profile Alias",
                            }
                        ],
                    }
                },
                {"stdout": {"success": True, "data": {"messages": [{"MsgID": "m1"}]}}},
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_lid_mapping(cfg.store_dir, lid="900001234567", pn="15551234567")
            self.write_message_counts(
                cfg.store_dir,
                {
                    "15551234567@s.whatsapp.net": 5,
                    "900001234567@lid": 0,
                },
            )

            result = agent.search_messages("invoice", chat="Profile Alias", limit=5, runner=runner, config=cfg)

        self.assertTrue(result["ok"])
        self.assertEqual(runner.commands[2][-4:], ["--limit", "5", "--chat", "15551234567@s.whatsapp.net"])
        self.assertEqual(result["result"]["resolution"]["used_jid"], "15551234567@s.whatsapp.net")

    def test_latest_reports_seed_missing_when_backfill_has_no_anchor(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": {"messages": []}}},
                {
                    "returncode": 1,
                    "stdout": {
                        "success": False,
                        "error": "no messages for 15551234567@s.whatsapp.net in local DB; run `wacli sync` first",
                    },
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_message_counts(cfg.store_dir, {})

            result = agent.latest("15551234567@s.whatsapp.net", limit=20, runner=runner, config=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("backfill_seed_missing", result["warnings"])
        self.assertEqual(result["result"]["backfill"]["before_count"], 0)

    def test_find_chat_refuses_ambiguous_contact_matches(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": []}},
                {
                    "stdout": {
                        "success": True,
                        "data": [
                            {"JID": "1@s.whatsapp.net", "Name": "Alias A"},
                            {"JID": "2@s.whatsapp.net", "Name": "Alias B"},
                        ],
                    }
                },
            ]
        )

        result = agent.find_chat("Alias", runner=runner)

        self.assertFalse(result["ok"])
        self.assertIn("ambiguous_chat", result["warnings"])

    def test_send_text_requires_confirmation_before_runner(self):
        runner = FakeRunner([])

        result = agent.send_text("123@s.whatsapp.net", "hello", confirm=False, runner=runner)

        self.assertFalse(result["ok"])
        self.assertIn("confirmation_required", result["warnings"])
        self.assertEqual(runner.commands, [])

    def test_confirmed_send_text_invokes_wacli(self):
        runner = FakeRunner([{"stdout": {"sent": True, "id": "msg1"}}])

        result = agent.send_text("123@s.whatsapp.net", "hello", confirm=True, runner=runner)

        self.assertTrue(result["ok"])
        self.assertIn("send", runner.commands[0])
        self.assertIn("text", runner.commands[0])
        self.assertNotIn("--read-only", runner.commands[0])

    def test_read_commands_use_read_only_env(self):
        runner = FakeRunner([{"stdout": {"messages": []}}])

        result = agent.latest("123@s.whatsapp.net", limit=2, runner=runner, auto_backfill=False)

        self.assertTrue(result["ok"])
        self.assertEqual(runner.envs[0].get("WACLI_READONLY"), "1")

    def test_backfill_resolves_chat_and_reports_count_delta(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": [{"JID": "15557654321@s.whatsapp.net", "Name": "Demo Contact"}],
                    }
                },
                {
                    "stdout": {
                        "success": True,
                        "data": {"messages_added": 100, "requests_sent": 1},
                    }
                },
            ]
        )
        counts_by_jid = {
            "15557654321@s.whatsapp.net": [1, 101, 101],
            "900001234567@lid": [0],
        }
        original_counter = agent.message_count_for_chat
        def fake_message_count(config, jid):
            values = counts_by_jid.setdefault(jid, [0])
            if len(values) > 1:
                return values.pop(0)
            return values[0]
        agent.message_count_for_chat = fake_message_count
        try:
            result = agent.backfill("Demo Contact", count=100, requests=3, wait_sec=60, runner=runner)
        finally:
            agent.message_count_for_chat = original_counter

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["before_count"], 1)
        self.assertEqual(result["result"]["after_count"], 101)
        self.assertEqual(result["result"]["messages_added"], 100)
        self.assertIn("history", runner.commands[1])
        self.assertIn("backfill", runner.commands[1])

    def test_backfill_refuses_ambiguous_chat_matches(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": [
                            {"JID": "1@s.whatsapp.net", "Name": "Demo A"},
                            {"JID": "2@s.whatsapp.net", "Name": "Demo B"},
                        ],
                    }
                }
            ]
        )

        result = agent.backfill("Demo", runner=runner)

        self.assertFalse(result["ok"])
        self.assertIn("ambiguous_chat", result["warnings"])

    def test_latest_auto_backfills_when_results_are_below_limit(self):
        runner = FakeRunner(
            [
                {"stdout": {"success": True, "data": {"messages": [{"MsgID": "m1"}]}}},
                {"stdout": {"success": True, "data": {"messages_added": 1}}},
                {"stdout": {"success": True, "data": {"messages": [{"MsgID": "m2"}, {"MsgID": "m1"}]}}},
            ]
        )
        counts_by_jid = {"123@s.whatsapp.net": [1, 1, 2, 2, 2]}
        original_counter = agent.message_count_for_chat
        def fake_message_count(config, jid):
            values = counts_by_jid.setdefault(jid, [0])
            if len(values) > 1:
                return values.pop(0)
            return values[0]
        agent.message_count_for_chat = fake_message_count
        try:
            result = agent.latest("123@s.whatsapp.net", limit=2, runner=runner)
        finally:
            agent.message_count_for_chat = original_counter

        self.assertTrue(result["ok"])
        self.assertEqual(len(runner.commands), 3)
        self.assertIn("history", runner.commands[1])
        self.assertTrue(result["result"]["backfill"]["backfill_attempted"])

    def test_latest_no_backfill_disables_auto_backfill(self):
        runner = FakeRunner(
            [{"stdout": {"success": True, "data": {"messages": [{"MsgID": "m1"}]}}}]
        )

        result = agent.latest("123@s.whatsapp.net", limit=2, runner=runner, auto_backfill=False)

        self.assertTrue(result["ok"])
        self.assertEqual(len(runner.commands), 1)
        self.assertEqual(result["result"]["backfill"]["backfill_attempted"], False)

    def test_latest_adds_presentation_display_name_from_resolution(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": [
                            {"JID": "193793236189416@lid", "Name": "Monzer"}
                        ],
                    }
                },
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "193793236189416@lid",
                                    "ChatName": "193793236189416@lid",
                                    "Text": "hello",
                                    "DisplayText": "hello",
                                }
                            ]
                        },
                    }
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            result = agent.latest(
                "Monzer",
                limit=1,
                runner=runner,
                config=cfg,
                auto_backfill=False,
            )

        message = result["result"]["payload"]["data"]["messages"][0]
        self.assertEqual(message["ChatName"], "193793236189416@lid")
        self.assertEqual(message["presentation"]["chat_display_name"], "Monzer")
        self.assertEqual(message["presentation"]["chat_display_name_source"], "resolution")
        self.assertEqual(message["presentation"]["text"], "hello")

    def test_presentation_uses_display_text_for_edited_messages(self):
        message = {
            "ChatJID": "123@s.whatsapp.net",
            "ChatName": "Demo",
            "Text": "",
            "DisplayText": "Edited message: corrected text",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            presentation = agent.presentation_for_message(
                message,
                config=cfg,
                resolution=None,
            )

        self.assertEqual(presentation["text"], "Edited message: corrected text")
        self.assertEqual(presentation["text_source"], "display_text")
        self.assertTrue(presentation["is_edited"])

    def test_presentation_keeps_media_placeholder_readable(self):
        message = {
            "ChatJID": "123@s.whatsapp.net",
            "ChatName": "Demo",
            "MsgID": "m1",
            "Text": "",
            "DisplayText": "Sent image",
            "MediaType": "image",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            presentation = agent.presentation_for_message(
                message,
                config=cfg,
                resolution=None,
            )

        self.assertEqual(presentation["media_type"], "image")
        self.assertEqual(presentation["text"], "Sent image")
        self.assertEqual(presentation["text_source"], "media_placeholder")
        self.assertEqual(presentation["media_label"], "Sent image")

    def test_presentation_media_caption_outranks_generic_placeholder(self):
        message = {
            "ChatJID": "123@s.whatsapp.net",
            "ChatName": "Demo",
            "MsgID": "m1",
            "Text": "Sent image",
            "DisplayText": "Sent image",
            "MediaType": "image",
            "MediaCaption": "receipt photo",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            presentation = agent.presentation_for_message(
                message,
                config=cfg,
                resolution=None,
            )

        self.assertEqual(presentation["text"], "receipt photo")
        self.assertEqual(presentation["text_source"], "media_caption")
        self.assertEqual(presentation["media_label"], "receipt photo")

    def test_latest_include_media_downloads_bounded_artifacts(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "123@s.whatsapp.net",
                                    "ChatName": "Demo",
                                    "DisplayText": "Sent image",
                                    "MediaType": "image",
                                }
                            ]
                        },
                    }
                },
                {
                    "stdout": {
                        "success": True,
                        "data": {"path": "C:\\tmp\\media\\m1.jpg"},
                    }
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            result = agent.latest(
                "123@s.whatsapp.net",
                limit=1,
                runner=runner,
                config=cfg,
                auto_backfill=False,
                include_media=True,
                media_limit=1,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(len(runner.commands), 2)
        self.assertEqual(runner.commands[1][-6:], ["media", "download", "--id", "m1", "--chat", "123@s.whatsapp.net"])
        self.assertEqual(runner.envs[1], {})
        message = result["result"]["payload"]["data"]["messages"][0]
        self.assertEqual(message["presentation"]["media"]["artifact_path"], "C:\\tmp\\media\\m1.jpg")
        self.assertTrue(message["presentation"]["media"]["downloaded"])
        self.assertEqual(result["result"]["media"]["media_attempted"], 1)

    def test_presentation_enriches_media_metadata_from_local_db(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "123@s.whatsapp.net",
                                    "ChatName": "Demo",
                                    "DisplayText": "Sent image",
                                    "MediaType": "image",
                                }
                            ]
                        },
                    }
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_media_message_metadata(
                cfg.store_dir,
                chat_jid="123@s.whatsapp.net",
                msg_id="m1",
            )
            result = agent.latest(
                "123@s.whatsapp.net",
                limit=1,
                runner=runner,
                config=cfg,
                auto_backfill=False,
            )

        presentation = result["result"]["payload"]["data"]["messages"][0]["presentation"]
        self.assertEqual(presentation["mime_type"], "image/jpeg")
        self.assertEqual(presentation["file_length"], 12345)
        self.assertEqual(presentation["filename"], "receipt.jpg")
        self.assertEqual(presentation["local_path"], "C:\\tmp\\media\\receipt.jpg")
        self.assertEqual(presentation["downloaded_at"], "2026-04-28T13:00:00Z")
        self.assertNotIn("media_key", presentation)
        self.assertNotIn("direct_path", presentation)
        self.assertNotIn("file_sha256", presentation)

    def test_locked_media_download_uses_existing_local_path_without_partial_failure(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "123@s.whatsapp.net",
                                    "ChatName": "Demo",
                                    "DisplayText": "Sent image",
                                    "MediaType": "image",
                                }
                            ]
                        },
                    }
                },
                {
                    "returncode": 1,
                    "stdout": {},
                    "stderr": "store is locked",
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_media_message_metadata(
                cfg.store_dir,
                chat_jid="123@s.whatsapp.net",
                msg_id="m1",
                local_path="C:\\tmp\\media\\receipt.jpg",
            )
            result = agent.latest(
                "123@s.whatsapp.net",
                limit=1,
                runner=runner,
                config=cfg,
                auto_backfill=False,
                include_media=True,
                media_limit=1,
            )

        media = result["result"]["payload"]["data"]["messages"][0]["presentation"]["media"]
        self.assertTrue(media["available"])
        self.assertEqual(media["artifact_path"], "C:\\tmp\\media\\receipt.jpg")
        self.assertEqual(media["artifact_source"], "existing_local_path")
        self.assertFalse(media["downloaded"])
        self.assertIn("store is locked", media["download_attempt_error"])
        self.assertNotIn("download_error", media)
        self.assertEqual(result["result"]["media"]["media_errors"], 0)
        self.assertNotIn("media_download_partial_failure", result["warnings"])

    def test_media_filename_derives_from_local_path_when_db_filename_missing(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "123@s.whatsapp.net",
                                    "ChatName": "Demo",
                                    "DisplayText": "Sent image",
                                    "MediaType": "image",
                                }
                            ]
                        },
                    }
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            self.write_media_message_metadata(
                cfg.store_dir,
                chat_jid="123@s.whatsapp.net",
                msg_id="m1",
                filename="",
                local_path="C:\\tmp\\media\\derived-name.jpg",
            )
            result = agent.latest(
                "123@s.whatsapp.net",
                limit=1,
                runner=runner,
                config=cfg,
                auto_backfill=False,
            )

        presentation = result["result"]["payload"]["data"]["messages"][0]["presentation"]
        self.assertEqual(presentation["filename"], "derived-name.jpg")

    def test_media_filename_derives_from_downloaded_artifact_path(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "123@s.whatsapp.net",
                                    "ChatName": "Demo",
                                    "DisplayText": "Sent image",
                                    "MediaType": "image",
                                }
                            ]
                        },
                    }
                },
                {
                    "stdout": {
                        "success": True,
                        "data": {"path": "C:\\tmp\\media\\downloaded-name.jpg"},
                    }
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = self.make_config(temp_dir)
            result = agent.latest(
                "123@s.whatsapp.net",
                limit=1,
                runner=runner,
                config=cfg,
                auto_backfill=False,
                include_media=True,
                media_limit=1,
            )

        media = result["result"]["payload"]["data"]["messages"][0]["presentation"]["media"]
        self.assertEqual(media["filename"], "downloaded-name.jpg")

    def test_draft_reply_context_uses_presentation_fields(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "123@s.whatsapp.net",
                                    "ChatName": "123@s.whatsapp.net",
                                    "Text": "",
                                    "DisplayText": "Edited message: yes",
                                }
                            ]
                        },
                    }
                }
            ]
        )
        result = agent.draft_reply(
            "123@s.whatsapp.net",
            "reply politely",
            runner=runner,
            limit=1,
        )

        message = result["result"]["context"]["data"]["messages"][0]
        self.assertEqual(message["presentation"]["text"], "Edited message: yes")
        self.assertTrue(message["presentation"]["is_edited"])

    def test_draft_reply_returns_model_free_draft_packet(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "123@s.whatsapp.net",
                                    "ChatName": "123@s.whatsapp.net",
                                    "Text": "Can you confirm?",
                                    "DisplayText": "Can you confirm?",
                                    "FromMe": False,
                                    "Timestamp": "2026-04-28T13:00:00Z",
                                }
                            ]
                        },
                    }
                }
            ]
        )
        result = agent.draft_reply(
            "123@s.whatsapp.net",
            "Confirm that I will review it today.",
            runner=runner,
            limit=1,
        )

        packet = result["result"]["draft_packet"]
        self.assertFalse(result["result"]["mutation_performed"])
        self.assertEqual(packet["draft_status"], "needs_model_generation")
        self.assertEqual(packet["instruction"], "Confirm that I will review it today.")
        self.assertEqual(packet["context_messages"][0]["text"], "Can you confirm?")
        self.assertEqual(packet["context_messages"][0]["message_id"], "m1")
        self.assertEqual(packet["media_artifacts"], [])
        self.assertIn("Return only the proposed reply text", packet["model_prompt"])

    def test_draft_reply_include_media_carries_artifact_paths(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "123@s.whatsapp.net",
                                    "ChatName": "Demo",
                                    "DisplayText": "Sent image",
                                    "MediaType": "image",
                                }
                            ]
                        },
                    }
                },
                {
                    "stdout": {
                        "success": True,
                        "data": {"path": "C:\\tmp\\media\\m1.jpg"},
                    }
                },
            ]
        )
        result = agent.draft_reply(
            "123@s.whatsapp.net",
            "Reply after considering the image.",
            runner=runner,
            limit=1,
            include_media=True,
            media_limit=1,
        )

        artifact = result["result"]["draft_packet"]["media_artifacts"][0]
        self.assertEqual(artifact["message_id"], "m1")
        self.assertEqual(artifact["artifact_path"], "C:\\tmp\\media\\m1.jpg")
        self.assertTrue(artifact["downloaded"])

    def test_draft_reply_packet_is_compact_and_exposes_media_availability(self):
        runner = FakeRunner(
            [
                {
                    "stdout": {
                        "success": True,
                        "data": {
                            "messages": [
                                {
                                    "MsgID": "m1",
                                    "ChatJID": "123@s.whatsapp.net",
                                    "ChatName": "Demo",
                                    "DisplayText": "Sent image",
                                    "MediaType": "image",
                                    "FromMe": False,
                                }
                            ]
                        },
                    }
                },
                {
                    "stdout": {
                        "success": True,
                        "data": {"path": "C:\\tmp\\media\\m1.jpg"},
                    }
                },
            ]
        )
        result = agent.draft_reply(
            "123@s.whatsapp.net",
            "Reply after considering the image.",
            runner=runner,
            limit=1,
            include_media=True,
            media_limit=1,
        )

        packet = result["result"]["draft_packet"]
        self.assertEqual(packet["context_message_count"], 1)
        self.assertEqual(packet["media_artifact_count"], 1)
        self.assertEqual(packet["context_summary"]["message_count"], 1)
        self.assertEqual(packet["context_summary"]["messages"][0]["text"], "Sent image")
        self.assertEqual(packet["context_summary"]["messages"][0]["media_type"], "image")
        context_message = packet["context_messages"][0]
        self.assertNotIn("sender_jid", context_message)
        self.assertNotIn("sender_name", context_message)
        artifact = packet["media_artifacts"][0]
        self.assertTrue(artifact["available"])
        self.assertEqual(artifact["artifact_source"], "downloaded")

    def test_parse_malformed_json_as_failure(self):
        payload = agent.normalize_process_result(
            operation="status",
            backend="wacli",
            completed=agent.ProcessResult(returncode=0, stdout="{bad", stderr=""),
        )

        self.assertFalse(payload["ok"])
        self.assertIn("malformed_json", payload["warnings"])

    def test_auth_login_popup_launches_raw_console_without_json(self):
        launched = []

        def launcher(command):
            launched.append(command)
            return 1234

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_wacli = Path(temp_dir) / "wacli.exe"
            fake_wacli.write_text("", encoding="utf-8")
            cfg = agent.Config(
                wacli_path=fake_wacli,
                store_dir=Path(temp_dir) / "store",
            )
            result = agent.auth_login(popup=True, config=cfg, launcher=launcher)

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "wacli-popup")
        self.assertEqual(result["result"]["pid"], 1234)
        self.assertTrue(result["result"]["login_process_safety"]["do_not_terminate_from_agent"])
        self.assertTrue(result["result"]["login_process_safety"]["requires_user_approval_before_kill"])
        self.assertIn("Do not terminate", result["result"]["note"])
        self.assertEqual(len(launched), 1)
        command_text = " ".join(launched[0])
        self.assertIn("wacli.exe", command_text)
        self.assertIn("auth", command_text)
        self.assertIn("Do not close or kill this window", command_text)
        self.assertIn("ask the user before terminating", command_text)
        self.assertNotIn("--json", command_text)

    def test_parser_accepts_auth_login_popup(self):
        parser = agent.build_parser()

        args = parser.parse_args(["auth-login", "--popup"])

        self.assertEqual(args.operation, "auth-login")
        self.assertTrue(args.popup)


if __name__ == "__main__":
    unittest.main()
