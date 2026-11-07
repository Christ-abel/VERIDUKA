"""Optional social comment intake.

The prototype UI does not depend on this module. Shops expose Instagram,
Facebook, and TikTok as public links, and the buyer reads those reviews on
the platform. The trust score stays on the registry and on buyer reports.

Two optional paths remain for a later deployment that has credentials:

1. A person pastes comments from a public post and includes the post link.
   Nothing moves the score until that link is present.

2. A shop connects its own Instagram professional account through the official
   Meta Graph API. Set META_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID.
   VeriDuka then reads comments on that account's own posts. It does not log
   into Instagram, and it does not pull comments from an account that has not
   authorized the app.

WhatsApp has no public comment feed. A shop can connect its own WhatsApp Business
number. Messages reach VeriDuka only through that shop's webhook, and only for
a number the shop has connected. Private chats are never scraped.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
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


URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def first_link(text: str) -> str | None:
    """A WhatsApp message has no permalink. Use a link the sender included, if any."""
    match = URL_IN_TEXT.search(text or "")
    return match.group(0).rstrip(".,)") if match else None


def valid_whatsapp_signature(raw_body: bytes, header: str | None) -> bool:
    """Check Meta's X-Hub-Signature-256. With no WHATSAPP_APP_SECRET set, signing is skipped."""
    secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    if not secret:
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def parse_whatsapp_messages(payload: dict) -> list[dict]:
    """Flatten a WhatsApp Cloud API webhook into text messages tagged with the receiving number id."""
    messages: list[dict] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            number_id = str((value.get("metadata") or {}).get("phone_number_id") or "")
            for message in value.get("messages") or []:
                if message.get("type") != "text":
                    continue
                body = ((message.get("text") or {}).get("body") or "").strip()
                if not number_id or not body:
                    continue
                messages.append(
                    {
                        "phone_number_id": number_id,
                        "external_id": str(message.get("id") or ""),
                        "sender": str(message.get("from") or ""),
                        "text": body,
                    }
                )
    return messages
