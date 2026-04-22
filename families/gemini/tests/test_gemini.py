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
        self.assertEqual(result["model_used"], "gemini-3-pro-preview")
        self.assertEqual(result["model_attempts"][0]["model"], "gemini-3-pro-preview")

    def test_default_url_run_uses_pro_model_and_sanitizes_billing_env(self):
        calls = []

        class Result:
            returncode = 0
            stdout = json.dumps({"response": "OK", "stats": {}})
            stderr = ""

        def fake_run(command, **kwargs):
            calls.append({"command": command, "env": kwargs["env"]})
            return Result()

        original_run = gemini.subprocess.run
        original_environ = dict(gemini.os.environ)
        gemini.subprocess.run = fake_run
        try:
            gemini.os.environ.update(
                {
                    "GEMINI_API_KEY": "paid-gemini-key",
                    "GOOGLE_API_KEY": "paid-google-key",
                    "GOOGLE_CLOUD_PROJECT": "paid-project",
                    "GOOGLE_CLOUD_LOCATION": "us-central1",
                    "GOOGLE_APPLICATION_CREDENTIALS": "credentials.json",
                    "CODEX_API_KEY": "must-stay",
                }
            )
            result = gemini.invoke_gemini_url(
                url="https://example.com/article",
                instruction="Summarize.",
                timeout_sec=30,
            )
        finally:
            gemini.subprocess.run = original_run
            gemini.os.environ.clear()
            gemini.os.environ.update(original_environ)

        self.assertTrue(result["ok"])
        self.assertIn("--model", calls[0]["command"])
        self.assertIn("gemini-3-pro-preview", calls[0]["command"])
        self.assertEqual(result["model_strategy"], "highest-with-fallback")
        self.assertEqual(result["model_used"], "gemini-3-pro-preview")
        self.assertTrue(result["auth_env_sanitized"])
        self.assertNotIn("GEMINI_API_KEY", calls[0]["env"])
        self.assertNotIn("GOOGLE_API_KEY", calls[0]["env"])
        self.assertNotIn("GOOGLE_CLOUD_PROJECT", calls[0]["env"])
        self.assertNotIn("GOOGLE_CLOUD_LOCATION", calls[0]["env"])
        self.assertNotIn("GOOGLE_APPLICATION_CREDENTIALS", calls[0]["env"])
        self.assertEqual(calls[0]["env"]["CODEX_API_KEY"], "must-stay")

    def test_allow_env_credentials_preserves_billing_env(self):
        calls = []

        class Result:
            returncode = 0
            stdout = json.dumps({"response": "OK", "stats": {}})
            stderr = ""

        def fake_run(command, **kwargs):
            calls.append({"command": command, "env": kwargs["env"]})
            return Result()

        original_run = gemini.subprocess.run
        original_environ = dict(gemini.os.environ)
        gemini.subprocess.run = fake_run
        try:
            gemini.os.environ["GEMINI_API_KEY"] = "paid-gemini-key"
            result = gemini.invoke_gemini_url(
                url="https://example.com/article",
                instruction="Summarize.",
                timeout_sec=30,
                allow_env_credentials=True,
            )
        finally:
            gemini.subprocess.run = original_run
            gemini.os.environ.clear()
            gemini.os.environ.update(original_environ)

        self.assertTrue(result["ok"])
        self.assertFalse(result["auth_env_sanitized"])
        self.assertEqual(calls[0]["env"]["GEMINI_API_KEY"], "paid-gemini-key")

    def test_model_used_reports_actual_main_model_from_stats_when_available(self):
        class Result:
            returncode = 0
            stdout = json.dumps(
                {
                    "response": "OK",
                    "stats": {
                        "models": {
                            "gemini-3.1-pro-preview": {
                                "roles": {
                                    "main": {
                                        "totalRequests": 1,
                                    }
                                }
                            }
                        }
                    },
                }
            )
            stderr = ""

        def fake_run(*args, **kwargs):
            return Result()

        original_run = gemini.subprocess.run
        gemini.subprocess.run = fake_run
        try:
            result = gemini.invoke_gemini_url(
                url="https://example.com/article",
                instruction="Summarize.",
                timeout_sec=30,
            )
        finally:
            gemini.subprocess.run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["model_attempts"][0]["model"], "gemini-3-pro-preview")
        self.assertEqual(result["model_attempts"][0]["actual_model"], "gemini-3.1-pro-preview")
        self.assertEqual(result["model_used"], "gemini-3.1-pro-preview")

    def test_quota_error_falls_back_from_pro_to_flash(self):
        calls = []

        class QuotaResult:
            returncode = 1
            stdout = json.dumps(
                {
                    "error": {
                        "message": "Quota exceeded for model gemini-3-pro-preview.",
                    }
                }
            )
            stderr = ""

        class SuccessResult:
            returncode = 0
            stdout = json.dumps({"response": "Fallback response", "stats": {}})
            stderr = ""

        def fake_run(command, **kwargs):
            calls.append(command)
            if len(calls) == 1:
                return QuotaResult()
            return SuccessResult()

        original_run = gemini.subprocess.run
        gemini.subprocess.run = fake_run
        try:
            result = gemini.invoke_gemini_url(
                url="https://example.com/article",
                instruction="Summarize.",
                timeout_sec=30,
            )
        finally:
            gemini.subprocess.run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["response"], "Fallback response")
        self.assertEqual(result["model_used"], "gemini-3-flash-preview")
        self.assertEqual(result["model_attempts"][0]["model"], "gemini-3-pro-preview")
        self.assertFalse(result["model_attempts"][0]["ok"])
        self.assertEqual(result["model_attempts"][1]["model"], "gemini-3-flash-preview")
        self.assertEqual(calls[0][calls[0].index("--model") + 1], "gemini-3-pro-preview")
        self.assertEqual(calls[1][calls[1].index("--model") + 1], "gemini-3-flash-preview")

    def test_explicit_model_is_attempted_first_then_ladder_continues(self):
        calls = []

        class QuotaResult:
            returncode = 1
            stdout = json.dumps({"error": {"message": "No capacity available for this model."}})
            stderr = ""

        class SuccessResult:
            returncode = 0
            stdout = json.dumps({"response": "Recovered", "stats": {}})
            stderr = ""

        def fake_run(command, **kwargs):
            calls.append(command)
            if len(calls) == 1:
                return QuotaResult()
            return SuccessResult()

        original_run = gemini.subprocess.run
        gemini.subprocess.run = fake_run
        try:
            result = gemini.invoke_gemini_research(
                "reccomend me a colony sim",
                model="gemini-2.0-pro-exp",
                timeout_sec=30,
            )
        finally:
            gemini.subprocess.run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["model_attempts"][0]["model"], "gemini-2.0-pro-exp")
        self.assertEqual(result["model_attempts"][1]["model"], "gemini-3-pro-preview")
        self.assertEqual(result["model_used"], "gemini-3-pro-preview")
        self.assertEqual(calls[0][calls[0].index("--model") + 1], "gemini-2.0-pro-exp")
        self.assertEqual(calls[1][calls[1].index("--model") + 1], "gemini-3-pro-preview")

    def test_auth_failure_does_not_fallback_to_next_model(self):
        calls = []

        class Result:
            returncode = 41
            stdout = ""
            stderr = json.dumps(
                {
                    "error": {
                        "message": "Please set an Auth method before running Gemini CLI.",
                    }
                }
            )

        def fake_run(command, **kwargs):
            calls.append(command)
            return Result()

        original_run = gemini.subprocess.run
        gemini.subprocess.run = fake_run
        try:
            result = gemini.invoke_gemini_url(
                url="https://example.com/article",
                instruction="Summarize.",
                timeout_sec=30,
            )
        finally:
            gemini.subprocess.run = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["model_used"], None)
        self.assertEqual(result["model_attempts"][0]["model"], "gemini-3-pro-preview")
        self.assertIn("Please set an Auth method", result["response"])

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
