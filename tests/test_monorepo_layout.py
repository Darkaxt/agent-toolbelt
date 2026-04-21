import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_FAMILIES = {
    "gemini": {
        "project_name": "agent-toolbelt-gemini",
        "script_name": "agent-toolbelt-gemini",
        "package_dir": "agent_toolbelt_gemini",
    },
    "everything": {
        "project_name": "agent-toolbelt-everything",
        "script_name": "agent-toolbelt-everything",
        "package_dir": "agent_toolbelt_everything",
    },
    "uvrun": {
        "project_name": "agent-toolbelt-uvrun",
        "script_name": "agent-toolbelt-uvrun",
        "package_dir": "agent_toolbelt_uvrun",
    },
    "media": {
        "project_name": "agent-toolbelt-media",
        "script_name": "agent-toolbelt-media",
        "package_dir": "agent_toolbelt_media",
    },
    "outlook-classic-mail": {
        "project_name": "agent-toolbelt-outlook-classic-mail",
        "script_name": "agent-toolbelt-outlook-classic-mail",
        "package_dir": "agent_toolbelt_outlook_classic_mail",
    },
    "amazon-cli": {
        "project_name": "agent-toolbelt-amazon-cli",
        "script_name": "agent-toolbelt-amazon-cli",
        "package_dir": "agent_toolbelt_amazon_cli",
    },
}


class MonorepoLayoutTests(unittest.TestCase):
    def test_root_pyproject_is_workspace_only(self):
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertNotIn("project", pyproject)
        self.assertEqual(
            pyproject["tool"]["uv"]["workspace"]["members"],
            [
                "packages/core",
                "families/gemini",
                "families/everything",
                "families/uvrun",
                "families/media",
                "families/outlook-classic-mail",
                "families/amazon-cli",
            ],
        )

    def test_shared_core_package_exists(self):
        core_root = REPO_ROOT / "packages" / "core"
        self.assertTrue((core_root / "README.md").is_file())
        self.assertTrue((core_root / "pyproject.toml").is_file())
        self.assertTrue((core_root / "src" / "agent_toolbelt_core").is_dir())

    def test_each_family_is_self_contained(self):
        for family_name, metadata in EXPECTED_FAMILIES.items():
            with self.subTest(family=family_name):
                family_root = REPO_ROOT / "families" / family_name
                self.assertTrue((family_root / "README.md").is_file())
                self.assertTrue((family_root / "pyproject.toml").is_file())
                self.assertTrue((family_root / "src").is_dir())
                self.assertTrue((family_root / "tests").is_dir())
                self.assertTrue((family_root / "codex").is_dir())
                self.assertTrue((family_root / "claude").is_dir())

                pyproject = tomllib.loads((family_root / "pyproject.toml").read_text(encoding="utf-8"))
                self.assertEqual(pyproject["project"]["name"], metadata["project_name"])
                self.assertEqual(
                    pyproject["project"]["scripts"][metadata["script_name"]],
                    f"{metadata['package_dir']}.cli:entrypoint",
                )
                self.assertTrue((family_root / "src" / metadata["package_dir"] / "cli.py").is_file())

    def test_root_runtime_package_is_removed(self):
        self.assertFalse((REPO_ROOT / "src" / "agent_toolbelt").exists())


if __name__ == "__main__":
    unittest.main()
