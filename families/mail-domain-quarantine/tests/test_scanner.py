import sys
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mail_domain_quarantine import scanner


class ScannerTests(unittest.TestCase):
    def test_scan_folder_uses_project_domain_cache(self):
        calls = []
        original = scanner.run_outlook_client
        scanner.run_outlook_client = lambda args, **kwargs: calls.append((args, kwargs)) or {"ok": True}
        try:
            scanner.scan_folder(
                account="demo@example.com",
                folder="inbox",
                days=7,
                limit=10,
                young_days=365,
            )
        finally:
            scanner.run_outlook_client = original

        args, kwargs = calls[0]
        cache_index = args.index("--rdap-cache")
        self.assertEqual(args[cache_index + 1], str(scanner.state.DOMAIN_CACHE_PATH))
        self.assertEqual(kwargs["timeout_seconds"], scanner.DEFAULT_OUTLOOK_TIMEOUT_SECONDS)

    def test_run_outlook_client_timeout_returns_error_payload(self):
        original_run = scanner.subprocess.run
        scanner.subprocess.run = lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd=["outlook-classic-mail-client"], timeout=12)
        )
        try:
            result = scanner.run_outlook_client(["scan-domain-refs"], timeout_seconds=12)
        finally:
            scanner.subprocess.run = original_run

        self.assertFalse(result["ok"])
        self.assertIn("timed out after 12", result["stderr"])

    def test_dry_run_records_quarantine_candidate_without_moving(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Inbox"},
            "messages": [
                {
                    "message": {
                        "entry_id": "entry-1",
                        "subject": "Suspicious",
                        "sender_email": "bad@fresh.biz",
                        "folder_path": "\\\\demo@example.com\\Inbox",
                    },
                    "domain_ages": [{"domain": "fresh.biz", "is_young": True}],
                }
            ],
        }
        moves = []

        report = scanner.evaluate_scan_payload(
            scan_payload,
            quarantine_folder="custom:Inbox/Quarantine",
            trusted_domains=set(),
            apply=False,
            move_message=lambda **kwargs: moves.append(kwargs),
        )

        self.assertEqual(len(report["candidates"]), 1)
        self.assertEqual(report["candidates"][0]["action"], "quarantine")
        self.assertEqual(moves, [])

    def test_apply_writes_ledger_before_move(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Spam"},
            "messages": [
                {
                    "message": {
                        "entry_id": "entry-1",
                        "subject": "Suspicious",
                        "sender_email": "bad@fresh.biz",
                        "folder_path": "\\\\demo@example.com\\Spam",
                    },
                    "domain_ages": [{"domain": "fresh.biz", "is_young": True}],
                }
            ],
        }
        events = []
        original = scanner.state.write_ledger_entry
        scanner.state.write_ledger_entry = lambda **kwargs: events.append("ledger")
        try:
            scanner.evaluate_scan_payload(
                scan_payload,
                quarantine_folder="custom:Inbox/Quarantine",
                trusted_domains=set(),
                apply=True,
                move_message=lambda **kwargs: events.append("move") or {"ok": True},
            )
        finally:
            scanner.state.write_ledger_entry = original

        self.assertEqual(events, ["ledger", "move"])

    def test_reputation_evidence_does_not_create_move_decision(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Inbox"},
            "messages": [
                {
                    "message": {
                        "entry_id": "entry-1",
                        "subject": "Needs review",
                        "sender_email": "sender@example.com",
                        "folder_path": "\\\\demo@example.com\\Inbox",
                    },
                    "domain_ages": [{"domain": "example.com", "is_young": False}],
                }
            ],
        }
        moves = []

        report = scanner.evaluate_scan_payload(
            scan_payload,
            quarantine_folder="custom:Inbox/Quarantine",
            trusted_domains=set(),
            apply=True,
            move_message=lambda **kwargs: moves.append(kwargs),
            reputation_by_message={
                "entry-1": {
                    "verdict": "malicious",
                    "score": 100,
                    "evidence": [{"provider": "test", "detail": "listed"}],
                }
            },
        )

        self.assertEqual(report["allowed"][0]["reputation"]["verdict"], "malicious")
        self.assertEqual(report["candidates"], [])
        self.assertEqual(moves, [])

    def test_reputation_observables_are_deduplicated_before_lookup(self):
        observables = [
            {"type": "domain", "value": "Example.COM", "source": "sender", "context": {"message_entry_id": "one"}},
            {"type": "domain", "value": "example.com", "source": "body", "context": {"message_entry_id": "two"}},
            {"type": "ip", "value": "203.0.113.7", "source": "received", "context": {"message_entry_id": "one"}},
        ]

        unique_observables, unique_keys, original_keys = scanner.deduplicate_reputation_observables(observables)

        self.assertEqual(len(unique_observables), 2)
        self.assertEqual(unique_keys, ["domain:example.com", "ip:203.0.113.7"])
        self.assertEqual(original_keys, ["domain:example.com", "domain:example.com", "ip:203.0.113.7"])

    def test_reputation_timeout_returns_error_payload(self):
        original_run = scanner.subprocess.run
        scanner.subprocess.run = lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd=["observable-reputation"], timeout=900)
        )
        try:
            result = scanner.run_observable_reputation(
                [{"type": "domain", "value": "example.com", "source": "sender", "context": {}}]
            )
        finally:
            scanner.subprocess.run = original_run

        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])

    def test_light_reputation_observables_skip_exact_urls_but_keep_domains(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Inbox"},
            "messages": [
                {
                    "message": {"entry_id": "entry-1", "subject": "Promo", "sender_email": "sender@example.com"},
                    "domain_references": [
                        {
                            "registrable_domain": "tracker.example",
                            "source": "html-url",
                            "raw_value": "https://click.tracker.example/path?id=1",
                        }
                    ],
                    "ip_references": [{"ip": "203.0.113.7", "source": "received", "raw_value": "203.0.113.7"}],
                }
            ],
        }

        observables = scanner.build_reputation_observables(scan_payload, include_urls=False)

        self.assertEqual([item["type"] for item in observables], ["domain", "ip"])
        self.assertEqual(observables[0]["value"], "tracker.example")

    def test_scan_folder_passes_blocklist_flags_to_outlook_inspection(self):
        calls = []
        original = scanner.run_outlook_client
        scanner.run_outlook_client = lambda args, **kwargs: calls.append((args, kwargs)) or {"ok": True}
        try:
            scanner.scan_folder(
                account="demo@example.com",
                folder="inbox",
                days=7,
                limit=10,
                young_days=365,
                with_blocklists=True,
                blocklist_profile="threat",
                outlook_timeout_seconds=123,
            )
        finally:
            scanner.run_outlook_client = original

        args, kwargs = calls[0]
        self.assertIn("--with-blocklists", args)
        self.assertEqual(args[args.index("--blocklist-profile") + 1], "threat")
        self.assertEqual(args[args.index("--blocklist-cache") + 1], str(scanner.state.BLOCKLIST_CACHE_PATH))
        self.assertEqual(kwargs["timeout_seconds"], 123)

    def test_non_threat_blocklist_hit_is_report_only_and_does_not_move(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Inbox"},
            "messages": [
                {
                    "message": {
                        "entry_id": "entry-1",
                        "subject": "Old listed domain",
                        "sender_email": "sender@example.com",
                        "folder_path": "\\\\demo@example.com\\Inbox",
                    },
                    "domain_ages": [
                        {
                            "domain": "oldlisted.example",
                            "is_young": False,
                            "blocklist_hits": [
                                {
                                    "source": "unit-debug",
                                    "category": "tracking",
                                    "matched_domain": "oldlisted.example",
                                    "profile": "debug-all",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        moves = []

        report = scanner.evaluate_scan_payload(
            scan_payload,
            quarantine_folder="custom:Inbox/Quarantine",
            trusted_domains=set(),
            apply=True,
            move_message=lambda **kwargs: moves.append(kwargs),
        )

        self.assertEqual(report["candidates"], [])
        self.assertEqual(moves, [])
        self.assertEqual(report["allowed"][0]["blocklist_hits"][0]["category"], "tracking")

    def test_threat_blocklist_hit_creates_quarantine_candidate(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Inbox"},
            "messages": [
                {
                    "message": {
                        "entry_id": "entry-1",
                        "subject": "Listed old domain",
                        "sender_email": "sender@oldlisted.example",
                    },
                    "domain_ages": [
                        {
                            "domain": "oldlisted.example",
                            "is_young": False,
                            "blocklist_hits": [
                                {
                                    "source": "unit-threat",
                                    "category": "malware",
                                    "matched_domain": "oldlisted.example",
                                    "profile": "threat",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        report = scanner.evaluate_scan_payload(
            scan_payload,
            quarantine_folder="custom:Inbox/Quarantine",
            trusted_domains=set(),
            apply=False,
        )

        self.assertEqual(report["allowed"], [])
        self.assertEqual(report["candidates"][0]["action"], "quarantine")
        self.assertIn("blocklisted domains", report["candidates"][0]["reason"])

    def test_debug_blocklist_hit_does_not_create_quarantine_candidate(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Inbox"},
            "messages": [
                {
                    "message": {"entry_id": "entry-1", "subject": "Social", "sender_email": "sender@example.com"},
                    "domain_ages": [
                        {
                            "domain": "facebook.com",
                            "is_young": False,
                            "blocklist_hits": [
                                {
                                    "source": "blocklistproject-facebook",
                                    "category": "facebook",
                                    "matched_domain": "facebook.com",
                                    "profile": "debug-all",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        report = scanner.evaluate_scan_payload(
            scan_payload,
            quarantine_folder="custom:Inbox/Quarantine",
            trusted_domains=set(),
            apply=False,
        )

        self.assertEqual(report["candidates"], [])
        self.assertEqual(report["allowed"][0]["blocklist_hits"][0]["profile"], "debug-all")

    def test_suppressed_blocklist_hit_is_preserved_but_not_alerted(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Inbox"},
            "messages": [
                {
                    "message": {
                        "entry_id": "entry-1",
                        "subject": "Shareholder notice",
                        "sender_email": "jga.repsol@email.repsol.com",
                        "folder_path": "\\\\demo@example.com\\Inbox",
                    },
                    "domain_ages": [
                        {
                            "domain": "exacttarget.com",
                            "is_young": False,
                            "blocklist_hits": [
                                {
                                    "source": "blocklistproject-malware",
                                    "category": "malware",
                                    "matched_domain": "exacttarget.com",
                                    "profile": "threat",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        report = scanner.evaluate_scan_payload(
            scan_payload,
            quarantine_folder="custom:Inbox/Quarantine",
            trusted_domains=set(),
            blocklist_suppressions={"exacttarget.com": "shared mail infrastructure"},
            apply=False,
        )

        row = report["allowed"][0]
        self.assertEqual(row["blocklist_hits"], [])
        self.assertEqual(row["suppressed_blocklist_hits"][0]["domain"], "exacttarget.com")
        self.assertEqual(row["suppressed_blocklist_hits"][0]["suppression_reason"], "shared mail infrastructure")

        markdown = scanner.render_markdown_report(
            {
                "mode": "dry-run",
                "generated_at": "2026-04-22T00:00:00",
                "days": 7,
                "young_days": 365,
                "with_blocklists": True,
                "blocklist_profile": "threat",
                "with_reputation": False,
                "reputation_profile": None,
                "accounts": [
                    {
                        "account": "demo@example.com",
                        "folders": [{"folder_selector": "inbox", "ok": True, **report}],
                    }
                ],
            }
        )
        self.assertNotIn("Blocklist-only", markdown)
        self.assertNotIn("exacttarget.com", markdown)

    def test_suppression_matches_exact_registrable_domain_only(self):
        active, suppressed = scanner.split_blocklist_hits_for_record(
            {
                "domain_ages": [
                    {
                        "domain": "notexacttarget.com",
                        "blocklist_hits": [
                            {
                                "source": "unit-threat",
                                "category": "malware",
                                "matched_domain": "notexacttarget.com",
                            }
                        ],
                    },
                    {
                        "domain": "exacttarget.com",
                        "blocklist_hits": [
                            {
                                "source": "unit-threat",
                                "category": "malware",
                                "matched_domain": "exacttarget.com",
                            }
                        ],
                    },
                ]
            },
            {"exacttarget.com": "shared mail infrastructure"},
        )

        self.assertEqual([hit["domain"] for hit in active], ["notexacttarget.com"])
        self.assertEqual([hit["domain"] for hit in suppressed], ["exacttarget.com"])

    def test_suppressed_blocklist_hit_does_not_affect_young_domain_quarantine(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Inbox"},
            "messages": [
                {
                    "message": {
                        "entry_id": "entry-1",
                        "subject": "Fresh campaign",
                        "sender_email": "sender@fresh.biz",
                    },
                    "domain_ages": [
                        {
                            "domain": "fresh.biz",
                            "is_young": True,
                            "blocklist_hits": [],
                        },
                        {
                            "domain": "exacttarget.com",
                            "is_young": False,
                            "blocklist_hits": [
                                {
                                    "source": "blocklistproject-malware",
                                    "category": "malware",
                                    "matched_domain": "exacttarget.com",
                                    "profile": "threat",
                                }
                            ],
                        },
                    ],
                }
            ],
        }

        report = scanner.evaluate_scan_payload(
            scan_payload,
            quarantine_folder="custom:Inbox/Quarantine",
            trusted_domains=set(),
            blocklist_suppressions={"exacttarget.com": "shared mail infrastructure"},
            apply=False,
        )

        self.assertEqual(report["candidates"][0]["young_domains"], ["fresh.biz"])
        self.assertEqual(report["candidates"][0]["blocklist_hits"], [])
        self.assertEqual(report["candidates"][0]["suppressed_blocklist_hits"][0]["domain"], "exacttarget.com")

    def test_structure_signals_are_added_to_rows_and_markdown(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Spam"},
            "messages": [
                {
                    "message": {
                        "entry_id": "entry-1",
                        "subject": "Photos will be deleted",
                        "sender_email": "bad@niybtzpr.rzge.mustbuilders.biz",
                    },
                    "domain_ages": [{"domain": "mustbuilders.biz", "is_young": True}],
                    "domain_structure": [
                        {
                            "domain": "niybtzpr.rzge.mustbuilders.biz",
                            "registrable_domain": "mustbuilders.biz",
                            "source": "sender",
                            "evidence_tags": ["random_like_label", "risky_tld"],
                        }
                    ],
                }
            ],
        }

        report = scanner.evaluate_scan_payload(
            scan_payload,
            quarantine_folder="custom:Inbox/Quarantine",
            trusted_domains=set(),
            apply=False,
        )

        self.assertEqual(report["candidates"][0]["structure_signals"][0]["domain"], "niybtzpr.rzge.mustbuilders.biz")
        markdown = scanner.render_markdown_report(
            {
                "mode": "dry-run",
                "generated_at": "2026-04-22T00:00:00",
                "days": 7,
                "young_days": 365,
                "with_blocklists": True,
                "blocklist_profile": "threat",
                "with_reputation": False,
                "reputation_profile": None,
                "accounts": [
                    {
                        "account": "demo@example.com",
                        "folders": [{"folder_selector": "spam", "ok": True, **report}],
                    }
                ],
            }
        )
        self.assertIn("Structure:", markdown)
        self.assertIn("random_like_label", markdown)

    def test_structure_signals_are_deduplicated_by_domain_and_tags(self):
        signals = scanner.structure_signals_for_record(
            {
                "domain_structure": [
                    {"domain": "click.example.com", "evidence_tags": ["deep_subdomain_chain"], "source": "body-url"},
                    {"domain": "click.example.com", "evidence_tags": ["deep_subdomain_chain"], "source": "html-url"},
                    {"domain": "other.example.com", "evidence_tags": ["random_like_label"], "source": "sender"},
                ]
            }
        )

        self.assertEqual([signal["domain"] for signal in signals], ["click.example.com", "other.example.com"])

    def test_structure_summary_groups_repeated_domain_tags(self):
        summary = scanner.summarize_structure_signals(
            [
                {"domain": "click.example.com", "evidence_tags": ["deep_subdomain_chain"]},
                {"domain": "click.example.com", "evidence_tags": ["random_like_sender_localpart"]},
                {"domain": "other.example.com", "evidence_tags": ["risky_tld"]},
            ]
        )

        self.assertEqual(summary.count("click.example.com"), 1)
        self.assertIn("deep_subdomain_chain", summary)
        self.assertIn("random_like_sender_localpart", summary)

    def test_clustering_surfaces_rotating_young_domains_without_changing_actions(self):
        folder_result = {
            "candidates": [
                {
                    "message": {
                        "entry_id": "entry-1",
                        "subject": "We've blocked your account! Renew your subscription now",
                        "body_excerpt": "iCloud payment expired. photos and videos will be deleted. renew now.",
                    },
                    "young_domains": ["acaere.co.uk"],
                    "reason": "young untrusted domains: acaere.co.uk",
                    "action": "quarantine",
                },
                {
                    "message": {
                        "entry_id": "entry-2",
                        "subject": "We've blocked your account! Renew your subscription now",
                        "body_excerpt": "iCloud payment expired. photos and videos will be deleted. renew now.",
                    },
                    "young_domains": ["mustbuilders.biz"],
                    "reason": "young untrusted domains: mustbuilders.biz",
                    "action": "quarantine",
                },
            ],
            "allowed": [],
            "errors": [],
        }

        scanner.attach_message_clusters(folder_result)

        cluster = folder_result["candidates"][0]["cluster"]
        self.assertEqual(cluster["type"], "rotating_young_domains")
        self.assertEqual(cluster["message_count"], 2)
        self.assertEqual(cluster["young_domains"], ["acaere.co.uk", "mustbuilders.biz"])

    def test_report_rotation_deletes_old_and_oversized_reports_but_preserves_current_pair(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reports = Path(tmpdir)
            current_json = reports / "2026-04-22-000000-dry-run.json"
            current_md = reports / "2026-04-22-000000-dry-run.md"
            old_json = reports / "2026-03-01-000000-dry-run.json"
            old_md = reports / "2026-03-01-000000-dry-run.md"
            large_json = reports / "2026-04-20-000000-dry-run.json"
            large_md = reports / "2026-04-20-000000-dry-run.md"
            for path, content in [
                (current_json, "current-json"),
                (current_md, "current-md"),
                (old_json, "old-json"),
                (old_md, "old-md"),
                (large_json, "x" * 700),
                (large_md, "x" * 700),
            ]:
                path.write_text(content, encoding="utf-8")
            old_time = (datetime.now() - timedelta(days=60)).timestamp()
            recent_time = datetime.now().timestamp()
            for path in (old_json, old_md):
                path.touch()
                import os

                os.utime(path, (old_time, old_time))
            for path in (large_json, large_md, current_json, current_md):
                import os

                os.utime(path, (recent_time, recent_time))

            result = scanner.rotate_reports(
                report_dir=reports,
                current_paths={current_json, current_md},
                retention_days=30,
                max_bytes=1000,
                now=datetime.now(),
            )

            self.assertTrue(current_json.exists())
            self.assertTrue(current_md.exists())
            self.assertFalse(old_json.exists())
            self.assertFalse(old_md.exists())
            self.assertFalse(large_json.exists())
            self.assertFalse(large_md.exists())
            self.assertGreaterEqual(len(result["deleted_files"]), 4)

    def test_write_reports_records_final_rotation_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_state_dir = scanner.state.STATE_DIR
            original_report_dir = scanner.state.REPORT_DIR
            scanner.state.STATE_DIR = Path(tmpdir) / "state"
            scanner.state.REPORT_DIR = Path(tmpdir) / "reports"
            report = {
                "mode": "dry-run",
                "generated_at": "2026-04-22T00:00:00",
                "days": 7,
                "young_days": 365,
                "with_blocklists": True,
                "blocklist_profile": "threat",
                "with_reputation": False,
                "reputation_profile": None,
                "accounts": [{"account": "bad\ud800account", "folders": []}],
            }
            try:
                scanner.write_reports(report, retention_days=30, max_mb=100, rotate_report_files=True)
                actual_size = scanner.report_dir_size(scanner.state.REPORT_DIR)
            finally:
                scanner.state.STATE_DIR = original_state_dir
                scanner.state.REPORT_DIR = original_report_dir

        self.assertEqual(report["report_rotation"]["bytes_after"], actual_size)
        self.assertEqual(report["accounts"][0]["account"], "bad\ufffdaccount")

    def test_external_reputation_observables_are_candidate_young_domains_only(self):
        folder_result = {
            "candidates": [
                {
                    "message": {"entry_id": "entry-1", "subject": "Fresh", "sender_email": "bad@fresh.biz"},
                    "young_domains": ["fresh.biz"],
                    "blocklist_hits": [{"domain": "fresh.biz", "category": "phishing"}],
                }
            ],
            "allowed": [
                {
                    "message": {"entry_id": "entry-2", "subject": "Old", "sender_email": "old@example.com"},
                    "young_domains": [],
                    "blocklist_hits": [{"domain": "old.example", "category": "malware"}],
                }
            ],
        }

        observables = scanner.build_candidate_reputation_observables(folder_result)

        self.assertEqual(len(observables), 1)
        self.assertEqual(observables[0]["value"], "fresh.biz")
        self.assertEqual(observables[0]["context"]["message_entry_id"], "entry-1")

    def test_v2_reputation_results_are_aggregated_by_message(self):
        reputation_report = {
            "observables": [
                {
                    "type": "domain",
                    "value": "fresh.biz",
                    "raw_value": "Fresh.Biz",
                    "normalized_value": "fresh.biz",
                    "domain": "fresh.biz",
                    "source": "young-domain",
                    "context": {"message_entry_id": "entry-1"},
                    "normalization": {"warnings": []},
                    "verdict": "suspicious",
                    "score": 50,
                    "provider_summary": {
                        "provider_count": 2,
                        "skipped_count": 1,
                        "error_count": 0,
                        "evidence_count": 1,
                        "verdicts": {"suspicious": 1, "skipped": 1},
                    },
                    "explanation": "suspicious verdict from 2 passive provider result(s).",
                    "evidence": [{"provider": "unit", "match": "feed"}],
                    "errors": [],
                },
                {
                    "type": "url",
                    "value": "https://fresh.biz/a",
                    "raw_value": "https://Fresh.Biz/a#section",
                    "normalized_value": "https://fresh.biz/a",
                    "domain": "fresh.biz",
                    "source": "body-url",
                    "context": {"message_entry_id": "entry-1"},
                    "normalization": {"warnings": ["fragment_removed"]},
                    "verdict": "malicious",
                    "score": 100,
                    "provider_summary": {
                        "provider_count": 1,
                        "skipped_count": 0,
                        "error_count": 1,
                        "evidence_count": 2,
                        "verdicts": {"malicious": 1},
                    },
                    "explanation": "malicious verdict from 1 passive provider result(s).",
                    "evidence": [{"provider": "unit", "match": "url"}, {"provider": "unit", "match": "host"}],
                    "errors": ["unit: rate limited"],
                },
            ]
        }

        grouped = scanner.reputation_by_message(reputation_report)

        reputation = grouped["entry-1"]
        self.assertEqual(reputation["verdict"], "malicious")
        self.assertEqual(reputation["score"], 100)
        self.assertEqual(reputation["provider_summary"]["provider_count"], 3)
        self.assertEqual(reputation["provider_summary"]["evidence_count"], 3)
        self.assertEqual(reputation["provider_summary"]["error_count"], 1)
        self.assertEqual(reputation["provider_summary"]["skipped_count"], 1)
        self.assertEqual(len(reputation["explanations"]), 2)
        self.assertEqual(reputation["normalized_observables"][1]["normalized_value"], "https://fresh.biz/a")
        self.assertEqual(reputation["normalized_observables"][1]["normalization"]["warnings"], ["fragment_removed"])

    def test_reputation_profile_scopes_full_observables_to_candidate_messages(self):
        scan_payload = {
            "account": "demo@example.com",
            "folder": {"path": "\\\\demo@example.com\\Inbox"},
            "messages": [
                {
                    "message": {"entry_id": "entry-1", "subject": "Fresh", "sender_email": "bad@fresh.biz"},
                    "domain_references": [
                        {
                            "registrable_domain": "tracker.example",
                            "source": "html-url",
                            "raw_value": "https://click.tracker.example/path?id=1",
                        }
                    ],
                    "ip_references": [{"ip": "203.0.113.7", "source": "received", "raw_value": "203.0.113.7"}],
                },
                {
                    "message": {"entry_id": "entry-2", "subject": "Allowed", "sender_email": "sender@example.com"},
                    "domain_references": [
                        {
                            "registrable_domain": "allowed.example",
                            "source": "body-url",
                            "raw_value": "https://allowed.example/a",
                        }
                    ],
                },
            ],
        }
        folder_result = {
            "candidates": [
                {
                    "message": {"entry_id": "entry-1", "subject": "Fresh", "sender_email": "bad@fresh.biz"},
                    "young_domains": ["fresh.biz"],
                }
            ],
            "allowed": [
                {
                    "message": {"entry_id": "entry-2", "subject": "Allowed", "sender_email": "sender@example.com"},
                    "young_domains": [],
                }
            ],
        }

        light = scanner.build_reputation_observables_for_profile(
            scan_payload,
            folder_result,
            reputation_profile="light",
        )
        full = scanner.build_reputation_observables_for_profile(
            scan_payload,
            folder_result,
            reputation_profile="full",
        )

        self.assertEqual([(item["type"], item["value"]) for item in light], [("domain", "fresh.biz")])
        self.assertEqual(
            [(item["type"], item["value"]) for item in full],
            [
                ("domain", "fresh.biz"),
                ("domain", "tracker.example"),
                ("url", "https://click.tracker.example/path?id=1"),
                ("ip", "203.0.113.7"),
            ],
        )
        self.assertNotIn("allowed.example", [item["value"] for item in full])

    def test_run_scan_attaches_reputation_v2_diagnostics_and_rejections(self):
        original_accounts = scanner.ACCOUNTS
        original_scan_folder = scanner.scan_folder
        original_run_reputation = scanner.run_observable_reputation
        original_write_reports = scanner.write_reports
        original_load_trusted = scanner.state.load_trusted_domains
        original_load_suppressions = scanner.state.load_blocklist_suppressions
        scanner.ACCOUNTS = (
            scanner.AccountConfig(
                account="demo@example.com",
                quarantine_folder="custom:Inbox/Quarantine",
                source_folders=("inbox",),
            ),
        )
        scanner.scan_folder = lambda **kwargs: {
            "ok": True,
            "result": {
                "account": "demo@example.com",
                "folder": {"path": "\\\\demo@example.com\\Inbox"},
                "messages": [
                    {
                        "message": {
                            "entry_id": "entry-1",
                            "subject": "Fresh",
                            "sender_email": "bad@fresh.biz",
                        },
                        "domain_ages": [{"domain": "fresh.biz", "is_young": True}],
                    }
                ],
            },
        }
        scanner.run_observable_reputation = lambda observables: {
            "ok": True,
            "observables": [
                {
                    "type": "domain",
                    "value": "fresh.biz",
                    "raw_value": "fresh.biz",
                    "normalized_value": "fresh.biz",
                    "source": "young-domain",
                    "context": {"message_entry_id": "entry-1"},
                    "normalization": {"warnings": []},
                    "verdict": "malicious",
                    "score": 100,
                    "provider_summary": {
                        "provider_count": 1,
                        "skipped_count": 0,
                        "error_count": 0,
                        "evidence_count": 1,
                        "verdicts": {"malicious": 1},
                    },
                    "explanation": "malicious verdict from 1 passive provider result(s).",
                    "evidence": [{"provider": "unit", "match": "feed"}],
                    "errors": [],
                }
            ],
            "diagnostics": {
                "observable_count": 1,
                "rejected_observable_count": 1,
                "cache": {"hit_count": 0, "miss_count": 1},
                "providers": {
                    "result_count": 1,
                    "skipped_count": 0,
                    "error_count": 0,
                    "verdicts": {"malicious": 1},
                },
            },
            "rejected_observables": [{"index": 9, "raw_value": "bad", "error": "invalid"}],
        }
        scanner.write_reports = lambda report, **kwargs: None
        scanner.state.load_trusted_domains = lambda: set()
        scanner.state.load_blocklist_suppressions = lambda: {}
        try:
            report = scanner.run_scan(
                apply=False,
                days=7,
                limit=10,
                young_days=365,
                with_reputation=True,
                reputation_profile="light",
            )
        finally:
            scanner.ACCOUNTS = original_accounts
            scanner.scan_folder = original_scan_folder
            scanner.run_observable_reputation = original_run_reputation
            scanner.write_reports = original_write_reports
            scanner.state.load_trusted_domains = original_load_trusted
            scanner.state.load_blocklist_suppressions = original_load_suppressions

        folder = report["accounts"][0]["folders"][0]
        reputation = folder["candidates"][0]["reputation"]
        self.assertEqual(reputation["explanations"], ["malicious verdict from 1 passive provider result(s)."])
        self.assertEqual(folder["reputation_diagnostics"]["observable_count"], 1)
        self.assertEqual(folder["rejected_reputation_observables"][0]["raw_value"], "bad")
        self.assertEqual(report["reputation_diagnostics"]["observable_count"], 1)
        self.assertEqual(report["reputation_diagnostics"]["rejected_observable_count"], 1)

    def test_markdown_includes_reputation_explanations_and_diagnostics(self):
        markdown = scanner.render_markdown_report(
            {
                "mode": "dry-run",
                "generated_at": "2026-04-22T00:00:00",
                "days": 7,
                "young_days": 365,
                "with_blocklists": False,
                "blocklist_profile": None,
                "with_reputation": True,
                "reputation_profile": "light",
                "accounts": [
                    {
                        "account": "demo@example.com",
                        "folders": [
                            {
                                "folder_selector": "inbox",
                                "ok": True,
                                "candidates": [
                                    {
                                        "message": {
                                            "entry_id": "entry-1",
                                            "subject": "Fresh",
                                            "sender_email": "bad@fresh.biz",
                                        },
                                        "young_domains": ["fresh.biz"],
                                        "blocklisted_domains": [],
                                        "reputation": {
                                            "verdict": "malicious",
                                            "score": 100,
                                            "evidence": [{"provider": "unit"}],
                                            "errors": ["unit: rate limited"],
                                            "explanations": ["malicious verdict from 1 passive provider result(s)."],
                                            "provider_summary": {"evidence_count": 1, "error_count": 1},
                                        },
                                    }
                                ],
                                "allowed": [],
                                "reputation_diagnostics": {
                                    "observable_count": 1,
                                    "rejected_observable_count": 1,
                                    "cache": {"hit_count": 0, "miss_count": 1},
                                    "providers": {"result_count": 1, "skipped_count": 0, "error_count": 1},
                                },
                            }
                        ],
                    }
                ],
            }
        )

        self.assertIn("Reputation: malicious score=100 evidence=1 errors=1", markdown)
        self.assertIn("malicious verdict from 1 passive provider result(s).", markdown)
        self.assertIn("Reputation diagnostics: observables=1 rejected=1 cache=0/1 providers=1 skipped=0 errors=1", markdown)


if __name__ == "__main__":
    unittest.main()
