import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_toolbelt import cli


class CLITests(unittest.TestCase):
    def test_gemini_url_subcommand_routes_to_url_handler(self):
        original = cli.gemini.invoke_gemini_url
        cli.gemini.invoke_gemini_url = lambda **kwargs: {
            "ok": True,
            "response": "done",
            "stats": {},
            "stderr": "",
            "exit_code": 0,
            "source_type": "web",
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(
                    [
                        "gemini-url",
                        "--url",
                        "https://example.com",
                        "--instruction",
                        "Summarize it.",
                    ]
                )
                payload = json.loads(buffer.getvalue())
        finally:
            cli.gemini.invoke_gemini_url = original

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["source_type"], "web")

    def test_gemini_research_subcommand_routes_to_research_handler(self):
        original = cli.gemini.invoke_gemini_research
        cli.gemini.invoke_gemini_research = lambda **kwargs: {
            "ok": True,
            "response": "done",
            "stats": {},
            "stderr": "",
            "exit_code": 0,
            "mode": "research",
            "original_question": "q",
            "normalized_question": "q",
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["gemini-research", "--question", "q"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.gemini.invoke_gemini_research = original

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "research")

    def test_everything_subcommand_routes_to_lookup_handler(self):
        original = cli.everything.lookup
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
                exit_code = cli.main(["everything", "--query", "demo.txt"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.everything.lookup = original

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["backend"], "everything")

    def test_uvrun_subcommand_routes_to_invoke_script(self):
        original = cli.uvrun.invoke_script
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
                exit_code = cli.main(["uvrun", "demo.py", "--check"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.uvrun.invoke_script = original

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["backend"], "uvrun")

    def test_uvrun_subcommand_preserves_check_flag_and_tail_args(self):
        captured = {}
        original = cli.uvrun.invoke_script

        def fake_invoke_script(**kwargs):
            captured.update(kwargs)
            return {
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

        cli.uvrun.invoke_script = fake_invoke_script
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(
                    [
                        "uvrun",
                        "demo.py",
                        "--check",
                        "--",
                        "https://www.youtube.com/watch?v=KFisvc-AMII",
                    ]
                )
                json.loads(buffer.getvalue())
        finally:
            cli.uvrun.invoke_script = original

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["script"], "demo.py")
        self.assertTrue(captured["check_only"])
        self.assertEqual(
            captured["script_args"],
            ["https://www.youtube.com/watch?v=KFisvc-AMII"],
        )

    def test_media_subcommand_routes_to_download_handler(self):
        original = cli.media.invoke_download
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
                exit_code = cli.main(["media", "download", "--url", "https://example.com/video"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.media.invoke_download = original

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "download")


if __name__ == "__main__":
    unittest.main()
