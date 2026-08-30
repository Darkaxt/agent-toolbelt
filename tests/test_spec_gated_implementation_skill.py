import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = (
    REPO_ROOT
    / "families"
    / "spec-gated-implementation"
    / "codex"
    / "skills"
    / "spec-gated-implementation"
)
SKILL_PATH = SKILL_ROOT / "SKILL.md"


class SpecGatedImplementationSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill_text = SKILL_PATH.read_text(encoding="utf-8")
        cls.skill_text_lower = cls.skill_text.lower()

    def test_skill_is_instruction_only_and_has_codex_metadata(self):
        self.assertTrue(SKILL_PATH.is_file())
        self.assertTrue((SKILL_ROOT / "agents" / "openai.yaml").is_file())
        self.assertFalse((SKILL_ROOT / "scripts").exists())
        self.assertIn("name: spec-gated-implementation", self.skill_text)

    def test_prior_implementation_authorization_is_reused(self):
        self.assertIn("already_authorized", self.skill_text)
        self.assertIn("authorization may have been given before", self.skill_text_lower)
        self.assertIn("never ask again for the same approved scope", self.skill_text_lower)

    def test_every_stage_reconciles_against_authoritative_specification(self):
        self.assertIn("for every stage", self.skill_text_lower)
        self.assertIn("re-read the authoritative specification", self.skill_text_lower)
        self.assertIn("not only the plan", self.skill_text_lower)
        self.assertIn("update the reconciliation ledger", self.skill_text_lower)

    def test_blockers_are_closed_before_advancing(self):
        self.assertIn("blockers must be fixed before advancing", self.skill_text_lower)
        self.assertIn("resolve all blockers", self.skill_text_lower)
        self.assertIn("rerun verification", self.skill_text_lower)

    def test_tracked_deferrals_cannot_survive_completion(self):
        self.assertIn("deferral changes scheduling only", self.skill_text_lower)
        self.assertIn("mandatory final-remediation stage", self.skill_text_lower)
        self.assertIn("tracked_deferrals = 0", self.skill_text)
        self.assertIn("tracked for later", self.skill_text_lower)
        self.assertIn("not completion", self.skill_text_lower)

    def test_only_user_can_remove_required_work(self):
        self.assertIn("only an explicit user decision can revise", self.skill_text_lower)
        self.assertIn("keep the plan incomplete", self.skill_text_lower)
        self.assertIn("without that decision is prohibited", self.skill_text_lower)


if __name__ == "__main__":
    unittest.main()
