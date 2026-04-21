import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


FAMILY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = FAMILY_ROOT.parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "core" / "src"))
sys.path.insert(0, str(FAMILY_ROOT / "src"))

from agent_toolbelt_whatsapp_local_read import cli, whatsapp_local_read  # noqa: E402


class WhatsAppLocalReadBridgeTests(unittest.TestCase):
    def test_resolves_client_home_from_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_value = whatsapp_local_read.os.environ.get(whatsapp_local_read.CLIENT_HOME_ENV)
            whatsapp_local_read.os.environ[whatsapp_local_read.CLIENT_HOME_ENV] = temp_dir
            try:
                self.assertEqual(whatsapp_local_read.resolve_client_home(), Path(temp_dir).resolve())
            finally:
                if old_value is None:
                    whatsapp_local_read.os.environ.pop(whatsapp_local_read.CLIENT_HOME_ENV, None)
                else:
                    whatsapp_local_read.os.environ[whatsapp_local_read.CLIENT_HOME_ENV] = old_value

    def test_build_client_command_uses_uv_project(self):
        command = whatsapp_local_read.build_client_command(
            client_home=Path("C:/Tools/whatsapp-local-read"),
            operation_args=["status"],
            uv_executable="uv",
        )

        self.assertEqual(command[:4], ["uv", "run", "--project", "C:\\Tools\\whatsapp-local-read"])
        self.assertEqual(command[-2:], [whatsapp_local_read.CLIENT_ENTRYPOINT, "status"])

    def test_cli_routes_suggest_response(self):
        original_invoke = whatsapp_local_read.invoke_client
        whatsapp_local_read.invoke_client = lambda **kwargs: {
            "ok": True,
            "operation": "suggest-response",
            "backend": "visible-ui",
            "result": {"suggestions": ["Thanks, I will check."]},
            "warnings": [],
            "stderr": "",
            "exit_code": 0,
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["suggest-response", "--instruction", "Acknowledge it."])
                payload = json.loads(buffer.getvalue())
        finally:
            whatsapp_local_read.invoke_client = original_invoke

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "suggest-response")
        self.assertEqual(payload["backend"], "visible-ui")

    def test_skill_documents_read_only_boundaries(self):
        skill_text = (
            FAMILY_ROOT
            / "codex"
            / "skills"
            / "whatsapp-local-read"
            / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("read-only", skill_text.lower())
        self.assertIn("no sending", skill_text.lower())
        self.assertIn("no local DB decryption", skill_text)
        self.assertIn("visible-ui", skill_text)


if __name__ == "__main__":
    unittest.main()
