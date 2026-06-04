import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
MEDIA_SRC = REPO_ROOT / "families" / "media" / "src"
OUTLOOK_SRC = REPO_ROOT / "families" / "outlook-classic-mail" / "src"
WHATSAPP_SRC = REPO_ROOT / "families" / "whatsapp-wacli" / "src"
AMAZON_SRC = REPO_ROOT / "families" / "amazon-cli" / "src"
ALIEXPRESS_SRC = REPO_ROOT / "families" / "aliexpress-cli" / "src"
for path in (CORE_SRC, MEDIA_SRC, OUTLOOK_SRC, WHATSAPP_SRC, AMAZON_SRC, ALIEXPRESS_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_core import common
from agent_toolbelt_amazon_cli import amazon_cli
from agent_toolbelt_aliexpress_cli import aliexpress_cli
from agent_toolbelt_media import media
from agent_toolbelt_outlook_classic_mail import outlook_classic_mail
from agent_toolbelt_whatsapp_wacli import whatsapp_wacli


class ToolResolutionGuidanceTests(unittest.TestCase):
    def test_windows_tool_resolution_prefers_path_before_local_tools_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            path_dir = temp_root / "path-bin"
            local_tools_dir = temp_root / "Tools"
            path_dir.mkdir()
            local_tools_dir.mkdir()
            path_tool = path_dir / "demo-tool.exe"
            local_tool = local_tools_dir / "demo-tool.exe"
            path_tool.write_text("from PATH", encoding="utf-8")
            local_tool.write_text("from local tools fallback", encoding="utf-8")

            original_path = os.environ.get("PATH", "")
            original_local_appdata = os.environ.get("LOCALAPPDATA")
            original_which = shutil.which
            os.environ["PATH"] = str(path_dir)
            os.environ["LOCALAPPDATA"] = str(temp_root)
            shutil.which = lambda name: str(path_tool) if name == "demo-tool.exe" else None
            try:
                resolved = common.resolve_windows_tool(
                    path_names=("demo-tool.exe",),
                    local_tool_name="demo-tool.exe",
                )
            finally:
                shutil.which = original_which
                os.environ["PATH"] = original_path
                if original_local_appdata is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = original_local_appdata

        self.assertEqual(resolved, str(path_tool))

    def test_public_docs_present_path_as_primary_binary_resolution(self):
        docs = (REPO_ROOT / "docs" / "windows-prerequisites.md").read_text(encoding="utf-8")

        self.assertIn("available on `PATH`", docs)
        self.assertNotIn("or under `%LOCALAPPDATA%\\Tools`", docs)
        self.assertIn("compatibility fallback", docs)

    def test_missing_binary_error_leads_with_path_and_marks_local_tools_as_compatibility(self):
        result = media.missing_binary_result("ffprobe", "probe")

        self.assertIn("PATH", result["stderr"])
        self.assertIn("compatibility fallback", result["stderr"])
        self.assertNotIn("or %LOCALAPPDATA%\\Tools", result["stderr"])

    def test_project_client_missing_errors_do_not_make_local_tools_primary(self):
        original_resolvers = (
            outlook_classic_mail.resolve_client_home,
            whatsapp_wacli.resolve_client_home,
            amazon_cli.resolve_client_home,
            aliexpress_cli.resolve_client_home,
        )
        outlook_classic_mail.resolve_client_home = lambda explicit_home=None: None
        whatsapp_wacli.resolve_client_home = lambda explicit_home=None: None
        amazon_cli.resolve_client_home = lambda explicit_home=None: None
        aliexpress_cli.resolve_client_home = lambda explicit_home=None: None
        try:
            outlook_result = outlook_classic_mail.invoke_client(operation_args=["accounts"])
            whatsapp_result = whatsapp_wacli.invoke_client(operation_args=["status"])
            amazon_result = amazon_cli.invoke_client(operation_args=["search", "coffee"])
            aliexpress_result = aliexpress_cli.invoke_client(operation_args=["search", "bin"])
        finally:
            (
                outlook_classic_mail.resolve_client_home,
                whatsapp_wacli.resolve_client_home,
                amazon_cli.resolve_client_home,
                aliexpress_cli.resolve_client_home,
            ) = original_resolvers

        for result in (outlook_result, whatsapp_result, amazon_result, aliexpress_result):
            self.assertIn("environment override", result["stderr"])
            self.assertIn("project root", result["stderr"])
            self.assertIn("compatibility fallback", result["stderr"])
            self.assertNotIn("install it under %LOCALAPPDATA%\\Tools", result["stderr"])


if __name__ == "__main__":
    unittest.main()
