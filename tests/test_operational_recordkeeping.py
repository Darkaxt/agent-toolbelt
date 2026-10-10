import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1] / "families/operational-recordkeeping/codex/skills/operational-recordkeeping"
spec = importlib.util.spec_from_file_location("recordkeeping", SKILL / "scripts/invoke_operational_recordkeeping.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def workbook(duplicate=False, formula=False):
    output = io.BytesIO()
    row = '<row r="2"><c r="A2" t="inlineStr"><is><t>A123</t></is></c><c r="B2" t="inlineStr"><is><t>paid</t></is></c><c r="C2"><v>95</v></c></row>'
    if formula:
        row = row.replace('<v>95</v>', '<f>1+94</f><v>95</v>')
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Payments" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Invoice</t></is></c><c r="B1" t="inlineStr"><is><t>Status</t></is></c><c r="C1" t="inlineStr"><is><t>Amount</t></is></c></row>' + row + (row.replace('r="2"', 'r="3"').replace('A2', 'A3').replace('B2', 'B3').replace('C2', 'C3') if duplicate else '') + '</sheetData></worksheet>')
    return output.getvalue()


class RecordkeepingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = {"profile_id": "company", "records": {
            "ledger": {"path": "ledger.json", "format": "json"},
            "tracker": {"path": "tracker.md", "format": "text"}},
            "routes": {"payment.confirmed": {"records": ["ledger", "tracker"]}}}
        self.event = {"event_id": "A123-paid", "kind": "payment.confirmed", "summary": "Confirmed payment",
                      "facts": {"record_key": "A123", "state": "paid"},
                      "evidence": [{"path": "evidence.json", "checks": [
                          {"fact": "record_key", "at": ["invoice"]}, {"fact": "state", "at": ["status"]}]}],
                      "checks": {"ledger": [{"fact": "record_key", "at": ["invoice"]}, {"fact": "state", "at": ["status"]}],
                                 "tracker": [{"fact": "record_key", "section": "## A123"}, {"fact": "state", "section": "## A123"}]}}
        self.put("profile.json", self.profile)
        self.put("event.json", self.event)
        self.put("ledger.json", {"invoice": "A123", "status": "unsettled"})
        self.put("evidence.json", {"invoice": "A123", "status": "paid"})
        self.put("tracker.md", "## A123\nA123 unsettled\n## History\nA123 paid\n")

    def put(self, name, value):
        (self.root / name).write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")

    def packet(self):
        return helper.prepare(self.root / "profile.json", self.root / "event.json")

    def test_missed_updates_fail_even_when_history_contains_paid(self):
        result = helper.check_packet(self.packet())
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "needs_update")
        self.assertTrue(all(not r["ok"] for r in result["records"]))

    def test_update_all_and_repeat_without_rewriting(self):
        packet = self.packet()
        self.put("ledger.json", {"invoice": "A123", "status": "paid"})
        self.put("tracker.md", "## A123\nA123 paid\n")
        result = helper.check_packet(packet)
        self.assertTrue(result["ok"])
        self.assertTrue(all(r["change"] == "changed" for r in result["records"]))
        second = helper.check_packet(self.packet())
        self.assertTrue(second["ok"])
        self.assertTrue(all(r["change"] == "already_consistent" for r in second["records"]))

    def test_partial_update_stays_unreconciled(self):
        packet = self.packet()
        self.put("ledger.json", {"invoice": "A123", "status": "paid"})
        self.assertFalse(helper.check_packet(packet)["ok"])

    def test_required_record_cannot_be_omitted(self):
        del self.event["checks"]["tracker"]
        self.put("event.json", self.event)
        with self.assertRaisesRegex(ValueError, "cover exactly"):
            self.packet()

    def test_required_positive_facts_cannot_be_omitted(self):
        self.event["checks"]["tracker"] = [self.event["checks"]["tracker"][0]]
        self.put("event.json", self.event)
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.packet()

    def test_missing_binding_blocks_instead_of_skipping(self):
        self.profile["records"]["tracker"]["path"] = None
        self.put("profile.json", self.profile)
        with self.assertRaisesRegex(ValueError, "Unbound"):
            self.packet()

    def test_evidence_must_support_facts(self):
        self.put("evidence.json", {"invoice": "A123", "status": "drafted"})
        with self.assertRaisesRegex(ValueError, "does not support"):
            self.packet()

    def test_evidence_change_or_loss_requires_repair(self):
        packet = self.packet()
        self.put("evidence.json", {"invoice": "A123", "status": "paid", "new": True})
        with self.assertRaisesRegex(ValueError, "Evidence changed"):
            helper.check_packet(packet)

        (self.root / "evidence.json").unlink()
        with self.assertRaises(FileNotFoundError):
            helper.check_packet(packet)

    def test_original_binary_receipt_is_retained_and_change_detected(self):
        (self.root / "receipt.pdf").write_bytes(b"%PDF-fictional-source")
        self.event["evidence"].append({"path": "receipt.pdf", "source_only": True})
        self.put("event.json", self.event)
        packet = self.packet()
        self.assertEqual(len(packet["evidence"]), 2)
        (self.root / "receipt.pdf").write_bytes(b"%PDF-changed")
        with self.assertRaisesRegex(ValueError, "Evidence changed"):
            helper.check_packet(packet)

    def test_binary_source_alone_cannot_prove_payment(self):
        (self.root / "receipt.pdf").write_bytes(b"%PDF-fictional-source")
        self.event["evidence"] = [{"path": "receipt.pdf", "source_only": True}]
        self.put("event.json", self.event)
        with self.assertRaisesRegex(ValueError, "nonempty list"):
            self.packet()

    def test_extra_record_is_required(self):
        self.event["extra_records"] = ["working_note"]
        self.put("event.json", self.event)
        with self.assertRaises(ValueError):
            self.packet()

    def test_structured_values_are_typed(self):
        self.assertFalse(helper.equal(True, 1))
        self.assertFalse(helper.equal("95", 95))
        self.assertTrue(helper.equal(95.0, 95))

    def test_existing_json_narrative_fields_need_no_schema_rewrite(self):
        checks = [{"fact": "state", "at": ["disposition"], "mode": "contains"}]
        self.assertTrue(helper.evaluate(b'{"disposition":"A123 paid; receipt retained"}', "json", checks,
                                       {"state": "paid"})[0]["ok"])
        self.assertFalse(helper.evaluate(b'{"disposition":"A123 unpaid; pending"}', "json", checks,
                                        {"state": "paid"})[0]["ok"])

    def test_paid_does_not_match_unpaid_or_wrong_amount(self):
        self.assertFalse(helper.evaluate(b"## Current\nunpaid", "text",
                         [{"fact": "state", "section": "## Current"}], {"state": "paid"})[0]["ok"])
        self.assertFalse(helper.evaluate(b"## Current\n195.50", "text",
                         [{"fact": "amount", "section": "## Current"}], {"amount": 95})[0]["ok"])

    def test_final_recheck_detects_concurrent_changes(self):
        packet = self.packet()
        original = helper.snapshot
        calls = {}

        def changed(path):
            calls[path] = calls.get(path, 0) + 1
            data, digest = original(path)
            return (data, "different") if calls[path] > 1 else (data, digest)

        with patch.object(helper, "snapshot", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "during reconciliation"):
                helper.check_packet(packet)

    def test_packet_missing_record_and_missing_proofs_rejected(self):
        packet = self.packet()
        packet["records"].pop()
        with self.assertRaisesRegex(ValueError, "coverage changed"):
            helper.check_packet(packet)
        packet = self.packet()
        packet["records"][0]["checks"].pop()
        with self.assertRaisesRegex(ValueError, "coverage"):
            helper.check_packet(packet)

    def test_absent_stale_statement_and_duplicate_section(self):
        facts = {"old": "unpaid"}
        proof = [{"fact": "old", "section": "## Current", "mode": "absent"}]
        self.assertTrue(helper.evaluate(b"## Current\npaid\n## History\nunpaid", "text", proof, facts)[0]["ok"])
        with self.assertRaises(ValueError):
            helper.evaluate(b"## Current\npaid\n## Current\npaid", "text", proof, facts)

    def test_xlsx_keyed_proofs_reject_duplicates_and_formulas(self):
        facts = {"record_key": "A123", "state": "paid", "amount": 95}
        checks = [{"fact": fact, "sheet": "Payments", "key_column": "Invoice", "key_fact": "record_key", "column": column}
                  for fact, column in [("record_key", "Invoice"), ("state", "Status"), ("amount", "Amount")]]
        self.assertTrue(all(p["ok"] for p in helper.evaluate(workbook(), "xlsx", checks, facts)))
        with self.assertRaisesRegex(ValueError, "found 2"):
            helper.evaluate(workbook(duplicate=True), "xlsx", checks, facts)
        with self.assertRaisesRegex(ValueError, "Formula"):
            helper.evaluate(workbook(formula=True), "xlsx", checks, facts)

    def test_check_does_not_modify_any_input(self):
        packet = self.packet()
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        helper.check_packet(packet)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_cli_json_and_no_clobber(self):
        with redirect_stdout(io.StringIO()) as output:
            code = helper.main(["prepare", "--profile", str(self.root / "profile.json"),
                                "--event", str(self.root / "event.json"), "--output", str(self.root / "packet.json")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "prepared_not_reconciled")
        with redirect_stdout(io.StringIO()):
            code = helper.main(["check", "--packet", str(self.root / "packet.json"), "--output", str(self.root / "ledger.json")])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads((self.root / "ledger.json").read_text())["status"], "unsettled")

    def test_unknown_event_fails(self):
        self.event["kind"] = "send.everything"
        self.put("event.json", self.event)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(helper.main(["prepare", "--profile", str(self.root / "profile.json"),
                                         "--event", str(self.root / "event.json"), "--output", str(self.root / "out.json")]), 2)

    def test_non_object_and_malformed_json_rejected_without_traceback(self):
        self.put("event.json", [])
        with redirect_stdout(io.StringIO()) as output:
            code = helper.main(["prepare", "--profile", str(self.root / "profile.json"),
                                "--event", str(self.root / "event.json"), "--output", str(self.root / "out.json")])
        self.assertEqual(code, 2)
        self.assertIn("roots must be objects", json.loads(output.getvalue())["error"])
        self.put("event.json", "broken json")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(helper.main(["prepare", "--profile", str(self.root / "profile.json"),
                                         "--event", str(self.root / "event.json"), "--output", str(self.root / "out.json")]), 2)


if __name__ == "__main__":
    unittest.main()
