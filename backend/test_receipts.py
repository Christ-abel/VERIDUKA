"""A confirmation code can move the score once.

Run from the backend folder:

    python -m unittest test_receipts.py

The first shop to file a code keeps a normal report. The next filing of that
code is stored and left out of the score, including when it names another shop.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Report, Vendor
from receipts import OTHER_SHOP, SAME_SHOP, attach_receipt, extract_confirmation_code, receipt_hash
from scoring import score_vendor, utcnow

CODE = "QK72H8L9P0"
PASTED = f"{CODE} Confirmed. Ksh500.00 sent to the shop on 7/11/26 at 2:30 PM."


def _shop(name: str) -> Vendor:
    return Vendor(name=name, category="General", location="Kenya", about="", kra_status="unverified", brs_status="unverified")


def _report(vendor_id: int, text: str, category: str = "SCAM") -> Report:
    return Report(
        vendor_id=vendor_id,
        report_type=category,
        ai_category=category,
        ai_confidence=0.9,
        ai_reasons="[]",
        sentiment="negative",
        is_false_report=False,
        description=text,
        user_phone="0711000000",
        source="buyer",
        score_eligible=True,
        verified=category == "POSITIVE",
        resolved=False,
        created_at=utcnow(),
    )


class ExtractTests(unittest.TestCase):
    def test_reads_the_code_that_leads_a_safaricom_sms(self):
        self.assertEqual(extract_confirmation_code(PASTED), CODE)

    def test_reads_a_labeled_code_in_any_case(self):
        text = "I paid Friday. Confirmation code: qk72h8l9p0. They blocked me."
        self.assertEqual(extract_confirmation_code(text), CODE)

    def test_ignores_a_phone_number_and_ordinary_words(self):
        text = "I paid 0712345678 on Friday. The rider never arrived and they blocked me on WhatsApp."
        self.assertIsNone(extract_confirmation_code(text))

    def test_hash_does_not_keep_the_raw_code(self):
        digest = receipt_hash(CODE)
        self.assertNotIn(CODE, digest)
        self.assertEqual(len(digest), 64)


class ReuseTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.path = Path(handle.name)
        self.engine = create_engine("sqlite:///" + self.path.as_posix())
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.first = _shop("First Shop")
        self.second = _shop("Second Shop")
        self.db.add_all([self.first, self.second])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.path.unlink(missing_ok=True)

    def _file(self, vendor: Vendor, text: str, category: str = "SCAM") -> Report:
        report = _report(vendor.id, text, category)
        attach_receipt(self.db, report, {})
        self.db.add(report)
        self.db.commit()
        return report

    def test_first_use_can_count_and_the_other_shop_cannot(self):
        original = self._file(self.first, PASTED)
        copy = self._file(self.second, f"Same screenshot. Confirmation code {CODE}.")

        self.assertTrue(original.score_eligible)
        self.assertFalse(copy.score_eligible)
        self.assertEqual(copy.ineligible_reason, OTHER_SHOP)
        self.assertEqual(original.receipt_hash, copy.receipt_hash)
        self.assertNotIn(CODE, original.receipt_hash or "")

        first_score = score_vendor(self.first, [original])["score"]
        second_score = score_vendor(self.second, [copy])["score"]
        self.assertEqual(first_score, 10)
        self.assertEqual(second_score, 50)
        self.assertIn("another shop", score_vendor(self.second, [copy])["impacts"][copy.id]["reason"])

    def test_a_second_copy_on_the_same_shop_does_not_count_twice(self):
        original = self._file(self.first, PASTED)
        copy = self._file(self.first, PASTED)
        self.assertTrue(original.score_eligible)
        self.assertFalse(copy.score_eligible)
        self.assertEqual(copy.ineligible_reason, SAME_SHOP)
        score = score_vendor(self.first, [original, copy])
        self.assertEqual(score["scam_points"], -40)
        self.assertEqual(score["score"], 10)

    def test_a_report_without_a_code_still_counts(self):
        report = self._file(self.first, "I paid the paybill on Friday and the parcel never arrived.")
        self.assertIsNone(report.receipt_hash)
        self.assertTrue(report.score_eligible)
        self.assertEqual(score_vendor(self.first, [report])["score"], 10)


if __name__ == "__main__":
    unittest.main()
