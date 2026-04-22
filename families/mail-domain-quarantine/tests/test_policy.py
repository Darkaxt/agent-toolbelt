import sys
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mail_domain_quarantine import policy


class PolicyTests(unittest.TestCase):
    def test_quarantines_when_any_untrusted_domain_is_young(self):
        decision = policy.decide_quarantine(
            domain_ages=[
                {"domain": "mailchimp.com", "is_young": False},
                {"domain": "new-campaign.biz", "is_young": True},
            ],
            trusted_domains={"trusted.example"},
        )

        self.assertEqual(decision.action, "quarantine")
        self.assertEqual(decision.young_domains, ["new-campaign.biz"])

    def test_allows_trusted_young_domain(self):
        decision = policy.decide_quarantine(
            domain_ages=[{"domain": "new-campaign.biz", "is_young": True}],
            trusted_domains={"new-campaign.biz"},
        )

        self.assertEqual(decision.action, "allow")
        self.assertEqual(decision.young_domains, [])

    def test_missing_creation_date_does_not_quarantine_by_itself(self):
        decision = policy.decide_quarantine(
            domain_ages=[{"domain": "unknown.example", "is_young": None}],
            trusted_domains=set(),
        )

        self.assertEqual(decision.action, "allow")


if __name__ == "__main__":
    unittest.main()
