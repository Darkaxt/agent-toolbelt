import io
import json
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_SRC = REPO_ROOT / "families" / "antigravity" / "src"
sys.path.insert(0, str(FAMILY_SRC))

from agent_toolbelt_antigravity import cli, runtime  # noqa: E402


class RuntimeIsolationTests(unittest.TestCase):
    def test_runtime_paths_are_owned_by_antigravity_review_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "Tools" / "antigravity-review"
            paths = runtime.RuntimePaths.from_base(base)

            self.assertEqual(paths.base, base.resolve())
            self.assertEqual(paths.releases, base.resolve() / "releases")
            self.assertEqual(paths.state, base.resolve() / "state")
            self.assertEqual(paths.auth, base.resolve() / "auth")
            self.assertEqual(paths.current, base.resolve() / "state" / "current.json")

    def test_isolation_rejects_claude_binary_auth_or_port_overlap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            helper = runtime.RuntimePaths.from_base(root / "helper")
            claude_binary = root / "claude" / "cli-proxy-api.exe"
            claude_auth = root / "claude-auth"

            runtime.assert_runtime_isolation(
                paths=helper,
                helper_binary=helper.releases / "7.2.88" / "cli-proxy-api.exe",
                helper_port=18317,
                claude_binary=claude_binary,
                claude_auth=claude_auth,
                claude_port=8317,
            )

            for kwargs in (
                {"helper_binary": claude_binary, "helper_port": 18317},
                {"helper_binary": helper.releases / "x" / "cli-proxy-api.exe", "helper_port": 8317},
            ):
                with self.subTest(kwargs=kwargs), self.assertRaises(runtime.IsolationError):
                    runtime.assert_runtime_isolation(
                        paths=helper,
                        claude_binary=claude_binary,
                        claude_auth=claude_auth,
                        claude_port=8317,
                        **kwargs,
                    )

            overlapping = runtime.RuntimePaths.from_base(claude_auth)
            with self.assertRaises(runtime.IsolationError):
                runtime.assert_runtime_isolation(
                    paths=overlapping,
                    helper_binary=overlapping.releases / "x" / "cli-proxy-api.exe",
                    helper_port=18317,
                    claude_binary=claude_binary,
                    claude_auth=claude_auth,
                    claude_port=8317,
                )

    def test_find_free_loopback_port_never_returns_forbidden_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            forbidden = occupied.getsockname()[1]

            selected = runtime.find_free_loopback_port({forbidden, 8317})

        self.assertNotIn(selected, {forbidden, 8317})
        self.assertGreater(selected, 0)


class StatusTests(unittest.TestCase):
    def test_status_is_read_only_and_redacts_auth_file_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = runtime.RuntimePaths.from_base(Path(temp_dir) / "helper")
            paths.auth.mkdir(parents=True)
            (paths.auth / "sensitive-account-name.json").write_text("{}", encoding="utf-8")
            before = sorted(path.relative_to(paths.base) for path in paths.base.rglob("*"))

            result = runtime.collect_status(
                paths,
                claude_detector=lambda: {
                    "detected": True,
                    "port": 8317,
                    "pid": 1234,
                    "binary_path": "C:/external/CLIProxyAPI/cli-proxy-api.exe",
                    "ownership": "external_claude_proxy",
                },
            )
            after = sorted(path.relative_to(paths.base) for path in paths.base.rglob("*"))

        self.assertEqual(before, after)
        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "status")
        self.assertEqual(result["auth"]["file_count"], 1)
        self.assertNotIn("files", result["auth"])
        self.assertTrue(result["claude_proxy"]["detected"])
        self.assertTrue(result["claude_proxy_untouched"])

    def test_cli_status_emits_one_json_document(self):
        original = cli.runtime.collect_status
        cli.runtime.collect_status = lambda paths: {
            "ok": True,
            "operation": "status",
            "runtime_root": str(paths.base),
        }
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["status"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.runtime.collect_status = original

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "status")


if __name__ == "__main__":
    unittest.main()
