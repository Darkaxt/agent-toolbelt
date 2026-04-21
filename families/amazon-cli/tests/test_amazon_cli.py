import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "amazon-cli" / "src"
CLAUDE_PLUGIN_META_DIR = "." + "claude-plugin"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_amazon_cli import amazon_cli


class AmazonCLIBridgeTests(unittest.TestCase):
    def test_resolve_client_home_prefers_explicit_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            explicit_home = Path(temp_dir) / "amazon-intent-cli"
            explicit_home.mkdir()

            resolved = amazon_cli.resolve_client_home(explicit_home=str(explicit_home))

        self.assertEqual(resolved, explicit_home.resolve())

    def test_resolve_client_home_prefers_env_override_over_local_tools_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_home = Path(temp_dir) / "env-client"
            env_home.mkdir()
            default_home = Path(temp_dir) / "Tools" / "amazon-intent-cli"
            default_home.mkdir(parents=True)

            original_env_home = os.environ.get("AMAZON_INTENT_CLI_HOME")
            original_local_appdata = os.environ.get("LOCALAPPDATA")
            os.environ["AMAZON_INTENT_CLI_HOME"] = str(env_home)
            os.environ["LOCALAPPDATA"] = temp_dir
            try:
                resolved = amazon_cli.resolve_client_home()
            finally:
                if original_env_home is None:
                    os.environ.pop("AMAZON_INTENT_CLI_HOME", None)
                else:
                    os.environ["AMAZON_INTENT_CLI_HOME"] = original_env_home
                if original_local_appdata is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = original_local_appdata

        self.assertEqual(resolved, env_home.resolve())

    def test_resolve_client_home_uses_local_tools_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            expected = Path(temp_dir) / "Tools" / "amazon-intent-cli"
            expected.mkdir(parents=True)

            original_env_home = os.environ.get("AMAZON_INTENT_CLI_HOME")
            original_local_appdata = os.environ.get("LOCALAPPDATA")
            os.environ.pop("AMAZON_INTENT_CLI_HOME", None)
            os.environ["LOCALAPPDATA"] = temp_dir
            try:
                resolved = amazon_cli.resolve_client_home()
            finally:
                if original_env_home is None:
                    os.environ.pop("AMAZON_INTENT_CLI_HOME", None)
                else:
                    os.environ["AMAZON_INTENT_CLI_HOME"] = original_env_home
                if original_local_appdata is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = original_local_appdata

        self.assertEqual(resolved, expected.resolve())

    def test_build_client_command_uses_uv_run_project_and_amazon_cli_entrypoint(self):
        client_home = Path(r"C:\Temp\Tools\amazon-intent-cli")
        command = amazon_cli.build_client_command(
            client_home=client_home,
            operation_args=["offers", "B0F2JCZPB4", "--marketplace", "de"],
            uv_executable="uv.exe",
        )

        self.assertEqual(command[:5], ["uv.exe", "run", "--project", str(client_home), "amazon-cli"])
        self.assertEqual(command[-4:], ["offers", "B0F2JCZPB4", "--marketplace", "de"])

    def test_invoke_client_normalizes_json_success(self):
        original_run = amazon_cli.run_process
        original_uv = amazon_cli.resolve_uv_executable
        original_home = amazon_cli.resolve_client_home
        amazon_cli.resolve_uv_executable = lambda: "uv.exe"
        amazon_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\amazon-intent-cli")
        amazon_cli.run_process = lambda command, **kwargs: amazon_cli.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"best_offer": {"marketplace": "de"}, "offers": []}),
            stderr="",
        )
        try:
            result = amazon_cli.invoke_client(operation_args=["offers", "B0F2JCZPB4"])
        finally:
            amazon_cli.run_process = original_run
            amazon_cli.resolve_uv_executable = original_uv
            amazon_cli.resolve_client_home = original_home

        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "offers")
        self.assertEqual(result["result"]["best_offer"]["marketplace"], "de")
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["exit_code"], 0)

    def test_invoke_client_drops_parent_virtual_env_for_external_project(self):
        captured_env = {}
        original_run = amazon_cli.run_process
        original_uv = amazon_cli.resolve_uv_executable
        original_home = amazon_cli.resolve_client_home
        original_virtual_env = os.environ.get("VIRTUAL_ENV")
        os.environ["VIRTUAL_ENV"] = r"C:\Repo\.venv"
        amazon_cli.resolve_uv_executable = lambda: "uv.exe"
        amazon_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\amazon-intent-cli")

        def fake_run(command, **kwargs):
            captured_env.update(kwargs["env"])
            return amazon_cli.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"ok": True}),
                stderr="",
            )

        amazon_cli.run_process = fake_run
        try:
            result = amazon_cli.invoke_client(operation_args=["offers", "B0F2JCZPB4"])
        finally:
            amazon_cli.run_process = original_run
            amazon_cli.resolve_uv_executable = original_uv
            amazon_cli.resolve_client_home = original_home
            if original_virtual_env is None:
                os.environ.pop("VIRTUAL_ENV", None)
            else:
                os.environ["VIRTUAL_ENV"] = original_virtual_env

        self.assertTrue(result["ok"])
        self.assertNotIn("VIRTUAL_ENV", captured_env)

    def test_invoke_client_preserves_nonzero_json_error(self):
        original_run = amazon_cli.run_process
        original_uv = amazon_cli.resolve_uv_executable
        original_home = amazon_cli.resolve_client_home
        amazon_cli.resolve_uv_executable = lambda: "uv.exe"
        amazon_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\amazon-intent-cli")
        amazon_cli.run_process = lambda command, **kwargs: amazon_cli.subprocess.CompletedProcess(
            command,
            2,
            stdout=json.dumps({"error": "Run amazon-cli session login --marketplace de --portal retail"}),
            stderr="",
        )
        try:
            result = amazon_cli.invoke_client(operation_args=["reviews", "B0F2JCZPB4"])
        finally:
            amazon_cli.run_process = original_run
            amazon_cli.resolve_uv_executable = original_uv
            amazon_cli.resolve_client_home = original_home

        self.assertFalse(result["ok"])
        self.assertEqual(result["operation"], "reviews")
        self.assertEqual(result["result"]["error"], "Run amazon-cli session login --marketplace de --portal retail")
        self.assertEqual(result["exit_code"], 2)

    def test_invoke_client_reports_missing_uv_cleanly(self):
        original_uv = amazon_cli.resolve_uv_executable
        original_home = amazon_cli.resolve_client_home
        amazon_cli.resolve_uv_executable = lambda: None
        amazon_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\amazon-intent-cli")
        try:
            result = amazon_cli.invoke_client(operation_args=["search", "tv"])
        finally:
            amazon_cli.resolve_uv_executable = original_uv
            amazon_cli.resolve_client_home = original_home

        self.assertFalse(result["ok"])
        self.assertEqual(result["operation"], "search")
        self.assertEqual(result["exit_code"], 127)
        self.assertIn("uv", result["stderr"].lower())

    def test_invoke_client_reports_timeout(self):
        original_run = amazon_cli.run_process
        original_uv = amazon_cli.resolve_uv_executable
        original_home = amazon_cli.resolve_client_home
        amazon_cli.resolve_uv_executable = lambda: "uv.exe"
        amazon_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\amazon-intent-cli")

        def raise_timeout(command, **kwargs):
            raise amazon_cli.subprocess.TimeoutExpired(command, timeout=kwargs["timeout_sec"], stderr="partial")

        amazon_cli.run_process = raise_timeout
        try:
            result = amazon_cli.invoke_client(operation_args=["session", "login"], timeout_sec=1)
        finally:
            amazon_cli.run_process = original_run
            amazon_cli.resolve_uv_executable = original_uv
            amazon_cli.resolve_client_home = original_home

        self.assertFalse(result["ok"])
        self.assertEqual(result["operation"], "session")
        self.assertEqual(result["exit_code"], 124)
        self.assertIn("timed out", result["stderr"].lower())

    def test_build_operation_args_preserves_pass_through_arguments_after_separator(self):
        parser = amazon_cli.build_parser()
        args = parser.parse_args(
            [
                "--timeout-sec",
                "30",
                "--",
                "search",
                "tv",
                "--brand",
                "LG",
                "--model",
                "C4",
                "--max-price",
                "560",
            ]
        )

        self.assertEqual(
            amazon_cli.build_operation_args(args),
            ["search", "tv", "--brand", "LG", "--model", "C4", "--max-price", "560"],
        )

    def test_codex_skill_documents_amazon_workflows_and_safety(self):
        skill_path = (
            REPO_ROOT
            / "families"
            / "amazon-cli"
            / "codex"
            / "skills"
            / "amazon-cli"
            / "SKILL.md"
        )

        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("offers", skill_text)
        self.assertIn("reviews", skill_text)
        self.assertIn("session login", skill_text)
        self.assertIn("managed sessions", skill_text)
        self.assertIn("read-only", skill_text)
        self.assertIn("variant mismatch", skill_text)
        self.assertIn("Do not add products to cart", skill_text)

    def test_claude_plugin_manifest_and_marketplace_exist(self):
        marketplace_root = (
            REPO_ROOT
            / "families"
            / "amazon-cli"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
        )
        plugin_root = marketplace_root / "plugins" / "amazon-cli"

        marketplace = json.loads((marketplace_root / CLAUDE_PLUGIN_META_DIR / "marketplace.json").read_text(encoding="utf-8"))
        manifest = json.loads((plugin_root / CLAUDE_PLUGIN_META_DIR / "plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "amazon-cli")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(marketplace["plugins"][0]["name"], "amazon-cli")
        self.assertEqual(marketplace["plugins"][0]["source"], "./plugins/amazon-cli")

    def test_claude_wrapper_bootstraps_family_package(self):
        wrapper_path = (
            REPO_ROOT
            / "families"
            / "amazon-cli"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
            / "plugins"
            / "amazon-cli"
            / "skills"
            / "amazon-cli"
            / "scripts"
            / "invoke_amazon_cli.py"
        )

        wrapper_text = wrapper_path.read_text(encoding="utf-8")

        self.assertIn("bootstrap_family_package", wrapper_text)
        self.assertIn('family_name="amazon-cli"', wrapper_text)
        self.assertIn('package_dir_name="agent_toolbelt_amazon_cli"', wrapper_text)
        self.assertIn("from agent_toolbelt_amazon_cli import cli", wrapper_text)
        self.assertNotIn("cookie", wrapper_text.lower())
        self.assertNotIn("local storage", wrapper_text.lower())


if __name__ == "__main__":
    unittest.main()
