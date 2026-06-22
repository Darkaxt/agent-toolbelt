import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "aliexpress-cli" / "src"
SOURCE_BUNDLED_CLIENT_ROOT = (
    FAMILY_SRC / "agent_toolbelt_aliexpress_cli" / "assets" / "aliexpress-intent-cli"
)
CLAUDE_PLUGIN_META_DIR = "." + "claude-plugin"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_aliexpress_cli import aliexpress_cli


class AliExpressCLIBridgeTests(unittest.TestCase):
    def test_resolve_client_home_prefers_explicit_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            explicit_home = Path(temp_dir) / "aliexpress-intent-cli"
            explicit_home.mkdir()

            resolved = aliexpress_cli.resolve_client_home(explicit_home=str(explicit_home))

        self.assertEqual(resolved, explicit_home.resolve())

    def test_resolve_client_home_prefers_env_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_home = Path(temp_dir) / "env-client"
            env_home.mkdir()

            original_env_home = os.environ.get("ALIEXPRESS_INTENT_CLI_HOME")
            os.environ["ALIEXPRESS_INTENT_CLI_HOME"] = str(env_home)
            try:
                resolved = aliexpress_cli.resolve_client_home()
            finally:
                if original_env_home is None:
                    os.environ.pop("ALIEXPRESS_INTENT_CLI_HOME", None)
                else:
                    os.environ["ALIEXPRESS_INTENT_CLI_HOME"] = original_env_home

        self.assertEqual(resolved, env_home.resolve())

    def test_bundled_client_source_is_present_without_runtime_artifacts(self):
        client_root = SOURCE_BUNDLED_CLIENT_ROOT

        self.assertTrue((client_root / "pyproject.toml").is_file())
        self.assertTrue((client_root / "aliexpress_intent_cli" / "cli.py").is_file())
        self.assertTrue((client_root / "tests" / "test_cli.py").is_file())

        forbidden_parts = {".venv", ".pytest_cache", "browser-profiles", "sessions"}
        forbidden_names = {"Cookies", "Local State", "uv.lock"}
        forbidden_suffixes = {".db", ".sqlite", ".sqlite3", ".ldb", ".log"}
        offenders = []
        for path in client_root.rglob("*"):
            relative = path.relative_to(client_root)
            if any(part in forbidden_parts for part in relative.parts):
                offenders.append(str(relative))
            if path.name in forbidden_names:
                offenders.append(str(relative))
            if path.is_file() and path.suffix.lower() in forbidden_suffixes:
                offenders.append(str(relative))

        self.assertEqual(offenders, [])

    def test_package_data_uses_explicit_bundled_client_allowlist(self):
        pyproject = tomllib.loads((REPO_ROOT / "families" / "aliexpress-cli" / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = pyproject["tool"]["setuptools"]["package-data"]["agent_toolbelt_aliexpress_cli"]

        self.assertIn("assets/aliexpress-intent-cli/pyproject.toml", package_data)
        self.assertIn("assets/aliexpress-intent-cli/aliexpress_intent_cli/*.py", package_data)
        self.assertIn("assets/aliexpress-intent-cli/tests/fixtures/*.html", package_data)
        self.assertNotIn("assets/aliexpress-intent-cli/**/*", package_data)
        self.assertFalse(any("uv.lock" in pattern for pattern in package_data))

    def test_build_client_command_uses_tool_runtime_without_no_project_warning(self):
        client_home = Path(r"C:\Temp\Tools\aliexpress-intent-cli")
        command = aliexpress_cli.build_client_command(
            client_home=client_home,
            operation_args=["search", "30L trash bin"],
            uv_executable="uv.exe",
        )

        self.assertEqual(command[:5], ["uv.exe", "tool", "run", "--from", str(client_home)])
        self.assertEqual(command[5:7], ["--with-editable", str(client_home)])
        self.assertNotIn("--no-project", command)
        self.assertEqual(command[7], "aliexpress-cli")
        self.assertEqual(command[-2:], ["search", "30L trash bin"])

    def test_bundled_client_declares_managed_session_dependency(self):
        pyproject = tomllib.loads((SOURCE_BUNDLED_CLIENT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertTrue(any(dependency.startswith("playwright") for dependency in pyproject["project"]["dependencies"]))

    def test_invoke_client_normalizes_json_success(self):
        original_run = aliexpress_cli.run_process
        original_uv = aliexpress_cli.resolve_uv_executable
        original_home = aliexpress_cli.resolve_client_home
        aliexpress_cli.resolve_uv_executable = lambda: "uv.exe"
        aliexpress_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\aliexpress-intent-cli")
        aliexpress_cli.run_process = lambda command, **kwargs: aliexpress_cli.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"command": "search", "results": [{"title": "30L bin"}]}),
            stderr="",
        )
        try:
            result = aliexpress_cli.invoke_client(operation_args=["search", "30L bin"])
        finally:
            aliexpress_cli.run_process = original_run
            aliexpress_cli.resolve_uv_executable = original_uv
            aliexpress_cli.resolve_client_home = original_home

        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "search")
        self.assertEqual(result["result"]["results"][0]["title"], "30L bin")
        self.assertEqual(result["warnings"], [])

    def test_invoke_client_reports_missing_uv_cleanly(self):
        original_uv = aliexpress_cli.resolve_uv_executable
        original_home = aliexpress_cli.resolve_client_home
        aliexpress_cli.resolve_uv_executable = lambda: None
        aliexpress_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\aliexpress-intent-cli")
        try:
            result = aliexpress_cli.invoke_client(operation_args=["search", "30L bin"])
        finally:
            aliexpress_cli.resolve_uv_executable = original_uv
            aliexpress_cli.resolve_client_home = original_home

        self.assertFalse(result["ok"])
        self.assertEqual(result["operation"], "search")
        self.assertEqual(result["exit_code"], 127)
        self.assertIn("uv", result["stderr"].lower())

    def test_build_operation_args_preserves_pass_through_arguments_after_separator(self):
        parser = aliexpress_cli.build_parser()
        args = parser.parse_args(["--timeout-sec", "30", "--", "search", "30L trash bin", "--use-session"])

        self.assertEqual(aliexpress_cli.build_operation_args(args), ["search", "30L trash bin", "--use-session"])

    def test_codex_skill_documents_workflows_and_safety(self):
        skill_path = (
            REPO_ROOT
            / "families"
            / "aliexpress-cli"
            / "codex"
            / "skills"
            / "aliexpress-cli"
            / "SKILL.md"
        )

        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("search", skill_text)
        self.assertIn("reviews", skill_text)
        self.assertIn("--use-session", skill_text)
        self.assertIn("No cart", skill_text)
        self.assertIn("no checkout", skill_text.lower())
        self.assertIn("single-threaded", skill_text.lower())

    def test_claude_plugin_manifest_and_marketplace_exist(self):
        marketplace_root = (
            REPO_ROOT
            / "families"
            / "aliexpress-cli"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
        )
        plugin_root = marketplace_root / "plugins" / "aliexpress-cli"

        marketplace = json.loads((marketplace_root / CLAUDE_PLUGIN_META_DIR / "marketplace.json").read_text(encoding="utf-8"))
        manifest = json.loads((plugin_root / CLAUDE_PLUGIN_META_DIR / "plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "aliexpress-cli")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(marketplace["plugins"][0]["name"], "aliexpress-cli")
        self.assertEqual(marketplace["plugins"][0]["source"], "./plugins/aliexpress-cli")

    def test_claude_wrapper_bootstraps_family_package(self):
        wrapper_path = (
            REPO_ROOT
            / "families"
            / "aliexpress-cli"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
            / "plugins"
            / "aliexpress-cli"
            / "skills"
            / "aliexpress-cli"
            / "scripts"
            / "invoke_aliexpress_cli.py"
        )

        wrapper_text = wrapper_path.read_text(encoding="utf-8")

        self.assertIn("bootstrap_family_package", wrapper_text)
        self.assertIn('"aliexpress-cli"', wrapper_text)
        self.assertIn('"agent_toolbelt_aliexpress_cli"', wrapper_text)
        self.assertIn("from agent_toolbelt_aliexpress_cli import cli", wrapper_text)
        self.assertNotIn("cookie", wrapper_text.lower())


if __name__ == "__main__":
    unittest.main()
