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
    "observable-reputation": {
        "project_name": "agent-toolbelt-observable-reputation",
        "script_name": "agent-toolbelt-observable-reputation",
        "package_dir": "observable_reputation",
    },
    "mail-domain-quarantine": {
        "project_name": "agent-toolbelt-mail-domain-quarantine",
        "script_name": "agent-toolbelt-mail-domain-quarantine",
        "package_dir": "mail_domain_quarantine",
    },
    "amazon-cli": {
        "project_name": "agent-toolbelt-amazon-cli",
        "script_name": "agent-toolbelt-amazon-cli",
        "package_dir": "agent_toolbelt_amazon_cli",
    },
    "linkedin-cv": {
        "project_name": "agent-toolbelt-linkedin-cv",
        "script_name": "agent-toolbelt-linkedin-cv",
        "package_dir": "agent_toolbelt_linkedin_cv",
    },
    "whatsapp-wacli": {
        "project_name": "agent-toolbelt-whatsapp-wacli",
        "script_name": "agent-toolbelt-whatsapp-wacli",
        "package_dir": "agent_toolbelt_whatsapp_wacli",
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
                "families/observable-reputation",
                "families/mail-domain-quarantine",
                "families/amazon-cli",
                "families/linkedin-cv",
                "families/whatsapp-wacli",
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

    def test_linkedin_skill_bundles_have_frontmatter(self):
        skill_paths = [
            REPO_ROOT / "families" / "linkedin-cv" / "codex" / "skills" / "linkedin-cv" / "SKILL.md",
            REPO_ROOT
            / "families"
            / "linkedin-cv"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
            / "plugins"
            / "linkedin-cv"
            / "skills"
            / "linkedin-cv"
            / "SKILL.md",
        ]

        for path in skill_paths:
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                self.assertIn("name:", text.split("---", 2)[1])
                self.assertIn("description:", text.split("---", 2)[1])

    def test_linkedin_temp_route_capture_is_not_committed(self):
        self.assertFalse((REPO_ROOT / "tmp-linkedin-skills-route.html").exists())

    def test_linkedin_family_uses_sanitized_public_fixtures(self):
        text = (
            REPO_ROOT / "families" / "linkedin-cv" / "tests" / "test_linkedin_cv.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("José Miguel Soriano de la Cámara", text)
        self.assertNotIn("josesorianocyber", text)


if __name__ == "__main__":
    unittest.main()
