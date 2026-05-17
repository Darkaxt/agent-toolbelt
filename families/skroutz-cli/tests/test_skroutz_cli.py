import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "skroutz-cli" / "src"
SOURCE_BUNDLED_CLIENT_ROOT = (
    FAMILY_SRC / "agent_toolbelt_skroutz_cli" / "assets" / "skroutz-intent-cli"
)
CLAUDE_PLUGIN_META_DIR = "." + "claude-plugin"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_skroutz_cli import skroutz_cli


class SkroutzCLIBridgeTests(unittest.TestCase):
    def test_resolve_client_home_prefers_explicit_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            explicit_home = Path(temp_dir) / "skroutz-intent-cli"
            explicit_home.mkdir()

            resolved = skroutz_cli.resolve_client_home(explicit_home=str(explicit_home))

        self.assertEqual(resolved, explicit_home.resolve())

    def test_resolve_client_home_prefers_env_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_home = Path(temp_dir) / "env-client"
            env_home.mkdir()

            original_env_home = os.environ.get("SKROUTZ_INTENT_CLI_HOME")
            os.environ["SKROUTZ_INTENT_CLI_HOME"] = str(env_home)
            try:
                resolved = skroutz_cli.resolve_client_home()
            finally:
                if original_env_home is None:
                    os.environ.pop("SKROUTZ_INTENT_CLI_HOME", None)
                else:
                    os.environ["SKROUTZ_INTENT_CLI_HOME"] = original_env_home

        self.assertEqual(resolved, env_home.resolve())

    def test_bundled_client_source_is_present_without_runtime_artifacts(self):
        client_root = SOURCE_BUNDLED_CLIENT_ROOT

        self.assertTrue((client_root / "pyproject.toml").is_file())
        self.assertTrue((client_root / "skroutz_intent_cli" / "cli.py").is_file())
        self.assertTrue((client_root / "tests" / "test_cli.py").is_file())

        forbidden_parts = {".venv", "__pycache__", ".pytest_cache", "browser-profiles", "sessions"}
        forbidden_names = {"Cookies", "Local State", "uv.lock"}
        forbidden_suffixes = {".db", ".sqlite", ".sqlite3", ".ldb", ".log", ".pyc", ".pyo"}
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
        pyproject = tomllib.loads((REPO_ROOT / "families" / "skroutz-cli" / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = pyproject["tool"]["setuptools"]["package-data"]["agent_toolbelt_skroutz_cli"]

        self.assertIn("assets/skroutz-intent-cli/pyproject.toml", package_data)
        self.assertIn("assets/skroutz-intent-cli/skroutz_intent_cli/*.py", package_data)
        self.assertIn("assets/skroutz-intent-cli/tests/fixtures/*.html", package_data)
        self.assertNotIn("assets/skroutz-intent-cli/**/*", package_data)
        self.assertFalse(any("uv.lock" in pattern for pattern in package_data))

    def test_build_client_command_uses_uv_run_no_project(self):
        client_home = Path(r"C:\Temp\Tools\skroutz-intent-cli")
        command = skroutz_cli.build_client_command(
            client_home=client_home,
            operation_args=["search", "iphone 17"],
            uv_executable="uv.exe",
        )

        self.assertEqual(command[:5], ["uv.exe", "run", "--no-project", "--with-editable", str(client_home)])
        self.assertEqual(command[5], "skroutz-cli")
        self.assertEqual(command[-2:], ["search", "iphone 17"])

    def test_invoke_client_normalizes_json_success(self):
        original_run = skroutz_cli.run_process
        original_uv = skroutz_cli.resolve_uv_executable
        original_home = skroutz_cli.resolve_client_home
        skroutz_cli.resolve_uv_executable = lambda: "uv.exe"
        skroutz_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\skroutz-intent-cli")
        skroutz_cli.run_process = lambda command, **kwargs: skroutz_cli.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"command": "search", "results": [{"title": "iPhone"}]}),
            stderr="",
        )
        try:
            result = skroutz_cli.invoke_client(operation_args=["search", "iphone"])
        finally:
            skroutz_cli.run_process = original_run
            skroutz_cli.resolve_uv_executable = original_uv
            skroutz_cli.resolve_client_home = original_home

        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "search")
        self.assertEqual(result["result"]["results"][0]["title"], "iPhone")
        self.assertEqual(result["warnings"], [])

    def test_invoke_client_reports_missing_uv_cleanly(self):
        original_uv = skroutz_cli.resolve_uv_executable
        original_home = skroutz_cli.resolve_client_home
        skroutz_cli.resolve_uv_executable = lambda: None
        skroutz_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\skroutz-intent-cli")
        try:
            result = skroutz_cli.invoke_client(operation_args=["search", "iphone"])
        finally:
            skroutz_cli.resolve_uv_executable = original_uv
            skroutz_cli.resolve_client_home = original_home

        self.assertFalse(result["ok"])
        self.assertEqual(result["operation"], "search")
        self.assertEqual(result["exit_code"], 127)
        self.assertIn("uv", result["stderr"].lower())

    def test_build_operation_args_preserves_pass_through_arguments_after_separator(self):
        parser = skroutz_cli.build_parser()
        args = parser.parse_args(["--timeout-sec", "30", "--", "offers", "62956505"])

        self.assertEqual(skroutz_cli.build_operation_args(args), ["offers", "62956505"])

    def test_codex_skill_documents_workflows_and_safety(self):
        skill_path = (
            REPO_ROOT
            / "families"
            / "skroutz-cli"
            / "codex"
            / "skills"
            / "skroutz-cli"
            / "SKILL.md"
        )

        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("search", skill_text)
        self.assertIn("offers", skill_text)
        self.assertIn("cart list", skill_text)
        self.assertIn("--confirm-cart-add", skill_text)
        self.assertIn("--confirm-cart-remove", skill_text)
        self.assertIn("never checkout", skill_text.lower())
        self.assertIn("single-threaded", skill_text.lower())

    def test_claude_plugin_manifest_and_marketplace_exist(self):
        marketplace_root = (
            REPO_ROOT
            / "families"
            / "skroutz-cli"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
        )
        plugin_root = marketplace_root / "plugins" / "skroutz-cli"

        marketplace = json.loads((marketplace_root / CLAUDE_PLUGIN_META_DIR / "marketplace.json").read_text(encoding="utf-8"))
        manifest = json.loads((plugin_root / CLAUDE_PLUGIN_META_DIR / "plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "skroutz-cli")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(marketplace["plugins"][0]["name"], "skroutz-cli")
        self.assertEqual(marketplace["plugins"][0]["source"], "./plugins/skroutz-cli")

    def test_claude_wrapper_bootstraps_family_package(self):
        wrapper_path = (
            REPO_ROOT
            / "families"
            / "skroutz-cli"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
            / "plugins"
            / "skroutz-cli"
            / "skills"
            / "skroutz-cli"
            / "scripts"
            / "invoke_skroutz_cli.py"
        )

        wrapper_text = wrapper_path.read_text(encoding="utf-8")

        self.assertIn("bootstrap_family_package", wrapper_text)
        self.assertIn('"skroutz-cli"', wrapper_text)
        self.assertIn('"agent_toolbelt_skroutz_cli"', wrapper_text)
        self.assertIn("from agent_toolbelt_skroutz_cli import cli", wrapper_text)
        self.assertNotIn("cookie", wrapper_text.lower())


if __name__ == "__main__":
    unittest.main()
