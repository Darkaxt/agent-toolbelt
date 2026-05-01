import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_SRC = REPO_ROOT / "families" / "skill-gardener" / "src"
if str(FAMILY_SRC) not in sys.path:
    sys.path.insert(0, str(FAMILY_SRC))

from agent_toolbelt_skill_gardener import cli, gardener


class SkillGardenerTests(unittest.TestCase):
    def test_structured_plan_text_is_not_a_correction(self):
        with tempfile.TemporaryDirectory() as td:
            rollout = Path(td) / "rollout.jsonl"
            write_jsonl(
                rollout,
                [
                    session_meta("thread-a", r"C:\work\alpha"),
                    user_message(
                        "PLEASE IMPLEMENT THIS PLAN:\n"
                        "# Summary\n"
                        "- Prefer a simple implementation.\n"
                        "- Do not change behavior.\n"
                    ),
                ],
            )

            parsed = gardener.parse_rollout(rollout)

            self.assertEqual(parsed.corrections, [])

    def test_github_shipping_correction_is_rejected_without_exact_skill_target(self):
        skill_index = index_with_skills(
            {
                "implementing-github-advanced-security-for-code-scanning": "Use for GitHub Advanced Security code scanning setup."
            }
        )
        session = gardener.SessionSignals(
            rollout_path=Path("rollout.jsonl"),
            thread_id="thread",
            timestamp="2026-04-20T10:00:00Z",
            workspace="Public",
            corrections=["Do not leave noise in github."],
        )

        findings = gardener.build_findings(
            sessions=[session],
            skill_index=skill_index,
            codex_home=Path("codex"),
            agents_home=Path("agents"),
            scout_runner=no_direct_public_skill,
        )

        self.assertEqual(findings, [])

    def test_skill_creator_correction_is_marked_already_covered_by_scout_skill(self):
        skill_index = index_with_skills(
            {
                "skill-creator": "Create or update skills.",
                "skills-sh-scout": "Query skills.sh before creating or expanding a skill and recommend install reuse or create.",
            }
        )
        session = gardener.SessionSignals(
            rollout_path=Path("rollout.jsonl"),
            thread_id="thread",
            timestamp="2026-04-20T10:00:00Z",
            workspace="Public",
            corrections=[
                'I think we may also want to overhaul the "Skill creation" skill or create another helper skill to query skills.sh before creating new skills.'
            ],
        )

        findings = gardener.build_findings(
            sessions=[session],
            skill_index=skill_index,
            codex_home=Path("codex"),
            agents_home=Path("agents"),
            scout_runner=no_direct_public_skill,
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].action, "already_covered")
        self.assertEqual(findings[0].name, "skills-sh-scout")

    def test_xsoar_standard_python_guardrail_is_already_covered(self):
        skill_index = index_with_skills(
            {
                "xsoar-development": (
                    "Use for Cortex XSOAR. Do not apply generic local Python practices to "
                    "XSOAR automations unless the artifact is explicitly a local helper script."
                )
            }
        )
        session = gardener.SessionSignals(
            rollout_path=Path("rollout.jsonl"),
            thread_id="thread",
            timestamp="2026-04-22T10:00:00Z",
            workspace="XSoar",
            corrections=["I see too many errors related to standard python practices that do not translate to XSoar development practices."],
        )

        findings = gardener.build_findings(
            sessions=[session],
            skill_index=skill_index,
            codex_home=Path("codex"),
            agents_home=Path("agents"),
            scout_runner=no_direct_public_skill,
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].action, "already_covered")
        self.assertEqual(findings[0].name, "xsoar-development")

    def test_explicit_mutable_skill_update_stages_concrete_patch(self):
        skill_index = index_with_skills({"demo-skill": "Use for demo workflows."}, source_kind="agent_created")
        session = gardener.SessionSignals(
            rollout_path=Path("rollout.jsonl"),
            thread_id="thread",
            timestamp="2026-04-22T10:00:00Z",
            workspace="Demo",
            corrections=["Update demo-skill: always run the preview command before applying changes."],
        )

        findings = gardener.build_findings(
            sessions=[session],
            skill_index=skill_index,
            codex_home=Path("codex"),
            agents_home=Path("agents"),
            scout_runner=no_direct_public_skill,
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].action, "propose_patch")
        self.assertIn("preview command", findings[0].proposed_instruction)
        self.assertNotIn("Review the trigger", gardener.render_patch_proposal(findings[0], False))

    def test_repeated_workflow_stages_new_skill_after_public_gate(self):
        sessions = [
            gardener.SessionSignals(
                rollout_path=Path("one.jsonl"),
                thread_id="one",
                timestamp="2026-04-22T10:00:00Z",
                workspace="One",
                command_counts={"customcli deploy": 6},
                corrections=["Always run customcli deploy with --preview first."],
            ),
            gardener.SessionSignals(
                rollout_path=Path("two.jsonl"),
                thread_id="two",
                timestamp="2026-04-23T10:00:00Z",
                workspace="Two",
                command_counts={"customcli deploy": 5},
                summaries=["Resolved setup issue: customcli deploy needs --preview before apply."],
            ),
        ]

        findings = gardener.build_findings(
            sessions=sessions,
            skill_index=index_with_skills({}),
            codex_home=Path("codex"),
            agents_home=Path("agents"),
            scout_runner=no_direct_public_skill,
        )

        proposals = [item for item in findings if item.action == "propose_new_skill"]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].name, "customcli-deploy-workflow")

    def test_repeated_workflow_rejected_when_public_skill_is_direct(self):
        sessions = [
            gardener.SessionSignals(
                rollout_path=Path("one.jsonl"),
                thread_id="one",
                timestamp="2026-04-22T10:00:00Z",
                workspace="One",
                command_counts={"customcli deploy": 6},
                corrections=["Always use customcli deploy for the helper script."],
            ),
            gardener.SessionSignals(
                rollout_path=Path("two.jsonl"),
                thread_id="two",
                timestamp="2026-04-23T10:00:00Z",
                workspace="Two",
                command_counts={"customcli deploy": 5},
                summaries=["Resolved setup issue: customcli deploy works for the helper script."],
            ),
        ]

        findings = gardener.build_findings(
            sessions=sessions,
            skill_index=index_with_skills({}),
            codex_home=Path("codex"),
            agents_home=Path("agents"),
            scout_runner=lambda workflow, queries: {
                "ok": True,
                "recommendation": {"category": "Install public skill", "summary": "Official uv skill covers this."},
            },
        )

        self.assertEqual([item.action for item in findings], ["public_alternative"])

    def test_stage_report_has_no_action_and_rejected_sections(self):
        finding = gardener.Finding(
            kind="already_covered",
            action="already_covered",
            name="demo",
            reason="Already covered.",
            evidence=[gardener.Evidence("thread", "2026-04-22", "Demo", "correction x")],
            proposed_instruction="Do x.",
        )
        with tempfile.TemporaryDirectory() as td:
            run_dir = gardener.stage_report(
                findings=[finding],
                diagnostics={"thread_count": 1, "session_count": 1, "skill_count": 1, "proposal_count": 0, "no_action_count": 1, "rejected_count": 0},
                output_root=Path(td),
                include_titles=False,
            )

            report = (run_dir / "REPORT.md").read_text(encoding="utf-8")

        self.assertIn("## No-action findings", report)
        self.assertIn("## Rejected candidates", report)

    def test_discover_threads_uses_sqlite_and_skips_archived(self):
        with tempfile.TemporaryDirectory() as td:
            codex_home = Path(td) / ".codex"
            sessions = codex_home / "sessions"
            sessions.mkdir(parents=True)
            rollout = sessions / "rollout.jsonl"
            rollout.write_text("", encoding="utf-8")
            con = sqlite3.connect(codex_home / "state_5.sqlite")
            con.execute(
                "create table threads (id text, title text, cwd text, rollout_path text, updated_at integer, archived integer)"
            )
            con.execute("insert into threads values (?, ?, ?, ?, ?, ?)", ("live", "Live", r"C:\work\a", str(rollout), 1776800000, 0))
            con.execute("insert into threads values (?, ?, ?, ?, ?, ?)", ("old", "Old", r"C:\work\b", str(rollout), 1776800000, 1))
            con.commit()
            con.close()

            threads = gardener.discover_threads(
                codex_home=codex_home,
                since_days=30,
                max_sessions=10,
                include_archived=False,
                now_epoch=1776805000,
            )

        self.assertEqual([thread.thread_id for thread in threads], ["live"])

    def test_cli_routes_scan_command(self):
        original = cli.gardener.run_scan
        cli.gardener.run_scan = lambda **kwargs: gardener.ScanResult(
            ok=True,
            console="dry summary",
            run_dir=None,
            findings=[],
            diagnostics={},
        )
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["scan", "--dry-run"])
                output = buffer.getvalue()
        finally:
            cli.gardener.run_scan = original

        self.assertEqual(exit_code, 0)
        self.assertIn("dry summary", output)


def no_direct_public_skill(workflow, queries):
    return {
        "ok": True,
        "recommendation": {"category": "Create new skill", "summary": "No direct public skill found."},
    }


def index_with_skills(items: dict[str, str], source_kind: str = "repo_managed") -> gardener.SkillIndex:
    index = gardener.SkillIndex()
    for name, body in items.items():
        index.add(
            gardener.SkillInfo(
                name=name,
                path=Path(f"C:/skills/{name}/SKILL.md"),
                description=body,
                content=f"---\nname: {name}\ndescription: {body}\n---\n\n{body}",
                source_kind=source_kind,
            )
        )
    return index


def write_jsonl(path: Path, entries: list[dict]):
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def session_meta(thread_id: str, cwd: str):
    return {"timestamp": "2026-04-22T10:00:00Z", "type": "session_meta", "payload": {"id": thread_id, "cwd": cwd}}


def user_message(text: str):
    return {
        "timestamp": "2026-04-22T10:01:00Z",
        "type": "response_item",
        "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
    }


if __name__ == "__main__":
    unittest.main()
