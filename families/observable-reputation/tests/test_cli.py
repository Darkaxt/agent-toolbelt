import json
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from observable_reputation import cli


class CliTests(unittest.TestCase):
    def test_classify_reads_input_and_writes_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "observables.json"
            output_path = Path(temp_dir) / "report.json"
            input_path.write_text(
                json.dumps({"observables": [{"type": "domain", "value": "example.com"}]}),
                encoding="utf-8",
            )

            exit_code = cli.main(["classify", "--input", str(input_path), "--output", str(output_path), "--no-network"])

            report = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["observables"][0]["type"], "domain")
        self.assertIn(report["observables"][0]["verdict"], {"unknown", "skipped"})

    def test_providers_status_reports_missing_optional_keys(self):
        exit_code = cli.main(["providers", "--status"])

        self.assertEqual(exit_code, 0)

    def test_quiet_classify_writes_output_without_printing_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "observables.json"
            output_path = Path(temp_dir) / "report.json"
            input_path.write_text(
                json.dumps({"observables": [{"type": "domain", "value": "example.com"}]}),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = cli.main(
                    ["classify", "--input", str(input_path), "--output", str(output_path), "--no-network", "--quiet"]
                )
            output_exists = output_path.exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(output_exists)


if __name__ == "__main__":
    unittest.main()
