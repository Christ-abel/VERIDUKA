"""Locks the signal-v1 contract the dashboard and ThriveWave SMS both use.

Run from the backend folder:

    python -m unittest test_score.py

These cases are the ones a marker should be able to recompute by hand.
Social profile URLs never appear here, because they are not score inputs.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from scoring import score_vendor, utcnow


class Shop:
    def __init__(self, kra_status="unverified", brs_status="unverified"):
        self.kra_status = kra_status
        self.brs_status = brs_status


class Report:
    def __init__(self, report_id, category, *, days_ago=10, verified=True, confidence=0.9, eligible=True):
        self.id = report_id
        self.report_type = category
        self.ai_category = category
        self.ai_confidence = confidence
        self.is_false_report = category == "SPAM"
        self.verified = verified
        self.resolved = False
        self.score_eligible = eligible
        self.created_at = utcnow() - timedelta(days=days_ago)


class ScoreTests(unittest.TestCase):
    def test_registry_match_is_worth_25(self):
        score = score_vendor(Shop(kra_status="verified"), [])
        self.assertEqual(score["score"], 75)
        self.assertEqual(score["legal_points"], 25)
        self.assertEqual(score["band"], "MODERATE_RISK")

    def test_pending_registry_does_not_earn_the_bonus(self):
        score = score_vendor(Shop(kra_status="pending", brs_status="pending"), [])
        self.assertEqual(score["legal_points"], 0)
        self.assertEqual(score["score"], 50)

    def test_praise_caps_at_20_and_needs_proof(self):
        reports = [Report(index, "POSITIVE", days_ago=40 - index) for index in range(1, 6)]
        reports.append(Report(9, "POSITIVE", verified=False))
        score = score_vendor(Shop(), reports)
        self.assertEqual(score["positive_points"], 20)
        self.assertEqual(score["score"], 70)

    def test_recent_scam_counts_double_and_spam_is_ignored(self):
        reports = [
            Report(1, "SCAM", days_ago=5, verified=False),
            Report(2, "SPAM", days_ago=1, verified=False),
            Report(3, "NON_DELIVERY", days_ago=60, verified=False),
        ]
        score = score_vendor(Shop(), reports)
        self.assertEqual(score["scam_points"], -40)
        self.assertEqual(score["service_points"], -5)
        self.assertEqual(score["false_count"], 1)
        self.assertEqual(score["score"], 5)

    def test_seed_shapes(self):
        """The three demo shops, reduced to the points that produce 95, 65, and 25."""
        tech = score_vendor(
            Shop(kra_status="verified", brs_status="verified"),
            [Report(index, "POSITIVE", days_ago=20 + index) for index in range(1, 5)],
        )
        mama = score_vendor(
            Shop(kra_status="pending", brs_status="pending"),
            [Report(index, "POSITIVE", days_ago=20 + index) for index in range(1, 6)]
            + [Report(8, "NON_DELIVERY", days_ago=42, verified=False)],
        )
        trendy = score_vendor(
            Shop(),
            [
                Report(1, "SCAM", days_ago=45, verified=False),
                Report(2, "NON_DELIVERY", days_ago=55, verified=False),
                Report(3, "SPAM", days_ago=6, verified=False),
                Report(4, "SPAM", days_ago=9, verified=False),
            ],
        )
        self.assertEqual((tech["score"], mama["score"], trendy["score"]), (95, 65, 25))
        self.assertEqual(tech["band"], "VERIFIED_SIGNAL")
        self.assertEqual(mama["band"], "MODERATE_RISK")
        self.assertEqual(trendy["band"], "HIGH_NOISE")


if __name__ == "__main__":
    unittest.main()
