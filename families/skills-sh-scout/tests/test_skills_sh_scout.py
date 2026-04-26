import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_SRC = REPO_ROOT / "families" / "skills-sh-scout" / "src"
if str(FAMILY_SRC) not in sys.path:
    sys.path.insert(0, str(FAMILY_SRC))

from agent_toolbelt_skills_sh_scout import cli, scout


class SkillsShScoutTests(unittest.TestCase):
    def test_query_generation_preserves_explicit_queries_first(self):
        queries = scout.build_queries(
            "Create a local WhatsApp automation skill",
            explicit_queries=["whatsapp", "whatsapp local"],
        )

        self.assertEqual(queries[:2], ["whatsapp", "whatsapp local"])
        self.assertIn("create a local whatsapp automation skill", queries)
        self.assertIn("whatsapp automation", queries)

    def test_search_parsing_dedupes_and_marks_capped_queries(self):
        responses = {
            "uv": {
                "count": 100,
                "skills": [
                    {
                        "id": "astral-sh/claude-code-plugins/uv",
                        "skillId": "uv",
                        "name": "uv",
                        "installs": 368,
                        "source": "astral-sh/claude-code-plugins",
                    }
                ],
            },
            "uv run": {
                "count": 1,
                "skills": [
                    {
                        "id": "astral-sh/claude-code-plugins/uv",
                        "skillId": "uv",
                        "name": "uv",
                        "installs": 369,
                        "source": "astral-sh/claude-code-plugins",
                    }
                ],
            },
        }

        result = scout.search_candidates(["uv", "uv run"], http_get_json=lambda url: responses[url.split("q=", 1)[1].split("&", 1)[0].replace("+", " ")])

        self.assertEqual(result.capped_queries, ["uv"])
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate["id"], "astral-sh/claude-code-plugins/uv")
        self.assertEqual(candidate["matched_queries"], ["uv", "uv run"])
        self.assertEqual(candidate["installs"], 369)

    def test_ranking_classifies_direct_partial_and_false_positive(self):
        candidates = [
            {
                "id": "astral-sh/claude-code-plugins/uv",
                "name": "uv",
                "skill_id": "uv",
                "source": "astral-sh/claude-code-plugins",
                "installs": 368,
                "matched_queries": ["uv"],
                "description": "Guide for using uv, the Python package and project manager.",
            },
            {
                "id": "example/repo/github-project-management",
                "name": "github-project-management",
                "skill_id": "github-project-management",
                "source": "example/repo",
                "installs": 9000,
                "matched_queries": ["uv"],
                "description": "Manage GitHub projects.",
            },
            {
                "id": "example/repo/python-helper",
                "name": "python-helper",
                "skill_id": "python-helper",
                "source": "example/repo",
                "installs": 100,
                "matched_queries": ["python runtime"],
                "description": "Python runtime helper.",
            },
        ]

        ranked = scout.rank_candidates(
            "Use uv for Python project dependency management",
            candidates,
            inspected_by_id={
                "astral-sh/claude-code-plugins/uv": {
                    "description": "Guide for using uv, the Python package and project manager.",
                    "body_excerpt": "uv run, uv add, uv sync",
                }
            },
        )

        self.assertEqual(ranked[0]["classification"], "direct")
        self.assertEqual(ranked[0]["id"], "astral-sh/claude-code-plugins/uv")
        classifications = {item["id"]: item["classification"] for item in ranked}
        self.assertEqual(classifications["example/repo/python-helper"], "partial")
        self.assertEqual(classifications["example/repo/github-project-management"], "false_positive")

    def test_github_inspection_extracts_matching_skill_markdown(self):
        def fake_json(url: str):
            if url.endswith("/repos/astral-sh/claude-code-plugins"):
                return {"default_branch": "main"}
            if "/git/trees/main" in url:
                return {
                    "tree": [
                        {"path": "skills/ruff/SKILL.md", "type": "blob"},
                        {"path": "skills/uv/SKILL.md", "type": "blob"},
                    ]
                }
            raise AssertionError(url)

        def fake_text(url: str):
            self.assertIn("/skills/uv/SKILL.md", url)
            return "---\nname: uv\ndescription: Use uv.\n---\n# uv\nUse `uv run` and `uv add`."

        inspected = scout.inspect_candidate_sources(
            [
                {
                    "id": "astral-sh/claude-code-plugins/uv",
                    "name": "uv",
                    "skill_id": "uv",
                    "source": "astral-sh/claude-code-plugins",
                    "installs": 1,
                    "matched_queries": ["uv"],
                }
            ],
            max_inspect=1,
            http_get_json=fake_json,
            http_get_text=fake_text,
        )

        self.assertEqual(inspected[0]["skill_path"], "skills/uv/SKILL.md")
        self.assertEqual(inspected[0]["frontmatter"]["name"], "uv")
        self.assertIn("uv run", inspected[0]["body_excerpt"])

    def test_scout_report_recommends_public_install_for_direct_official_candidate(self):
        def fake_search_json(url: str):
            return {
                "count": 1,
                "skills": [
                    {
                        "id": "astral-sh/claude-code-plugins/uv",
                        "skillId": "uv",
                        "name": "uv",
                        "installs": 368,
                        "source": "astral-sh/claude-code-plugins",
                    }
                ],
            }

        report = scout.build_scout_report(
            workflow="Use uv for Python package management",
            explicit_queries=["uv"],
            max_candidates=10,
            max_inspect=0,
            http_get_json=fake_search_json,
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["recommendation"]["category"], "Install public skill")
        self.assertEqual(report["recommendation"]["candidate_id"], "astral-sh/claude-code-plugins/uv")

    def test_scout_report_returns_structured_failure_on_search_error(self):
        report = scout.build_scout_report(
            workflow="create a skill for something",
            explicit_queries=["something"],
            max_candidates=5,
            max_inspect=0,
            http_get_json=lambda url: (_ for _ in ()).throw(RuntimeError("network unavailable")),
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["candidate_count"], 0)
        self.assertIn("network unavailable", report["errors"][0])
        self.assertEqual(report["recommendation"]["category"], "Create new skill")

    def test_exact_direct_candidate_is_not_crowded_out_by_high_install_partial_hits(self):
        payloads = {
            "uv": {
                "count": 2,
                "skills": [
                    {
                        "id": "wshobson/agents/python-performance-optimization",
                        "skillId": "python-performance-optimization",
                        "name": "python-performance-optimization",
                        "installs": 19715,
                        "source": "wshobson/agents",
                    },
                    {
                        "id": "astral-sh/claude-code-plugins/uv",
                        "skillId": "uv",
                        "name": "uv",
                        "installs": 368,
                        "source": "astral-sh/claude-code-plugins",
                    },
                ],
            }
        }

        report = scout.build_scout_report(
            workflow="Use uv for Python package management",
            explicit_queries=["uv"],
            max_candidates=1,
            max_inspect=0,
            http_get_json=lambda url: payloads.get(url.split("q=", 1)[1].split("&", 1)[0].replace("+", " "), {"count": 0, "skills": []}),
        )

        self.assertEqual(report["candidates"][0]["id"], "astral-sh/claude-code-plugins/uv")
        self.assertEqual(report["recommendation"]["category"], "Install public skill")

    def test_cli_writes_json_output(self):
        original = cli.scout.build_scout_report
        cli.scout.build_scout_report = lambda **kwargs: {
            "ok": True,
            "operation": "scout",
            "workflow": kwargs["workflow"],
            "queries": kwargs["explicit_queries"],
            "capped_queries": [],
            "candidate_count": 0,
            "candidates": [],
            "inspected_candidates": [],
            "recommendation": {"category": "Create new skill", "summary": "No candidates."},
            "warnings": [],
            "errors": [],
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "report.json"
                with io.StringIO() as buffer, redirect_stdout(buffer):
                    exit_code = cli.main(
                        [
                            "scout",
                            "--workflow",
                            "find a skill for desktop search",
                            "--query",
                            "desktop search",
                            "--output",
                            str(output),
                        ]
                    )
                    stdout_payload = json.loads(buffer.getvalue())

                file_payload = json.loads(output.read_text(encoding="utf-8"))
        finally:
            cli.scout.build_scout_report = original

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout_payload, file_payload)
        self.assertEqual(file_payload["workflow"], "find a skill for desktop search")


if __name__ == "__main__":
    unittest.main()
