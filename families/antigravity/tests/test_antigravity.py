import io
import hashlib
import json
import shutil
import socket
import sys
import tempfile
import unittest
import zipfile
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


class UpdateTests(unittest.TestCase):
    def test_helper_cleanup_retries_transient_windows_file_lock(self):
        calls = []
        sleeps = []

        def remover(path):
            calls.append(path)
            if len(calls) == 1:
                raise PermissionError(32, "file is in use")

        runtime._remove_tree_when_released(
            Path("C:/helper/staging"),
            remover=remover,
            heartbeat=lambda seconds: sleeps.append(seconds),
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [0.1])

    def test_release_parser_selects_windows_amd64_and_preserves_digest(self):
        payload = {
            "tag_name": "v7.2.88",
            "published_at": "2026-07-18T15:37:00Z",
            "prerelease": False,
            "assets": [
                {
                    "name": "CLIProxyAPI_7.2.88_windows_aarch64.zip",
                    "size": 10,
                    "browser_download_url": (
                        "https://github.com/router-for-me/CLIProxyAPI/releases/download/"
                        "v7.2.88/CLIProxyAPI_7.2.88_windows_aarch64.zip"
                    ),
                    "digest": "sha256:" + "a" * 64,
                },
                {
                    "name": "CLIProxyAPI_7.2.88_windows_amd64.zip",
                    "size": 20,
                    "browser_download_url": (
                        "https://github.com/router-for-me/CLIProxyAPI/releases/download/"
                        "v7.2.88/CLIProxyAPI_7.2.88_windows_amd64.zip"
                    ),
                    "digest": "sha256:" + "b" * 64,
                },
            ],
        }

        release = runtime.parse_github_release(payload)

        self.assertEqual(release.version, "7.2.88")
        self.assertEqual(release.asset_name, "CLIProxyAPI_7.2.88_windows_amd64.zip")
        self.assertEqual(release.sha256, "b" * 64)

    def test_check_update_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = runtime.RuntimePaths.from_base(Path(temp_dir) / "helper")
            release = runtime.ReleaseInfo(
                version="7.2.88",
                tag="v7.2.88",
                published_at="2026-07-18T15:37:00Z",
                asset_name="CLIProxyAPI_7.2.88_windows_amd64.zip",
                asset_url="https://example.invalid/release.zip",
                asset_size=20,
                sha256="b" * 64,
            )

            result = runtime.check_update(paths, release)

            self.assertFalse(paths.base.exists())
            self.assertTrue(result["ok"])
            self.assertTrue(result["update_available"])
            self.assertEqual(result["latest_version"], "7.2.88")

    def test_install_release_verifies_digest_and_activates_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = runtime.RuntimePaths.from_base(temp / "helper")
            archive = self._make_archive(temp, b"fake-cli-binary")
            release = self._release_for_archive("7.2.88", archive)

            result = runtime.install_release(
                paths,
                release,
                downloader=lambda url, destination: shutil.copyfile(archive, destination),
                version_probe=lambda binary: "7.2.88",
            )

            current = json.loads(paths.current.read_text(encoding="utf-8"))
            binary = Path(current["binary_path"])
            manifest = json.loads(Path(current["manifest_path"]).read_text(encoding="utf-8"))

            self.assertTrue(result["ok"])
            self.assertEqual(result["operation"], "update")
            self.assertEqual(current["version"], "7.2.88")
            self.assertTrue(binary.is_file())
            self.assertEqual(manifest["archive_sha256"], release.sha256)
            self.assertFalse((paths.state / "current.json.tmp").exists())

    def test_install_release_rejects_digest_mismatch_before_activation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = runtime.RuntimePaths.from_base(temp / "helper")
            archive = self._make_archive(temp, b"fake-cli-binary")
            release = self._release_for_archive("7.2.88", archive)
            release = runtime.ReleaseInfo(**{**release.__dict__, "sha256": "0" * 64})

            with self.assertRaisesRegex(runtime.UpdateError, "digest"):
                runtime.install_release(
                    paths,
                    release,
                    downloader=lambda url, destination: shutil.copyfile(archive, destination),
                    version_probe=lambda binary: "7.2.88",
                )

            self.assertFalse(paths.current.exists())

    def test_install_release_rejects_archive_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = runtime.RuntimePaths.from_base(temp / "helper")
            archive = temp / "bad.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../cli-proxy-api.exe", b"bad")
            release = self._release_for_archive("7.2.88", archive)

            with self.assertRaisesRegex(runtime.UpdateError, "unsafe archive"):
                runtime.install_release(
                    paths,
                    release,
                    downloader=lambda url, destination: shutil.copyfile(archive, destination),
                    version_probe=lambda binary: "7.2.88",
                )

            self.assertFalse(paths.current.exists())

    def test_install_release_rejects_reported_version_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = runtime.RuntimePaths.from_base(temp / "helper")
            archive = self._make_archive(temp, b"fake-cli-binary")
            release = self._release_for_archive("7.2.88", archive)

            with self.assertRaisesRegex(runtime.UpdateError, "reported version"):
                runtime.install_release(
                    paths,
                    release,
                    downloader=lambda url, destination: shutil.copyfile(archive, destination),
                    version_probe=lambda binary: "7.2.86",
                )

            self.assertFalse(paths.current.exists())

    def test_install_release_retains_only_active_and_previous(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = runtime.RuntimePaths.from_base(temp / "helper")
            for version in ("7.2.86", "7.2.87", "7.2.88"):
                archive = self._make_archive(temp, version.encode("ascii"), name=f"{version}.zip")
                release = self._release_for_archive(version, archive)
                runtime.install_release(
                    paths,
                    release,
                    downloader=lambda url, destination, source=archive: shutil.copyfile(
                        source, destination
                    ),
                    version_probe=lambda binary, value=version: value,
                )

            releases = sorted(path.name for path in paths.releases.iterdir() if path.is_dir())

            self.assertEqual(releases, ["7.2.87", "7.2.88"])

    @staticmethod
    def _make_archive(temp: Path, binary: bytes, *, name: str = "release.zip") -> Path:
        archive = temp / name
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("cli-proxy-api.exe", binary)
        return archive

    @staticmethod
    def _release_for_archive(version: str, archive: Path) -> runtime.ReleaseInfo:
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        return runtime.ReleaseInfo(
            version=version,
            tag=f"v{version}",
            published_at="2026-07-18T15:37:00Z",
            asset_name=archive.name,
            asset_url=f"https://example.invalid/{archive.name}",
            asset_size=archive.stat().st_size,
            sha256=digest,
        )


if __name__ == "__main__":
    unittest.main()
