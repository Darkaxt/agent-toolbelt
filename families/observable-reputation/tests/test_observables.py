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


if __name__ == "__main__":
    unittest.main()
