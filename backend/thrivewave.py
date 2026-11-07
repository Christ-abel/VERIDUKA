"""ThriveWave SMS gateway wrapper.

`ThriveWaveClient.dispatch` builds the provider payload and, unless
THRIVEWAVE_LIVE=true, returns a mock acceptance receipt. The webhook in
main.py uses `parse_sms_command` and `render_verify_sms` so inbound
"VERIFY 400200" texts and outbound replies share one format.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass


HELP_TEXT = (
    "VeriDuka: VERIFY paybill checks a shop. COMMENTS paybill reads reviews. "
    "NEXT for the next one. REGISTER Name, 07..., paybill."
)
SWAHILI_HELP_TEXT = (
    "VeriDuka: VERIFY paybill kuthibitisha duka. COMMENTS paybill kusoma maoni. "
    "NEXT maoni yanayofuata. REGISTER jina, simu, paybill."
)
UNKNOWN_TEXT = "VeriDuka: Send HELP, VERIFY 400200, COMMENTS 400200, or NEXT."
REGISTER_USAGE = "VeriDuka: REGISTER Name, 07..., paybill. Example: REGISTER Kayole Greens, 0711222333, 556677"

SWAHILI_MARKERS = (
    "tafadhali",
    "asante",
    "msaada",
    "nisaidie",
    "naomba",
    "nime",
    "nilituma",
    "nililipia",
    "pesa",
    "mzigo",
    "bidhaa",
    "duka",
    "imefika",
    "haijafika",
    "imechelewa",
    "sijapokea",
    "sijapata",
    "ameniblock",
    "alichukua",
    "huduma",
    "nzuri",
    "mbaya",
    "bei",
)


def is_swahili_sms(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in SWAHILI_MARKERS)


@dataclass
class DispatchResult:
    to: str
    sender_id: str
    text: str
    status: str
    provider_ref: str
    endpoint: str

    def as_dict(self) -> dict:
        return {
            "to": self.to,
            "sender_id": self.sender_id,
            "text": self.text,
            "status": self.status,
            "provider_ref": self.provider_ref,
            "endpoint": self.endpoint,
        }


class ThriveWaveClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("THRIVEWAVE_API_URL", "https://api.thrivewave.mock/v1").rstrip("/")
        self.api_key = os.getenv("THRIVEWAVE_API_KEY", "tw_test_mock")
        self.sender_id = os.getenv("THRIVEWAVE_SENDER_ID", "VERIDUKA")
        self.live = os.getenv("THRIVEWAVE_LIVE", "false").lower() in {"1", "true", "yes"}

    def dispatch(self, to: str, text: str) -> DispatchResult:
        destination = normalize_msisdn(to)
        payload = {
            "sender_id": self.sender_id,
            "to": destination,
            "message": text,
            "callback_url": os.getenv("THRIVEWAVE_CALLBACK_URL", ""),
        }
        endpoint = f"{self.base_url}/messages"
        provider_ref = "tw_" + uuid.uuid4().hex[:12]

        if not destination:
            return DispatchResult(destination, self.sender_id, text, "skipped", provider_ref, endpoint)

        if not self.live:
            return DispatchResult(destination, self.sender_id, text, "mocked", provider_ref, endpoint)

        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
            ref = str(body.get("id") or body.get("message_id") or provider_ref)
            return DispatchResult(destination, self.sender_id, text, "sent", ref, endpoint)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return DispatchResult(destination, self.sender_id, text, "failed", provider_ref, endpoint)


def normalize_msisdn(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    if digits.startswith("254") and len(digits) == 12:
        return digits
    return ""


def parse_sms_command(text: str) -> tuple[str, str | None]:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return "EMPTY", None
    if re.fullmatch(r"(?:help(?:\s+tafadhali)?|msaada|nisaidie|naomba msaada)", cleaned, re.IGNORECASE):
        return "HELP", None
    if re.fullmatch(r"next|more", cleaned, re.IGNORECASE):
        return "NEXT", None
    for name, pattern in (
        ("VERIFY", r"verify\s+(.+)"),
        ("COMMENTS", r"comments\s+(.+)"),
        ("REGISTER", r"register\s+(.+)"),
    ):
        match = re.fullmatch(pattern, cleaned, re.IGNORECASE)
        if match:
            argument = match.group(1).strip()
            if name == "VERIFY":
                argument = re.sub(r"[, ]+\s*(?:tafadhali|asante)[.!?]*$", "", argument, flags=re.IGNORECASE)
            return name, argument
    return "UNKNOWN", cleaned


def render_verify_sms(
    name: str,
    score: int,
    band: str,
    legal_state: str,
    has_comments: bool = False,
    swahili: bool = False,
) -> str:
    if swahili:
        advice = {
            "VERIFIED_SIGNAL": "Ni salama kulipa.",
            "MODERATE_RISK": "Lipa bidhaa ikifika.",
            "HIGH_NOISE": "USILIPIE mapema.",
        }.get(band, "Kagua till kabla ya kulipa.")
        label = {
            "VERIFIED_SIGNAL": "IMETHIBITISHWA",
            "MODERATE_RISK": "HATARI YA KATI",
            "HIGH_NOISE": "TAHADHARI YA UTAPELI",
        }.get(band, band)
        legal_bit = {
            "verified": "KRA/BRS imelingana.",
            "pending": "BRS inasubiriwa.",
        }.get(legal_state, "Hakuna ulinganifu wa KRA/BRS.")
        extra = " Tuma COMMENTS." if has_comments else ""
        suffix = f" yupo kwenye rekodi. {score}% {label}. {legal_bit} {advice}{extra}"
        prefix = "VeriDuka: "
        room = 160 - len(prefix) - len(suffix)
        shown = name if len(name) <= room else (name[: max(0, room - 3)].rstrip() + "...")
        return f"{prefix}{shown}{suffix}"[:160]

    advice = {
        "VERIFIED_SIGNAL": "Safe to pay.",
        "MODERATE_RISK": "Use pay on delivery.",
        "HIGH_NOISE": "Do NOT pay upfront.",
    }.get(band, "Check the till before you pay.")
    label = {
        "VERIFIED_SIGNAL": "VERIFIED SIGNAL",
        "MODERATE_RISK": "MODERATE RISK",
        "HIGH_NOISE": "FRAUD ALERT",
    }.get(band, band)
    legal_bit = {
        "verified": "KRA/BRS match.",
        "pending": "BRS pending.",
    }.get(legal_state, "No KRA/BRS match.")
    extra = " Text COMMENTS." if has_comments else ""
    suffix = f". {score}% {label}. {legal_bit} {advice}{extra}"
    prefix = "VeriDuka: "
    room = 160 - len(prefix) - len(suffix)
    shown = name if len(name) <= room else (name[: max(0, room - 3)].rstrip() + "...")
    text = f"{prefix}{shown}{suffix}"
    return text[:160]


def render_comment_sms(index: int, total: int, text: str) -> str:
    """One review, no score and no category. index is 1-based. Stays within 160 characters."""
    prefix = f"VeriDuka {index}/{total}: "
    suffix = " Reply NEXT." if index < total else " End."
    room = 160 - len(prefix) - len(suffix)
    shown = text if len(text) <= room else text[: max(0, room - 3)].rstrip() + "..."
    return f"{prefix}{shown}{suffix}"[:160]


def render_register_sms(name: str, paybill: str | None) -> str:
    where = f" Paybill {paybill}." if paybill else ""
    text = f"VeriDuka: {name} is on file.{where} Score 50%. No KRA/BRS yet. Text VERIFY then the paybill."
    return text[:160]


def render_unknown_sms(query: str) -> str:
    shown = " ".join(query.split())
    if len(shown) > 40:
        shown = shown[:37] + "..."
    text = f"VeriDuka: No trusted record for {shown}. Unverified noise. Do not pay upfront."
    return text[:160]
