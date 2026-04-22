import sys
import tempfile
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from observable_reputation import cache, classifier, observables, providers


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


if __name__ == "__main__":
    unittest.main()
