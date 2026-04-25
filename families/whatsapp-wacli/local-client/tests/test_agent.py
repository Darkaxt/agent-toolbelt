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
            conn.execute("create table whatsmeow_lid_map (lid text primary key, pn text not null)")
            conn.execute("insert into whatsmeow_lid_map (lid, pn) values (?, ?)", (lid, pn))
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
        self.assertEqual(len(launched), 1)
        command_text = " ".join(launched[0])
        self.assertIn("wacli.exe", command_text)
        self.assertIn("auth", command_text)
        self.assertNotIn("--json", command_text)

    def test_parser_accepts_auth_login_popup(self):
        parser = agent.build_parser()

        args = parser.parse_args(["auth-login", "--popup"])

        self.assertEqual(args.operation, "auth-login")
        self.assertTrue(args.popup)


if __name__ == "__main__":
    unittest.main()
