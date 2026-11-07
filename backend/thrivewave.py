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


HELP_TEXT = "VeriDuka: Text VERIFY then a paybill, phone, @handle, or KRA PIN. Example: VERIFY 400200"
UNKNOWN_TEXT = "VeriDuka: Send HELP or VERIFY <paybill|phone|@handle|KRA PIN>."


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
    if re.fullmatch(r"help", cleaned, re.IGNORECASE):
        return "HELP", None
    match = re.fullmatch(r"verify\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return "VERIFY", match.group(1).strip()
    return "UNKNOWN", cleaned


def render_verify_sms(name: str, score: int, band: str, legal_state: str) -> str:
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
    suffix = f". {score}% {label}. {legal_bit} {advice}"
    prefix = "VeriDuka: "
    room = 160 - len(prefix) - len(suffix)
    shown = name if len(name) <= room else (name[: max(0, room - 3)].rstrip() + "...")
    text = f"{prefix}{shown}{suffix}"
    return text[:160]


def render_unknown_sms(query: str) -> str:
    shown = " ".join(query.split())
    if len(shown) > 40:
        shown = shown[:37] + "..."
    text = f"VeriDuka: No trusted record for {shown}. Unverified noise. Do not pay upfront."
    return text[:160]
