import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agent_toolbelt_antigravity import cli, proxy, runtime


class ProxyConfigurationTests(unittest.TestCase):
    def test_locked_down_config_uses_only_helper_resources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = runtime.RuntimePaths.from_base(Path(temp_dir) / "helper")

            config = proxy.build_proxy_config(paths, port=41321, api_key="test-key")

            self.assertIn('host: "127.0.0.1"', config)
            self.assertIn("port: 41321", config)
            self.assertIn(f'auth-dir: "{paths.auth.as_posix()}"', config)
            self.assertIn('  - "test-key"', config)
            self.assertIn("secret-key: \"\"", config)
            self.assertIn("disable-control-panel: true", config)
            self.assertIn("enabled: false", config)
            self.assertIn("logging-to-file: false", config)
            self.assertIn("usage-statistics-enabled: false", config)
            self.assertIn("request-retry: 0", config)
            self.assertIn("max-retry-credentials: 1", config)
            self.assertIn("switch-project: false", config)
            self.assertIn("switch-preview-model: false", config)
            self.assertIn("antigravity-credits: false", config)
            self.assertIn('strategy: "fill-first"', config)
            self.assertNotIn("8317", config)
            self.assertNotIn(".cli-proxy-api", config)

    def test_windows_service_process_uses_no_console_flag(self):
        self.assertEqual(proxy.hidden_creation_flags("nt"), 0x08000000)
        self.assertEqual(proxy.hidden_creation_flags("posix"), 0)


class LoginTests(unittest.TestCase):
    def test_login_is_foreground_unbounded_and_uses_helper_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = runtime.RuntimePaths.from_base(Path(temp_dir) / "helper")
            binary = self._activate_fake_runtime(paths)
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))

                class Completed:
                    returncode = 0

                return Completed()

            result = proxy.run_login(paths, no_browser=True, process_runner=runner)

            command, kwargs = calls[0]
            self.assertTrue(result["ok"])
            self.assertEqual(command[0], str(binary))
            self.assertIn("-antigravity-login", command)
            self.assertIn("-no-browser", command)
            self.assertIn("-config", command)
            self.assertNotIn("timeout", kwargs)
            self.assertNotIn("creationflags", kwargs)
            self.assertTrue(result["claude_proxy_untouched"])

    @staticmethod
    def _activate_fake_runtime(paths: runtime.RuntimePaths) -> Path:
        release = paths.releases / "7.2.88"
        release.mkdir(parents=True)
        binary = release / "cli-proxy-api.exe"
        binary.write_bytes(b"fake")
        paths.state.mkdir(parents=True)
        paths.current.write_text(
            json.dumps({"version": "7.2.88", "binary_path": str(binary)}),
            encoding="utf-8",
        )
        return binary


class ReviewContractTests(unittest.TestCase):
    def test_review_payload_contains_no_tools_and_hashes_explicit_packet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            packet = Path(temp_dir) / "packet.md"
            packet.write_text("# Review packet\nConcrete evidence.\n", encoding="utf-8")

            prepared = proxy.prepare_review(
                packet=packet,
                instruction="Review for requirement drift.",
                model="gemini-3.1-pro-high",
            )

            self.assertEqual(
                prepared.packet_sha256,
                hashlib.sha256(packet.read_bytes()).hexdigest(),
            )
            self.assertNotIn("tools", prepared.request_payload)
            self.assertFalse(prepared.request_payload["stream"])
            self.assertEqual(prepared.request_payload["model"], "gemini-3.1-pro-high")
            self.assertEqual(
                prepared.request_payload["messages"][0],
                {"role": "system", "content": "Review for requirement drift."},
            )

    def test_exact_reported_model_is_required(self):
        result = proxy.normalize_review_response(
            requested_model="gemini-3.1-pro-high",
            response_payload={
                "model": "gemini-3.1-pro-high",
                "choices": [{"message": {"content": "Verdict: pass"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            },
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["model_verified"])
        self.assertEqual(result["response"], "Verdict: pass")

    def test_missing_model_attribution_fails_closed(self):
        result = proxy.normalize_review_response(
            requested_model="gemini-3.1-pro-high",
            response_payload={
                "choices": [{"message": {"content": "Verdict: pass"}}],
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_kind"], "model_attribution_missing")
        self.assertFalse(result["model_verified"])

    def test_model_mismatch_fails_closed_even_with_response_text(self):
        result = proxy.normalize_review_response(
            requested_model="gemini-3.1-pro-high",
            response_payload={
                "model": "gemini-3.1-flash",
                "choices": [{"message": {"content": "Verdict: pass"}}],
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_kind"], "model_mismatch")
        self.assertEqual(result["model_reported"], "gemini-3.1-flash")
        self.assertEqual(result["response"], "Verdict: pass")


class OwnedProcessTests(unittest.TestCase):
    def test_ephemeral_proxy_stops_only_the_process_it_started(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = runtime.RuntimePaths.from_base(Path(temp_dir) / "helper")
            binary = LoginTests._activate_fake_runtime(paths)

            class FakeProcess:
                pid = 4242

                def __init__(self):
                    self.terminated = False
                    self.waited = False

                def poll(self):
                    return None

                def terminate(self):
                    self.terminated = True

                def wait(self):
                    self.waited = True
                    return 0

            process = FakeProcess()
            calls = []

            def process_factory(command, **kwargs):
                calls.append((command, kwargs))
                return process

            with proxy.ephemeral_proxy(
                paths,
                process_factory=process_factory,
                readiness_probe=lambda port: True,
                port_selector=lambda forbidden: 41321,
                api_key_factory=lambda: "test-key",
            ) as service:
                self.assertEqual(service.pid, 4242)
                self.assertEqual(service.port, 41321)
                self.assertEqual(service.binary, binary)
                self.assertFalse(process.terminated)

            command, kwargs = calls[0]
            self.assertEqual(command[0], str(binary))
            self.assertIn("-config", command)
            self.assertEqual(kwargs["creationflags"], proxy.hidden_creation_flags())
            self.assertTrue(process.terminated)
            self.assertTrue(process.waited)
            self.assertFalse((paths.state / "runs").exists())


class CliParserTests(unittest.TestCase):
    def test_parser_accepts_login_models_and_exact_review(self):
        parser = cli.build_parser()

        login = parser.parse_args(["login", "--no-browser"])
        models = parser.parse_args(["models"])
        review = parser.parse_args(
            [
                "review",
                "--packet",
                "packet.md",
                "--instruction",
                "Review this.",
                "--model",
                "gemini-3.1-pro-high",
            ]
        )

        self.assertTrue(login.no_browser)
        self.assertEqual(models.command, "models")
        self.assertEqual(review.model, "gemini-3.1-pro-high")


if __name__ == "__main__":
    unittest.main()
