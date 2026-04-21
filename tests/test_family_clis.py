import importlib
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

FAMILY_IMPORTS = {
    "gemini": (
        REPO_ROOT / "families" / "gemini" / "src",
        "agent_toolbelt_gemini.cli",
    ),
    "everything": (
        REPO_ROOT / "families" / "everything" / "src",
        "agent_toolbelt_everything.cli",
    ),
    "uvrun": (
        REPO_ROOT / "families" / "uvrun" / "src",
        "agent_toolbelt_uvrun.cli",
    ),
    "media": (
        REPO_ROOT / "families" / "media" / "src",
        "agent_toolbelt_media.cli",
    ),
}


def import_family_cli(name: str):
    src_root, module_name = FAMILY_IMPORTS[name]
    sys.path.insert(0, str(REPO_ROOT / "packages" / "core" / "src"))
    sys.path.insert(0, str(src_root))
    try:
        return importlib.import_module(module_name)
    finally:
        while str(src_root) in sys.path:
            sys.path.remove(str(src_root))
        while str(REPO_ROOT / "packages" / "core" / "src") in sys.path:
            sys.path.remove(str(REPO_ROOT / "packages" / "core" / "src"))


class FamilyCLITests(unittest.TestCase):
    def test_gemini_cli_routes_url_and_research_commands(self):
        cli = import_family_cli("gemini")

        original_url = cli.gemini.invoke_gemini_url
        original_research = cli.gemini.invoke_gemini_research
        cli.gemini.invoke_gemini_url = lambda **kwargs: {
            "ok": True,
            "response": "url",
            "stats": {},
            "stderr": "",
            "exit_code": 0,
            "source_type": "web",
        }
        cli.gemini.invoke_gemini_research = lambda **kwargs: {
            "ok": True,
            "response": "research",
            "stats": {},
            "stderr": "",
            "exit_code": 0,
            "mode": "research",
            "original_question": "q",
            "normalized_question": "q",
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(
                    ["url", "--url", "https://example.com", "--instruction", "Summarize it."]
                )
                url_payload = json.loads(buffer.getvalue())

            with io.StringIO() as buffer, redirect_stdout(buffer):
                research_exit_code = cli.main(["research", "--question", "q"])
                research_payload = json.loads(buffer.getvalue())
        finally:
            cli.gemini.invoke_gemini_url = original_url
            cli.gemini.invoke_gemini_research = original_research

        self.assertEqual(exit_code, 0)
        self.assertEqual(url_payload["source_type"], "web")
        self.assertEqual(research_exit_code, 0)
        self.assertEqual(research_payload["mode"], "research")

    def test_everything_cli_routes_lookup_command(self):
        cli = import_family_cli("everything")

        original_lookup = cli.everything.lookup
        cli.everything.lookup = lambda **kwargs: {
            "ok": True,
            "backend": "everything",
            "query": kwargs["query"],
            "results": ["C:\\demo.txt"],
            "stderr": "",
            "exit_code": 0,
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["--query", "demo.txt"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.everything.lookup = original_lookup

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["backend"], "everything")

    def test_uvrun_cli_routes_standalone_script_command(self):
        cli = import_family_cli("uvrun")

        original_invoke = cli.uvrun.invoke_script
        cli.uvrun.invoke_script = lambda **kwargs: {
            "ok": True,
            "eligible": True,
            "backend": "uvrun",
            "script": kwargs["script"],
            "reason": "test",
            "command": ["powershell.exe"],
            "cwd": "D:\\repo",
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["demo.py", "--check"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.uvrun.invoke_script = original_invoke

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["backend"], "uvrun")

    def test_media_cli_routes_download_command(self):
        cli = import_family_cli("media")

        original_download = cli.media.invoke_download
        cli.media.invoke_download = lambda **kwargs: {
            "ok": True,
            "tool": "yt-dlp",
            "operation": "download",
            "exit_code": 0,
            "stderr": "",
            "artifacts": ["D:\\demo.mp4"],
            "metadata": {},
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["download", "--url", "https://example.com/video"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.media.invoke_download = original_download

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "download")


if __name__ == "__main__":
    unittest.main()
