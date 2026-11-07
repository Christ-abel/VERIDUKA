import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from main import mpesa_assessment, vendor_detail
from models import OfficialRecord, Vendor


class MpesaAssessmentTests(unittest.TestCase):
    settings = {
        "DARAJA_CONSUMER_KEY": "sandbox-key",
        "DARAJA_CONSUMER_SECRET": "sandbox-secret",
        "DARAJA_ENVIRONMENT": "sandbox",
    }

    def test_matching_sandbox_name_verifies_badge(self):
        vendor = SimpleNamespace(paybill="400200", mpesa_verified=False)

        verified, account_name, message = mpesa_assessment(
            vendor,
            "Nairobi Tech Hub Electronics",
            self.settings,
        )

        self.assertTrue(verified)
        self.assertEqual(account_name, "Nairobi Tech Hub Electronics Limited")
        self.assertIn("matches the linked registered name", message)

    def test_mismatched_sandbox_name_removes_badge_and_explains_mismatch(self):
        vendor = SimpleNamespace(paybill="987654", mpesa_verified=True)

        verified, account_name, message = mpesa_assessment(
            vendor,
            "Savanna Hardware Limited",
            self.settings,
        )

        self.assertFalse(verified)
        self.assertEqual(account_name, "Trendy Clothez Kenya")
        self.assertIn("M-Pesa name mismatch", message)

    def test_empty_credentials_preserve_existing_badge(self):
        vendor = SimpleNamespace(paybill="987654", mpesa_verified=True)

        verified, account_name, message = mpesa_assessment(vendor, None, {})

        self.assertTrue(verified)
        self.assertIsNone(account_name)
        self.assertIsNone(message)

    def test_no_linked_registered_name_does_not_verify(self):
        vendor = SimpleNamespace(paybill="400200", mpesa_verified=True)

        verified, account_name, message = mpesa_assessment(vendor, None, self.settings)

        self.assertFalse(verified)
        self.assertEqual(account_name, "Nairobi Tech Hub Electronics Limited")
        self.assertIn("no linked KRA/BRS registered name", message)

    def test_partial_credentials_do_not_preserve_legacy_badge(self):
        vendor = SimpleNamespace(paybill="400200", mpesa_verified=True)
        settings = {"DARAJA_CONSUMER_KEY": "sandbox-key"}

        verified, _, message = mpesa_assessment(vendor, "Nairobi Tech Hub Electronics Limited", settings)

        self.assertFalse(verified)
        self.assertIn("configure both", message)

    def test_vendor_detail_exposes_matching_badge_and_legal_explanation(self):
        detail = self._vendor_detail("400200", "Nairobi Tech Hub Electronics Limited")

        self.assertTrue(detail.mpesa_verified)
        self.assertTrue(detail.badges["mpesa_verified"])
        self.assertIn("matches the linked registered name", detail.mpesa_verification_message)

    def test_vendor_detail_exposes_mismatch_and_removes_badge(self):
        detail = self._vendor_detail("987654", "Savanna Hardware Limited")

        self.assertFalse(detail.mpesa_verified)
        self.assertFalse(detail.badges["mpesa_verified"])
        self.assertIn("M-Pesa name mismatch", detail.mpesa_verification_message)

    def _vendor_detail(self, paybill, registered_name):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            vendor = Vendor(
                name="Example Shop",
                paybill=paybill,
                kra_pin="PIN123",
                kra_status="verified",
                brs_status="verified",
                mpesa_verified=True,
            )
            record = OfficialRecord(
                kra_pin="PIN123",
                brs_number="BRS123",
                registered_name=registered_name,
                kra_status="active",
                brs_status="registered",
                county="Nairobi",
                entity_type="company",
                registered_on="2020-01-01",
            )
            session.add_all([vendor, record])
            session.flush()
            with patch.dict("os.environ", self.settings, clear=False):
                return vendor_detail(session, vendor)
        finally:
            session.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
