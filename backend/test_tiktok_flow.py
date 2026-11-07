"""Auto-add, match on registration, and claim. TikTok is stubbed, the database is a temp file."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_dir}/flow.db"
os.environ["APIFY_TOKEN"] = "t"
os.environ["OPENROUTER_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import tiktok  # noqa: E402


def fake_lookup(handle, videos=3, per=5):
    comments = tiktok.classify_comments(
        [
            {"cid": f"{handle}-a1", "text": "They took my money and blocked me, this is a scam", "uniqueId": "b1", "videoWebUrl": "https://www.tiktok.com/@x/video/1"},
            {"cid": f"{handle}-a2", "text": "Fast delivery, well packed, would buy again", "uniqueId": "b2", "videoWebUrl": "https://www.tiktok.com/@x/video/1"},
        ]
    )
    return {
        "profile": {
            "handle": handle, "nickname": "Kayole Greens", "profile_url": "", "verified": False,
            "bio": "Fresh veg, call 0711 222 333", "bio_link": None, "followers": 10, "likes": 5, "videos": 3,
            "private": False, "tiktok_seller": False, "business_account": False, "business_category": None,
        },
        "videos": [], "comments": comments, "summary": tiktok.summarize(comments), "ai": None,
    }


class FlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = mock.patch.object(tiktok, "lookup", fake_lookup)
        cls.patch.start()
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.patch.stop()

    def setUp(self):
        tiktok.usage_cap.per_client.clear()
        tiktok.usage_cap.day_count = 0

    def test_full_flow(self):
        r = self.client.post("/api/v1/tiktok/lookup", json={"query": "https://www.tiktok.com/@kayolegreens"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        shadow_id = body["vendor_id"]
        self.assertEqual(body["saved"], 2)
        self.assertIn("unclaimed TikTok shop", body["note"])

        again = self.client.post("/api/v1/tiktok/lookup", json={"query": "@kayolegreens"}).json()
        self.assertEqual(again["vendor_id"], shadow_id)
        self.assertEqual(again["saved"], 0)

        reg = self.client.post("/api/v1/vendors", json={"name": "Kayole Greens Ltd", "phone": "0711222333"})
        self.assertEqual(reg.status_code, 201, reg.text)
        mine = reg.json()["id"]

        matches = self.client.get(f"/api/v1/vendors/{mine}/tiktok-matches").json()
        self.assertEqual([m["id"] for m in matches], [shadow_id])
        self.assertEqual(matches[0]["comments"], 2)

        other = self.client.post("/api/v1/vendors", json={"name": "Someone Else Traders", "phone": "0733444555"}).json()["id"]
        self.assertEqual(self.client.get(f"/api/v1/vendors/{other}/tiktok-matches").json(), [])
        refused = self.client.post(f"/api/v1/vendors/{other}/claim-tiktok", json={"tiktok_vendor_id": shadow_id})
        self.assertEqual(refused.status_code, 409)
        self.assertIn("bio", refused.json()["detail"])

        ok = self.client.post(f"/api/v1/vendors/{mine}/claim-tiktok", json={"tiktok_vendor_id": shadow_id})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["id"], mine)
        self.assertEqual(len([x for x in ok.json()["reports"] if x["platform"] == "tiktok"]), 2)
        self.assertEqual(self.client.get(f"/api/v1/vendor/{shadow_id}").status_code, 404)

    def test_registration_with_a_handle_runs_the_check(self):
        reg = self.client.post("/api/v1/vendors", json={"name": "Mombasa Mats", "phone": "0755666777", "tiktok": "@mombasamats"})
        self.assertEqual(reg.status_code, 201, reg.text)
        detail = self.client.get(f"/api/v1/vendor/{reg.json()['id']}").json()
        self.assertEqual(len([x for x in detail["reports"] if x["platform"] == "tiktok"]), 2)

    def test_usage_cap(self):
        with mock.patch.dict("os.environ", {"TIKTOK_HOURLY_PER_CLIENT": "1"}):
            self.assertEqual(self.client.post("/api/v1/tiktok/lookup", json={"query": "@capone"}).status_code, 200)
            self.assertEqual(self.client.post("/api/v1/tiktok/lookup", json={"query": "@captwo"}).status_code, 429)


if __name__ == "__main__":
    unittest.main()
