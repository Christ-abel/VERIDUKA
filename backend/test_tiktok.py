"""TikTok lookup: handle parsing, shaping Apify output, and classifying comments. No network."""

from __future__ import annotations

import unittest
from unittest import mock

import tiktok

PROFILE_ITEM = {
    "authorMeta": {
        "name": "TrendyClothez_KE",
        "nickName": "Trendy Clothez Kenya",
        "profileUrl": "https://www.tiktok.com/@trendyclothez_ke",
        "verified": False,
        "signature": "Dresses and shoes. Pay on delivery in Nairobi.",
        "bioLink": "wa.me/254722000111",
        "fans": 12400,
        "heart": 88000,
        "video": 64,
        "privateAccount": False,
        "ttSeller": False,
        "commerceUserInfo": {"commerceUser": True, "category": "Clothing"},
    },
    "webVideoUrl": "https://www.tiktok.com/@trendyclothez_ke/video/111",
    "text": "New dresses",
    "commentCount": 40,
    "playCount": 9000,
    "hasTikTokShopProduct": False,
}
EMPTY_VIDEO = {**PROFILE_ITEM, "webVideoUrl": "https://www.tiktok.com/@trendyclothez_ke/video/222", "commentCount": 0}

COMMENTS = [
    {"cid": "1", "text": "They took my money and blocked me, this is a scam. Paybill 400200", "uniqueId": "buyer1", "videoWebUrl": "https://www.tiktok.com/@x/video/111", "diggCount": 4},
    {"cid": "2", "text": "Fast delivery, well packed, would buy again", "uniqueId": "buyer2", "videoWebUrl": "https://www.tiktok.com/@x/video/111"},
    {"cid": "2", "text": "Fast delivery, well packed, would buy again", "uniqueId": "buyer2", "videoWebUrl": "https://www.tiktok.com/@x/video/111"},
    {"cid": "3", "text": "😂", "uniqueId": "buyer3"},
    {"cid": "4", "text": "price?", "uniqueId": "buyer4"},
]


class ParseHandleTest(unittest.TestCase):
    def test_accepts_links_and_handles(self):
        for value in (
            "https://www.tiktok.com/@TrendyClothez_KE",
            "https://www.tiktok.com/@trendyclothez_ke/video/7704834703446117662?lang=en",
            "tiktok.com/@trendyclothez_ke",
            "@Trendyclothez_ke",
            "trendyclothez_ke",
        ):
            self.assertEqual(tiktok.parse_handle(value), "trendyclothez_ke", value)

    def test_rejects_names_and_short_links(self):
        for value in ("", "   ", "Trendy Clothez Kenya", "https://vm.tiktok.com/ZMabc123/", "a"):
            self.assertIsNone(tiktok.parse_handle(value), value)


class ShapeTest(unittest.TestCase):
    def test_profile_shape(self):
        profile = tiktok.shape_profile(PROFILE_ITEM["authorMeta"])
        self.assertEqual(profile["handle"], "trendyclothez_ke")
        self.assertEqual(profile["followers"], 12400)
        self.assertTrue(profile["business_account"])
        self.assertFalse(profile["tiktok_seller"])
        self.assertEqual(profile["business_category"], "Clothing")

    def test_comments_are_deduped_filtered_and_classified(self):
        out = tiktok.classify_comments(COMMENTS)
        self.assertEqual([c["external_id"] for c in out], ["tt:1", "tt:2", "tt:4"])
        by_id = {c["external_id"]: c["classification"] for c in out}
        self.assertEqual(by_id["tt:1"]["category"], "SCAM")
        self.assertEqual(by_id["tt:2"]["category"], "POSITIVE")
        self.assertEqual(tiktok.summarize(out).get("SCAM"), 1)


class LookupTest(unittest.TestCase):
    def test_lookup_skips_videos_without_comments_and_caps_inputs(self):
        calls = []

        def fake_run(actor, actor_input, token=None):
            calls.append((actor, actor_input))
            return [PROFILE_ITEM, EMPTY_VIDEO] if actor == tiktok.PROFILE_ACTOR else COMMENTS

        with mock.patch.dict("os.environ", {"APIFY_TOKEN": "t"}), mock.patch.object(tiktok, "run_actor", fake_run):
            result = tiktok.lookup("trendyclothez_ke", videos=99, comments_per_video=99)

        self.assertEqual(calls[0][1]["resultsPerPage"], tiktok.MAX_VIDEOS)
        self.assertEqual(calls[1][1]["commentsPerPost"], tiktok.MAX_COMMENTS_PER_VIDEO)
        self.assertEqual(calls[1][1]["postURLs"], [PROFILE_ITEM["webVideoUrl"]])
        self.assertEqual(len(result["videos"]), 2)
        self.assertEqual(result["summary"]["SCAM"], 1)

    def test_unknown_account_is_a_clear_error(self):
        with mock.patch.dict("os.environ", {"APIFY_TOKEN": "t"}), mock.patch.object(tiktok, "run_actor", lambda *a, **k: []):
            with self.assertRaisesRegex(tiktok.TikTokError, "No public TikTok account"):
                tiktok.lookup("nobody_here")

    def test_missing_token_is_a_clear_error(self):
        with mock.patch.dict("os.environ", {"APIFY_TOKEN": ""}):
            with self.assertRaisesRegex(tiktok.TikTokError, "APIFY_TOKEN"):
                tiktok.lookup("trendyclothez_ke")


if __name__ == "__main__":
    unittest.main()
