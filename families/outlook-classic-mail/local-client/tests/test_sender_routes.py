import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from outlook_classic_mail_client import client
from tests.test_client import make_response_session


class PrivateSenderRouteTests(unittest.TestCase):
    def setUp(self):
        self.session = make_response_session()
        self.anchor = self.session.GetItemFromID("anchor-1")
        self.account = client.resolve_account(self.session, "anchor@example.com")
        self.route = {"recipient_domain": "aliases.example", "send_using_account": "reply@example.com",
                      "provider": "simplelogin"}

    def select(self, *, explicit=None):
        return client.resolve_send_using_account(self.session, anchor_account_info=self.account,
            message=self.anchor, send_using_account_selector=explicit)

    def test_private_route_overrides_direct_transport_recipient(self):
        self.anchor.To = "shop@aliases.example; other@example.com"
        with patch.object(client, "load_sender_routes", return_value=[self.route]):
            selected, evidence = self.select()
        self.assertEqual(selected["smtp_address"], "reply@example.com")
        self.assertEqual(evidence["source"], "private_recipient_domain")
        self.assertEqual(evidence["alias_identity"]["addresses"], ["shop@aliases.example"])
        self.assertEqual(evidence["alias_identity"]["provider"], "simplelogin")
        self.assertIs(evidence["alias_identity"]["delivery_verified"], False)

    def test_explicit_sender_wins_without_reading_private_config(self):
        with patch.object(client, "load_sender_routes", side_effect=AssertionError("must not read")):
            selected, evidence = self.select(explicit="other@example.com")
        self.assertEqual(selected["smtp_address"], "other@example.com")
        self.assertEqual(evidence["source"], "explicit")

    def test_domain_matching_is_exact_and_case_insensitive(self):
        with patch.object(client, "load_sender_routes", return_value=[self.route]):
            for address in ("shop@evilaliases.example", "shop@aliases.example.evil", "shop@sub.aliases.example"):
                self.anchor.To = address
                self.assertEqual(self.select()[1]["source"], "anchor_account_fallback")
            self.anchor.To = "Shop@ALIASES.EXAMPLE"
            self.assertEqual(self.select()[0]["smtp_address"], "reply@example.com")

    def test_conflicting_private_routes_fail_before_creating_reply(self):
        self.anchor.To = "one@aliases.example; two@second.example"
        second = {**self.route, "recipient_domain": "second.example", "send_using_account": "other@example.com"}
        with patch.object(client, "load_sender_routes", return_value=[self.route, second]):
            with self.assertRaisesRegex(ValueError, "private sender routes"):
                client.draft_reply(self.session, account_selector="anchor@example.com", message_id="anchor-1",
                    instruction="Reply", body="Body", create_draft=True, confirm=True)
        self.assertIsNone(self.anchor.last_reply)

    def test_missing_configured_transport_does_not_fall_back(self):
        self.anchor.To = "shop@aliases.example"
        with patch.object(client, "load_sender_routes", return_value=[{**self.route, "send_using_account": "missing@example.com"}]):
            with self.assertRaises(ValueError):
                self.select()

    def test_reply_and_forward_use_private_transport_and_keep_native_destination(self):
        self.anchor.To = "shop@aliases.example"
        self.anchor.SenderEmailAddress = "contact_random@simplelogin.co"
        original_get = self.session.GetItemFromID
        drafts = client.resolve_account(self.session, "reply@example.com")["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        def reopen(entry, store=None):
            for item in drafts.Items:
                if item.EntryID == entry:
                    return item
            return original_get(entry, store)
        self.session.GetItemFromID = reopen
        with patch.object(client, "load_sender_routes", return_value=[self.route]):
            reply = client.draft_reply(self.session, account_selector="anchor@example.com", message_id="anchor-1",
                instruction="Reply", body="Body", create_draft=True, confirm=True)
            forward = client.draft_forward(self.session, account_selector="anchor@example.com", message_id="anchor-1",
                to="different@example.net", instruction="Forward", body="Body", create_draft=False, confirm=False)
        self.assertEqual(reply["to"], "contact_random@simplelogin.co")
        self.assertTrue(reply["draft_placement"]["sender_verification"]["verified"])
        self.assertEqual(forward["send_using_account"], "reply@example.com")
        self.assertIn("alias_reverse_route_requires_verification", reply["warnings"])
        self.assertIn("alias_reverse_route_requires_verification", forward["warnings"])

    def test_private_config_schema_loads_without_embedded_values(self):
        with patch.object(client, "sender_routes_path", return_value=Path("private.json")), \
             patch.object(Path, "read_text", return_value=json.dumps({"version": 1, "routes": [self.route]})):
            self.assertEqual(client.load_sender_routes(), [self.route])

    def test_missing_config_is_a_noop(self):
        with patch.object(client, "sender_routes_path", return_value=Path("missing.json")), \
             patch.object(Path, "read_text", side_effect=FileNotFoundError):
            self.assertEqual(client.load_sender_routes(), [])

    def test_invalid_private_config_fails_closed_without_echoing_contents(self):
        invalid = ["private broken json", {"version": 2, "routes": []},
                   {"version": 1, "routes": [{**self.route, "recipient_domain": "*.aliases.example"}]},
                   {"version": 1, "routes": [{**self.route, "send_using_account": "not-an-email"}]}]
        for value in invalid:
            raw = value if isinstance(value, str) else json.dumps(value)
            with patch.object(client, "sender_routes_path", return_value=Path("private.json")), \
                 patch.object(Path, "read_text", return_value=raw):
                with self.assertRaisesRegex(ValueError, "private sender routes") as error:
                    client.load_sender_routes()
                self.assertNotIn("aliases.example", str(error.exception))


if __name__ == "__main__":
    unittest.main()
