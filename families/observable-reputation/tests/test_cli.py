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
        self.assertIn("diagnostics", report)

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

    def test_normalize_command_accepts_messy_input_and_writes_rejections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "observables.json"
            output_path = Path(temp_dir) / "normalized.json"
            input_path.write_text(
                json.dumps({"observables": ["https://User:Pass@Example.COM/a#section", "not an observable"]}),
                encoding="utf-8",
            )

            exit_code = cli.main(["normalize", "--input", str(input_path), "--output", str(output_path)])
            report = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["observables"][0]["value"], "https://example.com/a")
        self.assertEqual(report["observables"][0]["raw_value"], "https://User:Pass@Example.COM/a#section")
        self.assertEqual(len(report["rejected_observables"]), 1)

    def test_classify_auto_detect_writes_csv_and_stix_exports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "observables.json"
            output_path = Path(temp_dir) / "report.json"
            csv_path = Path(temp_dir) / "report.csv"
            stix_path = Path(temp_dir) / "bundle.json"
            input_path.write_text(
                json.dumps({"observables": ["https://example.com/a", "not an observable"]}),
                encoding="utf-8",
            )

            exit_code = cli.main(
                [
                    "classify",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--auto-detect",
                    "--no-network",
                    "--csv-output",
                    str(csv_path),
                    "--stix-output",
                    str(stix_path),
                    "--quiet",
                ]
            )
            report = json.loads(output_path.read_text(encoding="utf-8"))
            csv_text = csv_path.read_text(encoding="utf-8")
            bundle = json.loads(stix_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(report["observables"]), 1)
        self.assertEqual(len(report["rejected_observables"]), 1)
        self.assertIn("type,value,raw_value,domain,source,verdict,score,cached", csv_text)
        self.assertEqual(bundle["type"], "bundle")
        self.assertEqual(bundle["objects"], [])


if __name__ == "__main__":
    unittest.main()
