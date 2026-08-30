from __future__ import annotations

from pathlib import Path
import unittest


FAMILY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = FAMILY_ROOT / "codex" / "skills" / "context-transfer"


class ContextTransferSkillTests(unittest.TestCase):
    def test_skill_is_codex_only_and_destination_owned(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("destination task owns", skill.casefold())
        self.assertIn("do not ask the source task to summarize itself", skill.casefold())
        self.assertIn("read_thread", skill)
        self.assertIn("set_thread_archived", skill)
        self.assertIn("validate-handoff", skill)
        self.assertIn("validate-acceptance", skill)
        self.assertIn("issue-deletion-ticket", skill)
        self.assertIn("apply-deletion", skill)
        self.assertIn("restore", skill)
        self.assertFalse((FAMILY_ROOT / "claude").exists())

    def test_skill_requires_live_repo_verification_and_bounded_catalog(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("bounded", skill.casefold())
        self.assertIn("live repository", skill.casefold())
        self.assertIn("critical_unmapped_objectives", skill)
        self.assertIn("explicit live-retirement authorization", skill.casefold())
        self.assertIn("no direct sqlite", skill.casefold())

    def test_wrapper_exists(self):
        self.assertTrue((SKILL_ROOT / "scripts" / "invoke_context_transfer.py").is_file())

    def test_skill_documents_staged_private_runtime(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("active.json", skill)
        self.assertIn("install_context_transfer_runtime.py", skill)
        self.assertIn("no cancellation timeout", skill.casefold())

    def test_runtime_scripts_exist(self):
        scripts = SKILL_ROOT / "scripts"

        self.assertTrue((scripts / "runtime_bootstrap.py").is_file())
        self.assertTrue((scripts / "install_context_transfer_runtime.py").is_file())


if __name__ == "__main__":
    unittest.main()
