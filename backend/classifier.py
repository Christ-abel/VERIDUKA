"""Pattern detection for unstructured buyer reports.

Cursor wrote this detector for the Zinduathon brief ("Cursor AI powered"
pattern detection). The API runs it on the server for every report. It does
not call Cursor, and it does not call another model, so the same text always
gets the same label.

It looks for a transaction narrative (channel + outcome), scores category
phrases in English and Swahili, and separates spam or thin accusations from
reports that describe a real order. Categories are SCAM, DELAYED_DELIVERY,
BAD_SERVICE, POSITIVE, and SPAM.

Swap `classify_report` for a hosted model later. The rest of the app only
depends on the Classification shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SCAM_PHRASES = (
    "blocked me",
    "ghost shop",
    "fake paybill",
    "took my money",
    "disappeared",
    "this is a scam",
    "nothing was delivered",
    "wrong till",
    "ameniblock",
    "aliniblock",
    "wameniblock",
    "ni tapeli",
    "amekula pesa zangu",
    "alichukua pesa zangu",
    "hakutuma bidhaa",
    "mzigo haukuwasili",
    "amepotea na pesa",
    "amezima simu",
)

DELAY_PHRASES = (
    "still waiting",
    "not arrived",
    "have not arrived",
    "rider is on the way",
    "delayed",
    "days late",
    "late delivery",
    "never came",
    "bado nasubiri",
    "bado sijapokea",
    "haijafika",
    "imechelewa kufika",
    "delivery imechelewa",
    "sijapata mzigo",
    "mzigo bado",
    "rider ako njiani",
    "imechukua siku",
)

SERVICE_PHRASES = (
    "rude",
    "poor quality",
    "damaged",
    "wrong item",
    "bad service",
    "ignored my calls",
    "refused a refund",
    "broken on arrival",
    "huduma mbaya",
    "ubora mbaya",
    "bidhaa imeharibika",
    "amenitumia tofauti",
    "hawajibu simu",
    "hanijibu",
    "alikuwa mkali",
    "walikataa kurejesha pesa",
    "bei ilikuwa tofauti",
)

POSITIVE_PHRASES = (
    "would buy again",
    "recommend",
    "legit",
    "genuine",
    "fast delivery",
    "well packed",
    "fair price",
    "answered the phone",
    "authentic",
    "same afternoon",
    "thank you",
    "arrived the next day",
    "nitanunua tena",
    "nawapendekeza",
    "huduma nzuri",
    "bei poa",
    "imefika haraka",
    "imefungwa vizuri",
    "bidhaa halisi",
    "asante sana",
    "mzigo umefika",
    "nitawatumia tena",
)

SPAM_PHRASES = (
    "bonyeza hapa",
    "umeshinda zawadi",
    "pata airtime bure",
    "shinda airtime",
    "tuma kwa whatsapp",
    "link ya zawadi",
    "jibu ndio ushinde",
)

CATEGORY_LABELS = {
    "SCAM": "Scam",
    "DELAYED_DELIVERY": "Delayed delivery",
    "BAD_SERVICE": "Bad service",
    "POSITIVE": "Positive experience",
    "SPAM": "Spam / false report",
}

CLAIMED_TO_AI = {
    "SCAM": "SCAM",
    "NON_DELIVERY": "DELAYED_DELIVERY",
    "POOR_SERVICE": "BAD_SERVICE",
    "POSITIVE": "POSITIVE",
}


@dataclass
class Classification:
    category: str
    confidence: float
    sentiment: str
    is_false_report: bool
    reasons: list[str] = field(default_factory=list)
    summary: str = ""

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "label": CATEGORY_LABELS.get(self.category, self.category),
            "confidence": self.confidence,
            "sentiment": self.sentiment,
            "is_false_report": self.is_false_report,
            "reasons": self.reasons,
            "summary": self.summary,
        }


def _hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    found = []
    for phrase in phrases:
        if phrase in text:
            found.append(phrase)
    return found


def _caps_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if ch.isupper()) / len(letters)


def _has_narrative(text: str) -> bool:
    channel = re.search(r"\b(paybill|m-?pesa|mpesa|till|whatsapp|instagram|rider|courier)\b", text)
    outcome = re.search(
        r"\b(blocked|delivered|waiting|arrived|refund|delayed|late|haijafika|"
        r"sijapokea|sijapata|imechelewa|ameniblock|aliniblock|amekula|alichukua)\b",
        text,
    )
    amount = re.search(r"\b\d{3,6}\b", text)
    return bool(channel and outcome) or bool(amount and outcome)


def _sentiment(category: str) -> str:
    if category == "POSITIVE":
        return "positive"
    if category == "SPAM":
        return "neutral"
    return "negative"


def _summary(category: str, confidence: float, is_false: bool) -> str:
    label = CATEGORY_LABELS.get(category, category)
    if is_false:
        return "This looks like spam or a report without a verifiable order. It will be kept and excluded from the trust score."
    percent = int(round(confidence * 100))
    return f"Reads as {label.lower()} with {percent}% pattern confidence."


def classify_report(text: str, claimed_type: str | None = None) -> Classification:
    raw = (text or "").strip()
    lower = re.sub(r"\s+", " ", raw.lower())
    reasons: list[str] = []

    scam = _hits(lower, SCAM_PHRASES)
    delay = _hits(lower, DELAY_PHRASES)
    service = _hits(lower, SERVICE_PHRASES)
    positive = _hits(lower, POSITIVE_PHRASES)
    spam = _hits(lower, SPAM_PHRASES)
    scores = {
        "SCAM": len(scam),
        "DELAYED_DELIVERY": len(delay),
        "BAD_SERVICE": len(service),
        "POSITIVE": len(positive),
    }
    for phrase in scam:
        reasons.append(f"Scam signal: “{phrase}”.")
    for phrase in delay:
        reasons.append(f"Delivery signal: “{phrase}”.")
    for phrase in service:
        reasons.append(f"Service signal: “{phrase}”.")
    for phrase in positive:
        reasons.append(f"Positive signal: “{phrase}”.")

    lure = bool(re.search(r"bit\.ly|tinyurl|free airtime|click here|you won|whatsapp this link", lower))
    if spam:
        reasons.append(f"Spam signal: “{spam[0]}”.")
    stuffing = bool(re.search(r"(?:scam[\s!.,]*){3,}", lower))
    extortion = bool(re.search(r"pay me|i will delete|i'll delete|remove this review|compensate me", lower))
    narrative = _has_narrative(lower)
    too_short = len(raw) < 28
    shouting = _caps_ratio(raw) > 0.6 and len(raw) > 12

    if lure:
        reasons.append("Spam signal: shortened link or airtime lure.")
    if stuffing:
        reasons.append("Spam signal: the word scam is repeated without a story.")
    if extortion:
        reasons.append("Spam signal: the text asks for payment to change a review.")
    if too_short:
        reasons.append("Thin report: not enough detail to check an order.")
    if shouting:
        reasons.append("Low-information burst of capital letters.")
    if narrative:
        reasons.append("Contains a transaction narrative.")

    priority = ("SCAM", "DELAYED_DELIVERY", "BAD_SERVICE", "POSITIVE")
    best = max(priority, key=lambda key: scores[key])
    best_score = scores[best]
    hard_spam = lure or bool(spam) or stuffing or extortion or ((too_short or shouting) and not narrative)
    strong_real_complaint = narrative and best_score >= 2 and best != "POSITIVE"

    if hard_spam and not strong_real_complaint:
        category = "SPAM"
        is_false = True
        confidence = min(
            0.96,
            0.62 + 0.08 * sum(1 for flag in (lure, bool(spam), stuffing, extortion, too_short, shouting) if flag),
        )
    elif best_score == 0:
        category = CLAIMED_TO_AI.get((claimed_type or "").upper(), "BAD_SERVICE")
        is_false = too_short and not narrative
        confidence = 0.42
        reasons.append("No strong phrase match. The reporter's category is kept at low confidence.")
    else:
        category = best
        is_false = False
        confidence = min(0.97, 0.5 + 0.1 * best_score)

    if scores["POSITIVE"] >= 2 and scores["SCAM"] >= 2:
        reasons.append("The text praises the shop and calls it a scam. Treated as unreliable.")
        category = "SPAM"
        is_false = True
        confidence = max(confidence, 0.8)

    confidence = round(confidence, 2)
    return Classification(
        category=category,
        confidence=confidence,
        sentiment=_sentiment(category),
        is_false_report=is_false,
        reasons=reasons,
        summary=_summary(category, confidence, is_false),
    )
