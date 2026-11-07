"""Plain review text for someone who cannot open TikTok, Instagram, or Facebook.

A feature phone, or the Public pages reader, walks these lines one at a time.
This module does not call the classifier and does not change the trust score.
Spam that was already set aside stays out of the reader so a handset is not
sent a link blast. Everything else is shown as written, including a shop reply.
"""

from __future__ import annotations


def reading_lines(reports) -> list[str]:
    ordered = sorted(reports, key=lambda report: report.created_at)
    lines: list[str] = []
    for report in ordered:
        if report.is_false_report:
            continue
        text = " ".join((report.description or "").split())
        if len(text) < 8:
            continue
        lines.append(text)
        for reply in list(getattr(report, "replies", None) or []):
            answer = " ".join((reply.text or "").split())
            if answer:
                who = " ".join((reply.author or "Shop").split()) or "Shop"
                lines.append(f"{who}: {answer}")
    return lines
