"""ThriveVas SMS gateway wrapper.

`dispatch` follows https://docs.thrivevas.com/ Send Single SMS:
POST https://sms.thrivevas.com/v1/message/send with the key in x-api-key.
Unless THRIVEWAVE_LIVE=true, it returns a mock receipt and does not call ThriveVas.
The webhook in main.py uses `parse_sms_command` and `render_verify_sms` so inbound
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

    def _load_settings(self) -> None:
        """Read .env on each send so a new gateway URL is used without a restart."""
        try:
            from dotenv import load_dotenv
            from pathlib import Path

            root = Path(__file__).resolve().parent.parent / ".env"
            load_dotenv(root, override=True)
        except ImportError:
            pass
        self.api_key = os.getenv("THRIVEVAS_API_KEY", "").strip() or os.getenv("THRIVEWAVE_API_KEY", "tw_test_mock")
        self.sender_id = os.getenv("THRIVEVAS_SENDER_ID", "ThriveVas").strip() or "ThriveVas"
        self.live = os.getenv("THRIVEWAVE_LIVE", "false").lower() in {"1", "true", "yes"}

    def dispatch(self, to: str, text: str) -> DispatchResult:
        """Send one SMS the way https://docs.thrivevas.com/ describes Send Single SMS."""
        self._load_settings()
        destination = normalize_msisdn(to)
        endpoint = os.getenv("THRIVEVAS_SMS_URL", "https://sms.thrivevas.com/v1/message/send").strip()
        provider_ref = "tv_" + uuid.uuid4().hex[:12]
        sender = self.sender_id or "ThriveVas"

        if not destination:
            return DispatchResult(destination, sender, text, "skipped", provider_ref, endpoint)

        key_ready = bool(self.api_key) and self.api_key != "tw_test_mock"
        if not self.live or not key_ready:
            return DispatchResult(destination, sender, text, "mocked", provider_ref, endpoint)

        payload = {"message": text, "msisdn": f"+{destination}", "sender_id": sender}
        callback = os.getenv("THRIVEWAVE_CALLBACK_URL", "").strip()
        if callback:
            payload["callback_url"] = callback
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
            return _thrivevas_result(destination, sender, text, endpoint, raw, provider_ref)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:180]
            return DispatchResult(destination, sender, text, "failed", _safe(detail) or f"HTTP {exc.code}", endpoint)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            reason = str(getattr(exc, "reason", exc))[:160]
            return DispatchResult(destination, sender, text, "failed", _safe(reason) or provider_ref, endpoint)


def _safe(text: str) -> str:
    cleaned = re.sub(r"(apiKey|apikey|api_key)[\"']?\s*[:=]\s*\S+", "apiKey=[hidden]", text or "", flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _thrivevas_result(destination: str, sender: str, text: str, endpoint: str, raw: str, fallback: str) -> DispatchResult:
    """ThriveVas queues a message with status 200 and a transaction_id."""
    try:
        body = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return DispatchResult(destination, sender, text, "failed", _safe(raw)[:160] or fallback, endpoint)
    code = int(body.get("status") or 0)
    if code == 200:
        ref = str(body.get("transaction_id") or body.get("message") or fallback)
        return DispatchResult(destination, sender, text, "sent", _safe(ref)[:160], endpoint)
    reason = str(body.get("message") or body.get("status") or "ThriveVas rejected the SMS")
    return DispatchResult(destination, sender, text, "failed", _safe(reason)[:160], endpoint)


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
