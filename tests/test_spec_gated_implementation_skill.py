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
        cls.skill_text_lower = " ".join(cls.skill_text.lower().split())

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
        self.assertIn("specifically named later stage", self.skill_text_lower)
        self.assertIn("no empty remediation stage", self.skill_text_lower)
        self.assertIn("tracked_deferrals = 0", self.skill_text)
        self.assertIn("tracked for later", self.skill_text_lower)
        self.assertIn("not completion", self.skill_text_lower)

    def test_only_user_can_remove_required_work(self):
        self.assertIn("only an explicit user decision can revise", self.skill_text_lower)
        self.assertIn("keep the plan incomplete", self.skill_text_lower)
        self.assertIn("without that decision is prohibited", self.skill_text_lower)

    def test_implementable_gaps_block_advancement_not_execution(self):
        self.assertIn("exactly two categories", self.skill_text_lower)
        self.assertIn("blocks stage completion and ordinary advancement", self.skill_text_lower)
        self.assertIn("does not stop implementation", self.skill_text_lower)
        self.assertIn("implementable gaps keep the stage active", self.skill_text_lower)
        self.assertNotIn("ordinary unfinished work or a blocker", self.skill_text_lower)

    def test_genuine_parking_does_not_waive_acceptance_or_dependencies(self):
        self.assertIn("cannot presently be resolved", self.skill_text_lower)
        self.assertIn("standing parking and dependency rules", self.skill_text_lower)
        self.assertIn("parking is not completion", self.skill_text_lower)
        self.assertIn("at most one active stage", self.skill_text_lower)

    def test_deferrals_cannot_excuse_current_stage_acceptance(self):
        self.assertIn("current-stage acceptance criteria do not depend on it", self.skill_text_lower)
        self.assertIn("reason, destination stage, and verification method", self.skill_text_lower)
        self.assertIn("all required tracked deferrals", self.skill_text_lower)

    def test_cohesive_work_is_not_a_patch_size_quota_or_scope_expansion(self):
        self.assertIn("cohesive patches", self.skill_text_lower)
        self.assertIn("narrowest required integrated workflow", self.skill_text_lower)
        self.assertIn("not a line-count quota", self.skill_text_lower)
        self.assertIn("micro-implementations", self.skill_text_lower)
        self.assertIn("speculative micro-optimizations", self.skill_text_lower)
        self.assertIn("meaningful test-first", self.skill_text_lower)

    def test_verification_reuse_requires_current_applicable_evidence(self):
        self.assertIn("relevant code, configuration, environment, dependencies and integration", self.skill_text_lower)
        self.assertIn("unchanged", self.skill_text_lower)
        self.assertIn("rerun affected checks", self.skill_text_lower)
        self.assertIn("missing or invalidated", self.skill_text_lower)
        self.assertIn("required integration and recovery checks", self.skill_text_lower)
        self.assertIn("full suite", self.skill_text_lower)
        self.assertIn("explicit requirement", self.skill_text_lower)

    def test_instruction_authority_and_reload_are_not_implicit(self):
        self.assertIn("standing instructions", self.skill_text_lower)
        self.assertIn("explicitly reread", self.skill_text_lower)
        self.assertIn("not proof", self.skill_text_lower)

    def test_formal_validation_waits_for_complete_features(self):
        self.assertIn("formal validation is feature-complete only", self.skill_text_lower)
        self.assertIn("required behavior, wiring and integration before acceptance validation", self.skill_text_lower)
        self.assertIn("do not validate micro-implementations", self.skill_text_lower)
        self.assertIn("diagnostic feedback is not feature validation", self.skill_text_lower)
        self.assertIn("rename an incomplete component a feature or vertical slice", self.skill_text_lower)
        self.assertIn("not that correctness has already been proven", self.skill_text_lower)
        self.assertIn("do not relabel micro-validation as diagnostics", self.skill_text_lower)
        self.assertIn("complete specified outcomes for non-feature work", self.skill_text_lower)

    def test_validation_gate_does_not_remove_intermediate_commit_authority(self):
        self.assertIn("intermediate commits remain allowed", self.skill_text_lower)
        self.assertIn("do not validate an incomplete feature or close a stage", self.skill_text_lower)

    def consolidation_text(self):
        start = self.skill_text_lower.index("### stage-closure refactoring assessment")
        return self.skill_text_lower[start:self.skill_text_lower.index("## 5.", start)]

    def test_assessment_is_lightweight_not_automatic_refactoring(self):
        text = self.consolidation_text()
        for requirement in ("fully implemented and verified", "final reconciliation",
                            "reuse an unchanged assessment", "not automatic refactoring",
                            "existing reconciliation ledger", "no material finding"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, text)

    def test_consolidation_requires_material_evidence_and_existing_authority(self):
        text = self.consolidation_text()
        for requirement in ("duplicated business logic", "stacked workarounds",
                            "conflicting state ownership", "obsolete implementation paths",
                            "existing specification requirement", "explicitly authorized maintenance",
                            "does not authorize", "optional opportunities are not missing required work"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, text)

    def test_refactoring_preserves_blocker_deferral_and_wip_boundaries(self):
        text = self.consolidation_text()
        for requirement in ("current-stage blockers", "named later stage",
                            "current acceptance does not depend", "one active stage",
                            "do not use consolidation to escape", "before overall completion"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, text)

    def test_consolidation_has_bounded_exit_and_workflow_revalidation(self):
        text = self.consolidation_text()
        for requirement in ("affected components", "preserved behavior", "observable acceptance",
                            "affected complete workflows", "stop when its acceptance criteria pass",
                            "no numerical cadence", "no unrelated full-suite reruns",
                            "do not validate individual cleanup edits"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, text)


if __name__ == "__main__":
    unittest.main()
