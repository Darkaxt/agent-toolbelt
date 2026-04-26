import sys
import tempfile
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from observable_reputation import cache, classifier, exports, observables, providers


class StaticProvider:
    def __init__(self, name, result):
        self.name = name
        self.result = result
        self.calls = 0

    def check(self, observable):
        self.calls += 1
        return self.result


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, *, headers=None, params=None):
        self.calls.append(("GET", url, headers or {}, params or {}))
        return self.payload


class ClassifierTests(unittest.TestCase):
    def test_aggregation_prefers_highest_severity_verdict(self):
        observable = observables.Observable(type="domain", value="bad.example")
        clean = providers.ProviderResult(provider="clean", verdict="clean", score=0)
        suspicious = providers.ProviderResult(provider="suspicious", verdict="suspicious", score=50)
        malicious = providers.ProviderResult(provider="malicious", verdict="malicious", score=100)

        result = classifier.classify_observable(
            observable,
            provider_list=[
                StaticProvider("clean", clean),
                StaticProvider("suspicious", suspicious),
                StaticProvider("malicious", malicious),
            ],
        )

        self.assertEqual(result["verdict"], "malicious")
        self.assertEqual(result["score"], 100)
        self.assertEqual([item["provider"] for item in result["providers"]], ["clean", "suspicious", "malicious"])

    def test_cache_reuses_non_expired_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reputation_cache = cache.ReputationCache(Path(temp_dir) / "cache.sqlite", ttl_seconds=3600)
            observable = observables.Observable(type="domain", value="cached.example")
            provider = StaticProvider(
                "static",
                providers.ProviderResult(provider="static", verdict="suspicious", score=50),
            )

            first = classifier.classify_observable(observable, provider_list=[provider], reputation_cache=reputation_cache)
            second = classifier.classify_observable(observable, provider_list=[provider], reputation_cache=reputation_cache)

        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(provider.calls, 1)

    def test_cache_does_not_reuse_missing_key_result_after_provider_is_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reputation_cache = cache.ReputationCache(Path(temp_dir) / "cache.sqlite", ttl_seconds=3600)
            observable = observables.Observable(type="domain", value="example.com")
            classifier.classify_observable(
                observable,
                provider_list=[providers.UrlscanProvider(api_key=None)],
                reputation_cache=reputation_cache,
            )

            http = FakeHttp({"results": []})
            second = classifier.classify_observable(
                observable,
                provider_list=[providers.UrlscanProvider(api_key="key", http=http)],
                reputation_cache=reputation_cache,
            )

        self.assertFalse(second["cached"])
        self.assertEqual(second["verdict"], "clean")
        self.assertEqual(len(http.calls), 1)

    def test_cache_does_not_reuse_provider_error_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reputation_cache = cache.ReputationCache(Path(temp_dir) / "cache.sqlite", ttl_seconds=3600)
            observable = observables.Observable(type="domain", value="flaky.example")
            error_provider = StaticProvider(
                "static",
                providers.ProviderResult(provider="static", verdict="error", errors=["rate limited"]),
            )
            clean_provider = StaticProvider(
                "static",
                providers.ProviderResult(provider="static", verdict="clean", evidence=[{"result": "ok"}]),
            )

            first = classifier.classify_observable(
                observable,
                provider_list=[error_provider],
                reputation_cache=reputation_cache,
            )
            second = classifier.classify_observable(
                observable,
                provider_list=[clean_provider],
                reputation_cache=reputation_cache,
            )

        self.assertEqual(first["verdict"], "error")
        self.assertFalse(second["cached"])
        self.assertEqual(second["verdict"], "clean")
        self.assertEqual(clean_provider.calls, 1)

    def test_classify_records_reports_diagnostics_summaries_and_rejections(self):
        report = classifier.classify_records(
            [
                "https://bad.example/path",
                {"type": "auto", "value": "203.0.113.7"},
                {"type": "auto", "value": "not an observable"},
            ],
            auto_detect=True,
            provider_list=[
                StaticProvider(
                    "malicious-feed",
                    providers.ProviderResult(
                        provider="malicious-feed",
                        verdict="malicious",
                        score=100,
                        evidence=[{"match": "feed"}],
                    ),
                ),
                StaticProvider(
                    "skipped-provider",
                    providers.ProviderResult(
                        provider="skipped-provider",
                        verdict="skipped",
                        evidence=[{"reason": "unsupported observable type"}],
                    ),
                ),
            ],
        )

        self.assertEqual(len(report["observables"]), 2)
        self.assertEqual(len(report["rejected_observables"]), 1)
        first = report["observables"][0]
        self.assertEqual(first["raw_value"], "https://bad.example/path")
        self.assertEqual(first["normalized_value"], "https://bad.example/path")
        self.assertEqual(first["provider_summary"]["verdicts"]["malicious"], 1)
        self.assertEqual(first["provider_summary"]["skipped_count"], 1)
        self.assertIn("malicious", first["explanation"])
        diagnostics = report["diagnostics"]
        self.assertEqual(diagnostics["observable_count"], 2)
        self.assertEqual(diagnostics["rejected_observable_count"], 1)
        self.assertEqual(diagnostics["providers"]["configured_count"], 2)
        self.assertEqual(diagnostics["providers"]["skipped_count"], 2)

    def test_cache_key_version_prevents_reusing_v1_cached_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reputation_cache = cache.ReputationCache(Path(temp_dir) / "cache.sqlite", ttl_seconds=3600)
            observable = observables.Observable(type="domain", value="example.com")
            reputation_cache.set(
                "domain:example.com|providers=static()",
                {
                    "type": "domain",
                    "value": "example.com",
                    "verdict": "malicious",
                    "providers": [],
                    "errors": [],
                },
            )
            provider = StaticProvider(
                "static",
                providers.ProviderResult(provider="static", verdict="clean", evidence=[{"result": "fresh"}]),
            )

            result = classifier.classify_observable(observable, provider_list=[provider], reputation_cache=reputation_cache)

        self.assertEqual(result["verdict"], "clean")
        self.assertFalse(result["cached"])
        self.assertEqual(provider.calls, 1)

    def test_csv_and_stix_exports_are_bounded_and_deterministic(self):
        report = {
            "observables": [
                {
                    "type": "domain",
                    "value": "bad.example",
                    "raw_value": "Bad.Example",
                    "domain": "bad.example",
                    "source": "mail",
                    "verdict": "malicious",
                    "score": 100,
                    "cached": False,
                    "providers": [{"provider": "static", "verdict": "malicious"}],
                    "evidence": [{"provider": "static", "match": "feed"}],
                    "errors": [],
                    "explanation": "malicious evidence from static",
                },
                {
                    "type": "url",
                    "value": "https://clean.example/a",
                    "raw_value": "https://clean.example/a",
                    "domain": "clean.example",
                    "source": "mail",
                    "verdict": "clean",
                    "score": 0,
                    "cached": True,
                    "providers": [{"provider": "static", "verdict": "clean"}],
                    "evidence": [],
                    "errors": [],
                    "explanation": "clean evidence",
                },
                {
                    "type": "ip",
                    "value": "2001:db8::1",
                    "raw_value": "2001:db8::1",
                    "domain": None,
                    "source": "log",
                    "verdict": "suspicious",
                    "score": 50,
                    "cached": False,
                    "providers": [{"provider": "static", "verdict": "suspicious"}],
                    "evidence": [{"provider": "static", "match": "range"}],
                    "errors": [],
                    "explanation": "suspicious evidence from static",
                },
            ]
        }

        csv_text = exports.report_to_csv_text(report)
        bundle = exports.report_to_stix_bundle(report)

        self.assertIn("type,value,raw_value,domain,source,verdict,score,cached,provider_verdicts", csv_text)
        self.assertIn("domain,bad.example,Bad.Example,bad.example,mail,malicious,100,False,static:malicious", csv_text)
        self.assertEqual(bundle["type"], "bundle")
        self.assertEqual(len(bundle["objects"]), 2)
        patterns = {item["pattern"] for item in bundle["objects"]}
        self.assertIn("[domain-name:value = 'bad.example']", patterns)
        self.assertIn("[ipv6-addr:value = '2001:db8::1']", patterns)


if __name__ == "__main__":
    unittest.main()
