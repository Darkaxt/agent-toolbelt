import sys
import tempfile
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mail_domain_quarantine import state


class StateTests(unittest.TestCase):
    def test_default_blocklist_suppressions_are_seeded_in_trust_db(self):
        original_state_dir = state.STATE_DIR
        original_report_dir = state.REPORT_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            state.STATE_DIR = Path(tmpdir) / "state"
            state.REPORT_DIR = Path(tmpdir) / "reports"
            try:
                suppressions = state.load_blocklist_suppressions()
            finally:
                state.STATE_DIR = original_state_dir
                state.REPORT_DIR = original_report_dir

        self.assertIn("exacttarget.com", suppressions)
        self.assertIn("shared", suppressions["exacttarget.com"])
        self.assertIn("awstrack.me", suppressions)


if __name__ == "__main__":
    unittest.main()
