"""Trust Signal Score, formula id signal-v1.

The score uses only the tools in the brief:

- the mock BRS / KRA registry on the shop (active KRA or registered BRS)
- buyer reports after the on-box classifier accepts them
- the same integer is what ThriveWave SMS reads back

It starts at 50 and moves like this:

- Government legal verification (active KRA PIN or registered BRS): +25
- Verified positive reviews: +5 each, capped at +20
- Unresolved scam reports: -20 each
- Non-delivery, delayed delivery, or poor service: -5 each
- A negative report newer than 30 days counts double

The result is clamped to 0 to 100. Praise does not get a recency bonus. Only
penalties double, so a burst of fresh complaints is louder than old ones.

Instagram, Facebook, and TikTok URLs are not inputs. A buyer opens those
pages and reads the reviews there. A comment moves this function only after
someone files it as a report and the classifier keeps it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

SERVICE_CATEGORIES = {
    "NON_DELIVERY",
    "DELAYED_DELIVERY",
    "POOR_SERVICE",
    "BAD_SERVICE",
}

BANDS = (
    (80, "VERIFIED_SIGNAL", "VERIFIED SIGNAL", "Safe to order via M-Pesa."),
        (50, "MODERATE_RISK", "MODERATE RISK", "Use pay on delivery or escrow before you send the full amount."),
    (0, "HIGH_NOISE", "HIGH NOISE / FRAUD ALERT", "High risk of a ghost vendor. Do not pay upfront."),
)


def _held(report, category: str, recent: bool) -> dict | None:
    if report.is_false_report:
        return None
    if getattr(report, "score_eligible", True) is False:
        reason = getattr(report, "ineligible_reason", None) or (
            "Saved. Add the public post link before this comment moves the score."
        )
        return {
            "points": 0,
            "counted": False,
            "category": category,
            "recent": recent,
            "reason": reason,
        }
    return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_recent(when: datetime, now: datetime) -> bool:
    return now - when < timedelta(days=30)


def category_for_score(report) -> str:
    """Prefer a confident model reading. Fall back to the reporter's label."""
    if report.is_false_report:
        return "SPAM"
    ai = (report.ai_category or "").upper()
    claimed = (report.report_type or "").upper()
    if ai == "SPAM":
        return "SPAM"
    # 0.55 is the bar for trusting the classifier over the label the buyer picked.
    # Below that, the buyer's own category stands, unless the text was spam.
    if (report.ai_confidence or 0) >= 0.55 and ai:
        return ai
    return claimed or ai or "POOR_SERVICE"


def band_for(score: int) -> tuple[str, str, str]:
    for floor, key, label, advice in BANDS:
        if score >= floor:
            return key, label, advice
    return BANDS[-1][1:]


def legally_verified(vendor) -> bool:
    return vendor.kra_status == "verified" or vendor.brs_status == "verified"


def _impact(report, now: datetime) -> dict:
    category = category_for_score(report)
    recent = is_recent(report.created_at, now)
    held = _held(report, category, recent)
    if held:
        return held

    if category == "SPAM" or report.is_false_report:
        return {
            "points": 0,
            "counted": False,
            "category": "SPAM",
            "recent": recent,
            "reason": "Excluded. The text looks like spam or an unverifiable report.",
        }

    if category == "POSITIVE":
        if not report.verified:
            return {
                "points": 0,
                "counted": False,
                "category": category,
                "recent": recent,
                "reason": "Listed, but praise needs a proof link before it moves the score.",
            }
        return {
            "points": 5,
            "counted": True,
            "in_rating": True,
            "category": category,
            "recent": recent,
            "reason": "Verified positive review.",
            "capped_positive": True,
        }

    if category == "SCAM":
        if report.resolved:
            return {
                "points": 0,
                "counted": False,
                "category": category,
                "recent": recent,
                "reason": "Scam report is marked resolved, so it no longer penalises the shop.",
            }
        points = -40 if recent else -20
        reason = "Unresolved scam report."
        if recent:
            reason = "Unresolved scam report from the last 30 days. Penalty counted twice."
        return {
            "points": points,
            "counted": True,
            "category": category,
            "recent": recent,
            "reason": reason,
        }

    if category in SERVICE_CATEGORIES:
        points = -10 if recent else -5
        reason = "Delivery or service complaint."
        if recent:
            reason = "Recent delivery or service complaint. Penalty counted twice."
        return {
            "points": points,
            "counted": True,
            "category": category,
            "recent": recent,
            "reason": reason,
        }

    return {
        "points": 0,
        "counted": False,
        "category": category,
        "recent": recent,
        "reason": "This category does not move the score.",
    }


def score_vendor(vendor, reports, now: datetime | None = None) -> dict:
    now = now or utcnow()
    legal_points = 25 if legally_verified(vendor) else 0
    impacts: dict[int, dict] = {}
    positive_ids: list[int] = []

    for report in reports:
        impact = _impact(report, now)
        impacts[report.id] = impact
        if impact.get("capped_positive"):
            positive_ids.append(report.id)

    positive_ids.sort(key=lambda report_id: next(r.created_at for r in reports if r.id == report_id))
    budget = 20
    for report_id in positive_ids:
        grant = min(5, budget)
        budget -= grant
        impacts[report_id]["points"] = grant
        impacts[report_id]["in_rating"] = True
        if grant == 0:
            impacts[report_id]["counted"] = False
            impacts[report_id]["reason"] = "Verified praise, past the +20 review cap."

    positive_points = sum(item["points"] for item in impacts.values() if item["category"] == "POSITIVE")
    scam_points = 0
    service_points = 0
    for impact in impacts.values():
        if not impact["counted"]:
            continue
        if impact["category"] == "SCAM":
            scam_points += impact["points"]
        elif impact["category"] in SERVICE_CATEGORIES:
            service_points += impact["points"]

    raw = 50 + legal_points + positive_points + scam_points + service_points
    score = max(0, min(100, raw))
    band, label, advice = band_for(score)

    positive_count = sum(1 for item in impacts.values() if item["category"] == "POSITIVE" and item.get("in_rating"))
    scam_count = sum(1 for item in impacts.values() if item["counted"] and item["category"] == "SCAM")
    service_count = sum(1 for item in impacts.values() if item["counted"] and item["category"] in SERVICE_CATEGORIES)
    false_count = sum(1 for item in impacts.values() if item["category"] == "SPAM")
    service_total = positive_count + scam_count + service_count

    if service_total == 0:
        stars = None
        positive_pct = None
    else:
        weighted = positive_count * 5 + service_count * 2 + scam_count * 1
        stars = round(weighted / service_total, 1)
        positive_pct = round(100 * positive_count / service_total)

    notes: list[str] = []
    if legal_points:
        notes.append("A government registry match is on file (+25).")
    elif vendor.kra_status == "pending" or vendor.brs_status == "pending":
        notes.append("Registration is still pending, so the legal bonus is not applied.")
    else:
        notes.append("No active KRA PIN or BRS registration is linked to this shop.")
    if positive_count:
        notes.append(f"{positive_count} verified buyer review{'s' if positive_count != 1 else ''} (+{positive_points}, cap 20).")
    if scam_count:
        notes.append(f"{scam_count} unresolved scam report{'s' if scam_count != 1 else ''} ({scam_points}).")
    if service_count:
        notes.append(f"{service_count} delivery or service complaint{'s' if service_count != 1 else ''} ({service_points}).")
    if false_count:
        notes.append(f"{false_count} report{'s' if false_count != 1 else ''} set aside as spam or unverifiable.")
    if raw != score:
        notes.append("The raw total sits outside 0 to 100 and is clamped for the gauge.")

    return {
        "formula": "signal-v1",
        "score": score,
        "raw": raw,
        "band": band,
        "label": label,
        "advice": advice,
        "base": 50,
        "legal_points": legal_points,
        "positive_points": positive_points,
        "scam_points": scam_points,
        "service_points": service_points,
        "positive_count": positive_count,
        "scam_count": scam_count,
        "service_count": service_count,
        "false_count": false_count,
        "notes": notes,
        "impacts": impacts,
        "service_rating": {
            "stars": stars,
            "positive_pct": positive_pct,
            "counts": {
                "positive": positive_count,
                "scam": scam_count,
                "service": service_count,
                "excluded": false_count,
            },
        },
    }
