"""Daraja till-name checks only verify a paybill against an official entity."""

from __future__ import annotations

import base64
import json
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from database import _ensure_vendor_columns
from daraja import DarajaClient, DarajaConfigurationError, registered_names_match
from main import badges_for, vendor_card, verify_legal
from models import Base, OfficialRecord, Vendor
from schemas import LegalIn
from scoring import score_vendor


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self.payload


class DarajaClientTests(unittest.TestCase):
    def test_oauth_and_name_lookup_use_sandbox_and_return_merchant_name(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))
            if len(requests) == 1:
                return FakeResponse({"access_token": "sandbox-token"})
            return FakeResponse({"MerchantName": " Nairobi Tech Hub Electronics Ltd "})

        with patch.dict(
            os.environ,
            {
                "DARAJA_CONSUMER_KEY": "consumer-key",
                "DARAJA_CONSUMER_SECRET": "consumer-secret",
                "DARAJA_ENVIRONMENT": "sandbox",
                "DARAJA_NAME_LOOKUP_URL": "/name-inquiry",
            },
        ), patch("daraja.urlopen", side_effect=fake_urlopen):
            name = DarajaClient().lookup_paybill_name("400200")

        self.assertEqual(name, "Nairobi Tech Hub Electronics Ltd")
        oauth_request, oauth_timeout = requests[0]
        self.assertEqual(oauth_request.full_url, "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials")
        self.assertEqual(
            oauth_request.get_header("Authorization"),
            "Basic " + base64.b64encode(b"consumer-key:consumer-secret").decode("ascii"),
        )
        self.assertEqual(oauth_timeout, 10)

        lookup_request, lookup_timeout = requests[1]
        self.assertEqual(lookup_request.full_url, "https://sandbox.safaricom.co.ke/name-inquiry")
        self.assertEqual(lookup_request.get_header("Authorization"), "Bearer sandbox-token")
        self.assertEqual(json.loads(lookup_request.data), {"ShortCode": "400200"})
        self.assertEqual(lookup_timeout, 10)

    def test_empty_lookup_url_uses_query_organization_info(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            if len(requests) == 1:
                return FakeResponse({"access_token": "sandbox-token"})
            return FakeResponse({"OrganizationName": "Nairobi Tech Hub Electronics Limited"})

        with patch.dict(
            os.environ,
            {
                "DARAJA_CONSUMER_KEY": "consumer-key",
                "DARAJA_CONSUMER_SECRET": "consumer-secret",
                "DARAJA_ENVIRONMENT": "sandbox",
                "DARAJA_NAME_LOOKUP_URL": "",
            },
        ), patch("daraja.urlopen", side_effect=fake_urlopen):
            name = DarajaClient().lookup_paybill_name("400200")

        self.assertEqual(name, "Nairobi Tech Hub Electronics Limited")
        self.assertEqual(
            requests[1].full_url,
            "https://sandbox.safaricom.co.ke/mpesa/orginfo/v1/query",
        )
        self.assertEqual(json.loads(requests[1].data), {"ShortCode": "400200"})

    def test_lookup_url_must_match_configured_safaricom_host(self):
        with patch.dict(
            os.environ,
            {
                "DARAJA_CONSUMER_KEY": "consumer-key",
                "DARAJA_CONSUMER_SECRET": "consumer-secret",
                "DARAJA_NAME_LOOKUP_URL": "https://example.com/name",
            },
        ):
            client = DarajaClient()
            with self.assertRaises(DarajaConfigurationError):
                client._endpoint("https://sandbox.safaricom.co.ke")

    def test_registered_name_comparison_ignores_case_punctuation_and_legal_suffix(self):
        self.assertTrue(registered_names_match("Nairobi Tech Hub Electronics Ltd.", "nairobi tech hub electronics limited"))
        self.assertFalse(registered_names_match("Nairobi Tech Hub Electronics", "Nairobi Tech Hub Electronics Kenya"))


class VerifyLegalDarajaTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.record = OfficialRecord(
            kra_pin="P051987654Z",
            brs_number="PVT-9X2K41",
            registered_name="Nairobi Tech Hub Electronics Limited",
            kra_status="active",
            brs_status="registered",
            county="Nairobi",
            entity_type="private_company",
            registered_on="2019-04-12",
        )
        self.vendor = Vendor(
            name="Nairobi Tech Hub Electronics",
            paybill="400200",
            kra_pin=self.record.kra_pin,
            brs_number=self.record.brs_number,
            kra_status="verified",
            brs_status="verified",
            mpesa_verified=True,
        )
        self.db.add_all([self.record, self.vendor])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _verify(self, till_name: str):
        with patch.dict(
            os.environ,
            {
                "DARAJA_CONSUMER_KEY": "consumer-key",
                "DARAJA_CONSUMER_SECRET": "consumer-secret",
                "DARAJA_NAME_LOOKUP_URL": "/name-inquiry",
            },
        ), patch("main.DarajaClient.lookup_paybill_name", return_value=till_name):
            return verify_legal(
                LegalIn(
                    vendor_id=self.vendor.id,
                    business_name=self.vendor.name,
                    kra_pin=self.vendor.kra_pin,
                    brs_number=self.vendor.brs_number,
                ),
                self.db,
            )

    def test_matching_till_name_keeps_badge(self):
        result = self._verify("Nairobi Tech Hub Electronics Ltd")
        self.db.refresh(self.vendor)

        self.assertTrue(self.vendor.mpesa_name_match)
        self.assertTrue(badges_for(self.vendor)["mpesa_verified"])
        self.assertIn("M-Pesa Verified", result.message)

    def test_mismatched_till_name_removes_badge_and_explains_mismatch(self):
        result = self._verify("Savanna Hardware Limited")
        self.db.refresh(self.vendor)

        self.assertFalse(self.vendor.mpesa_name_match)
        self.assertFalse(badges_for(self.vendor)["mpesa_verified"])
        self.assertFalse(vendor_card(self.vendor, score_vendor(self.vendor, []), "profile").mpesa_verified)
        self.assertIn("does not match registered entity", result.message)
        self.assertIn("Savanna Hardware Limited", result.message)

    def test_empty_keys_preserve_seeded_badge_without_calling_daraja(self):
        with patch.dict(
            os.environ,
            {
                "DARAJA_CONSUMER_KEY": "",
                "DARAJA_CONSUMER_SECRET": "",
                "DARAJA_NAME_LOOKUP_URL": "",
            },
        ), patch("main.DarajaClient.lookup_paybill_name", side_effect=AssertionError("unexpected lookup")):
            verify_legal(
                LegalIn(
                    vendor_id=self.vendor.id,
                    business_name=self.vendor.name,
                    kra_pin=self.vendor.kra_pin,
                    brs_number=self.vendor.brs_number,
                ),
                self.db,
            )

        self.assertTrue(badges_for(self.vendor)["mpesa_verified"])
        self.assertIsNone(self.vendor.mpesa_till_name)


class VendorMigrationTests(unittest.TestCase):
    def test_existing_sqlite_vendors_table_gets_daraja_columns(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE vendors (id INTEGER PRIMARY KEY)"))
        db = Session(engine)
        try:
            with patch("database.DATABASE_URL", "sqlite:///existing.db"):
                _ensure_vendor_columns(db)
            columns = {row[1] for row in db.execute(text("PRAGMA table_info(vendors)"))}
        finally:
            db.close()
            engine.dispose()

        self.assertIn("mpesa_till_name", columns)
        self.assertIn("mpesa_name_match", columns)


if __name__ == "__main__":
    unittest.main()
