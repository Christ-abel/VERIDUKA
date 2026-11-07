"""VeriDuka API: search, trust profiles, buyer reports, registry checks, SMS.

The score on every response comes from scoring.signal-v1: the mock BRS/KRA
registry plus buyer reports the classifier accepted. ThriveWave SMS returns
that same integer. Instagram, Facebook, and TikTok are profile links on the
shop so a buyer can read those reviews themselves. This prototype does not
call Meta or TikTok.
"""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from classifier import CATEGORY_LABELS, classify_report
from daraja import DarajaClient, DarajaError, daraja_credentials_configured, registered_names_match
from database import (
    EXACT_FIELDS,
    AmbiguousIdentifier,
    DuplicateShop,
    SessionLocal,
    create_registered_vendor,
    get_db,
    handle_of,
    init_db,
    resolve_identifier,
    search_vendors,
    utcnow,
)
from models import OfficialRecord, Report, ReportReply, SmsCursor, SmsLog, Vendor
from schemas import (
    canonical_phone,
    ClassifyIn,
    ClassifyOut,
    LegalIn,
    LegalOut,
    OfficialOut,
    ProfileLink,
    ReportCreated,
    ReplyIn,
    ReplyOut,
    ReportIn,
    ReportOut,
    ResolveIn,
    ReadingOut,
    ScoreOut,
    SearchOut,
    SmsOut,
    SocialImportIn,
    SocialImportOut,
    SocialSyncOut,
    TikTokClaimIn,
    TikTokLookupIn,
    TikTokLookupOut,
    TikTokMatchOut,
    VendorCard,
    VendorDetail,
    VendorRegisterIn,
    WhatsAppConnectIn,
    WhatsAppConnectOut,
    WhatsAppWebhookOut,
)
from reading import reading_lines
from receipts import attach_receipt
from scoring import legally_verified, score_vendor
import tiktok as tiktok_lookup
from social import comment_to_report, fetch_authorized_instagram, first_link, parse_whatsapp_messages, valid_whatsapp_signature
from thrivewave import (
    HELP_TEXT,
    REGISTER_USAGE,
    UNKNOWN_TEXT,
    SWAHILI_HELP_TEXT,
    ThriveWaveClient,
    is_swahili_sms,
    normalize_msisdn,
    parse_sms_command,
    render_comment_sms,
    render_register_sms,
    render_unknown_sms,
    render_verify_sms,
)

logger = logging.getLogger("veriduka")
sms_client = ThriveWaveClient()

LABELS = {
    **CATEGORY_LABELS,
    "NON_DELIVERY": "Non-delivery",
    "POOR_SERVICE": "Poor service",
}

STOP_WORDS = {
    "limited",
    "ltd",
    "kenya",
    "the",
    "and",
    "co",
    "company",
    "enterprises",
    "organic",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    init_db()
    yield


app = FastAPI(
    title="VeriDuka",
    version="1.0.0",
    summary="Signal-based merchant verification for Kenyan online shops.",
    description=(
        "Search a paybill, phone, social handle, KRA PIN, or shop name. "
        "The trust score uses the mock BRS/KRA registry and buyer reports the classifier accepted. "
        "ThriveWave SMS returns the same number. "
        "Instagram, Facebook, and TikTok are links the buyer opens. This prototype does not call those APIs."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def display_phone(stored: str | None) -> str | None:
    if not stored:
        return None
    if stored.startswith("254") and len(stored) == 12:
        return "0" + stored[3:]
    return stored


def mask_phone(stored: str) -> str:
    local = display_phone(stored) or stored
    if len(local) < 6:
        return "hidden"
    return f"{local[:2]}****{local[-2:]}"


def iso(value) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def legal_state(vendor: Vendor) -> str:
    if legally_verified(vendor):
        return "verified"
    if vendor.kra_status == "pending" or vendor.brs_status == "pending":
        return "pending"
    return "unverified"


def profile_links(vendor: Vendor) -> dict[str, ProfileLink]:
    """Build the pages a buyer can open. Handles stay on the shop. URLs are derived.

    The prototype has no Meta or TikTok token, so these links are the social
    feature. Opening one does not change the trust score.
    """
    links: dict[str, ProfileLink] = {}
    instagram = handle_of(vendor.instagram)
    if instagram:
        links["instagram"] = ProfileLink(handle=instagram, url=f"https://www.instagram.com/{instagram}/")
    facebook = (vendor.facebook or "").strip().strip("/")
    if facebook:
        links["facebook"] = ProfileLink(handle=facebook, url=f"https://www.facebook.com/{facebook}")
    tiktok = handle_of(vendor.tiktok)
    if tiktok:
        links["tiktok"] = ProfileLink(handle=tiktok, url=f"https://www.tiktok.com/@{tiktok}")
    return links


def badges_for(vendor: Vendor) -> dict:
    """M-Pesa Verified is a till-name match, not a point on the trust score.

    With no Daraja keys, the seeded flag stands. With keys, the badge stays
    on only after a lookup stored a till name that matches the KRA/BRS entity.
    """
    mpesa_verified = bool(vendor.mpesa_verified)
    if daraja_credentials_configured():
        mpesa_verified = bool(
            mpesa_verified
            and vendor.mpesa_till_name
            and vendor.mpesa_name_match is True
        )
    return {
        "brs_registered": vendor.brs_status == "verified",
        "kra_active": vendor.kra_status == "verified",
        "mpesa_verified": mpesa_verified,
    }


def load_reports(db: Session, vendor_id: int) -> list[Report]:
    return (
        db.query(Report)
        .filter(Report.vendor_id == vendor_id)
        .order_by(Report.created_at.desc())
        .all()
    )


def score_out(score: dict) -> ScoreOut:
    return ScoreOut(
        formula=score["formula"],
        score=score["score"],
        raw=score["raw"],
        band=score["band"],
        label=score["label"],
        advice=score["advice"],
        base=score["base"],
        legal_points=score["legal_points"],
        positive_points=score["positive_points"],
        scam_points=score["scam_points"],
        service_points=score["service_points"],
        positive_count=score["positive_count"],
        scam_count=score["scam_count"],
        service_count=score["service_count"],
        false_count=score["false_count"],
        notes=score["notes"],
        service_rating=score["service_rating"],
    )


def vendor_card(vendor: Vendor, score: dict, match_field: str) -> VendorCard:
    return VendorCard(
        id=vendor.id,
        name=vendor.name,
        category=vendor.category,
        location=vendor.location,
        about=vendor.about,
        phone=display_phone(vendor.phone),
        paybill=vendor.paybill,
        instagram=vendor.instagram,
        facebook=vendor.facebook,
        tiktok=vendor.tiktok,
        profiles=profile_links(vendor),
        kra_pin=vendor.kra_pin,
        brs_number=vendor.brs_number,
        kra_status=vendor.kra_status,
        brs_status=vendor.brs_status,
        mpesa_verified=badges_for(vendor)["mpesa_verified"],
        mpesa_till_name=vendor.mpesa_till_name,
        mpesa_name_match=vendor.mpesa_name_match,
        is_shadow=bool(vendor.is_shadow),
        match_field=match_field,
        score=score["score"],
        band=score["band"],
        label=score["label"],
        advice=score["advice"],
    )


def official_for(db: Session, vendor: Vendor) -> OfficialRecord | None:
    if vendor.kra_pin:
        row = db.query(OfficialRecord).filter(OfficialRecord.kra_pin == vendor.kra_pin.upper()).first()
        if row:
            return row
    if vendor.brs_number:
        return db.query(OfficialRecord).filter(OfficialRecord.brs_number == vendor.brs_number.upper()).first()
    return None


def official_out(row: OfficialRecord | None) -> OfficialOut | None:
    if row is None:
        return None
    return OfficialOut(
        registered_name=row.registered_name,
        kra_pin=row.kra_pin,
        brs_number=row.brs_number,
        kra_status=row.kra_status,
        brs_status=row.brs_status,
        county=row.county,
        entity_type=row.entity_type,
        registered_on=row.registered_on,
    )


def reply_out(reply: ReportReply) -> ReplyOut:
    return ReplyOut(id=reply.id, text=reply.text, author=reply.author, created_at=iso(reply.created_at))


def report_out(report: Report, impact: dict) -> ReportOut:
    try:
        reasons = json.loads(report.ai_reasons or "[]")
    except json.JSONDecodeError:
        reasons = []
    return ReportOut(
        id=report.id,
        report_type=report.report_type,
        ai_category=report.ai_category,
        ai_label=LABELS.get(report.ai_category, report.ai_category),
        ai_confidence=report.ai_confidence,
        sentiment=report.sentiment,
        is_false_report=bool(report.is_false_report),
        reasons=reasons,
        description=report.description,
        proof_url=report.proof_url,
        user_phone_masked=mask_phone(report.user_phone),
        verified=bool(report.verified),
        resolved=bool(report.resolved),
        resolved_by=report.resolved_by,
        resolved_at=iso(report.resolved_at) if report.resolved_at else None,
        replies=[reply_out(reply) for reply in report.replies],
        created_at=iso(report.created_at),
        impact=impact,
        source=report.source or "buyer",
        platform=report.platform,
        author_handle=report.author_handle,
        permalink=report.permalink,
    )


def vendor_detail(db: Session, vendor: Vendor, match_field: str = "profile") -> VendorDetail:
    reports = load_reports(db, vendor.id)
    score = score_vendor(vendor, reports)
    card = vendor_card(vendor, score, match_field)
    return VendorDetail(
        **card.model_dump(),
        badges=badges_for(vendor),
        legal_state=legal_state(vendor),
        score_detail=score_out(score),
        official=official_out(official_for(db, vendor)),
        reports=[report_out(report, score["impacts"].get(report.id, {})) for report in reports],
    )


def tokens(value: str) -> set[str]:
    return {part for part in re.findall(r"[a-z0-9]+", value.lower()) if len(part) > 2 and part not in STOP_WORDS}


def name_similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    if overlap == 0:
        return 0.0
    shorter = min(len(a), len(b))
    ratio = overlap / shorter
    jaccard = overlap / len(a | b)
    if overlap < 2 and len(a | b) > 2:
        return 0.0
    return max(ratio, jaccard)


def names_match(left: str, right: str) -> bool:
    return name_similarity(left, right) >= 0.5


def best_name_record(db: Session, business_name: str) -> OfficialRecord | None:
    scored: list[tuple[float, OfficialRecord]] = []
    for row in db.query(OfficialRecord).all():
        score = name_similarity(business_name, row.registered_name)
        if score >= 0.5:
            scored.append((score, row))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def map_kra(status: str) -> str:
    if status == "active":
        return "verified"
    if status == "pending":
        return "pending"
    return "unverified"


def map_brs(status: str) -> str:
    if status == "registered":
        return "verified"
    if status == "pending":
        return "pending"
    return "unverified"


def apply_record(vendor: Vendor, row: OfficialRecord) -> None:
    vendor.kra_pin = row.kra_pin
    vendor.brs_number = row.brs_number
    vendor.kra_status = map_kra(row.kra_status)
    vendor.brs_status = map_brs(row.brs_status)


async def sms_payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Webhook body is not valid JSON.") from exc
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Webhook JSON must be an object.")
        return data
    if "form" in content_type:
        form = await request.form()
        return {key: form.get(key) for key in form.keys()}
    raw = (await request.body()).decode("utf-8", errors="ignore").strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Webhook body is not valid JSON.") from exc
        if isinstance(data, dict):
            return data
    return {"text": raw}


def first_value(payload: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return ""


@app.get("/health")
@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "veriduka"}


@app.get("/api/v1/search", response_model=SearchOut)
def search(
    query: str = Query(default="", max_length=80, description="Shop name, phone, paybill, handle, KRA PIN, or BRS number."),
    db: Session = Depends(get_db),
):
    matches = search_vendors(db, query)
    results = []
    for vendor, field in matches:
        score = score_vendor(vendor, load_reports(db, vendor.id))
        results.append(vendor_card(vendor, score, field))
    return SearchOut(query=query.strip(), count=len(results), results=results)


@app.get("/api/v1/vendor/{vendor_id}", response_model=VendorDetail)
def get_vendor(vendor_id: int, db: Session = Depends(get_db)):
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="No vendor with that id.")
    return vendor_detail(db, vendor)


@app.get("/api/v1/vendor/{vendor_id}/reading", response_model=ReadingOut)
def read_vendor_comments(vendor_id: int, db: Session = Depends(get_db)):
    """Reviews in the order a person would read them. No classifier, no score change."""
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="No vendor with that id.")
    lines = reading_lines(load_reports(db, vendor.id))
    return ReadingOut(vendor_id=vendor.id, vendor_name=vendor.name, count=len(lines), lines=lines)


@app.post("/api/v1/vendors", response_model=VendorDetail, status_code=201)
def register_vendor(payload: VendorRegisterIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    """A shop registers itself. A KRA PIN or BRS number that matches the registry adds the legal bonus."""
    try:
        vendor = create_registered_vendor(
            db,
            name=payload.name,
            phone=payload.phone,
            paybill=payload.paybill,
            instagram=payload.instagram,
            facebook=payload.facebook,
            tiktok=payload.tiktok,
            category=payload.category,
            location=payload.location,
            about=payload.about,
            kra_pin=payload.kra_pin,
            brs_number=payload.brs_number,
        )
        _link_registration_record(db, vendor, payload.kra_pin, payload.brs_number)
    except DuplicateShop as exc:
        labels = {"paybill": "paybill", "phone": "phone", "kra_pin": "KRA PIN", "brs_number": "BRS number"}
        label = labels.get(exc.field, exc.field)
        raise HTTPException(status_code=409, detail=f"That {label} is already on file.") from exc
    db.commit()
    db.refresh(vendor)
    handle = tiktok_lookup.parse_handle(payload.tiktok or "")
    if handle:
        background.add_task(_tiktok_check_in_background, handle)
    return vendor_detail(db, vendor)


def _link_registration_record(db: Session, vendor: Vendor, kra_pin: str | None, brs_number: str | None) -> None:
    """Keep a typed PIN on the shop. Apply the +25 only when the registry name agrees."""
    if not kra_pin and not brs_number:
        return
    record = None
    if kra_pin:
        record = db.query(OfficialRecord).filter(OfficialRecord.kra_pin == kra_pin).first()
    if brs_number:
        other = db.query(OfficialRecord).filter(OfficialRecord.brs_number == brs_number).first()
        if record and other and other.id != record.id:
            raise HTTPException(status_code=400, detail="The KRA PIN and BRS number belong to different businesses.")
        if record is None:
            record = other
    if record is None:
        return
    if not names_match(vendor.name, record.registered_name):
        raise HTTPException(
            status_code=409,
            detail=f"That record belongs to {record.registered_name}. The shop name has to match it before the legal bonus applies.",
        )
    apply_record(vendor, record)
    if vendor.about.startswith("Registered by the shop. No legal record"):
        vendor.about = f"Registered by the shop. The name matches {record.registered_name}."[:1000]


@app.post("/api/v1/classify", response_model=ClassifyOut)
def classify(payload: ClassifyIn):
    return ClassifyOut(**classify_report(payload.description, payload.report_type).as_dict())


@app.post("/api/v1/reports", response_model=ReportCreated)
def create_report(payload: ReportIn, db: Session = Depends(get_db)):
    if payload.vendor_id is None and not payload.identifier:
        raise HTTPException(status_code=400, detail="Send a vendor_id or an identifier such as a paybill, phone, or handle.")

    created_shadow = False
    if payload.vendor_id is not None:
        vendor = db.get(Vendor, payload.vendor_id)
        if vendor is None:
            raise HTTPException(status_code=404, detail="No vendor with that id.")
    else:
        try:
            vendor, created_shadow = resolve_identifier(db, payload.identifier or "")
        except AmbiguousIdentifier as exc:
            raise HTTPException(
                status_code=409,
                detail="That text matches more than one shop. Open the shop and report from its profile.",
            ) from exc

    result = classify_report(payload.description, payload.report_type)
    verified = (
        payload.report_type == "POSITIVE"
        and result.category == "POSITIVE"
        and not result.is_false_report
        and payload.proof_url is not None
    )
    report = Report(
        vendor_id=vendor.id,
        report_type=payload.report_type,
        ai_category=result.category,
        ai_confidence=result.confidence,
        ai_reasons=json.dumps(result.reasons),
        sentiment=result.sentiment,
        is_false_report=result.is_false_report,
        description=payload.description.strip(),
        proof_url=payload.proof_url,
        user_phone=payload.user_phone,
        verified=verified,
        resolved=False,
        source="buyer",
        score_eligible=True,
        created_at=utcnow(),
    )
    attach_receipt(db, report, {})
    db.add(report)
    db.flush()
    score = score_vendor(vendor, load_reports(db, vendor.id))
    db.commit()
    return ReportCreated(
        id=report.id,
        vendor_id=vendor.id,
        vendor_name=vendor.name,
        created_shadow=created_shadow,
        classification=ClassifyOut(**result.as_dict()),
        verified=verified,
        score=score["score"],
        band=score["band"],
        label=score["label"],
    )


@app.post("/api/v1/reports/{report_id}/replies", response_model=ReplyOut, status_code=201)
def reply_to_report(report_id: int, payload: ReplyIn, db: Session = Depends(get_db)):
    """Attach a public reply. It is shown with the complaint and never changes the score."""
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No report with that id.")
    reply = ReportReply(report_id=report.id, text=payload.text, author=payload.author, created_at=utcnow())
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return reply_out(reply)


@app.post("/api/v1/reports/{report_id}/resolve", response_model=ReportOut)
def resolve_report(
    report_id: int,
    payload: ResolveIn,
    db: Session = Depends(get_db),
    review_key: str | None = Header(default=None, alias="X-Review-Key"),
):
    """Explicit review action. Only this endpoint stops a scam report from costing points.

    When REVIEW_API_KEY is set the caller must send it as X-Review-Key, so a
    shop cannot resolve its own complaint. Without it the endpoint is open,
    which is fine for local development only.
    """
    expected = os.getenv("REVIEW_API_KEY", "")
    if expected and review_key != expected:
        raise HTTPException(status_code=403, detail="A valid review key is required to resolve a report.")
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No report with that id.")
    if not report.resolved:
        report.resolved = True
        report.resolved_by = payload.reviewer
        report.resolved_at = utcnow()
        db.commit()
        db.refresh(report)
    score = score_vendor(report.vendor, load_reports(db, report.vendor_id))
    impact = score["impacts"].get(report.id, {})
    return report_out(report, impact)


@app.post("/api/v1/verify-legal", response_model=LegalOut)
def verify_legal(payload: LegalIn, db: Session = Depends(get_db)):
    if not any((payload.business_name, payload.kra_pin, payload.brs_number)):
        raise HTTPException(status_code=400, detail="Send a business name, KRA PIN, or BRS number.")

    pin = payload.kra_pin.upper() if payload.kra_pin else None
    brs = payload.brs_number.upper() if payload.brs_number else None
    record = None
    conflict = False

    if pin:
        record = db.query(OfficialRecord).filter(OfficialRecord.kra_pin == pin).first()
        if brs:
            other = db.query(OfficialRecord).filter(OfficialRecord.brs_number == brs).first()
            if record and other and other.id != record.id:
                conflict = True
            if record is None and other is not None:
                record = None
    elif brs:
        record = db.query(OfficialRecord).filter(OfficialRecord.brs_number == brs).first()
    elif payload.business_name:
        record = best_name_record(db, payload.business_name)

    if conflict:
        return LegalOut(
            found=False,
            kra_match=False,
            brs_match=False,
            name_match=False,
            bonus_eligible=False,
            official_name=None,
            kra_pin=None,
            brs_number=None,
            kra_status=None,
            brs_status=None,
            county=None,
            entity_type=None,
            registered_on=None,
            message="The KRA PIN and BRS number belong to different records.",
            vendor_updated=False,
        )

    name_match = bool(record and payload.business_name and names_match(payload.business_name, record.registered_name))
    kra_match = bool(record and pin and record.kra_pin == pin and record.kra_status == "active")
    brs_match = bool(record and brs and record.brs_number == brs and record.brs_status == "registered")
    bonus = kra_match or brs_match

    if record is None:
        message = "No BRS or KRA record matches these details."
    elif kra_match and brs_match:
        message = "KRA PIN is active and the BRS number matches the official record."
    elif bonus:
        message = "A registry identifier matches an active record. The legal bonus can apply."
    elif record.kra_status == "pending" or record.brs_status == "pending":
        message = "An application is on file, but the KRA PIN is not active yet. The legal bonus is not applied."
    elif payload.business_name and not name_match:
        message = f"Found {record.registered_name}, but the shop name does not match that record."
    else:
        message = f"Found {record.registered_name}. Submit the KRA PIN or BRS number to confirm it."

    vendor_updated = False
    vendor = None
    if payload.vendor_id is not None:
        vendor = db.get(Vendor, payload.vendor_id)
        if vendor is None:
            raise HTTPException(status_code=404, detail="No vendor with that id.")
        same_pin = bool(record and vendor.kra_pin and vendor.kra_pin.upper() == record.kra_pin)
        if record and (same_pin or name_match):
            apply_record(vendor, record)
            vendor_updated = True
            db.commit()

        # Separate from the +25. This asks Safaricom who owns the short code,
        # then keeps M-Pesa Verified only when that name is the registered entity.
        if daraja_credentials_configured():
            if not vendor.paybill:
                vendor.mpesa_till_name = None
                vendor.mpesa_name_match = None
                vendor.mpesa_verified = False
                mpesa_message = "M-Pesa verification was not run because no paybill is on file."
            else:
                try:
                    till_name = DarajaClient().lookup_paybill_name(vendor.paybill)
                except DarajaError as exc:
                    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

                registered_record = official_for(db, vendor)
                vendor.mpesa_till_name = till_name
                vendor.mpesa_name_match = (
                    registered_names_match(till_name, registered_record.registered_name)
                    if registered_record
                    else None
                )
                vendor.mpesa_verified = bool(
                    vendor.mpesa_name_match is True and legally_verified(vendor)
                )
                if registered_record is None:
                    mpesa_message = (
                        f"Daraja reports {till_name}, but no KRA/BRS entity is on file to compare it with."
                    )
                elif vendor.mpesa_name_match is False:
                    mpesa_message = (
                        f"Daraja reports {till_name}, which does not match registered entity "
                        f"{registered_record.registered_name}. M-Pesa verification is off."
                    )
                elif not vendor.mpesa_verified:
                    mpesa_message = (
                        f"Daraja name matches {registered_record.registered_name}, but its KRA/BRS "
                        "record is not active or registered. M-Pesa verification is off."
                    )
                else:
                    mpesa_message = (
                        f"Daraja name matches registered entity {registered_record.registered_name}. "
                        "M-Pesa Verified."
                    )
            db.commit()
            message = f"{message} {mpesa_message}"

    return LegalOut(
        found=record is not None,
        kra_match=kra_match,
        brs_match=brs_match,
        name_match=name_match,
        bonus_eligible=bonus,
        official_name=record.registered_name if record else None,
        kra_pin=record.kra_pin if record else None,
        brs_number=record.brs_number if record else None,
        kra_status=record.kra_status if record else None,
        brs_status=record.brs_status if record else None,
        county=record.county if record else None,
        entity_type=record.entity_type if record else None,
        registered_on=record.registered_on if record else None,
        message=message,
        vendor_updated=vendor_updated,
    )


def _open_vendor(db: Session, vendor_id: int | None, identifier: str | None) -> tuple[Vendor, bool]:
    if vendor_id is None and not identifier:
        raise HTTPException(status_code=400, detail="Send a vendor_id or a paybill, phone, or handle.")
    if vendor_id is not None:
        vendor = db.get(Vendor, vendor_id)
        if vendor is None:
            raise HTTPException(status_code=404, detail="No vendor with that id.")
        return vendor, False
    try:
        return resolve_identifier(db, identifier or "")
    except AmbiguousIdentifier as exc:
        raise HTTPException(
            status_code=409,
            detail="That text matches more than one shop. Open the shop and import from its profile.",
        ) from exc


@app.post("/api/v1/social/import", response_model=SocialImportOut)
def import_social(payload: SocialImportIn, db: Session = Depends(get_db)):
    vendor, _created = _open_vendor(db, payload.vendor_id, payload.identifier)
    imported = 0
    counted = 0
    seen_receipts: dict[str, int] = {}
    for item in payload.comments:
        report = comment_to_report(
            vendor_id=vendor.id,
            platform=payload.platform,
            text=item.text,
            author_handle=item.author_handle,
            permalink=item.permalink or payload.permalink,
        )
        attach_receipt(db, report, seen_receipts)
        db.add(report)
        imported += 1
        if report.score_eligible:
            counted += 1
    db.flush()
    score = score_vendor(vendor, load_reports(db, vendor.id))
    db.commit()
    return SocialImportOut(
        vendor_id=vendor.id,
        vendor_name=vendor.name,
        imported=imported,
        counted=counted,
        held=imported - counted,
        score=score["score"],
        band=score["band"],
        label=score["label"],
    )


@app.post("/api/v1/social/sync", response_model=SocialSyncOut)
def sync_social(db: Session = Depends(get_db)):
    try:
        username, comments = fetch_authorized_instagram()
    except RuntimeError as exc:
        message = str(exc)
        configured = "not connected" not in message.lower()
        return SocialSyncOut(configured=configured, imported=0, message=message)

    vendor = db.query(Vendor).filter(Vendor.instagram == username.lower()).first()
    if vendor is None:
        return SocialSyncOut(
            configured=True,
            imported=0,
            username=username,
            message=f"No shop is linked to @{username}. Set that Instagram handle on the shop, then sync again.",
        )

    imported = 0
    seen_receipts: dict[str, int] = {}
    for comment in comments:
        external_id = comment.get("external_id") or None
        if external_id and db.query(Report).filter(Report.external_id == external_id).first():
            continue
        report = comment_to_report(
            vendor_id=vendor.id,
            platform="instagram",
            text=comment["text"],
            author_handle=comment.get("author_handle"),
            permalink=comment.get("permalink"),
            external_id=external_id,
        )
        attach_receipt(db, report, seen_receipts)
        db.add(report)
        imported += 1
    db.commit()
    return SocialSyncOut(
        configured=True,
        imported=imported,
        username=username,
        vendor_id=vendor.id,
        message=f"Imported {imported} comment{'s' if imported != 1 else ''} from @{username}.",
    )


def _bio_text(profile: dict) -> str:
    link = f" {profile['bio_link']}" if profile.get("bio_link") else ""
    return f"{profile['bio']}{link}".strip()[:1000]


def _store_tiktok(db: Session, handle: str, result: dict) -> tuple[Vendor, int, bool]:
    """Find or add the shop behind a TikTok handle and file its comments.

    A handle nobody has registered becomes an unclaimed TikTok shop. The owner
    can claim it later when they register (see claim_tiktok).
    """
    profile = result["profile"]
    vendor = db.query(Vendor).filter(Vendor.tiktok == handle).order_by(Vendor.is_shadow).first()
    created = vendor is None
    if vendor is None:
        vendor = Vendor(
            name=(profile["nickname"] or handle)[:160],
            tiktok=handle,
            category="TikTok shop",
            location="Not on a registry",
            about=_bio_text(profile),
            is_shadow=True,
            kra_status="unverified",
            brs_status="unverified",
            mpesa_verified=False,
            created_at=utcnow(),
        )
        db.add(vendor)
        db.flush()
    saved = 0
    for comment in result["comments"]:
        external_id = comment["external_id"]
        if external_id and db.query(Report).filter(Report.external_id == external_id).first():
            continue
        db.add(
            comment_to_report(
                vendor_id=vendor.id,
                platform="tiktok",
                text=comment["text"],
                author_handle=comment["author"],
                permalink=comment["video_url"],
                external_id=external_id,
            )
        )
        saved += 1
    db.commit()
    return vendor, saved, created


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() if forwarded else "") or (request.client.host if request.client else "unknown")


@app.post("/api/v1/tiktok/lookup", response_model=TikTokLookupOut)
def tiktok_lookup_endpoint(payload: TikTokLookupIn, request: Request, db: Session = Depends(get_db)):
    """Shop details and a sample of comments for a TikTok shop, each comment classified.

    A shop VeriDuka has not seen is added automatically as an unclaimed TikTok
    shop, and its comments are filed under the usual social-comment rules.
    Send save=false for a read-only look.
    """
    handle = tiktok_lookup.parse_handle(payload.query)
    if handle is None:
        named = [v for v, field in search_vendors(db, payload.query) if field == "name" and v.tiktok]
        if len(named) == 1:
            handle = named[0].tiktok.lstrip("@").lower()
    if handle is None:
        raise HTTPException(
            status_code=422,
            detail="Send the shop's TikTok link or @handle. A name only works for a shop already in VeriDuka with its TikTok set.",
        )
    refused = tiktok_lookup.usage_cap.allow(_client_key(request))
    if refused:
        raise HTTPException(status_code=429, detail=refused)
    try:
        result = tiktok_lookup.lookup(handle, payload.videos, payload.comments_per_video)
    except tiktok_lookup.TikTokError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    vendor = db.query(Vendor).filter(Vendor.tiktok == handle).first()
    saved = 0
    note = "Read only. Nothing was saved or scored."
    if payload.save:
        vendor, saved, created = _store_tiktok(db, handle, result)
        note = (
            f"Added {vendor.name} to VeriDuka as an unclaimed TikTok shop. Saved {saved} comment{'s' if saved != 1 else ''}."
            if created
            else f"Saved {saved} new comment{'s' if saved != 1 else ''} to {vendor.name}."
        )
    return TikTokLookupOut(
        handle=handle,
        profile=result["profile"],
        videos=result["videos"],
        comments=result["comments"],
        summary=result["summary"],
        ai=result["ai"],
        vendor_id=vendor.id if vendor else None,
        saved=saved,
        note=note,
    )


def _tiktok_check_in_background(handle: str) -> None:
    """The TikTok check for a newly registered shop. Runs after the response so signing up stays quick."""
    if tiktok_lookup.usage_cap.allow("registration") is not None:
        return
    session = SessionLocal()
    try:
        result = tiktok_lookup.lookup(handle, 3, 5)
        _store_tiktok(session, handle, result)
    except Exception as exc:  # a failed check must never break registration
        logger.warning("tiktok check for @%s failed: %s", handle, exc)
    finally:
        session.close()


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _bio_proves(vendor: Vendor, claimed: Vendor) -> bool:
    """The TikTok bio carries the registering shop's phone or paybill, so the same person controls both."""
    bio = _digits(claimed.about)
    proofs = []
    if vendor.phone and len(_digits(vendor.phone)) >= 9:
        proofs.append(_digits(vendor.phone)[-9:])
    if vendor.paybill and len(_digits(vendor.paybill)) >= 5:
        proofs.append(_digits(vendor.paybill))
    return any(proof in bio for proof in proofs)


@app.get("/api/v1/vendors/{vendor_id}/tiktok-matches", response_model=list[TikTokMatchOut])
def tiktok_matches(vendor_id: int, db: Session = Depends(get_db)):
    """Unclaimed TikTok shops that look like this registered shop: the same handle, or a similar name."""
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="No vendor with that id.")
    handle = handle_of(vendor.tiktok)
    out = []
    for other in db.query(Vendor).filter(Vendor.is_shadow.is_(True), Vendor.category == "TikTok shop", Vendor.id != vendor.id).all():
        if not other.tiktok:
            continue
        same = bool(handle) and other.tiktok.lstrip("@").lower() == handle
        if same or names_match(vendor.name, other.name) or names_match(vendor.name, other.tiktok.replace("_", " ").replace(".", " ")):
            count = db.query(Report).filter(Report.vendor_id == other.id).count()
            out.append(TikTokMatchOut(id=other.id, name=other.name, tiktok=other.tiktok, about=other.about[:200], comments=count, same_handle=same))
    out.sort(key=lambda item: not item.same_handle)
    return out[:5]


@app.post("/api/v1/vendors/{vendor_id}/claim-tiktok", response_model=VendorDetail)
def claim_tiktok(vendor_id: int, payload: TikTokClaimIn, db: Session = Depends(get_db)):
    """Connect a registered shop to the TikTok shop it owns. Its comments move over.

    The claim works only when the TikTok bio shows the shop's phone number or
    paybill, so one person cannot take over another shop's TikTok history.
    """
    vendor = db.get(Vendor, vendor_id)
    claimed = db.get(Vendor, payload.tiktok_vendor_id)
    if vendor is None or claimed is None:
        raise HTTPException(status_code=404, detail="Shop not found.")
    if vendor.is_shadow or not claimed.is_shadow or claimed.category != "TikTok shop" or not claimed.tiktok:
        raise HTTPException(status_code=409, detail="That TikTok shop cannot be claimed.")
    if not _bio_proves(vendor, claimed):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Put your shop's phone number or paybill in the @{claimed.tiktok} TikTok bio, "
                "then connect again so we know it is yours."
            ),
        )
    db.query(Report).filter(Report.vendor_id == claimed.id).update({Report.vendor_id: vendor.id})
    vendor.tiktok = claimed.tiktok
    db.delete(claimed)
    db.commit()
    db.refresh(vendor)
    return vendor_detail(db, vendor)


def _require_review_key(review_key: str | None) -> None:
    expected = os.getenv("REVIEW_API_KEY", "")
    if expected and review_key != expected:
        raise HTTPException(status_code=403, detail="A valid review key is required.")


@app.post("/api/v1/whatsapp/connect", response_model=WhatsAppConnectOut)
def connect_whatsapp(
    payload: WhatsAppConnectIn,
    db: Session = Depends(get_db),
    review_key: str | None = Header(default=None, alias="X-Review-Key"),
):
    """Record that a shop connected its own WhatsApp Business number. Until then its webhook is ignored."""
    _require_review_key(review_key)
    vendor = db.get(Vendor, payload.vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="No vendor with that id.")
    taken = db.query(Vendor).filter(Vendor.whatsapp_phone_number_id == payload.phone_number_id, Vendor.id != vendor.id).first()
    if taken is not None:
        raise HTTPException(status_code=409, detail="That WhatsApp number is already connected to another shop.")
    vendor.whatsapp_phone_number_id = payload.phone_number_id
    db.commit()
    return WhatsAppConnectOut(vendor_id=vendor.id, vendor_name=vendor.name, phone_number_id=payload.phone_number_id)


@app.get("/api/v1/whatsapp/webhook")
def whatsapp_verify(
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    """Meta's one-time handshake when the webhook URL is registered."""
    expected = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    if not expected or mode != "subscribe" or token != expected:
        raise HTTPException(status_code=403, detail="Webhook verification failed.")
    return Response(content=challenge or "", media_type="text/plain")


@app.post("/api/v1/whatsapp/webhook", response_model=WhatsAppWebhookOut)
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Opted-in WhatsApp messages. Only a connected shop's number is accepted; everything else is dropped."""
    raw = await request.body()
    if not valid_whatsapp_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=403, detail="Bad webhook signature.")
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Webhook body is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Webhook JSON must be an object.")

    messages = parse_whatsapp_messages(data)
    imported = 0
    seen: set[str] = set()
    seen_receipts: dict[str, int] = {}
    for item in messages:
        vendor = db.query(Vendor).filter(Vendor.whatsapp_phone_number_id == item["phone_number_id"]).first()
        if vendor is None:
            continue
        external_id = f"wa:{item['external_id']}" if item["external_id"] else None
        if external_id and (external_id in seen or db.query(Report).filter(Report.external_id == external_id).first()):
            continue
        if external_id:
            seen.add(external_id)
        report = comment_to_report(
            vendor_id=vendor.id,
            platform="whatsapp",
            text=item["text"],
            author_handle=mask_phone(item["sender"]),
            permalink=first_link(item["text"]),
            external_id=external_id,
        )
        attach_receipt(db, report, seen_receipts)
        db.add(report)
        imported += 1
    db.commit()
    return WhatsAppWebhookOut(received=len(messages), imported=imported, ignored=len(messages) - imported)


def _sms_shop(db: Session, argument: str) -> tuple[Vendor | None, str | None]:
    matches = [
        (vendor, field)
        for vendor, field in search_vendors(db, argument or "")
        if field in EXACT_FIELDS or field == "name"
    ]
    exact = [(vendor, field) for vendor, field in matches if field in EXACT_FIELDS]
    chosen = exact or matches
    if not chosen:
        return None, render_unknown_sms(argument or "")
    if len(chosen) > 1 and chosen[0][1] not in EXACT_FIELDS:
        return None, "VeriDuka: Several shops match. Text the paybill or phone."
    return chosen[0][0], None


def _page_comments(db: Session, msisdn: str, vendor: Vendor, restart: bool) -> str:
    """Show one saved review. Does not classify the text and does not rescore the shop."""
    lines = reading_lines(load_reports(db, vendor.id))
    if not lines:
        return "VeriDuka: No reviews on file yet. The score is unchanged."
    cursor = db.query(SmsCursor).filter(SmsCursor.msisdn == msisdn).one_or_none()
    if cursor is None:
        cursor = SmsCursor(msisdn=msisdn, vendor_id=vendor.id, position=0)
        db.add(cursor)
    if restart or cursor.vendor_id != vendor.id:
        cursor.position = 0
        cursor.vendor_id = vendor.id
    index = 0 if cursor.position >= len(lines) else cursor.position
    cursor.position = index + 1
    cursor.vendor_id = vendor.id
    return render_comment_sms(index + 1, len(lines), lines[index])


def _register_from_sms(db: Session, argument: str) -> tuple[str, int | None]:
    parts = [part.strip() for part in (argument or "").split(",")]
    if len(parts) < 3 or len(parts[0]) < 3:
        return REGISTER_USAGE, None
    try:
        phone = canonical_phone(parts[1])
    except ValueError:
        return REGISTER_USAGE, None
    paybill = re.sub(r"\D", "", parts[2])
    if not re.fullmatch(r"\d{5,7}", paybill):
        return REGISTER_USAGE, None
    try:
        vendor = create_registered_vendor(db, name=parts[0], phone=phone, paybill=paybill)
    except DuplicateShop as exc:
        label = "paybill" if exc.field == "paybill" else "phone"
        return f"VeriDuka: That {label} is already on file. Text VERIFY {paybill}."[:160], None
    return render_register_sms(vendor.name, vendor.paybill), vendor.id


@app.post("/api/v1/sms/webhook", response_model=SmsOut)
async def sms_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await sms_payload(request)
    text = first_value(payload, ("text", "message", "body", "content"))
    sender = first_value(payload, ("from", "msisdn", "phone", "sender"))
    command, argument = parse_sms_command(text)
    msisdn = normalize_msisdn(sender) or "sandbox"

    vendor_id = None
    score_value = None
    band = None

    if command in {"HELP", "EMPTY"}:
        reply = SWAHILI_HELP_TEXT if is_swahili_sms(text) else HELP_TEXT
    elif command == "UNKNOWN":
        reply = UNKNOWN_TEXT
    elif command == "REGISTER":
        reply, vendor_id = _register_from_sms(db, argument or "")
    elif command == "NEXT":
        cursor = db.query(SmsCursor).filter(SmsCursor.msisdn == msisdn).one_or_none()
        vendor = db.get(Vendor, cursor.vendor_id) if cursor else None
        if vendor is None:
            reply = "VeriDuka: Text COMMENTS and a paybill first. Example: COMMENTS 400200"
        else:
            reply = _page_comments(db, msisdn, vendor, restart=False)
            vendor_id = vendor.id
    elif command in {"VERIFY", "COMMENTS"}:
        vendor, problem = _sms_shop(db, argument or "")
        if vendor is None:
            reply = problem or UNKNOWN_TEXT
        elif command == "COMMENTS":
            reply = _page_comments(db, msisdn, vendor, restart=True)
            vendor_id = vendor.id
        else:
            reports = load_reports(db, vendor.id)
            score = score_vendor(vendor, reports)
            reply = render_verify_sms(
                vendor.name,
                score["score"],
                score["band"],
                legal_state(vendor),
                has_comments=bool(reading_lines(reports)),
                swahili=is_swahili_sms(text),
            )
            vendor_id = vendor.id
            score_value = score["score"]
            band = score["band"]
    else:
        reply = UNKNOWN_TEXT

    dispatch = sms_client.dispatch(sender, reply)
    db.add(
        SmsLog(
            msisdn=dispatch.to,
            inbound_text=text.strip(),
            reply_text=reply,
            vendor_id=vendor_id,
            provider_ref=dispatch.provider_ref,
            dispatch_status=dispatch.status,
            created_at=utcnow(),
        )
    )
    db.commit()
    logger.info("sms command=%s status=%s ref=%s", command, dispatch.status, dispatch.provider_ref)
    return SmsOut(
        command=command,
        query=argument,
        reply=reply,
        vendor_id=vendor_id,
        score=score_value,
        band=band,
        dispatch=dispatch.as_dict(),
    )


static_dir = Path(__file__).resolve().parent / "static"
if (static_dir / "index.html").exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")
