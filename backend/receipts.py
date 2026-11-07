"""One M-Pesa confirmation code can support one shop.

Buyers paste the Safaricom SMS into a report. The code in that message
(for example QK72H8L9P0) is hashed with SHA-256 and stored on the report.
The raw code is not given its own column or API field.

The first saved report owns the hash and can still move the score. A later
report that carries the same code is kept on file, marked ineligible, and
left out of the score. That stops one screenshot from being filed under
several ghost shops, and it stops the same receipt from being counted twice
on one shop.
"""

from __future__ import annotations

import hashlib
import re

from models import Report

# A labeled code is the reliable case: "confirmation code QK72H8L9P0".
LABELED_CODE = re.compile(
    r"(?:confirmation|m-?pesa|transaction|receipt)\s*(?:code|id|no\.?|number)?\s*[:#\-]?\s*([A-Za-z0-9]{8,12})\b",
    re.IGNORECASE,
)
# A bare Safaricom code leads the SMS: "QK72H8L9P0 Confirmed. ..."
# It starts with a letter, is 10 characters, and contains a digit, so a
# phone number or an ordinary word is not treated as a receipt.
STANDALONE_CODE = re.compile(r"\b([A-Z][A-Z0-9]{9})\b")

OTHER_SHOP = (
    "This M-Pesa confirmation code is already tied to another shop, "
    "so this report stays on file and does not move the score."
)
SAME_SHOP = (
    "This M-Pesa confirmation code is already on file for this shop, "
    "so this copy does not move the score."
)


def _mixed(token: str) -> bool:
    return any(character.isalpha() for character in token) and any(character.isdigit() for character in token)


def extract_confirmation_code(text: str) -> str | None:
    """Return the first M-Pesa confirmation code in a pasted receipt, or None."""
    if not text:
        return None
    for match in LABELED_CODE.finditer(text):
        token = match.group(1).upper()
        if _mixed(token):
            return token
    for match in STANDALONE_CODE.finditer(text.upper()):
        token = match.group(1)
        if _mixed(token):
            return token
    return None


def receipt_hash(code: str) -> str:
    """SHA-256 of the normalised code. Callers store this, not the code."""
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def attach_receipt(db, report: Report, seen: dict[str, int] | None = None) -> None:
    """Hash a code found in the report. A code that already has an owner does not score.

    `seen` tracks codes claimed earlier in the same request, before they are
    committed. The value is the vendor id that owns the code.
    """
    code = extract_confirmation_code(report.description or "")
    if code is None:
        return
    digest = receipt_hash(code)
    report.receipt_hash = digest

    owner_vendor: int | None = None
    if seen is not None and digest in seen:
        owner_vendor = seen[digest]
    else:
        owner = db.query(Report).filter(Report.receipt_hash == digest).order_by(Report.id.asc()).first()
        if owner is not None:
            owner_vendor = owner.vendor_id

    if seen is not None and digest not in seen:
        seen[digest] = report.vendor_id if owner_vendor is None else owner_vendor

    if owner_vendor is None:
        return

    report.score_eligible = False
    report.verified = False
    report.ineligible_reason = OTHER_SHOP if owner_vendor != report.vendor_id else SAME_SHOP
