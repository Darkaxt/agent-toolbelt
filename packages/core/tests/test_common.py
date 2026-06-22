import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from agent_toolbelt_core import common  # noqa: E402


class CommonTests(unittest.TestCase):
    def test_validate_public_url_accepts_public_https_url(self):
        self.assertEqual(
            common.validate_public_url("https://example.com/path"),
            "https://example.com/path",
        )

    def test_validate_public_url_rejects_localhost(self):
        with self.assertRaisesRegex(ValueError, "Localhost URLs are not allowed"):
            common.validate_public_url("http://localhost:8000")

    def test_run_process_captures_text_as_utf8_with_replacement(self):
        original_run = common.subprocess.run
        calls = []

        def fake_run(command, **kwargs):
            calls.append(kwargs)
            return common.subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

        common.subprocess.run = fake_run
        try:
            common.run_process(["tool"], timeout_sec=1)
        finally:
            common.subprocess.run = original_run

        self.assertEqual(calls[0]["encoding"], "utf-8")
        self.assertEqual(calls[0]["errors"], "replace")


if __name__ == "__main__":
    unittest.main()
