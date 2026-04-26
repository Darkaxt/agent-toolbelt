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
    "outlook-classic-mail": (
        REPO_ROOT / "families" / "outlook-classic-mail" / "src",
        "agent_toolbelt_outlook_classic_mail.cli",
    ),
    "amazon-cli": (
        REPO_ROOT / "families" / "amazon-cli" / "src",
        "agent_toolbelt_amazon_cli.cli",
    ),
    "linkedin-cv": (
        REPO_ROOT / "families" / "linkedin-cv" / "src",
        "agent_toolbelt_linkedin_cv.cli",
    ),
    "codex-thread-recall": (
        REPO_ROOT / "families" / "codex-thread-recall" / "src",
        "agent_toolbelt_codex_thread_recall.cli",
    ),
    "whatsapp-wacli": (
        REPO_ROOT / "families" / "whatsapp-wacli" / "src",
        "agent_toolbelt_whatsapp_wacli.cli",
    ),
    "skills-sh-scout": (
        REPO_ROOT / "families" / "skills-sh-scout" / "src",
        "agent_toolbelt_skills_sh_scout.cli",
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

    def test_outlook_classic_mail_cli_routes_accounts_command(self):
        cli = import_family_cli("outlook-classic-mail")

        original_invoke = cli.outlook_classic_mail.invoke_client
        cli.outlook_classic_mail.invoke_client = lambda **kwargs: {
            "ok": True,
            "operation": "accounts",
            "account": None,
            "store": None,
            "result": {"accounts": [{"smtp_address": "demo@example.com"}]},
            "warnings": [],
            "stderr": "",
            "exit_code": 0,
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["accounts"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.outlook_classic_mail.invoke_client = original_invoke

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "accounts")

    def test_amazon_cli_routes_pass_through_command(self):
        cli = import_family_cli("amazon-cli")

        original_invoke = cli.amazon_cli.invoke_client
        cli.amazon_cli.invoke_client = lambda **kwargs: {
            "ok": True,
            "operation": "offers",
            "result": {"best_offer": {"marketplace": "de"}},
            "warnings": [],
            "stderr": "",
            "exit_code": 0,
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["--", "offers", "B0F2JCZPB4", "--marketplace", "de"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.amazon_cli.invoke_client = original_invoke

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "offers")
        self.assertEqual(payload["result"]["best_offer"]["marketplace"], "de")

    def test_linkedin_cv_cli_routes_profile_capture(self):
        cli = import_family_cli("linkedin-cv")

        original_capture = cli.linkedin_cv.capture_accessible_profile
        cli.linkedin_cv.capture_accessible_profile = lambda **kwargs: {
            "ok": True,
            "operation": "profile.capture",
            "result": {"profile_id": "demo-profile", "capture_type": "accessible_profile"},
            "warnings": [],
            "stderr": "",
            "exit_code": 0,
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(
                    [
                        "profile",
                        "capture",
                        "--profile",
                        "personal",
                        "--profile-id",
                        "demo-profile",
                        "--confirm-accessible-profile-capture",
                    ]
                )
                payload = json.loads(buffer.getvalue())
        finally:
            cli.linkedin_cv.capture_accessible_profile = original_capture

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "profile.capture")
        self.assertEqual(payload["result"]["capture_type"], "accessible_profile")

    def test_codex_thread_recall_cli_routes_status_command(self):
        cli = import_family_cli("codex-thread-recall")

        original_status = cli.thread_recall.status
        cli.thread_recall.status = lambda **kwargs: {
            "ok": True,
            "thread": {"id": "019-thread"},
            "warnings": [],
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["status"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.thread_recall.status = original_status

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["thread"]["id"], "019-thread")

    def test_whatsapp_wacli_routes_latest_command(self):
        cli = import_family_cli("whatsapp-wacli")

        original_invoke = cli.whatsapp_wacli.invoke_client
        cli.whatsapp_wacli.invoke_client = lambda **kwargs: {
            "ok": True,
            "operation": "latest",
            "backend": "whatsapp-wacli-agent",
            "result": {"payload": {"data": {"messages": []}}},
            "warnings": [],
            "stderr": "",
            "exit_code": 0,
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["latest", "--chat", "Demo Contact", "--limit", "5"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.whatsapp_wacli.invoke_client = original_invoke

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "latest")

    def test_skills_sh_scout_cli_routes_scout_command(self):
        cli = import_family_cli("skills-sh-scout")

        original_report = cli.scout.build_scout_report
        cli.scout.build_scout_report = lambda **kwargs: {
            "ok": True,
            "operation": "scout",
            "workflow": kwargs["workflow"],
            "queries": kwargs["explicit_queries"],
            "capped_queries": [],
            "candidate_count": 0,
            "candidates": [],
            "inspected_candidates": [],
            "recommendation": {"category": "Create new skill", "summary": "No candidates."},
            "warnings": [],
            "errors": [],
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["scout", "--workflow", "find a skill for x", "--query", "x"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.scout.build_scout_report = original_report

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "scout")
        self.assertEqual(payload["queries"], ["x"])


if __name__ == "__main__":
    unittest.main()
