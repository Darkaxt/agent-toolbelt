import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "amazon-cli" / "src"
SOURCE_BUNDLED_CLIENT_ROOT = (
    FAMILY_SRC / "agent_toolbelt_amazon_cli" / "assets" / "amazon-intent-cli"
)
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

    def test_resolve_client_home_uses_bundled_client_before_local_tools_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            default_home = Path(temp_dir) / "Tools" / "amazon-intent-cli"
            default_home.mkdir(parents=True)

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

        self.assertEqual(resolved, amazon_cli.bundled_client_home().resolve())

    def test_resolve_client_home_uses_local_tools_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            expected = Path(temp_dir) / "Tools" / "amazon-intent-cli"
            expected.mkdir(parents=True)

            original_env_home = os.environ.get("AMAZON_INTENT_CLI_HOME")
            original_local_appdata = os.environ.get("LOCALAPPDATA")
            os.environ.pop("AMAZON_INTENT_CLI_HOME", None)
            os.environ["LOCALAPPDATA"] = temp_dir
            original_bundled_client_home = amazon_cli.bundled_client_home
            amazon_cli.bundled_client_home = lambda: Path(temp_dir) / "missing-bundled-client"
            try:
                resolved = amazon_cli.resolve_client_home()
            finally:
                amazon_cli.bundled_client_home = original_bundled_client_home
                if original_env_home is None:
                    os.environ.pop("AMAZON_INTENT_CLI_HOME", None)
                else:
                    os.environ["AMAZON_INTENT_CLI_HOME"] = original_env_home
                if original_local_appdata is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = original_local_appdata

        self.assertEqual(resolved, expected.resolve())

    def test_bundled_client_source_is_present_without_runtime_artifacts(self):
        client_root = SOURCE_BUNDLED_CLIENT_ROOT

        self.assertTrue((client_root / "pyproject.toml").is_file())
        self.assertTrue((client_root / "amazon_intent_cli" / "cli.py").is_file())
        self.assertTrue((client_root / "amazon_intent_cli" / "offers.py").is_file())
        self.assertTrue((client_root / "tests" / "test_cli.py").is_file())

        forbidden_parts = {".venv", "__pycache__", ".pytest_cache", "browser-profiles", "sessions"}
        forbidden_names = {"Cookies", "Local State", "uv.lock", "todo.md", "derived_todo.md"}
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
        pyproject = tomllib.loads((REPO_ROOT / "families" / "amazon-cli" / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = pyproject["tool"]["setuptools"]["package-data"]["agent_toolbelt_amazon_cli"]

        self.assertIn("assets/amazon-intent-cli/pyproject.toml", package_data)
        self.assertIn("assets/amazon-intent-cli/amazon_intent_cli/*.py", package_data)
        self.assertIn("assets/amazon-intent-cli/tests/fixtures/*.html", package_data)
        self.assertNotIn("assets/amazon-intent-cli/**/*", package_data)
        self.assertFalse(any("uv.lock" in pattern for pattern in package_data))
        self.assertFalse(any(".venv" in pattern for pattern in package_data))

    def test_build_client_command_uses_uv_run_project_and_amazon_cli_entrypoint(self):
        client_home = Path(r"C:\Temp\Tools\amazon-intent-cli")
        command = amazon_cli.build_client_command(
            client_home=client_home,
            operation_args=["offers", "B0F2JCZPB4", "--marketplace", "de"],
            uv_executable="uv.exe",
        )

        self.assertEqual(command[:5], ["uv.exe", "run", "--no-project", "--with-editable", str(client_home)])
        self.assertEqual(command[5], "amazon-cli")
        self.assertEqual(command[-4:], ["offers", "B0F2JCZPB4", "--marketplace", "de"])

    def test_runtime_venv_dir_is_outside_bundled_client_source(self):
        runtime_dir = amazon_cli.runtime_venv_dir()
        bundled_home = SOURCE_BUNDLED_CLIENT_ROOT.resolve()

        self.assertFalse(runtime_dir.resolve().is_relative_to(bundled_home))
        self.assertIn("agent-toolbelt", runtime_dir.parts)
        self.assertEqual(runtime_dir.name, "uv-env")

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
        self.assertEqual(captured_env["UV_PROJECT_ENVIRONMENT"], str(amazon_cli.runtime_venv_dir()))
        self.assertEqual(captured_env["PYTHONDONTWRITEBYTECODE"], "1")

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

    def test_invoke_client_warns_when_offer_trust_signals_are_uncertain(self):
        original_run = amazon_cli.run_process
        original_uv = amazon_cli.resolve_uv_executable
        original_home = amazon_cli.resolve_client_home
        amazon_cli.resolve_uv_executable = lambda: "uv.exe"
        amazon_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\amazon-intent-cli")
        amazon_cli.run_process = lambda command, **kwargs: amazon_cli.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "command": "offers",
                    "trusted_best_offer": None,
                    "raw_best_offer": {"marketplace": "fr", "total_price": 15.0},
                    "current_offer": {"marketplace": "de", "total_price": 19.0},
                    "address_consistency": {"status": "mismatch"},
                    "offers": [{"marketplace": "fr", "status": "ok"}],
                }
            ),
            stderr="",
        )
        try:
            result = amazon_cli.invoke_client(operation_args=["offers", "B0TEST0001"])
        finally:
            amazon_cli.run_process = original_run
            amazon_cli.resolve_uv_executable = original_uv
            amazon_cli.resolve_client_home = original_home

        self.assertTrue(result["ok"])
        self.assertIn("trusted_best_offer is missing; verify address_consistency before recommending a cheapest offer.", result["warnings"])
        self.assertIn("address_consistency status is mismatch; cross-market prices may not share the same destination.", result["warnings"])

    def test_invoke_client_warns_when_search_has_variant_or_partial_results(self):
        original_run = amazon_cli.run_process
        original_uv = amazon_cli.resolve_uv_executable
        original_home = amazon_cli.resolve_client_home
        amazon_cli.resolve_uv_executable = lambda: "uv.exe"
        amazon_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\amazon-intent-cli")
        amazon_cli.run_process = lambda command, **kwargs: amazon_cli.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "command": "search",
                    "pagination": {"partial": True, "stopped_reason": "page_2: blocked"},
                    "results": [
                        {
                            "asin": "B0TEST0001",
                            "model_match": "variant",
                            "model_disclosure": "Requested OLED65C5ELB; resolved listing model OLED65C54LA (variant).",
                        }
                    ],
                }
            ),
            stderr="",
        )
        try:
            result = amazon_cli.invoke_client(operation_args=["search", "tv"])
        finally:
            amazon_cli.run_process = original_run
            amazon_cli.resolve_uv_executable = original_uv
            amazon_cli.resolve_client_home = original_home

        self.assertTrue(result["ok"])
        self.assertIn("Search pagination is partial: page_2: blocked", result["warnings"])
        self.assertIn(
            "Search result B0TEST0001 has model_match=variant: Requested OLED65C5ELB; resolved listing model OLED65C54LA (variant).",
            result["warnings"],
        )

    def test_invoke_client_warns_when_reviews_use_fallback_or_partial_results(self):
        original_run = amazon_cli.run_process
        original_uv = amazon_cli.resolve_uv_executable
        original_home = amazon_cli.resolve_client_home
        amazon_cli.resolve_uv_executable = lambda: "uv.exe"
        amazon_cli.resolve_client_home = lambda explicit_home=None: Path(r"C:\Tools\amazon-intent-cli")
        amazon_cli.run_process = lambda command, **kwargs: amazon_cli.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "command": "reviews",
                    "deep_reviews_available": False,
                    "session_status": "missing",
                    "fallback_reason": "Run amazon-cli session login --marketplace de --portal retail",
                    "pagination": {"partial": True, "stopped_reason": "page_2: ajax endpoint changed"},
                }
            ),
            stderr="",
        )
        try:
            result = amazon_cli.invoke_client(operation_args=["reviews", "B0TEST0001"])
        finally:
            amazon_cli.run_process = original_run
            amazon_cli.resolve_uv_executable = original_uv
            amazon_cli.resolve_client_home = original_home

        self.assertTrue(result["ok"])
        self.assertIn(
            "Deep review collection is unavailable; reviews are from fallback evidence (session_status=missing).",
            result["warnings"],
        )
        self.assertIn("Review pagination is partial: page_2: ajax endpoint changed", result["warnings"])

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
        self.assertIn("inspect-identifier", skill_text)
        self.assertIn("session login", skill_text)
        self.assertIn("managed sessions", skill_text)
        self.assertIn("read-only", skill_text)
        self.assertIn("variant mismatch", skill_text)
        self.assertIn("address inspect", skill_text)
        self.assertIn("--vat-mode auto", skill_text)
        self.assertIn("trusted_best_offer", skill_text)
        self.assertIn("address_consistency", skill_text)
        self.assertIn("cart add", skill_text)
        self.assertIn("--confirm-cart-add", skill_text)
        self.assertIn("cart remove", skill_text)
        self.assertIn("--confirm-cart-remove", skill_text)
        self.assertIn("auto-detected", skill_text)
        self.assertIn("--manual-confirm", skill_text)
        self.assertIn("--login-timeout-sec", skill_text)
        self.assertIn("targeted waits", skill_text)
        self.assertIn("action_timing_ms", skill_text)
        self.assertIn("never checkout", skill_text.lower())
        self.assertIn("Repurchase workflow", skill_text)
        self.assertIn("primary marketplace exact search", skill_text)
        self.assertIn("same-format candidate ASIN", skill_text)
        self.assertIn("Run `offers` only after selecting that ASIN", skill_text)

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

    def test_claude_skill_documents_explicit_cart_safety(self):
        skill_path = (
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
            / "SKILL.md"
        )

        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("cart add", skill_text)
        self.assertIn("inspect-identifier", skill_text)
        self.assertIn("--confirm-cart-add", skill_text)
        self.assertIn("cart remove", skill_text)
        self.assertIn("--confirm-cart-remove", skill_text)
        self.assertIn("trusted_best_offer", skill_text)
        self.assertIn("auto-detected", skill_text)
        self.assertIn("--manual-confirm", skill_text)
        self.assertIn("targeted waits", skill_text)
        self.assertIn("never checkout", skill_text.lower())

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
