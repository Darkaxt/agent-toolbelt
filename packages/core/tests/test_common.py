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


if __name__ == "__main__":
    unittest.main()
