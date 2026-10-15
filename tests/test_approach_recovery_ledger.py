import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "families/approach-recovery-ledger/codex/skills/approach-recovery-ledger"
HELPER = BUNDLE / "scripts/invoke_approach_recovery_ledger.py"
SPEC = importlib.util.spec_from_file_location("approach_ledger", HELPER)
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)
EXAMPLE = json.loads((BUNDLE / "examples/attempt.json").read_text(encoding="utf-8"))


class ApproachRecoveryLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path("D:/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
        scratch.mkdir(parents=True, exist_ok=True)
        cls.root = Path(tempfile.mkdtemp(prefix="approach-ledger-tests-", dir=scratch))
        print(f"\nReviewed-fixture cleanup root: {cls.root}", flush=True)

    def setUp(self):
        self.work = self.root / self._testMethodName
        self.work.mkdir()
        self.db = self.work / "ledger.sqlite3"
        self.entry = copy.deepcopy(EXAMPLE)

    def packet_file(self, entry, name="attempt.json"):
        path = self.work / name
        path.write_text(json.dumps(entry), encoding="utf-8")
        return path

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = ledger.main(["--ledger", str(self.db), *map(str, args)])
        return code, json.loads(output.getvalue())

    def completed(self, identifier="fictional-completed-002"):
        entry = copy.deepcopy(self.entry)
        entry.update(attempt_id=identifier, thread_id="fictional-thread-beta", outcome="completed",
                     interruption=None, interrupted_at=None,
                     satisfied_criteria=entry["plan"]["acceptance_criteria"][:], outstanding_criteria=[])
        entry["execution"]["summary"] = "Fictional verification completed; all original fields matched."
        entry["next_decision"]["action"] = "resolved"
        return entry

    def test_cli_shared_record_search_and_show(self):
        path = self.packet_file(self.entry)
        result = subprocess.run([sys.executable, "-B", str(HELPER), "--ledger", str(self.db),
                                 "record", "--input", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        ledger.record(self.db, self.completed())
        code, found = self.cli("search", "--query", "parser reference")
        self.assertEqual(code, 0)
        self.assertEqual({e["thread_id"] for e in found["attempts"]},
                         {"fictional-thread-alpha", "fictional-thread-beta"})
        _, shown = self.cli("show", "--attempt-id", self.entry["attempt_id"])
        self.assertEqual(shown["attempt"]["execution"]["tool_outcome"], "completed")
        self.assertEqual(shown["attempt"]["outcome"], "interrupted")
        self.assertEqual(shown["attempt"]["outstanding_criteria"], self.entry["outstanding_criteria"])

    def test_immutable_idempotent_entries(self):
        first = ledger.record(self.db, self.entry)
        second = ledger.record(self.db, self.entry)
        self.assertTrue(second["already_recorded"])
        self.assertEqual(first["recorded_at"], second["recorded_at"])
        self.entry["lesson"] = "Changed observation must be appended, not overwritten."
        with self.assertRaises(ledger.LedgerError) as caught:
            ledger.record(self.db, self.entry)
        self.assertEqual(caught.exception.kind, "immutable_conflict")
        self.assertEqual(len(ledger.search(self.db)), 1)

    def test_timestamps_normalize_and_unknown_is_not_fabricated(self):
        self.entry["attempted_at"] = "2026-10-14T13:00:00+03:00"
        self.assertEqual(ledger.validate_entry(self.entry)["attempted_at"], "2026-10-14T10:00:00.000000Z")
        self.entry.update(attempted_at=None, attempt_time_source="unknown")
        ledger.record(self.db, self.entry)
        found = ledger.search(self.db)[0]
        self.assertIsNone(found["attempted_at"])
        self.assertIsNotNone(found["recorded_at"])

    def test_invalid_timestamps_fail_before_database_creation(self):
        for value in ("2026-10-14T10:00:00", "not-a-date", "9999-01-01T00:00:00Z"):
            with self.subTest(value=value):
                self.entry["attempted_at"] = value
                with self.assertRaises(ledger.LedgerError):
                    ledger.record(self.db, self.entry)
        self.assertFalse(self.db.exists())

    def test_missing_actual_plan_or_evidence_rejected(self):
        for field in ("objective", "scope", "method", "steps", "intended_next_action"):
            entry = copy.deepcopy(self.entry)
            del entry["plan"][field]
            with self.subTest(field=field), self.assertRaises(ledger.LedgerError):
                ledger.validate_entry(entry)
        self.entry["execution"]["evidence"] = []
        with self.assertRaises(ledger.LedgerError):
            ledger.validate_entry(self.entry)

    def test_acceptance_partition_and_completion(self):
        for change in ({"outstanding_criteria": []},
                       {"satisfied_criteria": self.entry["plan"]["acceptance_criteria"]},
                       {"outcome": "completed"}):
            with self.subTest(change=change), self.assertRaises(ledger.LedgerError):
                ledger.validate_entry(self.entry | change)

    def test_query_filters_and_literal_wildcards(self):
        self.entry["lesson"] += " Literal marker x_% is evidence."
        self.entry["context"].update(model="fixture-pro", cyber_access_program="daybreak_blue",
                                     program_source="user_report", program_evidence="fictional://explicit-report")
        ledger.record(self.db, self.entry)
        ledger.record(self.db, self.completed())
        found = ledger.search(self.db, query="x_%", model="fixture-pro", program="daybreak_blue",
                              outcome="interrupted", since="2026-10-14T09:00:00Z")
        self.assertEqual(len(found), 1)
        self.assertEqual(ledger.search(self.db, query="x_Z"), [])
        self.assertEqual(ledger.search(self.db, since="2026-10-14T11:00:00Z"), [])
        self.assertEqual(len(ledger.search(self.db, limit=1)), 1)
        for limit in (0, 101):
            with self.assertRaises(ledger.LedgerError):
                ledger.search(self.db, limit=limit)

    def test_known_program_requires_provenance_not_desktop_preference(self):
        self.entry["context"].update(cyber_access_program="daybreak_red", desktop_daybreak_preference=True)
        with self.assertRaises(ledger.LedgerError):
            ledger.validate_entry(self.entry)
        self.entry["context"]["program_source"] = "desktop_preference"
        with self.assertRaises(ledger.LedgerError):
            ledger.validate_entry(self.entry)
        self.entry["context"].update(program_source="codex_turn_context", program_evidence="fictional://turn")
        self.assertEqual(ledger.validate_entry(self.entry)["context"]["cyber_access_program"], "daybreak_red")

    def test_context_normalizer_codex_and_unknown_model_alias(self):
        packet = {"type": "turn_context", "payload": {"model": "fixture-model",
                  "cyber_access_program": "standard", "irrelevant_secret": "not returned"}}
        result = ledger.normalize_context(packet, "codex_turn_context", "fictional://turn")
        self.assertEqual(result["cyber_access_program"], "standard")
        self.assertNotIn("irrelevant_secret", result)
        for packet in ({"model": "daybreak-blue-alias"}, {"cyber_access_program": ["daybreak_blue"]}):
            self.assertEqual(ledger.normalize_context(packet, "codex_turn_context", "ref")["cyber_access_program"], "unknown")

    def test_context_normalizer_api_missing_null_and_error(self):
        for packet, expected in (({"access_programs": {"cyber": "daybreak_blue"}}, "daybreak_blue"),
                                 ({"access_programs": None}, "standard"), ({}, "unknown"),
                                 ({"access_programs": {}}, "unknown"),
                                 ({"access_programs": None, "error": {"code": "cyber_policy"}}, "unknown")):
            with self.subTest(packet=packet):
                self.assertEqual(ledger.normalize_context(packet, "responses_api", "ref")["cyber_access_program"], expected)

    def test_supersession_preserves_original_and_all_criteria(self):
        ledger.record(self.db, self.entry)
        followup = self.completed()
        followup.update(previous_attempt_id=self.entry["attempt_id"], relationship="supersedes")
        ledger.record(self.db, followup)
        _, original = self.cli("show", "--attempt-id", self.entry["attempt_id"])
        self.assertEqual(original["attempt"]["superseded_by"], [followup["attempt_id"]])
        self.assertEqual(original["attempt"]["outcome"], "interrupted")
        bad = copy.deepcopy(followup)
        bad["attempt_id"] = "weakened-003"
        bad["plan"]["acceptance_criteria"] = bad["satisfied_criteria"] = ["generated records read"]
        with self.assertRaises(ledger.LedgerError):
            ledger.record(self.db, bad)
        self.assertEqual(len(ledger.search(self.db)), 2)

    def test_unknown_parent_and_self_link_rejected(self):
        self.entry.update(previous_attempt_id="missing", relationship="continuation")
        with self.assertRaises(ledger.LedgerError) as caught:
            ledger.record(self.db, self.entry)
        self.assertEqual(caught.exception.kind, "unknown_previous_attempt")
        self.entry["previous_attempt_id"] = self.entry["attempt_id"]
        with self.assertRaises(ledger.LedgerError):
            ledger.validate_entry(self.entry)

    def test_concurrent_writer_gets_busy_and_same_entry_can_resume(self):
        ledger.record(self.db, self.entry)
        path = self.packet_file(self.completed())
        with contextlib.closing(sqlite3.connect(self.db)) as other:
            other.execute("BEGIN IMMEDIATE")
            code, result = self.cli("record", "--input", path)
            self.assertEqual(code, 1)
            self.assertEqual(result["failure_kind"], "ledger_busy")
            other.rollback()
        code, result = self.cli("record", "--input", path)
        self.assertEqual(code, 0)
        self.assertFalse(result["already_recorded"])
        self.assertEqual(len(ledger.search(self.db)), 2)

    def test_unrelated_database_preserved(self):
        with contextlib.closing(sqlite3.connect(self.db)) as conn:
            conn.execute("CREATE TABLE unrelated (value TEXT)")
            conn.execute("INSERT INTO unrelated VALUES ('preserve')")
            conn.commit()
        with self.assertRaises(ledger.LedgerError) as caught:
            ledger.record(self.db, self.entry)
        self.assertEqual(caught.exception.kind, "unsupported_ledger")
        with contextlib.closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT value FROM unrelated").fetchone()[0], "preserve")
            self.assertEqual(conn.execute("PRAGMA application_id").fetchone()[0], 0)

    def test_sensitive_or_oversized_packets_rejected(self):
        for value in ("-----BEGIN PRIVATE KEY-----", "sk-" + "x" * 30, "x" * 70000):
            with self.subTest(value=value[:12]), self.assertRaises(ledger.LedgerError):
                ledger.record(self.db, self.entry | {"lesson": value})
        self.assertFalse(self.db.exists())

    def test_malformed_inputs_produce_structured_failure(self):
        for name in ("outcome", "attempt_time_source"):
            code, result = self.cli("record", "--input", self.packet_file(self.entry | {name: []}))
            self.assertEqual(code, 1)
            self.assertEqual(result["failure_kind"], "invalid_entry")
        path = self.work / "bad.json"
        path.write_text("{broken", encoding="utf-8")
        self.assertEqual(self.cli("record", "--input", path)[1]["failure_kind"], "invalid_json")

    def test_read_commands_never_create_missing_ledger(self):
        self.assertEqual(self.cli("status")[1]["count"], 0)
        self.assertEqual(self.cli("search")[1]["attempts"], [])
        self.assertEqual(self.cli("show", "--attempt-id", "missing")[1]["failure_kind"], "attempt_not_found")
        path = self.packet_file({"model": "fixture-model", "cyber_access_program": "daybreak_red"})
        code, result = self.cli("context", "--input", path, "--source", "codex_turn_context")
        self.assertEqual(code, 0)
        self.assertEqual(result["context"]["cyber_access_program"], "daybreak_red")
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
