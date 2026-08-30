from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_SRC = REPO_ROOT / "families" / "context-transfer" / "src"
if str(FAMILY_SRC) not in sys.path:
    sys.path.insert(0, str(FAMILY_SRC))

from agent_toolbelt_context_transfer import handoff


TEMP_ROOT = Path(r"D:\Temp")
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rollout_line(text: str, *, role: str = "assistant", timestamp: str = "2026-08-30T10:00:00Z") -> str:
    return json.dumps(
        {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{"type": "output_text", "text": text}],
            },
        }
    )


class HandoffFixture:
    def __init__(self, root: Path):
        self.root = root
        self.rollout = root / "rollout.jsonl"
        lines = [
            rollout_line("Initial objective: modernize Apollo."),
            rollout_line("User constraint: preserve active repository state.", role="user"),
        ]
        lines.extend(rollout_line(f"ordinary middle secret {index}") for index in range(20))
        lines.append("{malformed")
        lines.append(rollout_line("Decision: use a staged recovery archive."))
        lines.append(rollout_line("Tests passed and commit abcdef1 was pushed."))
        lines.append(rollout_line("Current blocker: deployment verification is missing."))
        lines.append(rollout_line("Exact next action: inspect the deployment.", role="user"))
        self.rollout.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        stat_result = self.rollout.stat()
        self.inventory = {
            "schema": "agent_toolbelt_context_transfer.inventory.v1",
            "source_thread_id": "root",
            "destination_thread_id": "destination",
            "thread_count": 2,
            "edge_count": 1,
            "total_rollout_bytes": stat_result.st_size,
            "retirement_ready": True,
            "blockers": [],
            "threads": [
                {
                    "thread_id": "root",
                    "depth": 0,
                    "rollout_path": str(self.rollout),
                    "file_state": "readable",
                    "size": stat_result.st_size,
                    "mtime_ns": stat_result.st_mtime_ns,
                    "sha256": digest(self.rollout),
                    "metadata": {"title": "Apollo", "cwd": "D:/repo"},
                },
                {
                    "thread_id": "child",
                    "depth": 1,
                    "rollout_path": str(self.rollout),
                    "file_state": "readable",
                    "size": stat_result.st_size,
                    "mtime_ns": stat_result.st_mtime_ns,
                    "sha256": digest(self.rollout),
                    "metadata": {"title": "worker", "cwd": "D:/repo"},
                },
            ],
            "edges": [
                {
                    "parent_thread_id": "root",
                    "child_thread_id": "child",
                    "status": "closed",
                }
            ],
        }
        self.manifest = root / "inspection.json"
        self.manifest.write_text(json.dumps(self.inventory), encoding="utf-8")

    def valid_handoff(self) -> str:
        return """# Context Transfer

## Current Objective
Continue the Apollo modernization with verified recovery.

## Authoritative Specifications And Plans
Use docs/spec.md and docs/plan.md.

## Completed Work With Evidence
Commit abcdef1 passed focused tests.

## Active Stage And Exact Next Actions
Inspect the deployment, then resume Stage 4.

## Unresolved Blockers And Required Deferrals
Deployment verification is the only blocker. No deferrals.

## Durable Decisions And User Constraints
Preserve active repository and task state.

## Failed Approaches Not To Repeat
Do not trust stale summaries without repository verification.

## Repositories Branches And Artifacts
Repository D:/repo, branch main, commit abcdef1.

## Child-Agent Contribution Map
child: investigated deployment verification.

## Uncertainties Requiring Verification
Confirm the live deployment before changing code.
"""


class EvidenceCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.fixture = HandoffFixture(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_catalog_is_bounded_and_keeps_offsets_without_raw_duplication(self):
        before = digest(self.fixture.rollout)

        catalog = handoff.build_evidence_catalog(
            inspection_manifest_path=self.fixture.manifest,
            max_entries_per_thread=6,
            max_total_entries=8,
            excerpt_chars=80,
        )

        self.assertEqual(digest(self.fixture.rollout), before)
        self.assertLessEqual(catalog["entry_count"], 8)
        self.assertGreater(catalog["malformed_line_count"], 0)
        self.assertTrue(catalog["truncated"])
        self.assertTrue(all(len(item["excerpt"]) <= 80 for item in catalog["entries"]))
        self.assertTrue(all(item["byte_end"] > item["byte_start"] for item in catalog["entries"]))
        encoded = json.dumps(catalog)
        self.assertNotIn("ordinary middle secret 10", encoded)
        self.assertNotIn("raw_text", encoded)
        self.assertNotIn("search_text", encoded)
        self.assertEqual(catalog["storage"], "bounded_excerpts_and_source_offsets")

    def test_catalog_rejects_non_ready_inspection(self):
        payload = json.loads(self.fixture.manifest.read_text(encoding="utf-8"))
        payload["retirement_ready"] = False
        payload["blockers"] = ["non_terminal_children"]
        self.fixture.manifest.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(handoff.HandoffError) as raised:
            handoff.build_evidence_catalog(inspection_manifest_path=self.fixture.manifest)

        self.assertEqual(raised.exception.kind, "inspection_not_ready")

    def test_catalog_bounds_milestone_candidates_while_streaming(self):
        observed_max_lengths: list[int | None] = []
        original_deque = handoff.deque

        def tracking_deque(*args, **kwargs):
            observed_max_lengths.append(kwargs.get("maxlen"))
            return original_deque(*args, **kwargs)

        with mock.patch.object(handoff, "deque", side_effect=tracking_deque):
            handoff.build_evidence_catalog(
                inspection_manifest_path=self.fixture.manifest,
                max_entries_per_thread=5,
                max_total_entries=10,
                excerpt_chars=80,
            )

        self.assertIn(5, observed_max_lengths)
        self.assertIn(3, observed_max_lengths)


class HandoffValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.fixture = HandoffFixture(self.root)
        self.handoff_path = self.root / "CONTEXT_TRANSFER.md"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_handoff_requires_every_required_section_and_child(self):
        self.handoff_path.write_text(self.fixture.valid_handoff(), encoding="utf-8")

        result = handoff.validate_handoff(
            handoff_path=self.handoff_path,
            inspection_manifest_path=self.fixture.manifest,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_sections"], [])
        self.assertEqual(result["missing_child_thread_ids"], [])
        self.assertEqual(result["handoff_sha256"], digest(self.handoff_path))

    def test_missing_section_fails(self):
        content = self.fixture.valid_handoff().replace(
            "## Current Objective\nContinue the Apollo modernization with verified recovery.\n\n",
            "",
        )
        self.handoff_path.write_text(content, encoding="utf-8")

        with self.assertRaises(handoff.HandoffError) as raised:
            handoff.validate_handoff(
                handoff_path=self.handoff_path,
                inspection_manifest_path=self.fixture.manifest,
            )

        self.assertEqual(raised.exception.kind, "handoff_incomplete")
        self.assertIn("Current Objective", raised.exception.details["missing_sections"])

    def test_missing_child_contribution_fails(self):
        content = self.fixture.valid_handoff().replace(
            "child: investigated deployment verification.",
            "No child contributions recorded.",
        )
        self.handoff_path.write_text(content, encoding="utf-8")

        with self.assertRaises(handoff.HandoffError) as raised:
            handoff.validate_handoff(
                handoff_path=self.handoff_path,
                inspection_manifest_path=self.fixture.manifest,
            )

        self.assertEqual(raised.exception.kind, "handoff_incomplete")
        self.assertEqual(raised.exception.details["missing_child_thread_ids"], ["child"])

    def test_destination_acceptance_validates_handoff_and_continuation_evidence(self):
        self.handoff_path.write_text(self.fixture.valid_handoff(), encoding="utf-8")
        acceptance_path = self.root / "destination-acceptance.json"
        acceptance_path.write_text(
            json.dumps(
                {
                    "schema": "agent_toolbelt_context_transfer.destination_acceptance.v1",
                    "source_thread_id": "root",
                    "destination_thread_id": "destination",
                    "handoff_ready": True,
                    "mapped_active_requirements": ["deployment verification"],
                    "evidence_sources_inspected": ["source rollout offsets", "live repository"],
                    "repository_state_verified": [
                        {"path": "D:/repo", "branch": "main", "commit": "abcdef1"}
                    ],
                    "unresolved_uncertainties": ["live deployment state"],
                    "critical_unmapped_objectives": [],
                    "first_continuation_action": "Inspect the live deployment.",
                    "handoff_sha256": digest(self.handoff_path),
                }
            ),
            encoding="utf-8",
        )

        result = handoff.validate_destination_acceptance(
            acceptance_path=acceptance_path,
            handoff_path=self.handoff_path,
            inspection_manifest_path=self.fixture.manifest,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["handoff_ready"])
        self.assertEqual(result["critical_unmapped_objectives"], [])

    def test_acceptance_rejects_empty_requirements_and_unmapped_objectives(self):
        self.handoff_path.write_text(self.fixture.valid_handoff(), encoding="utf-8")
        acceptance_path = self.root / "destination-acceptance.json"
        acceptance_path.write_text(
            json.dumps(
                {
                    "schema": "agent_toolbelt_context_transfer.destination_acceptance.v1",
                    "source_thread_id": "root",
                    "destination_thread_id": "destination",
                    "handoff_ready": True,
                    "mapped_active_requirements": [],
                    "evidence_sources_inspected": [],
                    "repository_state_verified": [],
                    "unresolved_uncertainties": [],
                    "critical_unmapped_objectives": ["release verification"],
                    "first_continuation_action": "",
                    "handoff_sha256": digest(self.handoff_path),
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(handoff.HandoffError) as raised:
            handoff.validate_destination_acceptance(
                acceptance_path=acceptance_path,
                handoff_path=self.handoff_path,
                inspection_manifest_path=self.fixture.manifest,
            )

        self.assertEqual(raised.exception.kind, "acceptance_incomplete")
        self.assertIn("mapped_active_requirements", raised.exception.details["invalid_fields"])


if __name__ == "__main__":
    unittest.main()
