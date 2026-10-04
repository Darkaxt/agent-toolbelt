import contextlib
import io
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


class CatalogContracts(unittest.TestCase):
    def setUp(self):
        self.usage = importlib.import_module("agent_toolbelt_gradle_build_gate.usage")
        self.temp = tempfile.TemporaryDirectory(prefix="gradle-usage-test-", dir="D:/Temp" if Path("D:/Temp").is_dir() else None)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "catalog"
        if os.name != "nt":
            lock = patch.object(self.usage, "NamedMutex", side_effect=lambda *a: contextlib.nullcontext())
            lock.start(); self.addCleanup(lock.stop)

    def project(self, name, version):
        project = self.root / name
        props = project / "gradle/wrapper/gradle-wrapper.properties"
        props.parent.mkdir(parents=True, exist_ok=True)
        (project / "gradlew.bat").touch()
        props.write_text(f"distributionUrl=https\\://private.invalid/gradle-{version}-bin.zip?token=DO-NOT-STORE\n")
        return project

    def test_registration_refresh_preserves_reservations_and_omits_url_secrets(self):
        project = self.project("app", "8.6")
        result = self.usage.record_project(project, root=self.state, keep_versions=["8.6"])
        self.assertEqual(result["wrapper_version"], "8.6")
        self.project("app", "8.13")
        self.usage.record_project(project, root=self.state)
        catalog = self.usage.load_catalog(self.state)
        entry = next(iter(catalog["projects"].values()))
        self.assertEqual(entry["wrapper_version"], "8.13")
        self.assertEqual(entry["keep_versions"], ["8.6"])
        self.assertNotIn("DO-NOT-STORE", (self.state / "usage.json").read_text())
        self.assertNotIn("private.invalid", (self.state / "usage.json").read_text())
        self.assertTrue(self.usage.unregister_project(project, root=self.state)["removed"])
        self.assertEqual(self.usage.load_catalog(self.state)["projects"], {})
        self.assertTrue((project / "gradlew.bat").is_file())

    def test_corrupt_catalog_not_reset_and_invalid_reservation_not_saved(self):
        project = self.project("app", "8.6")
        with self.assertRaises(ValueError):
            self.usage.record_project(project, root=self.state, keep_versions=["../../user-data"])
        self.assertFalse((self.state / "usage.json").exists())
        self.state.mkdir()
        path = self.state / "usage.json"; path.write_text('{"schema":999}')
        with self.assertRaises(ValueError):
            self.usage.record_project(project, root=self.state)
        self.assertEqual(path.read_text(), '{"schema":999}')

    @unittest.skipUnless(os.name == "nt", "Native cross-process catalog serialization")
    def test_concurrent_registrations_do_not_lose_projects(self):
        children = []
        try:
            with self.usage.NamedMutex(self.usage.catalog_mutex_name(self.state)):
                for number in range(3):
                    project = self.project(str(number), "8.13")
                    code = ('from agent_toolbelt_gradle_build_gate.usage import record_project; from pathlib import Path; '
                            'import sys; print("ready",flush=True); record_project(Path(sys.argv[1]),root=Path(sys.argv[2]))')
                    child = subprocess.Popen([sys.executable, "-B", "-c", code, str(project), str(self.state)],
                                             env={**os.environ, "PYTHONPATH": str(SRC)}, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, text=True,
                                             creationflags=subprocess.CREATE_NO_WINDOW)
                    children.append(child)
                    self.assertEqual(child.stdout.readline().strip(), "ready")
            for child in children:
                self.assertEqual(child.wait(), 0, child.stderr.read())
            self.assertEqual(len(self.usage.load_catalog(self.state)["projects"]), 3)
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()  # Owned synthetic metadata writer only.
                child.wait(); child.stdout.close(); child.stderr.close()


class InventoryContracts(CatalogContracts):
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        homes = patch.object(self.usage, "observation_homes", return_value=[self.home])
        homes.start(); self.addCleanup(homes.stop)
        activity = patch.object(self.usage, "inspect_activity", return_value={"safe_to_start": True, "connections_known": True, "processes": []})
        self.activity = activity.start(); self.addCleanup(activity.stop)

    def artifact(self, relative, content=b"data"):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def inventory(self, **kwargs):
        return self.usage.inventory(root=self.state, **kwargs)

    def test_only_known_version_roots_are_proposed_and_new_baseline_unverified(self):
        project = self.project("app", "8.6")
        self.usage.record_project(project, root=self.state, keep_versions=["8.7"])
        for version in ("8.6", "8.7", "8.13", "9.0-rc-1"):
            self.artifact(f"wrapper/dists/gradle-{version}-bin/hash/lib/a.jar")
            self.artifact(f"caches/{version}/metadata.bin")
        for name in ("modules-2", "jars-9", "transforms-3", "build-cache-1"):
            self.artifact(f"caches/{name}/keep")
        self.artifact("jdks/17/keep")
        result = self.usage.cleanup_plan(root=self.state)
        self.assertEqual({p["version"] for p in result["proposals"]}, {"8.13", "9.0-rc-1"})
        self.assertEqual(result["estimated_bytes"], 16)
        self.assertTrue(result["transactional_cleanup_required"])
        self.assertFalse(result["deletes_files"])
        self.assertEqual(result["baseline_candidates"][0]["version"], "8.13")
        self.assertFalse(result["baseline_candidates"][0]["compatibility_verified"])
        self.assertEqual(len(result["artifacts"]), 8)
        self.assertTrue((self.home / "caches/8.13/metadata.bin").exists())

    def test_refresh_and_missing_project_are_conservative_without_mutating_catalog(self):
        project = self.project("app", "8.6")
        self.usage.record_project(project, root=self.state)
        before = (self.state / "usage.json").read_bytes()
        self.project("app", "8.13")
        self.artifact("caches/8.13/keep")
        self.assertFalse(self.inventory()["artifacts"][0]["eligible_for_review"])
        self.assertEqual((self.state / "usage.json").read_bytes(), before)
        (project / "gradlew.bat").unlink()
        result = self.inventory()
        self.assertTrue(result["reference_uncertainty"])
        self.assertFalse(result["artifacts"][0]["eligible_for_review"])

    def test_activity_and_live_idle_daemon_protect_cleanup(self):
        self.usage.record_project(self.project("app", "8.6"), root=self.state)
        self.artifact("caches/8.13/keep")
        self.activity.return_value = {"safe_to_start": True, "connections_known": True, "processes": [{"state": "idle", "version": "8.13"}]}
        self.assertEqual(self.usage.cleanup_plan(root=self.state)["proposals"], [])
        for state in ("active", "ambiguous"):
            self.activity.return_value = {"safe_to_start": False, "processes": [{"state": state, "version": "9.0"}]}
            result = self.usage.cleanup_plan(root=self.state)
            self.assertEqual(result["proposals"], [])
            self.assertIn("build_activity_not_clear", result["artifacts"][0]["protected_reasons"])

    def test_no_registered_projects_or_unknown_wrapper_cannot_propose_cleanup(self):
        self.artifact("caches/8.13/keep")
        self.assertEqual(self.usage.cleanup_plan(root=self.state)["proposals"], [])
        project = self.project("app", "8.6")
        (project / "gradle/wrapper/gradle-wrapper.properties").write_text("distributionUrl=https://private.invalid/custom.zip")
        self.usage.record_project(project, root=self.state)
        self.assertTrue(self.inventory()["reference_uncertainty"])
        self.assertEqual(self.usage.cleanup_plan(root=self.state)["proposals"], [])

    def test_hardlinks_and_incomplete_walk_never_become_proposals(self):
        self.usage.record_project(self.project("app", "8.6"), root=self.state)
        original = self.artifact("caches/8.13/keep")
        os.link(original, self.root / "outside")
        row = self.inventory()["artifacts"][0]
        self.assertIn("linked_or_reparse_content", row["protected_reasons"])
        with patch.object(self.usage.os, "scandir", side_effect=PermissionError("denied")):
            result = self.usage.cleanup_plan(root=self.state)
        self.assertEqual(result["proposals"], [])
        self.assertTrue(result["inventory_incomplete"])

    def test_reparse_measurement_does_not_follow_target(self):
        from types import SimpleNamespace
        import stat
        path = self.root / "junction"
        with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)), \
             patch.object(self.usage.os, "scandir") as scan:
            result = self.usage.measure_tree(path)
        self.assertTrue(result["linked_content"])
        self.assertEqual(result["bytes"], 0)
        scan.assert_not_called()

    def test_cli_routes_registration_and_read_only_commands(self):
        cli = importlib.import_module("agent_toolbelt_gradle_build_gate.cli")
        project = self.project("cli-app", "8.6")
        with patch.object(self.usage, "catalog_root", return_value=self.state):
            for arguments in (["register-project", "--project", str(project), "--keep-version", "8.7"],
                              ["inventory"], ["cleanup-plan"], ["unregister-project", "--project", str(project)]):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(cli.main(arguments), 0)
                self.assertTrue(json.loads(output.getvalue())["ok"])
        self.assertEqual(self.usage.load_catalog(self.state)["projects"], {})


class PolicyContracts(unittest.TestCase):
    def test_agent_bundles_match_and_require_scoped_verified_maintenance(self):
        family = SRC.parent
        codex = family / "codex/skills/gradle-build-gate"
        claude = family / "claude/marketplaces/agent-toolbelt-local/plugins/gradle-build-gate/skills/gradle-build-gate"
        for relative in ("SKILL.md", "references/runtime.md", "scripts/invoke_gradle_build_gate.py"):
            self.assertEqual((codex / relative).read_bytes(), (claude / relative).read_bytes())
        text = (codex / "SKILL.md").read_text()
        for requirement in ("already authorized", "highest installed/used is not proof", "AGP", "Kotlin", "JDK",
                            "Do NOT upgrade wrappers", "transactional-cleanup", "rollback/offline", "not a deletion ticket"):
            self.assertIn(requirement, text)


if __name__ == "__main__":
    unittest.main()
