import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "whatsapp-wacli" / "src"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_whatsapp_wacli import whatsapp_wacli  # noqa: E402


class WhatsAppWacliBridgeTests(unittest.TestCase):
    def test_resolve_client_home_prefers_env_var(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_env = os.environ.get(whatsapp_wacli.CLIENT_HOME_ENV)
            os.environ[whatsapp_wacli.CLIENT_HOME_ENV] = temp_dir
            try:
                resolved = whatsapp_wacli.resolve_client_home()
            finally:
                if old_env is None:
                    os.environ.pop(whatsapp_wacli.CLIENT_HOME_ENV, None)
                else:
                    os.environ[whatsapp_wacli.CLIENT_HOME_ENV] = old_env

        self.assertEqual(resolved, Path(temp_dir).resolve())

    def test_build_client_command_uses_uv_project(self):
        command = whatsapp_wacli.build_client_command(
            client_home=Path("C:/Tools/whatsapp-wacli-agent"),
            operation_args=["latest", "--chat", "Demo Contact", "--limit", "5"],
            uv_executable="uv",
        )

        self.assertEqual(command[:4], ["uv", "run", "--project", "C:\\Tools\\whatsapp-wacli-agent"])
        self.assertEqual(command[4:], ["whatsapp-wacli-agent", "latest", "--chat", "Demo Contact", "--limit", "5"])

    def test_parser_forwards_confirm_only_when_present(self):
        parser = whatsapp_wacli.build_parser()

        preview = whatsapp_wacli.build_operation_args(
            parser.parse_args(["send-text", "--chat", "123@s.whatsapp.net", "--message", "hello"])
        )
        confirmed = whatsapp_wacli.build_operation_args(
            parser.parse_args(["send-text", "--chat", "123@s.whatsapp.net", "--message", "hello", "--confirm"])
        )

        self.assertNotIn("--confirm", preview)
        self.assertIn("--confirm", confirmed)

    def test_parser_forwards_backfill_command(self):
        parser = whatsapp_wacli.build_parser()

        args = whatsapp_wacli.build_operation_args(
            parser.parse_args(
                [
                    "backfill",
                    "--chat",
                    "Demo Contact",
                    "--count",
                    "100",
                    "--requests",
                    "3",
                    "--wait-sec",
                    "60",
                ]
            )
        )

        self.assertEqual(
            args,
            [
                "backfill",
                "--chat",
                "Demo Contact",
                "--count",
                "100",
                "--requests",
                "3",
                "--wait-sec",
                "60",
            ],
        )

    def test_parser_forwards_latest_backfill_flags(self):
        parser = whatsapp_wacli.build_parser()

        args = whatsapp_wacli.build_operation_args(
            parser.parse_args(
                [
                    "latest",
                    "--chat",
                    "Demo Contact",
                    "--limit",
                    "100",
                    "--no-backfill",
                    "--backfill-count",
                    "25",
                    "--backfill-requests",
                    "2",
                    "--backfill-wait-sec",
                    "30",
                ]
            )
        )

        self.assertIn("--no-backfill", args)
        self.assertIn("--backfill-count", args)
        self.assertIn("25", args)
        self.assertIn("--backfill-requests", args)
        self.assertIn("--backfill-wait-sec", args)

    def test_invoke_client_normalizes_json_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_resolve_uv = whatsapp_wacli.resolve_uv_executable
            old_run = whatsapp_wacli.run_process
            whatsapp_wacli.resolve_uv_executable = lambda: "uv"
            whatsapp_wacli.run_process = lambda command, timeout_sec: whatsapp_wacli.ProcessLike(
                returncode=0,
                stdout=json.dumps({"ok": True, "operation": "status", "result": {"ready": True}}),
                stderr="",
            )
            try:
                result = whatsapp_wacli.invoke_client(
                    operation_args=["status"],
                    client_home=temp_dir,
                )
            finally:
                whatsapp_wacli.resolve_uv_executable = old_resolve_uv
                whatsapp_wacli.run_process = old_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "status")
        self.assertTrue(result["result"]["ready"])

    def test_claude_plugin_bundle_is_present(self):
        plugin_root = (
            REPO_ROOT
            / "families"
            / "whatsapp-wacli"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
            / "plugins"
            / "whatsapp-wacli"
        )

        self.assertTrue((plugin_root / ("." + "claude-plugin") / "plugin.json").is_file())
        self.assertTrue((plugin_root / "skills" / "whatsapp-wacli" / "SKILL.md").is_file())
        self.assertTrue(
            (plugin_root / "skills" / "whatsapp-wacli" / "scripts" / "invoke_whatsapp_wacli.py").is_file()
        )

    def test_claude_skill_documents_resolution_and_confirmation_gates(self):
        skill = (
            REPO_ROOT
            / "families"
            / "whatsapp-wacli"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
            / "plugins"
            / "whatsapp-wacli"
            / "skills"
            / "whatsapp-wacli"
            / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("resolved_jid", skill)
        self.assertIn("backfill_seed_missing", skill)
        self.assertIn("--confirm", skill)
        self.assertIn("WhatsApp-visible", skill)

    def test_local_client_source_is_present_without_generated_artifacts(self):
        client_root = REPO_ROOT / "families" / "whatsapp-wacli" / "local-client"

        self.assertTrue((client_root / "pyproject.toml").is_file())
        self.assertTrue((client_root / "src" / "whatsapp_wacli_agent" / "agent.py").is_file())
        self.assertTrue((client_root / "tests" / "test_agent.py").is_file())

        ignored_generated_parts = {".venv", "__pycache__"}
        forbidden_parts = {"store"}
        forbidden_suffixes = {".db", ".sqlite", ".sqlite3", ".exe", ".dll", ".pyc"}
        offenders = []
        for path in client_root.rglob("*"):
            relative = path.relative_to(client_root)
            if any(part in ignored_generated_parts for part in relative.parts):
                continue
            if any(part in forbidden_parts for part in relative.parts):
                offenders.append(str(relative))
            if path.is_file() and path.suffix.lower() in forbidden_suffixes:
                offenders.append(str(relative))

        self.assertEqual(offenders, [])

    def test_whatsapp_family_has_no_private_paths_or_live_session_artifacts(self):
        family_root = REPO_ROOT / "families" / "whatsapp-wacli"
        checked_suffixes = {".md", ".py", ".json", ".toml"}
        forbidden_text = ["C:" + "\\Users\\"]
        forbidden_suffixes = {".db", ".sqlite", ".sqlite3", ".exe", ".dll", ".pyc"}
        offenders = []

        for path in family_root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {"__pycache__", ".venv"} for part in path.relative_to(family_root).parts):
                continue
            if path.suffix.lower() in forbidden_suffixes:
                offenders.append(str(path.relative_to(family_root)))
                continue
            if path.suffix.lower() not in checked_suffixes:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden_text:
                if token in text:
                    offenders.append(f"{path.relative_to(family_root)} -> {token}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
