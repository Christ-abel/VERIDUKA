"""AI review: parsing and the fallbacks. No network."""

from __future__ import annotations

import io
import json
import unittest
from unittest import mock

import ai_review

SHOP = {"nickname": "Shop", "handle": "shop", "bio": ""}
COMMENTS = [{"text": "Walinichukua pesa yangu, matapeli"}, {"text": "price?"}]


def fake_response(content):
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
    response = mock.MagicMock()
    response.read.return_value = body
    response.__enter__.return_value = response
    return response


class ReviewTest(unittest.TestCase):
    def test_no_key_means_no_review(self):
        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}):
            self.assertIsNone(ai_review.review_comments(SHOP, COMMENTS))

    def test_parses_json_inside_a_code_fence_and_drops_bad_rows(self):
        content = (
            "```json\n"
            '{"overall": "Do not pay upfront.", "comments": ['
            '{"i": 0, "category": "scam", "confidence": 1.7, "describes_order": true, "reason": "took money"},'
            '{"i": 1, "category": "NEUTRAL", "confidence": 0.9, "describes_order": false, "reason": "question"},'
            '{"i": 7, "category": "SCAM", "confidence": 0.9},'
            '{"i": 1, "category": "MADE_UP", "confidence": 0.9}]}\n```'
        )
        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "k"}), mock.patch("urllib.request.urlopen", return_value=fake_response(content)):
            out = ai_review.review_comments(SHOP, COMMENTS)
        self.assertEqual(out["overall"], "Do not pay upfront.")
        self.assertEqual(out["reviews"][0]["category"], "SCAM")
        self.assertEqual(out["reviews"][0]["confidence"], 1.0)
        self.assertEqual(out["reviews"][1]["category"], "NEUTRAL")
        self.assertNotIn(7, out["reviews"])

    def test_sends_comments_as_data_with_the_configured_model(self):
        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["body"] = json.loads(request.data.decode())
            return fake_response('{"overall": "", "comments": []}')

        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "k", "OPENROUTER_MODEL": "some/model"}), mock.patch("urllib.request.urlopen", fake_urlopen):
            ai_review.review_comments(SHOP, COMMENTS)
        self.assertEqual(captured["body"]["model"], "some/model")
        self.assertIn("untrusted", captured["body"]["messages"][0]["content"])
        self.assertIn("0. Walinichukua", captured["body"]["messages"][1]["content"])

    def test_failure_or_garbage_returns_none(self):
        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "k"}):
            with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
                self.assertIsNone(ai_review.review_comments(SHOP, COMMENTS))
            with mock.patch("urllib.request.urlopen", return_value=fake_response("sorry, I cannot")):
                self.assertIsNone(ai_review.review_comments(SHOP, COMMENTS))


if __name__ == "__main__":
    unittest.main()
