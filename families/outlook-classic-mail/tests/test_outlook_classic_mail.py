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
        )

        self.assertEqual(command[:5], ["uv.exe", "run", "--project", str(client_home), "outlook-classic-mail-client"])
        self.assertEqual(command[-1], "accounts")

    def test_invoke_client_normalizes_json_success(self):
        original_run = outlook_classic_mail.run_process
        original_uv = outlook_classic_mail.resolve_uv_executable
        original_home = outlook_classic_mail.resolve_client_home
        outlook_classic_mail.resolve_uv_executable = lambda: "uv.exe"
        outlook_classic_mail.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\outlook-classic-mail")
        outlook_classic_mail.run_process = lambda command, **kwargs: outlook_classic_mail.subprocess.CompletedProcess(
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
                }
            ),
            stderr="",
        )
        try:
            result = outlook_classic_mail.invoke_client(operation_args=["accounts"])
        finally:
            outlook_classic_mail.run_process = original_run
            outlook_classic_mail.resolve_uv_executable = original_uv
            outlook_classic_mail.resolve_client_home = original_home

        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "accounts")
        self.assertEqual(result["result"]["accounts"][0]["smtp_address"], "demo@example.com")

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
        self.assertIn("Gmail", skill_text)
        self.assertIn("explicit confirmation", skill_text)


if __name__ == "__main__":
    unittest.main()
