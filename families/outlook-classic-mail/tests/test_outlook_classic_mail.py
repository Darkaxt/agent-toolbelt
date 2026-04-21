import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "outlook-classic-mail" / "src"
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


if __name__ == "__main__":
    unittest.main()
