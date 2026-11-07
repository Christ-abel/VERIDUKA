"""English, Swahili, and Sheng report classification coverage."""

from __future__ import annotations

import unittest
from datetime import timedelta
from types import SimpleNamespace

from classifier import classify_report
from scoring import score_vendor, utcnow


class ClassifierTests(unittest.TestCase):
    def test_swahili_and_sheng_phrases_cover_all_categories(self):
        examples = (
            ("Nilituma 5000 kwa paybill lakini ameniblock.", "SCAM"),
            ("Nimetuma pesa kwa paybill lakini bado sijapokea mzigo.", "DELAYED_DELIVERY"),
            ("Bidhaa imeharibika na huduma mbaya baada ya kulipa paybill.", "BAD_SERVICE"),
            ("Nitanunua tena, bidhaa halisi na huduma nzuri.", "POSITIVE"),
            ("Pata airtime bure, umeshinda zawadi, bonyeza hapa.", "SPAM"),
        )

        for text, expected in examples:
            with self.subTest(category=expected):
                result = classify_report(text)
                self.assertEqual(result.category, expected)

    def test_swahili_scam_penalizes_score_like_an_english_scam(self):
        now = utcnow()
        vendor = SimpleNamespace(kra_status="unverified", brs_status="unverified")
        scores = []

        for report_id, text in enumerate(
            (
                "I paid the paybill but they blocked me after taking my money.",
                "Nilituma 5000 kwa paybill lakini ameniblock baada ya kuchukua pesa.",
            ),
            start=1,
        ):
            result = classify_report(text)
            self.assertEqual(result.category, "SCAM")
            report = SimpleNamespace(
                id=report_id,
                report_type=result.category,
                ai_category=result.category,
                ai_confidence=result.confidence,
                is_false_report=result.is_false_report,
                score_eligible=True,
                created_at=now - timedelta(days=5),
                verified=False,
                resolved=False,
            )
            scores.append(score_vendor(vendor, [report], now=now))

        self.assertEqual(scores[0]["scam_points"], -40)
        self.assertEqual(scores[1]["scam_points"], scores[0]["scam_points"])
        self.assertEqual(scores[1]["score"], scores[0]["score"])


if __name__ == "__main__":
    unittest.main()
