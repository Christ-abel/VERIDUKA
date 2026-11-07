"""VeriDuka API: search, trust profiles, buyer reports, registry checks, SMS."""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from classifier import CATEGORY_LABELS, classify_report
from database import EXACT_FIELDS, AmbiguousIdentifier, get_db, init_db, resolve_identifier, search_vendors, utcnow
from models import OfficialRecord, Report, ReportReply, SmsLog, Vendor
from schemas import (
    ClassifyIn,
    ClassifyOut,
    LegalIn,
    LegalOut,
    OfficialOut,
    ReportCreated,
    ReplyIn,
    ReplyOut,
    ReportIn,
    ReportOut,
    ResolveIn,
    ScoreOut,
    SearchOut,
    SmsOut,
    SocialImportIn,
    SocialImportOut,
    SocialSyncOut,
    VendorCard,
    VendorDetail,
)
from scoring import legally_verified, score_vendor
from social import comment_to_report, fetch_authorized_instagram
from thrivewave import (
    HELP_TEXT,
    UNKNOWN_TEXT,
    ThriveWaveClient,
    parse_sms_command,
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
        "Search a paybill, phone, Instagram handle, KRA PIN, or shop name. "
        "The trust score mixes a mock BRS/KRA registry with buyer reports. "
        "ThriveWave SMS uses the same score."
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


def badges_for(vendor: Vendor) -> dict:
    return {
        "brs_registered": vendor.brs_status == "verified",
        "kra_active": vendor.kra_status == "verified",
        "mpesa_verified": bool(vendor.mpesa_verified),
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
        kra_pin=vendor.kra_pin,
        brs_number=vendor.brs_number,
        kra_status=vendor.kra_status,
        brs_status=vendor.brs_status,
        mpesa_verified=bool(vendor.mpesa_verified),
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
    if payload.vendor_id is not None:
        vendor = db.get(Vendor, payload.vendor_id)
        if vendor is None:
            raise HTTPException(status_code=404, detail="No vendor with that id.")
        same_pin = bool(record and vendor.kra_pin and vendor.kra_pin.upper() == record.kra_pin)
        if record and (same_pin or name_match):
            apply_record(vendor, record)
            vendor_updated = True
            db.commit()

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
    for item in payload.comments:
        report = comment_to_report(
            vendor_id=vendor.id,
            platform=payload.platform,
            text=item.text,
            author_handle=item.author_handle,
            permalink=item.permalink or payload.permalink,
        )
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
    for comment in comments:
        external_id = comment.get("external_id") or None
        if external_id and db.query(Report).filter(Report.external_id == external_id).first():
            continue
        db.add(
            comment_to_report(
                vendor_id=vendor.id,
                platform="instagram",
                text=comment["text"],
                author_handle=comment.get("author_handle"),
                permalink=comment.get("permalink"),
                external_id=external_id,
            )
        )
        imported += 1
    db.commit()
    return SocialSyncOut(
        configured=True,
        imported=imported,
        username=username,
        vendor_id=vendor.id,
        message=f"Imported {imported} comment{'s' if imported != 1 else ''} from @{username}.",
    )


@app.post("/api/v1/sms/webhook", response_model=SmsOut)
async def sms_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await sms_payload(request)
    text = first_value(payload, ("text", "message", "body", "content"))
    sender = first_value(payload, ("from", "msisdn", "phone", "sender"))
    command, argument = parse_sms_command(text)

    vendor_id = None
    score_value = None
    band = None

    if command in {"HELP", "EMPTY"}:
        reply = HELP_TEXT
    elif command == "UNKNOWN":
        reply = UNKNOWN_TEXT
    else:
        matches = [(vendor, field) for vendor, field in search_vendors(db, argument or "") if field in EXACT_FIELDS or field == "name"]
        exact = [(vendor, field) for vendor, field in matches if field in EXACT_FIELDS]
        chosen = exact or matches
        if len(chosen) == 1 or (chosen and chosen[0][1] in EXACT_FIELDS):
            vendor = chosen[0][0]
            score = score_vendor(vendor, load_reports(db, vendor.id))
            reply = render_verify_sms(vendor.name, score["score"], score["band"], legal_state(vendor))
            vendor_id = vendor.id
            score_value = score["score"]
            band = score["band"]
        elif len(chosen) > 1:
            reply = "VeriDuka: Several shops match. Text VERIFY with the paybill or phone."
        else:
            reply = render_unknown_sms(argument or "")

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
