import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "gemini" / "src"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_gemini import gemini


class GeminiTests(unittest.TestCase):
    def test_localhost_urls_are_rejected(self):
        with self.assertRaises(ValueError):
            gemini.validate_public_url("http://localhost:8080/test")

    def test_youtube_urls_are_classified_authoritatively(self):
        self.assertEqual(
            gemini.classify_source_type("https://www.youtube.com/watch?v=KFisvc-AMII"),
            "youtube",
        )
        self.assertEqual(
            gemini.classify_source_type("https://youtu.be/KFisvc-AMII"),
            "youtube",
        )
        self.assertEqual(
            gemini.classify_source_type("https://example.com/article"),
            "web",
        )

    def test_successful_url_run_parses_json_output_with_trailing_noise(self):
        class Result:
            returncode = 0
            stdout = (
                json.dumps(
                    {
                        "response": "Video summary",
                        "stats": {"tools": {"byName": {"web_fetch": {"count": 1}}}},
                    }
                )
                + "\nYOLO mode is enabled.\n"
            )
            stderr = ""

        def fake_run(*args, **kwargs):
            return Result()

        original_run = gemini.subprocess.run
        gemini.subprocess.run = fake_run
        try:
            result = gemini.invoke_gemini_url(
                url="https://www.youtube.com/watch?v=KFisvc-AMII",
                instruction="Summarize the video.",
                timeout_sec=30,
            )
        finally:
            gemini.subprocess.run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["source_type"], "youtube")
        self.assertEqual(result["response"], "Video summary")

    def test_malformed_json_is_reported_cleanly(self):
        class Result:
            returncode = 0
            stdout = "not-json"
            stderr = ""

        def fake_run(*args, **kwargs):
            return Result()

        original_run = gemini.subprocess.run
        gemini.subprocess.run = fake_run
        try:
            result = gemini.invoke_gemini_url(
                url="https://example.com/article",
                instruction="Summarize the article.",
                timeout_sec=30,
            )
        finally:
            gemini.subprocess.run = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(result["source_type"], "web")
        self.assertIn("Failed to parse Gemini CLI JSON output", result["response"])

    def test_json_error_payload_on_stderr_is_surfaced(self):
        class Result:
            returncode = 41
            stdout = ""
            stderr = (
                "YOLO mode is enabled.\n"
                + json.dumps(
                    {
                        "error": {
                            "message": "Please set an Auth method before running Gemini CLI.",
                            "code": 41,
                        }
                    }
                )
            )

        def fake_run(*args, **kwargs):
            return Result()

        original_run = gemini.subprocess.run
        gemini.subprocess.run = fake_run
        try:
            result = gemini.invoke_gemini_url(
                url="https://example.com/article",
                instruction="Summarize the article.",
                timeout_sec=30,
            )
        finally:
            gemini.subprocess.run = original_run

        self.assertFalse(result["ok"])
        self.assertIn("Please set an Auth method", result["response"])
        self.assertEqual(result["exit_code"], 41)

    def test_normalization_preserves_original_question(self):
        result = gemini.normalize_research_question("best colony sim for solo play")

        self.assertEqual(result["original_question"], "best colony sim for solo play")
        self.assertEqual(result["normalized_question"], "best colony sim for solo play")

    def test_normalization_fixes_obvious_typos(self):
        result = gemini.normalize_research_question("reccomend me a colony sim")
        self.assertEqual(result["normalized_question"], "recommend me a colony sim")

    def test_normalization_adds_high_confidence_entity_context(self):
        result = gemini.normalize_research_question("Going Medieval issues")
        self.assertIn("Going Medieval", result["normalized_question"])
        self.assertIn("2021", result["normalized_question"])
        self.assertIn("PC colony sim game", result["normalized_question"])

    def test_prompt_keeps_research_independent_from_codex_findings(self):
        normalized = gemini.normalize_research_question("best colony sim for solo play")
        prompt = gemini.build_research_prompt(
            original_question=normalized["original_question"],
            normalized_question=normalized["normalized_question"],
        )

        self.assertIn("Do not assume any prior Codex findings", prompt)
        self.assertNotIn("http://", prompt)
        self.assertNotIn("https://", prompt)

    def test_missing_npx_is_reported_cleanly_for_research(self):
        original_resolver = gemini.resolve_npx_executable
        gemini.resolve_npx_executable = lambda: None
        try:
            result = gemini.invoke_gemini_research("best colony sim for solo play")
        finally:
            gemini.resolve_npx_executable = original_resolver

        self.assertFalse(result["ok"])
        self.assertEqual(result["mode"], "research")
        self.assertEqual(result["original_question"], "best colony sim for solo play")
        self.assertEqual(result["normalized_question"], "best colony sim for solo play")
        self.assertEqual(result["exit_code"], 127)

    def test_timeout_is_reported_cleanly_for_research(self):
        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=30, stderr="timed out")

        original_run = gemini.subprocess.run
        gemini.subprocess.run = fake_run
        try:
            result = gemini.invoke_gemini_research("best colony sim for solo play", timeout_sec=30)
        finally:
            gemini.subprocess.run = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(result["mode"], "research")
        self.assertEqual(result["exit_code"], 124)
        self.assertIn("timed out", result["stderr"])

    def test_successful_research_run_returns_original_and_normalized_question(self):
        class Result:
            returncode = 0
            stdout = json.dumps(
                {
                    "response": "Try RimWorld, Against the Storm, and Going Medieval.",
                    "stats": {"tools": {"byName": {"google_web_search": {"count": 2}}}},
                }
            ) + "\nYOLO mode is enabled.\n"
            stderr = ""

        def fake_run(*args, **kwargs):
            return Result()

        original_run = gemini.subprocess.run
        gemini.subprocess.run = fake_run
        try:
            result = gemini.invoke_gemini_research("reccomend me a colony sim", timeout_sec=30)
        finally:
            gemini.subprocess.run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "research")
        self.assertEqual(result["original_question"], "reccomend me a colony sim")
        self.assertEqual(result["normalized_question"], "recommend me a colony sim")
        self.assertIn("RimWorld", result["response"])


if __name__ == "__main__":
    unittest.main()
