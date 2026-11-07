"""Social comment intake.

Two ways a comment becomes a trust signal:

1. A person pastes comments from a public post and includes the post link.
   VeriDuka classifies each comment. Nothing moves the score until that link
   is present, so a random paste cannot silently punish a shop.

2. A shop connects its own Instagram professional account through the official
   Meta Graph API. Set META_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID.
   VeriDuka then reads comments on that account's own posts. It does not log
   into Instagram, and it does not pull comments from an account that has not
   authorized the app.

WhatsApp has no public comment feed. A buyer pastes the chat, or a shop later
connects the WhatsApp Business webhook.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from classifier import classify_report
from models import Report
from scoring import utcnow

AI_TO_REPORT = {
    "SCAM": "SCAM",
    "DELAYED_DELIVERY": "NON_DELIVERY",
    "BAD_SERVICE": "POOR_SERVICE",
    "POSITIVE": "POSITIVE",
    "SPAM": "SCAM",
}

PLATFORMS = {"instagram", "facebook", "tiktok", "x", "whatsapp"}


def comment_to_report(
    *,
    vendor_id: int,
    platform: str,
    text: str,
    author_handle: str | None = None,
    permalink: str | None = None,
    external_id: str | None = None,
) -> Report:
    cleaned = " ".join(text.split())
    result = classify_report(cleaned, None)
    link = (permalink or "").strip()
    has_link = link.startswith("http://") or link.startswith("https://")
    eligible = has_link and not result.is_false_report and result.confidence >= 0.55
    verified = eligible and result.category == "POSITIVE"
    return Report(
        vendor_id=vendor_id,
        report_type=AI_TO_REPORT.get(result.category, "POOR_SERVICE"),
        ai_category=result.category,
        ai_confidence=result.confidence,
        ai_reasons=json.dumps(result.reasons),
        sentiment=result.sentiment,
        is_false_report=result.is_false_report,
        description=cleaned,
        proof_url=link or None,
        user_phone="",
        source="social",
        platform=platform,
        author_handle=(author_handle or "").lstrip("@") or None,
        permalink=link or None,
        external_id=external_id,
        verified=verified,
        score_eligible=eligible,
        resolved=False,
        created_at=utcnow(),
    )


def fetch_authorized_instagram() -> tuple[str, list[dict]]:
    """Comments on the Instagram professional account that authorized this app."""
    token = os.getenv("META_ACCESS_TOKEN", "").strip()
    account_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "").strip()
    version = os.getenv("META_GRAPH_VERSION", "v21.0").strip() or "v21.0"
    if not token or not account_id:
        raise RuntimeError(
            "Instagram is not connected. Add META_ACCESS_TOKEN and "
            "INSTAGRAM_BUSINESS_ACCOUNT_ID to .env for the shop that authorized the Meta app."
        )

    fields = "username,media.limit(8){permalink,comments.limit(25){id,text,username,timestamp}}"
    query = urllib.parse.urlencode({"fields": fields, "access_token": token})
    url = f"https://graph.facebook.com/{version}/{account_id}?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Meta Graph API refused the request ({exc.code}). {detail[:240]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not reach the Meta Graph API.") from exc

    username = str(payload.get("username") or "")
    comments: list[dict] = []
    for media in (payload.get("media") or {}).get("data") or []:
        permalink = media.get("permalink") or ""
        for comment in (media.get("comments") or {}).get("data") or []:
            text = (comment.get("text") or "").strip()
            if len(text) < 8:
                continue
            comments.append(
                {
                    "external_id": str(comment.get("id") or ""),
                    "text": text,
                    "author_handle": comment.get("username") or "",
                    "permalink": permalink,
                }
            )
    return username, comments
