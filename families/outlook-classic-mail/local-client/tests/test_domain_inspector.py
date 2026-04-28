import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from outlook_classic_mail_client import domain_inspector


class FakePropertyAccessor:
    def __init__(self, headers: str):
        self.headers = headers

    def GetProperty(self, _name: str) -> str:
        return self.headers


class FakeMessage:
    EntryID = "message-1"
    Subject = "Security alert"
    SenderName = "Example Sender"
    SenderEmailAddress = "alerts@mail.example.co.uk"
    To = "user@example.com"
    ReceivedTime = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    UnRead = True
    Body = "Visit https://login.security-check.invalid/path or example.org now."
    HTMLBody = (
        '<a href="https://click.mailchimp.com/track?u=https%3A%2F%2Fbrand-launch.biz%2Fwelcome">'
        "Track</a><img src=\"cid:logo.png\"> visible-brand.co.uk"
    )
    ConversationID = "conversation-1"
    ConversationTopic = "Security alert"

    def __init__(self):
        self.PropertyAccessor = FakePropertyAccessor(
            "\r\n".join(
                [
                    "Reply-To: support@reply.newbrand.biz",
                    "Return-Path: <bounce@mailer.sender.test>",
                    "Received: from mail.sender.test ([203.0.113.8]) by mx.google.com;",
                    "Received-SPF: pass (google.com: domain of sender.test designates 198.51.100.9 as permitted sender) client-ip=198.51.100.9;",
                    "Authentication-Results: mx.google.com; dkim=pass header.d=campaign.example.net",
                    "List-Unsubscribe: <https://unsubscribe.mail.example.co.uk/u/123>",
                ]
            )
        )


class DomainInspectorTests(unittest.TestCase):
    def test_registrable_domain_handles_common_suffixes(self):
        self.assertEqual(domain_inspector.registrable_domain("a.b.example.com"), "example.com")
        self.assertEqual(domain_inspector.registrable_domain("x.y.acaere.co.uk"), "acaere.co.uk")
        self.assertEqual(domain_inspector.registrable_domain("sfbd.newsadvisor.de"), "newsadvisor.de")

    def test_extract_domain_references_finds_headers_and_body_links(self):
        refs = domain_inspector.extract_domain_references(FakeMessage())
        by_domain = {(ref.registrable_domain, ref.source) for ref in refs}

        self.assertIn(("example.co.uk", "sender"), by_domain)
        self.assertIn(("newbrand.biz", "reply-to"), by_domain)
        self.assertIn(("sender.test", "return-path"), by_domain)
        self.assertIn(("example.net", "authentication-results"), by_domain)
        self.assertIn(("example.co.uk", "list-unsubscribe"), by_domain)
        self.assertIn(("security-check.invalid", "body-url"), by_domain)
        self.assertIn(("mailchimp.com", "html-url"), by_domain)
        self.assertIn(("brand-launch.biz", "html-url-embedded"), by_domain)
        self.assertIn(("visible-brand.co.uk", "html-domain"), by_domain)

    def test_extract_ip_references_finds_header_ips(self):
        refs = domain_inspector.extract_ip_references(FakeMessage())
        by_ip = {(ref["ip"], ref["source"]) for ref in refs}

        self.assertIn(("203.0.113.8", "received"), by_ip)
        self.assertIn(("198.51.100.9", "received-spf"), by_ip)

    def test_bare_domain_extraction_ignores_file_like_tokens(self):
        refs = domain_inspector.domains_from_bare_text(
            "https://tracker.example.com/assets/asdsdasdadasasd.html logo.png icon.svg "
            "real-domain.example.org",
            "body-domain",
        )

        self.assertEqual(
            [(ref.registrable_domain, ref.raw_value) for ref in refs],
            [("example.org", "real-domain.example.org")],
        )

    def test_domain_age_marks_recent_domains_young(self):
        age = domain_inspector.domain_age_summary(
            "fresh.biz",
            {
                "registration_date": "2026-01-01T00:00:00Z",
                "expiration_date": "2027-01-01T00:00:00Z",
            },
            now=datetime(2026, 4, 21, tzinfo=timezone.utc),
            young_days=365,
        )

        self.assertEqual(age["age_days"], 110)
        self.assertTrue(age["is_young"])

    def test_rdap_cache_does_not_keep_transient_rate_limits(self):
        transient = {"domain": "example.com", "error": "HTTP Error 429: Too Many Requests"}
        terminal = {"domain": "example.com", "error": "HTTP Error 404: Not Found"}

        self.assertFalse(domain_inspector.should_cache_rdap_payload(transient))
        self.assertTrue(domain_inspector.should_cache_rdap_payload(terminal))

    def test_rdap_provider_urls_prefer_tld_authorities(self):
        self.assertIn("rdap.verisign.com/com", domain_inspector.rdap_urls_for_domain("example.com")[0])
        self.assertIn("rdap.nominet.uk", domain_inspector.rdap_urls_for_domain("acaere.co.uk")[0])

    def test_inspect_item_domains_adds_blocklist_hits_next_to_rdap_age(self):
        class FakeBlocklistCache:
            def refresh(self, *, profile, force=False):
                return {"profile": profile, "refreshed": 0}

            def lookup(self, domain, *, profile):
                if domain == "brand-launch.biz":
                    return [
                        {
                            "source": "unit-threat",
                            "category": "phishing",
                            "matched_domain": "brand-launch.biz",
                            "profile": profile,
                            "fetched_at": "2026-04-22T00:00:00+00:00",
                        }
                    ]
                return []

        result = domain_inspector.inspect_item_domains(
            FakeMessage(),
            with_rdap=False,
            with_blocklists=True,
            blocklist_profile="threat",
            blocklist_cache=FakeBlocklistCache(),
        )
        ages_by_domain = {item["domain"]: item for item in result["domain_ages"]}

        self.assertEqual(
            ages_by_domain["brand-launch.biz"]["blocklist_hits"][0]["category"],
            "phishing",
        )

    def test_domain_structure_flags_generated_subdomain_and_sender_localpart(self):
        refs = [
            domain_inspector.DomainReference(
                raw_value="jiuuzciubwdtyqpylwhzs@niybtzpr.rzge.mustbuilders.biz",
                domain="niybtzpr.rzge.mustbuilders.biz",
                registrable_domain="mustbuilders.biz",
                source="sender",
            )
        ]

        structures = domain_inspector.domain_structure_summaries(refs)

        self.assertEqual(len(structures), 1)
        self.assertEqual(structures[0]["domain"], "niybtzpr.rzge.mustbuilders.biz")
        self.assertEqual(structures[0]["registrable_domain"], "mustbuilders.biz")
        self.assertEqual(structures[0]["subdomain_labels"], ["niybtzpr", "rzge"])
        self.assertIn("random_like_label", structures[0]["evidence_tags"])
        self.assertIn("random_like_sender_localpart", structures[0]["evidence_tags"])
        self.assertIn("risky_tld", structures[0]["evidence_tags"])

    def test_domain_structure_does_not_flag_normal_common_domain(self):
        refs = [
            domain_inspector.DomainReference(
                raw_value="alerts@mail.example.co.uk",
                domain="mail.example.co.uk",
                registrable_domain="example.co.uk",
                source="sender",
            )
        ]

        structures = domain_inspector.domain_structure_summaries(refs)

        self.assertEqual(structures[0]["subdomain_labels"], ["mail"])
        self.assertEqual(structures[0]["evidence_tags"], [])

    def test_inspect_item_domains_includes_domain_structure(self):
        result = domain_inspector.inspect_item_domains(FakeMessage(), with_rdap=False)

        self.assertIn("domain_structure", result)
        self.assertTrue(any(item["registrable_domain"] == "example.co.uk" for item in result["domain_structure"]))


if __name__ == "__main__":
    unittest.main()
