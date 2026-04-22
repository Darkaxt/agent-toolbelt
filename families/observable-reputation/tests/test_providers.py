import sys
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from observable_reputation import observables, providers


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, *, headers=None, params=None):
        self.calls.append(("GET", url, headers or {}, params or {}))
        return self.payload

    def post_form_json(self, url, data, *, headers=None):
        self.calls.append(("POST_FORM", url, headers or {}, data or {}))
        return self.payload

    def get_text(self, url, *, headers=None):
        self.calls.append(("GET_TEXT", url, headers or {}, {}))
        return self.payload


class ProviderTests(unittest.TestCase):
    def test_missing_api_key_returns_skipped(self):
        observable = observables.Observable(type="domain", value="example.com")

        result = providers.UrlscanProvider(api_key=None).check(observable)

        self.assertEqual(result.verdict, "skipped")
        self.assertEqual(result.provider, "urlscan")

    def test_urlscan_uses_search_endpoint_not_scan_endpoint(self):
        http = FakeHttp({"results": [{"verdicts": {"overall": {"malicious": True, "score": 80}}}]})
        observable = observables.Observable(type="domain", value="example.com")

        result = providers.UrlscanProvider(api_key="key", http=http).check(observable)

        self.assertEqual(result.verdict, "suspicious")
        self.assertEqual(http.calls[0][0], "GET")
        self.assertIn("/api/v1/search", http.calls[0][1])
        self.assertNotIn("/api/v1/scan", http.calls[0][1])

    def test_virustotal_uses_existing_object_lookup_only(self):
        http = FakeHttp({"data": {"attributes": {"last_analysis_stats": {"malicious": 2}}}})
        observable = observables.Observable(type="domain", value="bad.example")

        result = providers.VirusTotalProvider(api_key="key", http=http).check(observable)

        self.assertEqual(result.verdict, "malicious")
        self.assertEqual(http.calls, [("GET", "https://www.virustotal.com/api/v3/domains/bad.example", {"x-apikey": "key"}, {})])

    def test_abuseipdb_uses_check_endpoint_not_report_endpoint(self):
        http = FakeHttp({"data": {"abuseConfidenceScore": 91}})
        observable = observables.Observable(type="ip", value="203.0.113.7")

        result = providers.AbuseIpdbProvider(api_key="key", http=http).check(observable)

        self.assertEqual(result.verdict, "malicious")
        self.assertIn("/api/v2/check", http.calls[0][1])
        self.assertNotIn("/api/v2/report", http.calls[0][1])

    def test_urlhaus_uses_lookup_endpoint_not_submission_endpoint(self):
        http = FakeHttp({"query_status": "ok", "url_status": "online"})
        observable = observables.Observable(type="url", value="https://bad.example/a")

        result = providers.UrlhausProvider(auth_key="key", http=http).check(observable)

        self.assertEqual(result.verdict, "malicious")
        self.assertEqual(http.calls[0][0], "POST_FORM")
        self.assertIn("/v1/url/", http.calls[0][1])
        self.assertNotIn("submission", http.calls[0][1])

    def test_spamhaus_queries_dbl_and_zrd_domain_zones_only(self):
        queries = []

        def resolver(query):
            queries.append(query)
            return ["127.0.1.2"] if ".dbl." in query else []

        observable = observables.Observable(type="domain", value="bad.example")

        result = providers.SpamhausProvider(dqs_key="key", resolver=resolver).check(observable)

        self.assertEqual(result.verdict, "malicious")
        self.assertEqual(
            queries,
            [
                "bad.example.key.dbl.dq.spamhaus.net",
                "bad.example.key.zrd.dq.spamhaus.net",
            ],
        )

    def test_openphish_exact_url_match_is_malicious(self):
        provider = providers.OpenPhishProvider(feed_text="https://bad.example/a\n")
        observable = observables.Observable(type="url", value="https://bad.example/a")

        result = provider.check(observable)

        self.assertEqual(result.verdict, "malicious")


if __name__ == "__main__":
    unittest.main()
