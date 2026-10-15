"""Exercise the documented multi-source workflow through the actual CLI.

Set CONTEXT_TRANSFER_TEST_WRAPPER to exercise a deployed wrapper/runtime instead
of the repository wrapper. All conversation state is an isolated fixture.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from test_archive import ArchiveFixture


REPO = Path(__file__).resolve().parents[3]
WRAPPER = Path(os.environ.get(
    "CONTEXT_TRANSFER_TEST_WRAPPER",
    str(REPO / "families/context-transfer/codex/skills/context-transfer/scripts/invoke_context_transfer.py"),
))


@unittest.skipUnless(shutil.which("7z.exe") or shutil.which("7z"), "7-Zip required")
class AggregateWorkflowTests(unittest.TestCase):
    def test_shared_handoff_preserves_two_purposes_child_and_shared_ancestor(self):
        scratch = Path(os.environ.get("CONTEXT_TRANSFER_TEST_TEMP", "D:/Temp"))
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="aggregate-", dir=scratch) as value:
            root = Path(value)
            fixture = ArchiveFixture(root)
            wrapper_env = dict(os.environ)
            wrapper_env.pop("AGENT_TOOLBELT_HOME", None)
            wrapper_env["PYTHONDONTWRITEBYTECODE"] = "1"

            def invoke(*args, succeeds=True):
                process = subprocess.run(
                    [sys.executable, "-B", str(WRAPPER), *map(str, args)],
                    capture_output=True, text=True, encoding="utf-8", env=wrapper_env,
                )
                packet = json.loads(process.stdout)
                self.assertEqual(process.returncode, 0 if succeeds else 1,
                                 process.stdout + process.stderr)
                self.assertEqual(packet["ok"], succeeds)
                return packet

            for tid, parent in (("ancestor", None), ("research", "ancestor"),
                                ("implementation", "ancestor"), ("worker", None),
                                ("unselected", "ancestor"), ("destination", None)):
                meta = {"id": tid}
                if parent:
                    meta.update(forked_from_id=parent, forked_from_ordinal_exclusive=10)
                fixture.add_thread(tid, (json.dumps({"type": "session_meta", "payload": meta})
                                        + "\n").encode(), tid)
            fixture.add_edge("implementation", "worker")
            with closing(sqlite3.connect(fixture.codex_home / "thread_history_1.sqlite")) as conn:
                conn.execute("CREATE TABLE thread_items(thread_id TEXT,item_json TEXT)")
                conn.executemany("INSERT INTO thread_items VALUES (?,?)", [
                    (tid, json.dumps({"text": f"database-only {tid}"}))
                    for tid in ("ancestor", "research", "implementation", "worker", "unselected")
                ])
                conn.commit()
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in fixture.codex_home.glob("*.sqlite")}
            handoff = root / "CONTEXT_TRANSFER.md"
            handoff.write_text("""# Consolidated catalogue activity

## Current Objective
One destination continues catalogue research and implementation.
## Authoritative Specifications And Plans
One catalogue contract with preserved research and implementation criteria.
## Completed Work With Evidence
Research identified catalogue constraints; implementation is still unverified.
## Active Stage And Exact Next Actions
Catalogue integration is ACTIVE; verify the real catalogue path next.
## Unresolved Blockers And Required Deferrals
Integration remains a blocker. A source-bound heartbeat needs authorized retargeting
before source retirement. Unselected still needs ancestor, so ancestor must survive.
## Durable Decisions And User Constraints
research:R1 and implementation:R2 map to catalogue:C1 with both criteria retained.
No thread or schedule mutation is authorized by this fixture handoff.
## Failed Approaches Not To Repeat
Do not confuse research conclusions with verified implementation.
## Repositories Branches And Artifacts
Isolated fixture, no live repository or scheduler changes.
## Child-Agent Contribution Map
worker: researched catalogue integration; evidence belongs to implementation.
## Uncertainties Requiring Verification
Production integration remains unverified; this is migration acceptance only.
## Database Evidence And Recall References
research and implementation inherit ancestor. Archive receipts and schedule
definitions live beside this handoff. Read database-only evidence by exact owner
using read-database; normal recall cannot automatically read retired rows.
""", encoding="utf-8")
            handoff_hash = hashlib.sha256(handoff.read_bytes()).hexdigest()
            manifests, archives, acceptances = {}, {}, {}
            for source in ("research", "implementation", "ancestor"):
                manifest = root / f"{source}-inspection.json"
                packet = invoke("inspect", "--source-thread-id", source,
                                "--destination-thread-id", "destination",
                                "--codex-home", fixture.codex_home,
                                "--archive-root", root / "archives", "--output", manifest)
                inventory = packet["result"]
                self.assertEqual(inventory["destination_history_ancestors"], [])
                activity_path = root / f"{source}-activity.json"
                activity_path.write_text(json.dumps({
                    "schema": "agent_toolbelt_context_transfer.activity_evidence.v1",
                    "evidence_source": "codex_task_api", "source_thread_id": source,
                    "destination_thread_id": "destination",
                    "inspection_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                    "observations": [{"thread_id": item["thread_id"], "host_id": "local",
                                      "status": "notLoaded", "tool": "read_thread",
                                      "observed_at": "2026-10-16T00:00:00Z"}
                                     for item in inventory["threads"]],
                }), encoding="utf-8")
                reconciled = root / f"{source}-reconciled.json"
                invoke("reconcile-activity", "--manifest", manifest,
                       "--activity-evidence", activity_path, "--output", reconciled)
                manifests[source] = reconciled
                invoke("catalog", "--manifest", reconciled, "--max-total-entries", 5)
                invoke("validate-handoff", "--manifest", reconciled, "--handoff", handoff)
                extra = ["--preserve-referenced-history"] if source == "ancestor" else []
                receipt = invoke("pack", "--manifest", reconciled, "--handoff", handoff,
                                 "--archive-root", root / "archives", "--dictionary-mib", 32,
                                 *extra)["result"]
                self.assertTrue(receipt["database_evidence_verified"])
                self.assertFalse(receipt["source_snapshot"]["source_paths_passed_to_seven_zip"])
                archives[source] = receipt["archive_path"]
                for owner in [item["thread_id"] for item in inventory["threads"]]:
                    read = invoke("read-database", "--archive", receipt["archive_path"],
                                  "--thread-id", owner, "--table", "thread_items", "--limit", 1)
                    self.assertEqual(read["result"]["total_matches"], 1)
                    self.assertIn(f"database-only {owner}", json.dumps(read["result"]["matches"]))
                unrelated = invoke("read-database", "--archive", receipt["archive_path"],
                                   "--thread-id", "unselected", "--limit", 1)
                self.assertEqual(unrelated["result"]["total_matches"], 0)
                if source == "ancestor":
                    stored = json.loads((Path(receipt["transaction_root"]) / "manifest.json").read_text())
                    self.assertTrue(stored["preservation_only"])
                    self.assertIn("unselected", json.dumps(stored["history_reference_dependents"]))
                    continue
                acceptance = root / f"{source}-acceptance.json"
                acceptance.write_text(json.dumps({
                    "schema": "agent_toolbelt_context_transfer.destination_acceptance.v1",
                    "source_thread_id": source, "destination_thread_id": "destination",
                    "handoff_ready": True, "handoff_sha256": handoff_hash,
                    "mapped_active_requirements": [f"{source} requirement -> catalogue:C1"],
                    "evidence_sources_inspected": [str(reconciled), receipt["archive_path"]],
                    "repository_state_verified": ["isolated fixture; no live repository"],
                    "unresolved_uncertainties": ["integration and schedule retargeting remain pending"],
                    "critical_unmapped_objectives": [],
                    "first_continuation_action": "Verify catalogue integration; retain sources until schedule reconciliation.",
                }), encoding="utf-8")
                acceptances[source] = acceptance
                validated = invoke("validate-acceptance", "--manifest", reconciled,
                                   "--handoff", handoff, "--acceptance", acceptance)
                self.assertEqual(validated["result"]["handoff_sha256"], handoff_hash)

            # One source's success cannot substitute for the other's identity or children.
            rejected = invoke("validate-acceptance", "--manifest", manifests["implementation"],
                              "--handoff", handoff, "--acceptance", acceptances["research"],
                              succeeds=False)
            self.assertIn("source_thread_id", rejected["error"]["details"]["invalid_fields"])
            handoff.write_text(handoff.read_text().replace("worker: researched", "omitted: researched"))
            invoke("validate-handoff", "--manifest", manifests["research"], "--handoff", handoff)
            rejected = invoke("validate-handoff", "--manifest", manifests["implementation"],
                              "--handoff", handoff, succeeds=False)
            self.assertIn("worker", rejected["error"]["details"]["missing_child_thread_ids"])
            rejected = invoke("validate-acceptance", "--manifest", manifests["research"],
                              "--handoff", handoff, "--acceptance", acceptances["research"],
                              succeeds=False)
            self.assertIn("handoff_sha256", rejected["error"]["details"]["invalid_fields"])
            after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in fixture.codex_home.glob("*.sqlite")}
            self.assertEqual(before, after)
            self.assertEqual(len(archives), 3)  # Shared ancestor preserved once.
            self.assertTrue((fixture.sessions / "rollout-unselected.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
