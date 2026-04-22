import sys
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mail_domain_quarantine import cli


class CliTests(unittest.TestCase):
    def test_console_json_escapes_non_ascii(self):
        text = cli.console_json({"subject": "hidden\u200cmarker"})

        self.assertIn("\\u200c", text)

    def test_scan_accepts_with_reputation_flag(self):
        original = cli.scanner.run_scan
        calls = []
        cli.scanner.run_scan = lambda **kwargs: calls.append(kwargs) or {"ok": True}
        try:
            exit_code = cli.main(["scan", "--dry-run", "--with-reputation"])
        finally:
            cli.scanner.run_scan = original

        self.assertEqual(exit_code, 0)
        self.assertTrue(calls[0]["with_reputation"])


if __name__ == "__main__":
    unittest.main()
