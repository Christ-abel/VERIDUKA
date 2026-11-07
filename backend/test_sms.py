"""Feature-phone commands stay inside one SMS and do not rescore a shop."""

from __future__ import annotations

import unittest
from datetime import datetime

from reading import reading_lines
from thrivewave import HELP_TEXT, parse_sms_command, render_comment_sms, render_verify_sms


class Reply:
    def __init__(self, text, author="Shop"):
        self.text = text
        self.author = author


class Note:
    def __init__(self, description, *, spam=False, replies=()):
        self.description = description
        self.is_false_report = spam
        self.created_at = datetime(2026, 1, 1)
        self.replies = list(replies)


class SmsTests(unittest.TestCase):
    def test_help_and_comments_fit_in_one_sms(self):
        self.assertLessEqual(len(HELP_TEXT), 160)
        long_review = render_comment_sms(2, 8, "paid " * 80)
        self.assertLessEqual(len(long_review), 160)
        self.assertIn("Reply NEXT.", long_review)
        verify = render_verify_sms("Nairobi Tech Hub Electronics", 95, "VERIFIED_SIGNAL", "verified", True)
        self.assertLessEqual(len(verify), 160)
        self.assertIn("Text COMMENTS.", verify)

    def test_commands(self):
        self.assertEqual(parse_sms_command("COMMENTS 400200"), ("COMMENTS", "400200"))
        self.assertEqual(parse_sms_command("next"), ("NEXT", None))
        self.assertEqual(parse_sms_command("REGISTER Kayole Greens, 0711222333, 556677")[0], "REGISTER")

    def test_reader_skips_spam_and_does_not_label(self):
        lines = reading_lines(
            [
                Note("The dress never arrived after I paid the paybill."),
                Note("SCAM click here", spam=True),
                Note("Fresh sukuma arrived the same day.", replies=[Reply("Sorry about the delay.")]),
            ]
        )
        self.assertEqual(
            lines,
            [
                "The dress never arrived after I paid the paybill.",
                "Fresh sukuma arrived the same day.",
                "Shop: Sorry about the delay.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
