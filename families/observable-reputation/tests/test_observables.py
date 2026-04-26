import sys
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from observable_reputation import observables


class ObservableTests(unittest.TestCase):
    def test_normalizes_domain_url_and_ip_observables(self):
        domain = observables.normalize_observable({"type": "domain", "value": " Mail.Example.COM. "})
        url = observables.normalize_observable(
            {"type": "url", "value": "HTTPS://Example.COM/Login?A=1", "source": "body"}
        )
        ip = observables.normalize_observable({"type": "ip", "value": " 203.0.113.7 "})

        self.assertEqual(domain.value, "mail.example.com")
        self.assertEqual(url.value, "https://example.com/Login?A=1")
        self.assertEqual(url.domain, "example.com")
        self.assertEqual(url.source, "body")
        self.assertEqual(ip.value, "203.0.113.7")

    def test_rejects_unsupported_observable_type(self):
        with self.assertRaises(ValueError):
            observables.normalize_observable({"type": "email", "value": "user@example.com"})

    def test_auto_detects_and_normalizes_messy_records(self):
        normalized, rejected = observables.normalize_records(
            [
                "HTTPS://User:Pass@Exämple.COM/path?q=1#frag",
                {"type": "auto", "value": "admin@Mail.Example.COM", "source": "sender"},
                {"value": " 203.0.113.7 ", "source": "header"},
                {"type": "auto", "value": "not an observable"},
            ],
            auto_detect=True,
        )

        self.assertEqual([item.type for item in normalized], ["url", "domain", "ip"])
        self.assertEqual(normalized[0].raw_value, "HTTPS://User:Pass@Exämple.COM/path?q=1#frag")
        self.assertEqual(normalized[0].value, "https://xn--exmple-cua.com/path?q=1")
        self.assertEqual(normalized[0].domain, "xn--exmple-cua.com")
        self.assertIn("userinfo_removed", normalized[0].normalization["warnings"])
        self.assertIn("fragment_removed", normalized[0].normalization["warnings"])
        self.assertEqual(normalized[1].value, "mail.example.com")
        self.assertEqual(normalized[1].normalization["detected_from"], "email-domain")
        self.assertEqual(normalized[2].value, "203.0.113.7")
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["raw_value"], "not an observable")

    def test_strict_records_report_malformed_observables_without_auto_detection(self):
        normalized, rejected = observables.normalize_records(
            [
                {"type": "domain", "value": "Example.COM"},
                {"value": "example.net"},
                {"type": "email", "value": "user@example.org"},
            ]
        )

        self.assertEqual([item.value for item in normalized], ["example.com"])
        self.assertEqual(len(rejected), 2)
        self.assertIn("Unsupported observable type", rejected[0]["error"])


if __name__ == "__main__":
    unittest.main()
