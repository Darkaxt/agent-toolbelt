import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "outlook-classic-mail" / "src"
CLAUDE_PLUGIN_META_DIR = "." + "claude-plugin"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_outlook_classic_mail import outlook_classic_mail


class OutlookClassicMailBridgeTests(unittest.TestCase):
    def test_resolve_client_home_prefers_env_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_home = Path(temp_dir) / "explicit-client"
            tool_home.mkdir()

            original_value = os.environ.get("OUTLOOK_CLASSIC_MAIL_HOME")
            os.environ["OUTLOOK_CLASSIC_MAIL_HOME"] = str(tool_home)
            try:
                resolved = outlook_classic_mail.resolve_client_home()
            finally:
                if original_value is None:
                    os.environ.pop("OUTLOOK_CLASSIC_MAIL_HOME", None)
                else:
                    os.environ["OUTLOOK_CLASSIC_MAIL_HOME"] = original_value

        self.assertEqual(resolved, tool_home)

    def test_resolve_client_home_uses_local_tools_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            expected = Path(temp_dir) / "Tools" / "outlook-classic-mail"
            expected.mkdir(parents=True)

            original_local_appdata = os.environ.get("LOCALAPPDATA")
            original_tool_home = os.environ.get("OUTLOOK_CLASSIC_MAIL_HOME")
            os.environ["LOCALAPPDATA"] = temp_dir
            os.environ.pop("OUTLOOK_CLASSIC_MAIL_HOME", None)
            try:
                resolved = outlook_classic_mail.resolve_client_home()
            finally:
                if original_local_appdata is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = original_local_appdata
                if original_tool_home is None:
                    os.environ.pop("OUTLOOK_CLASSIC_MAIL_HOME", None)
                else:
                    os.environ["OUTLOOK_CLASSIC_MAIL_HOME"] = original_tool_home

        self.assertEqual(resolved, expected)

    def test_build_client_command_uses_uv_run_project_and_cli_name(self):
        client_home = Path(r"C:\Temp\Tools\outlook-classic-mail")
        command = outlook_classic_mail.build_client_command(
            client_home=client_home,
            operation_args=["accounts"],
            uv_executable="uv.exe",
            queue_timeout_sec=900,
        )

        self.assertEqual(command[:7], ["uv.exe", "run", "--project", str(client_home), "outlook-classic-mail-client", "--queue-timeout-sec", "900"])
        self.assertEqual(command[-1], "accounts")

    def test_standalone_local_client_is_source_controlled(self):
        client_root = REPO_ROOT / "families" / "outlook-classic-mail" / "local-client"

        self.assertTrue((client_root / "pyproject.toml").is_file())
        self.assertTrue((client_root / "src" / "outlook_classic_mail_client" / "client.py").is_file())
        self.assertTrue((client_root / "tests" / "test_client.py").is_file())
        self.assertFalse((client_root / "state").exists())

    def test_invoke_client_normalizes_json_success(self):
        original_run = outlook_classic_mail.run_process
        original_uv = outlook_classic_mail.resolve_uv_executable
        original_home = outlook_classic_mail.resolve_client_home
        captured = {}
        outlook_classic_mail.resolve_uv_executable = lambda: "uv.exe"
        outlook_classic_mail.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\outlook-classic-mail")
        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["timeout_sec"] = kwargs["timeout_sec"]
            return outlook_classic_mail.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "operation": "accounts",
                        "account": None,
                        "store": None,
                        "result": {"accounts": [{"smtp_address": "demo@example.com"}]},
                        "warnings": [],
                        "stderr": "",
                        "exit_code": 0,
                        "queue": {"used": True, "timeout_seconds": 900},
                    }
                ),
                stderr="",
            )
        outlook_classic_mail.run_process = fake_run
        try:
            result = outlook_classic_mail.invoke_client(operation_args=["accounts"], timeout_sec=180, queue_timeout_sec=900)
        finally:
            outlook_classic_mail.run_process = original_run
            outlook_classic_mail.resolve_uv_executable = original_uv
            outlook_classic_mail.resolve_client_home = original_home

        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "accounts")
        self.assertEqual(result["result"]["accounts"][0]["smtp_address"], "demo@example.com")
        self.assertEqual(result["queue"]["timeout_seconds"], 900)
        self.assertEqual(captured["timeout_sec"], 1095)
        self.assertIn("--queue-timeout-sec", captured["command"])
        self.assertEqual(result["wrapper_diagnostics"]["access_model"], "local_outlook_classic_com")
        self.assertFalse(result["wrapper_diagnostics"]["cloud_connector_used"])
        self.assertEqual(result["wrapper_diagnostics"]["client_home_source"], "resolved")
        self.assertEqual(result["wrapper_diagnostics"]["client_home_resolved"], r"C:\Tools\outlook-classic-mail")
        self.assertEqual(result["wrapper_diagnostics"]["queue_timeout_sec"], 900)
        self.assertEqual(result["wrapper_diagnostics"]["command_timeout_sec"], 180)

    def test_invoke_client_reports_missing_uv_cleanly(self):
        original_uv = outlook_classic_mail.resolve_uv_executable
        original_home = outlook_classic_mail.resolve_client_home
        outlook_classic_mail.resolve_uv_executable = lambda: None
        outlook_classic_mail.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\outlook-classic-mail")
        try:
            result = outlook_classic_mail.invoke_client(operation_args=["accounts"])
        finally:
            outlook_classic_mail.resolve_uv_executable = original_uv
            outlook_classic_mail.resolve_client_home = original_home

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 127)
        self.assertIn("uv", result["stderr"].lower())
        self.assertEqual(result["wrapper_diagnostics"]["failure_kind"], "uv_unavailable")
        self.assertFalse(result["wrapper_diagnostics"]["cloud_connector_used"])
        self.assertRegex(result["wrapper_diagnostics"]["invocation_id"], r"^[0-9a-f-]{36}$")

    def test_invoke_client_preserves_client_diagnostics(self):
        original_run = outlook_classic_mail.run_process
        original_uv = outlook_classic_mail.resolve_uv_executable
        original_home = outlook_classic_mail.resolve_client_home
        outlook_classic_mail.resolve_uv_executable = lambda: "uv.exe"
        outlook_classic_mail.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\outlook-classic-mail")

        def fake_run(command, **kwargs):
            return outlook_classic_mail.subprocess.CompletedProcess(
                command,
                74,
                stdout=json.dumps(
                    {
                        "ok": False,
                        "operation": "accounts",
                        "stderr": "outlook_dispatch_failed: Outlook.Application COM dispatch failed.",
                        "exit_code": 74,
                        "result": {},
                        "warnings": [],
                        "client_diagnostics": {
                            "invocation_id": "client-invocation",
                            "failure_kind": "outlook_dispatch_failed",
                        },
                    }
                ),
                stderr="",
            )

        outlook_classic_mail.run_process = fake_run
        try:
            result = outlook_classic_mail.invoke_client(operation_args=["accounts"])
        finally:
            outlook_classic_mail.run_process = original_run
            outlook_classic_mail.resolve_uv_executable = original_uv
            outlook_classic_mail.resolve_client_home = original_home

        self.assertFalse(result["ok"])
        self.assertEqual(result["client_diagnostics"]["failure_kind"], "outlook_dispatch_failed")
        self.assertEqual(result["client_diagnostics"]["invocation_id"], "client-invocation")
        self.assertIn("wrapper_diagnostics", result)

    def test_invoke_client_reports_missing_client_home_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_local_appdata = os.environ.get("LOCALAPPDATA")
            original_tool_home = os.environ.get("OUTLOOK_CLASSIC_MAIL_HOME")
            os.environ["LOCALAPPDATA"] = temp_dir
            os.environ.pop("OUTLOOK_CLASSIC_MAIL_HOME", None)
            try:
                result = outlook_classic_mail.invoke_client(operation_args=["accounts"], client_home=str(Path(temp_dir) / "missing-client"))
            finally:
                if original_local_appdata is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = original_local_appdata
                if original_tool_home is None:
                    os.environ.pop("OUTLOOK_CLASSIC_MAIL_HOME", None)
                else:
                    os.environ["OUTLOOK_CLASSIC_MAIL_HOME"] = original_tool_home

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 127)
        diagnostics = result["wrapper_diagnostics"]
        self.assertEqual(diagnostics["access_model"], "local_outlook_classic_com")
        self.assertFalse(diagnostics["cloud_connector_used"])
        self.assertEqual(diagnostics["failure_kind"], "client_unavailable")
        self.assertIsNone(diagnostics["client_home_resolved"])
        self.assertEqual(diagnostics["queue_timeout_sec"], outlook_classic_mail.DEFAULT_QUEUE_TIMEOUT_SEC)

    def test_invoke_client_reports_wrapper_timeout_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_run = outlook_classic_mail.run_process
            original_uv = outlook_classic_mail.resolve_uv_executable
            outlook_classic_mail.resolve_uv_executable = lambda: "uv.exe"

            def fake_run(command, **kwargs):
                raise outlook_classic_mail.subprocess.TimeoutExpired(command, timeout=kwargs["timeout_sec"], stderr="client busy")

            outlook_classic_mail.run_process = fake_run
            try:
                result = outlook_classic_mail.invoke_client(
                    operation_args=["accounts"],
                    client_home=temp_dir,
                    timeout_sec=12,
                    queue_timeout_sec=34,
                )
            finally:
                outlook_classic_mail.run_process = original_run
                outlook_classic_mail.resolve_uv_executable = original_uv

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 124)
        self.assertIn("client busy", result["stderr"])
        self.assertEqual(result["wrapper_diagnostics"]["failure_kind"], "wrapper_timeout")
        self.assertEqual(result["wrapper_diagnostics"]["command_timeout_sec"], 12)
        self.assertEqual(result["wrapper_diagnostics"]["queue_timeout_sec"], 34)

    def test_build_operation_args_routes_find_folders(self):
        parser = outlook_classic_mail.build_parser()
        args = parser.parse_args(["find-folders", "--query", "lettre24", "--all-accounts", "--limit", "5"])

        operation_args = outlook_classic_mail.build_operation_args(args)

        self.assertEqual(
            operation_args,
            ["find-folders", "--query", "lettre24", "--all-accounts", "--limit", "5"],
        )

    def test_build_operation_args_routes_search_all_folders(self):
        parser = outlook_classic_mail.build_parser()
        args = parser.parse_args(
            [
                "search",
                "--all-folders",
                "--query",
                "lettre24",
                "--all-accounts",
                "--folder-limit",
                "10",
                "--per-folder-limit",
                "5",
            ]
        )

        operation_args = outlook_classic_mail.build_operation_args(args)

        self.assertEqual(
            operation_args,
            [
                "search",
                "--all-folders",
                "--query",
                "lettre24",
                "--all-accounts",
                "--limit",
                "20",
                "--folder-limit",
                "10",
                "--per-folder-limit",
                "5",
            ],
        )

    def test_build_operation_args_routes_cache_search_flags(self):
        parser = outlook_classic_mail.build_parser()
        args = parser.parse_args(
            [
                "search",
                "--all-folders",
                "--query",
                "lettre24",
                "--all-accounts",
                "--folder-limit",
                "10",
                "--per-folder-limit",
                "5",
                "--bypass-cache",
                "--broad-scan",
                "--no-update-cache",
                "--cache-path",
                "state/mail_cache.sqlite",
            ]
        )

        operation_args = outlook_classic_mail.build_operation_args(args)

        self.assertEqual(
            operation_args,
            [
                "search",
                "--all-folders",
                "--query",
                "lettre24",
                "--all-accounts",
                "--limit",
                "20",
                "--folder-limit",
                "10",
                "--per-folder-limit",
                "5",
                "--bypass-cache",
                "--broad-scan",
                "--no-update-cache",
                "--cache-path",
                "state/mail_cache.sqlite",
            ],
        )

    def test_build_operation_args_routes_cache_and_sync_commands(self):
        parser = outlook_classic_mail.build_parser()

        cache_refresh = parser.parse_args(["cache-refresh", "--all-accounts", "--days", "30", "--force"])
        cache_show = parser.parse_args(["cache-show", "--query", "lettre24", "--limit", "5"])
        sync_mail = parser.parse_args(["sync-mail", "--refresh-cache", "--all-accounts"])

        self.assertEqual(
            outlook_classic_mail.build_operation_args(cache_refresh),
            ["cache-refresh", "--all-accounts", "--days", "30", "--force"],
        )
        self.assertEqual(
            outlook_classic_mail.build_operation_args(cache_show),
            ["cache-show", "--query", "lettre24", "--limit", "5"],
        )
        self.assertEqual(
            outlook_classic_mail.build_operation_args(sync_mail),
            ["sync-mail", "--refresh-cache", "--all-accounts", "--days", "90"],
        )

    def test_parser_accepts_queue_timeout(self):
        parser = outlook_classic_mail.build_parser()
        args = parser.parse_args(["--queue-timeout-sec", "45", "accounts"])
        self.assertEqual(args.queue_timeout_sec, 45)

    def test_parser_routes_diagnostics_commands(self):
        parser = outlook_classic_mail.build_parser()

        probe_args = parser.parse_args(["diagnostics-probe"])
        log_args = parser.parse_args(["diagnostics-log", "--limit", "7"])

        self.assertEqual(outlook_classic_mail.build_operation_args(probe_args), ["diagnostics-probe"])
        self.assertEqual(outlook_classic_mail.build_operation_args(log_args), ["diagnostics-log", "--limit", "7"])

    def test_build_operation_args_routes_find_response(self):
        parser = outlook_classic_mail.build_parser()
        args = parser.parse_args(
            [
                "find-response",
                "--account",
                "anchor@example.com",
                "--message-id",
                "anchor-1",
                "--limit",
                "7",
                "--fallback-all-accounts",
                "--exclude-drafts",
            ]
        )

        operation_args = outlook_classic_mail.build_operation_args(args)

        self.assertEqual(
            operation_args,
            [
                "find-response",
                "--account",
                "anchor@example.com",
                "--message-id",
                "anchor-1",
                "--limit",
                "7",
                "--fallback-all-accounts",
                "--exclude-drafts",
            ],
        )

    def test_build_operation_args_routes_move_message(self):
        parser = outlook_classic_mail.build_parser()
        args = parser.parse_args(
            [
                "move-message",
                "--account",
                "demo@example.com",
                "--message-id",
                "msg-1",
                "--target-folder",
                "custom:Inbox/Projects",
                "--confirm",
            ]
        )

        operation_args = outlook_classic_mail.build_operation_args(args)

        self.assertEqual(
            operation_args,
            [
                "move-message",
                "--account",
                "demo@example.com",
                "--message-id",
                "msg-1",
                "--target-folder",
                "custom:Inbox/Projects",
                "--confirm",
            ],
        )

    def test_build_operation_args_routes_draft_send_using_account(self):
        parser = outlook_classic_mail.build_parser()
        args = parser.parse_args(
            [
                "draft-reply",
                "--account",
                "anchor@example.com",
                "--send-using-account",
                "reply@example.com",
                "--message-id",
                "anchor-1",
                "--instruction",
                "Confirm the schedule.",
                "--body",
                "Confirmed.",
                "--create-draft",
                "--confirm",
            ]
        )

        operation_args = outlook_classic_mail.build_operation_args(args)

        self.assertEqual(
            operation_args,
            [
                "draft-reply",
                "--account",
                "anchor@example.com",
                "--message-id",
                "anchor-1",
                "--instruction",
                "Confirm the schedule.",
                "--send-using-account",
                "reply@example.com",
                "--body",
                "Confirmed.",
                "--create-draft",
                "--confirm",
            ],
        )

    def test_build_operation_args_routes_domain_inspection_with_blocklists(self):
        parser = outlook_classic_mail.build_parser()
        args = parser.parse_args(
            [
                "inspect-domains",
                "--account",
                "demo@example.com",
                "--message-id",
                "entry-1",
                "--with-rdap",
                "--young-days",
                "30",
                "--rdap-cache",
                "state/domain_cache.sqlite",
                "--with-blocklists",
                "--blocklist-profile",
                "threat",
                "--blocklist-cache",
                "state/blocklist_cache.sqlite",
            ]
        )

        operation_args = outlook_classic_mail.build_operation_args(args)

        self.assertEqual(
            operation_args,
            [
                "inspect-domains",
                "--account",
                "demo@example.com",
                "--message-id",
                "entry-1",
                "--with-rdap",
                "--young-days",
                "30",
                "--rdap-cache",
                "state/domain_cache.sqlite",
                "--with-blocklists",
                "--blocklist-profile",
                "threat",
                "--blocklist-cache",
                "state/blocklist_cache.sqlite",
            ],
        )

    def test_build_operation_args_routes_blocklist_cache_refresh(self):
        parser = outlook_classic_mail.build_parser()
        args = parser.parse_args(
            [
                "blocklists",
                "refresh",
                "--blocklist-profile",
                "debug-all",
                "--blocklist-cache",
                "state/blocklist_cache.sqlite",
                "--force",
            ]
        )

        operation_args = outlook_classic_mail.build_operation_args(args)

        self.assertEqual(
            operation_args,
            [
                "blocklists",
                "refresh",
                "--blocklist-profile",
                "debug-all",
                "--blocklist-cache",
                "state/blocklist_cache.sqlite",
                "--force",
            ],
        )

    def test_codex_skill_documents_find_response_lookup(self):
        skill_path = (
            REPO_ROOT
            / "families"
            / "outlook-classic-mail"
            / "codex"
            / "skills"
            / "outlook-classic-mail"
            / "SKILL.md"
        )

        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("find-response", skill_text)
        self.assertIn("manual Sent/Drafts searches", skill_text)
        self.assertIn("anchor message", skill_text)

    def test_codex_skill_documents_move_message_preview_flow(self):
        skill_path = (
            REPO_ROOT
            / "families"
            / "outlook-classic-mail"
            / "codex"
            / "skills"
            / "outlook-classic-mail"
            / "SKILL.md"
        )

        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("move-message", skill_text)
        self.assertIn("without `--confirm` as a preview", skill_text)
        self.assertIn("explicit user approval", skill_text)

    def test_codex_skill_documents_draft_thread_and_sender_diagnostics(self):
        skill_path = (
            REPO_ROOT
            / "families"
            / "outlook-classic-mail"
            / "codex"
            / "skills"
            / "outlook-classic-mail"
            / "SKILL.md"
        )

        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("prefer `draft-reply` or `draft-forward`", skill_text)
        self.assertIn("draft_content.thread_content_included", skill_text)
        self.assertIn("draft_placement.actual_send_using_account", skill_text)
        self.assertIn("thread_quote_fallback_used", skill_text)
        self.assertIn("standalone new drafts", skill_text)
        self.assertIn("Treat `--instruction` as guidance only", skill_text)
        self.assertIn("draft_status: needs_body", skill_text)
        self.assertIn("--body \"<final draft text>\" --create-draft --confirm", skill_text)

    def test_codex_skill_documents_cache_and_sync_workflows(self):
        skill_path = (
            REPO_ROOT
            / "families"
            / "outlook-classic-mail"
            / "codex"
            / "skills"
            / "outlook-classic-mail"
            / "SKILL.md"
        )

        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("cache-refresh", skill_text)
        self.assertIn("sync-mail", skill_text)
        self.assertIn("bypass-cache", skill_text)
        self.assertIn("outlook_busy", skill_text)
        self.assertIn("FIFO queue", skill_text)
        self.assertIn("queue_timeout", skill_text)
        self.assertIn("wrapper_diagnostics", skill_text)
        self.assertIn("local Outlook Classic COM", skill_text)
        self.assertIn("cloud connector", skill_text)

    def test_claude_plugin_manifest_and_marketplace_exist(self):
        marketplace_root = (
            REPO_ROOT
            / "families"
            / "outlook-classic-mail"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
        )
        plugin_root = marketplace_root / "plugins" / "outlook-classic-mail"

        marketplace = json.loads((marketplace_root / CLAUDE_PLUGIN_META_DIR / "marketplace.json").read_text(encoding="utf-8"))
        manifest = json.loads((plugin_root / CLAUDE_PLUGIN_META_DIR / "plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "outlook-classic-mail")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(marketplace["plugins"][0]["name"], "outlook-classic-mail")
        self.assertEqual(marketplace["plugins"][0]["source"], "./plugins/outlook-classic-mail")

    def test_claude_wrapper_bootstraps_family_package(self):
        wrapper_path = (
            REPO_ROOT
            / "families"
            / "outlook-classic-mail"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
            / "plugins"
            / "outlook-classic-mail"
            / "skills"
            / "outlook-classic-mail"
            / "scripts"
            / "invoke_outlook_mail.py"
        )

        wrapper_text = wrapper_path.read_text(encoding="utf-8")

        self.assertIn("bootstrap_family_package", wrapper_text)
        self.assertIn('family_name="outlook-classic-mail"', wrapper_text)
        self.assertIn('package_dir_name="agent_toolbelt_outlook_classic_mail"', wrapper_text)
        self.assertIn("from agent_toolbelt_outlook_classic_mail import cli", wrapper_text)
        self.assertNotIn("win32com", wrapper_text.lower())
        self.assertNotIn("DEFAULT_AGENT_TOOLBELT_HOME", wrapper_text)

    def test_claude_skill_documents_outlook_workflows(self):
        skill_path = (
            REPO_ROOT
            / "families"
            / "outlook-classic-mail"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
            / "plugins"
            / "outlook-classic-mail"
            / "skills"
            / "outlook-classic-mail"
            / "SKILL.md"
        )

        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("find-folders", skill_text)
        self.assertIn("find-response", skill_text)
        self.assertIn("scan-domain-refs", skill_text)
        self.assertIn("blocklists status", skill_text)
        self.assertIn("move-message", skill_text)
        self.assertIn("cache-refresh", skill_text)
        self.assertIn("sync-mail", skill_text)
        self.assertIn("FIFO queue", skill_text)
        self.assertIn("queue_timeout", skill_text)
        self.assertIn("Gmail", skill_text)
        self.assertIn("explicit confirmation", skill_text)
        self.assertIn("wrapper_diagnostics", skill_text)
        self.assertIn("cloud connector", skill_text)
        self.assertIn("draft_content.thread_content_included", skill_text)
        self.assertIn("draft_placement.actual_send_using_account", skill_text)
        self.assertIn("thread_quote_fallback_used", skill_text)


if __name__ == "__main__":
    unittest.main()
