import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from outlook_classic_mail_client import blocklists


class BlocklistTests(unittest.TestCase):
    def test_parse_blocklist_domains_from_common_formats(self):
        text = """
        # comment
        0.0.0.0 malware.example.com
        127.0.0.1 ads.example.net
        phishing.example.org
        ||tracker.example.biz^
        *.wild.example.co.uk
        server=/dnsmasq.example.com/
        address=/address.example.com/0.0.0.0
        https://url.example.org/path
        logo.png
        """

        domains = blocklists.parse_blocklist_domains(text)

        self.assertIn("malware.example.com", domains)
        self.assertIn("tracker.example.biz", domains)
        self.assertIn("wild.example.co.uk", domains)
        self.assertIn("dnsmasq.example.com", domains)
        self.assertIn("address.example.com", domains)
        self.assertIn("url.example.org", domains)
        self.assertNotIn("logo.png", domains)

    def test_sqlite_cache_refresh_status_and_suffix_lookup(self):
        fetched = []

        def fetcher(url):
            fetched.append(url)
            return "listed.example.com\nexample.net\n"

        source = blocklists.BlocklistSource(
            name="unit-threat",
            category="malware",
            url="https://example.test/list.txt",
            profile="threat",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = blocklists.BlocklistCache(Path(temp_dir) / "blocklists.sqlite", sources=[source], fetcher=fetcher)
            summary = cache.refresh(profile="threat", force=True)
            hits = cache.lookup("a.b.listed.example.com", profile="threat")
            parent_hits = cache.lookup("sub.example.net", profile="threat")
            status = cache.status(profile="threat")

        self.assertEqual(summary["refreshed"], 1)
        self.assertEqual(len(fetched), 1)
        self.assertEqual(hits[0]["matched_domain"], "listed.example.com")
        self.assertEqual(parent_hits[0]["matched_domain"], "example.net")
        self.assertEqual(status[0]["domains"], 2)

    def test_cache_refresh_honors_ttl(self):
        now = datetime(2026, 4, 22, tzinfo=timezone.utc)
        fetched = []

        def fetcher(url):
            fetched.append(url)
            return "example.com\n"

        source = blocklists.BlocklistSource(
            name="unit-threat",
            category="malware",
            url="https://example.test/list.txt",
            profile="threat",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = blocklists.BlocklistCache(Path(temp_dir) / "blocklists.sqlite", sources=[source], fetcher=fetcher)
            cache.refresh(profile="threat", force=True, now=now)
            cache.refresh(profile="threat", now=now + timedelta(hours=1))
            cache.refresh(profile="threat", now=now + timedelta(days=2))

        self.assertEqual(len(fetched), 2)


if __name__ == "__main__":
    unittest.main()
