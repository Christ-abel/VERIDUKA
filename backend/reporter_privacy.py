"""Privacy-preserving reporter phone helpers."""

from __future__ import annotations

import hashlib
import re


def canonical_reporter_phone(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        return "254" + digits[1:]
    if len(digits) == 9 and digits.startswith("7"):
        return "254" + digits
    return None


def reporter_fingerprint(value: str | None) -> str | None:
    phone = canonical_reporter_phone(value)
    if phone is None:
        return None
    return hashlib.sha256(phone.encode("ascii")).hexdigest()


def masked_reporter_phone(value: str | None) -> str:
    phone = canonical_reporter_phone(value)
    if phone is None:
        return "hidden"
    local = "0" + phone[3:]
    return f"{local[:2]}****{local[-2:]}"
