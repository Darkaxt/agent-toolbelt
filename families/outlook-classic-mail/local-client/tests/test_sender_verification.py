import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from outlook_classic_mail_client import client
from tests.test_client import FakeReply, make_session


class ReferenceOnlyDraft:
    """Model Outlook accepting PROPERTYPUT without assigning an Account reference."""

    def __init__(self):
        self.account = None
        self.attribute_writes = 0
        self._oleobj_ = SimpleNamespace(
            GetIDsOfNames=Mock(return_value=64209), Invoke=Mock(side_effect=self.put_reference)
        )

    @property
    def SendUsingAccount(self):
        return self.account

    @SendUsingAccount.setter
    def SendUsingAccount(self, account):
        self.attribute_writes += 1

    def put_reference(self, member, locale, flags, result_wanted, account):
        if flags != 8:
            raise ValueError("Account requires reference assignment")
        self.account = account


class SenderVerificationTests(unittest.TestCase):
    def setUp(self):
        self.session = make_session()
        self.account = client.resolve_account(self.session, "demo@example.com")
        self.draft = FakeReply(Subject="Draft", To="recipient@example.com")
        self.persisted = FakeReply(Subject="Draft", To="recipient@example.com")
        self.persisted.SendUsingAccount = self.account["account"]
        original_get = self.session.GetItemFromID
        self.session.GetItemFromID = Mock(side_effect=lambda entry, store=None: self.persisted if entry == self.draft.EntryID else original_get(entry, store))

    def test_verification_uses_reopened_item_not_original_object(self):
        self.draft.SendUsingAccount = SimpleNamespace(SmtpAddress="wrong@example.com")
        result = client.verify_saved_draft_sender(self.session, self.draft, self.account)
        self.assertTrue(result["verified"])
        self.assertEqual(result["actual"], "demo@example.com")
        self.assertEqual(result["source"], "saved_item_readback")
        self.session.GetItemFromID.assert_called_once_with(self.draft.EntryID, self.account["store_id"])

    def test_persisted_mismatch_overrules_good_in_memory_account(self):
        self.draft.SendUsingAccount = self.account["account"]
        self.persisted.SendUsingAccount = SimpleNamespace(SmtpAddress="other@example.com")
        result = client.verify_saved_draft_sender(self.session, self.draft, self.account)
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "mismatch")

    def test_reopen_error_has_sanitized_diagnostics_and_no_success(self):
        self.session.GetItemFromID.side_effect = RuntimeError(
            f"Denied for private@example.com at {self.draft.EntryID} in {self.account['store_id']}")
        result = client.verify_saved_draft_sender(self.session, self.draft, self.account)
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "reopen_error")
        self.assertEqual(result["errors"][0]["stage"], "reopen")
        self.assertNotIn("private@example.com", str(result["errors"]))
        self.assertNotIn(self.draft.EntryID, str(result["errors"]))
        self.assertNotIn(self.account["store_id"], str(result["errors"]))

    def test_property_failure_is_distinct_from_unset_account(self):
        class Broken:
            @property
            def SendUsingAccount(self):
                raise RuntimeError("Account getter failed")
        failure = client.inspect_sender_account(Broken(), expected="demo@example.com")
        empty = client.inspect_sender_account(SimpleNamespace(SendUsingAccount=None), expected="demo@example.com")
        self.assertEqual(failure["status"], "read_error")
        self.assertEqual(empty["status"], "unset")
        self.assertEqual(failure["errors"][0]["stage"], "account_read")

    def test_setter_failure_is_retained_separately_from_getter_failure(self):
        self.draft.reject_send_using = True
        details, warnings = {}, []
        client.set_send_using_account(self.draft, self.account, warnings, diagnostics=details)
        self.assertFalse(details["write_succeeded"])
        self.assertEqual(details["errors"][0]["stage"], "account_write")
        self.assertEqual(details["readback"]["status"], "unset")

    def test_wrong_reopened_identity_cannot_verify_sender(self):
        self.session.GetItemFromID.side_effect = None
        self.session.GetItemFromID.return_value = SimpleNamespace(EntryID="different-draft", SendUsingAccount=self.account["account"])
        result = client.verify_saved_draft_sender(self.session, self.draft, self.account)
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "reopen_error")

    def test_unknown_expected_sender_is_observation_not_verification(self):
        result = client.inspect_sender_account(self.persisted)
        self.assertIsNone(result["verified"])
        self.assertEqual(result["status"], "observed")

    def test_assignment_readback_is_not_labeled_persisted_verification(self):
        details = {}
        client.set_send_using_account(self.draft, self.account, [], diagnostics=details)
        self.assertNotIn("verified", details["readback"])
        self.assertEqual(details["readback"]["source"], "assignment_readback")
        self.assertTrue(details["readback"]["matches_requested"])

    def test_com_sender_assignment_uses_property_reference_and_resolved_member(self):
        draft = ReferenceOnlyDraft()
        details, warnings = {}, []
        with patch.dict(sys.modules, {"pythoncom": SimpleNamespace(DISPATCH_PROPERTYPUTREF=8)}):
            actual = client.set_send_using_account(draft, self.account, warnings, diagnostics=details)
        self.assertEqual(actual, "demo@example.com")
        self.assertEqual(draft.attribute_writes, 0)
        draft._oleobj_.GetIDsOfNames.assert_called_once_with("SendUsingAccount")
        draft._oleobj_.Invoke.assert_called_once_with(64209, 0, 8, 0, self.account["account"])
        self.assertEqual(details["method"], "dispatch_property_putref")
        self.assertTrue(details["readback"]["matches_requested"])
        self.assertEqual(warnings, [])

    def test_com_reference_failure_is_reported_without_attribute_fallback(self):
        draft = ReferenceOnlyDraft()
        draft._oleobj_.Invoke.side_effect = RuntimeError("Denied for private@example.com")
        details, warnings = {}, []
        with patch.dict(sys.modules, {"pythoncom": SimpleNamespace(DISPATCH_PROPERTYPUTREF=8)}):
            actual = client.set_send_using_account(draft, self.account, warnings, diagnostics=details)
        self.assertEqual(actual, "")
        self.assertEqual(draft.attribute_writes, 0)
        self.assertFalse(details["write_succeeded"])
        self.assertEqual(details["errors"][0]["stage"], "account_write")
        self.assertNotIn("private@example.com", str(details))
        self.assertIn("send_using_account_unset", warnings)

    def test_com_member_resolution_failure_does_not_guess_dispatch_id(self):
        draft = ReferenceOnlyDraft()
        draft._oleobj_.GetIDsOfNames.side_effect = RuntimeError("Unknown member")
        details = {}
        with patch.dict(sys.modules, {"pythoncom": SimpleNamespace(DISPATCH_PROPERTYPUTREF=8)}):
            client.set_send_using_account(draft, self.account, [], diagnostics=details)
        draft._oleobj_.Invoke.assert_not_called()
        self.assertEqual(draft.attribute_writes, 0)
        self.assertFalse(details["write_succeeded"])

    def test_missing_saved_identity_fails_closed_without_reopening(self):
        result = client.verify_saved_draft_sender(self.session, SimpleNamespace(EntryID=None), self.account)
        self.assertFalse(result["verified"])
        self.assertEqual(result["errors"][0]["stage"], "saved_identity")
        self.session.GetItemFromID.assert_not_called()

    def test_smtp_getter_error_retains_hresult_and_is_not_empty_smtp(self):
        class BrokenSmtp:
            @property
            def SmtpAddress(self):
                error = RuntimeError("SMTP getter failed for private@example.com")
                error.hresult = -2147352567
                raise error
        failure = client.inspect_sender_account(SimpleNamespace(SendUsingAccount=BrokenSmtp()), expected="demo@example.com")
        empty = client.inspect_sender_account(SimpleNamespace(SendUsingAccount=SimpleNamespace(SmtpAddress="")), expected="demo@example.com")
        self.assertEqual(failure["status"], "read_error")
        self.assertEqual(failure["errors"][0]["stage"], "smtp_read")
        self.assertEqual(failure["errors"][0]["hresult"], -2147352567)
        self.assertNotIn("private@example.com", str(failure))
        self.assertEqual(empty["status"], "empty_smtp")

    def test_native_template_error_survives_successful_target_store_fallback(self):
        original = self.session.GetItemFromID("msg-1")
        original.Reply = lambda: FakeReply(Subject="RE: Draft", To="recipient@example.com", reject_send_using=True)
        result = client.draft_reply(self.session, account_selector="demo@example.com", message_id="msg-1",
                                    instruction="guidance", body="Body", create_draft=True, confirm=True)
        sender = result["draft_placement"]["sender_verification"]
        self.assertTrue(sender["verified"])
        self.assertEqual(sender["assignment"]["native_template"]["errors"][0]["stage"], "account_write")

    def test_creation_metadata_requires_persisted_readback(self):
        result = client.draft_reply(self.session, account_selector="demo@example.com", message_id="msg-1",
                                    instruction="guidance", body="Final plain text", create_draft=True, confirm=True)
        sender = result["draft_placement"]["sender_verification"]
        self.assertTrue(sender["verified"])
        self.assertEqual(result["draft_placement"]["actual_send_using_account"], sender["actual"])

    def test_sender_log_excludes_account_values_and_ids(self):
        sender = client.verify_saved_draft_sender(self.session, self.draft, self.account)
        sender.update(verified=False, status="unset", actual=None)
        result = {"ok": True, "result": {"draft_placement": {"sender_verification": sender}}}
        with patch.object(client, "write_diagnostics_event") as log:
            client.record_sender_diagnostics(result, {})
        event = log.call_args.args[0]
        self.assertEqual(event["warning_kind"], "draft_sender_unverified")
        self.assertNotIn("demo@example.com", str(event))
        self.assertNotIn(self.draft.EntryID, str(event))

    def test_post_save_log_failure_does_not_invalidate_saved_result(self):
        result = {"ok": True, "result": {"draft_sender": {"verified": False, "status": "unset"}}}
        with patch.object(client, "write_diagnostics_event", side_effect=OSError("Log unavailable")):
            client.record_sender_diagnostics(result, {})
        self.assertTrue(result["ok"])
        self.assertIn("sender_diagnostic_log_failed", result["warnings"])

    def test_forward_and_standalone_paths_reopen_after_save(self):
        for operation in ("forward", "standalone"):
            session = make_session()
            account = client.resolve_account(session, "demo@example.com")
            original_get = session.GetItemFromID
            draft = FakeReply(Subject="Draft", To="recipient@example.com")
            draft.Parent = account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
            session.GetItemFromID = Mock(side_effect=lambda entry, store=None: draft if entry == draft.EntryID else original_get(entry, store))
            with patch.object(client, "create_mail_item_in_folder", return_value=draft):
                if operation == "forward":
                    anchor = original_get("msg-1")
                    anchor.Forward = lambda: draft
                    result = client.draft_forward(session, account_selector="demo@example.com", message_id="msg-1",
                        to="recipient@example.com", instruction="guidance", body="Body", create_draft=True, confirm=True)
                else:
                    result = client.apply_action(session, account_selector="demo@example.com", message_id=None,
                        action="create-draft", confirm=True, subject="Draft", to="recipient@example.com", body="Body")
            self.assertTrue(draft.saved)
            self.assertTrue(result["draft_placement"]["sender_verification"]["verified"])

    def test_edit_preserves_existing_sender_instead_of_using_store_account(self):
        session = make_session()
        account = client.resolve_account(session, "demo@example.com")
        draft = FakeReply(Subject="Draft", To="recipient@example.com")
        draft.Parent = account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        draft.SendUsingAccount = SimpleNamespace(SmtpAddress="existing@example.com")
        session.GetItemFromID = Mock(return_value=draft)
        result = client.edit_draft(session, account_selector="demo@example.com", message_id=draft.EntryID,
                                   subject="Updated draft", confirm=True)
        self.assertEqual(draft.SendUsingAccount.SmtpAddress, "existing@example.com")
        self.assertTrue(result["draft_sender"]["verified"])
        self.assertEqual(result["draft_sender"]["requested"], "existing@example.com")
        readback = client.read_message(session, account_selector="demo@example.com", message_id=draft.EntryID)
        self.assertEqual(readback["draft_sender"]["actual"], "existing@example.com")
        self.assertIsNone(readback["draft_sender"]["verified"])

    def test_explicit_sender_repair_preserves_existing_draft(self):
        draft = self.draft
        draft.Parent = self.account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        before = (draft.EntryID, draft.Subject, draft.Body, draft.HTMLBody, draft.To,
                  draft.CC, list(draft.Attachments))
        # The saved item is the same original draft, not a recreated template.
        self.session.GetItemFromID = Mock(return_value=draft)
        result = client.edit_draft(self.session, account_selector="demo@example.com",
            message_id=draft.EntryID, send_using_account_selector="demo@example.com", confirm=True)
        self.assertTrue(result["draft_sender"]["verified"])
        self.assertEqual(result["draft_sender"]["source"], "saved_item_readback")
        self.assertTrue(result["draft_sender"]["assignment"]["write_succeeded"])
        self.assertEqual(before, (draft.EntryID, draft.Subject, draft.Body, draft.HTMLBody,
                                 draft.To, draft.CC, list(draft.Attachments)))
        self.assertTrue(draft.saved)

    def test_explicit_sender_repair_uses_requested_account_not_store(self):
        self.draft.Parent = self.account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        self.session.GetItemFromID = Mock(return_value=self.draft)
        other = {**self.account, "smtp_address": "other@example.com",
                 "account": SimpleNamespace(SmtpAddress="other@example.com")}
        resolve = client.resolve_account
        with patch.object(client, "resolve_account", side_effect=lambda session, selector:
                          other if selector == "other@example.com" else resolve(session, selector)):
            result = client.edit_draft(self.session, account_selector="demo@example.com",
                message_id=self.draft.EntryID, send_using_account_selector="other@example.com", confirm=True)
        self.assertEqual(result["draft_sender"]["requested"], "other@example.com")
        self.assertTrue(result["draft_sender"]["verified"])
        self.session.GetItemFromID.assert_called_with(self.draft.EntryID, self.account["store_id"])

    def test_explicit_sender_repair_failure_retains_original_draft(self):
        self.draft.Parent = self.account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        self.draft.reject_send_using = True
        self.session.GetItemFromID = Mock(return_value=self.draft)
        result = client.edit_draft(self.session, account_selector="demo@example.com",
            message_id=self.draft.EntryID, send_using_account_selector="demo@example.com", confirm=True)
        self.assertFalse(result["draft_sender"]["verified"])
        self.assertEqual(result["draft_sender"]["status"], "unset")
        self.assertFalse(result["draft_sender"]["assignment"]["write_succeeded"])
        self.assertIn("send_using_account_unverified", result["draft_edit"]["warnings"])
        self.assertTrue(self.draft.saved)

    def test_explicit_sender_repair_still_requires_confirmation_and_drafts(self):
        self.session.GetItemFromID = Mock(return_value=self.draft)
        for confirm in (False, True):
            with self.assertRaises(ValueError):
                client.edit_draft(self.session, account_selector="demo@example.com",
                    message_id=self.draft.EntryID, send_using_account_selector="demo@example.com", confirm=confirm)
        self.assertFalse(self.draft.saved)

    def test_invalid_requested_sender_fails_before_changing_draft(self):
        self.draft.Parent = self.account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        self.session.GetItemFromID = Mock(return_value=self.draft)
        with self.assertRaises(ValueError):
            client.edit_draft(self.session, account_selector="demo@example.com",
                message_id=self.draft.EntryID, subject="Must not change",
                send_using_account_selector="missing@example.com", confirm=True)
        self.assertEqual(self.draft.Subject, "Draft")
        self.assertFalse(self.draft.saved)

    def test_sender_only_option_is_dispatched_through_client_cli(self):
        self.draft.Parent = self.account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        self.session.GetItemFromID = Mock(return_value=self.draft)
        args = client.build_parser().parse_args(["edit-draft", "--account", "demo@example.com",
            "--message-id", self.draft.EntryID, "--send-using-account", "demo@example.com", "--confirm"])
        result = client.dispatch_operation(args, application=None, session=self.session)
        self.assertTrue(result["result"]["draft_sender"]["verified"])

    def test_good_assignment_cannot_hide_failed_saved_readback_during_repair(self):
        self.draft.Parent = self.account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        self.persisted.SendUsingAccount = None
        self.session.GetItemFromID = Mock(side_effect=[self.draft, self.persisted])
        result = client.edit_draft(self.session, account_selector="demo@example.com",
            message_id=self.draft.EntryID, send_using_account_selector="demo@example.com", confirm=True)
        self.assertTrue(result["draft_sender"]["assignment"]["write_succeeded"])
        self.assertFalse(result["draft_sender"]["verified"])
        self.assertIn("send_using_account_unverified", result["draft_edit"]["warnings"])

    def test_read_command_retains_draft_sender_evidence(self):
        self.draft.Parent = self.account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        self.draft.SendUsingAccount = self.account["account"]
        self.session.GetItemFromID = Mock(return_value=self.draft)
        args = client.build_parser().parse_args(["read-message", "--account", "demo@example.com",
                                                "--message-id", self.draft.EntryID])
        result = client.dispatch_operation(args, application=None, session=self.session)
        self.assertEqual(result["result"]["draft_sender"]["actual"], "demo@example.com")
        self.assertIsNone(result["result"]["draft_sender"]["verified"])


if __name__ == "__main__":
    unittest.main()
