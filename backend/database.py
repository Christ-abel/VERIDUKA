"""SQLite setup, seed shops, and identifier search."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import config  # noqa: F401  loads .env before the database URL is read
from classifier import classify_report
from models import Base, OfficialRecord, Report, ReportReply, Vendor


class AmbiguousIdentifier(Exception):
    """More than one shop matches the text the buyer sent."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured
    path = Path(__file__).resolve().parent / "veriduka.db"
    return "sqlite:///" + path.as_posix()


DATABASE_URL = database_url()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

EXACT_FIELDS = {"paybill", "phone", "instagram", "facebook", "tiktok", "kra_pin", "brs_number"}

# Demo shops keep these handles so the dossier can link to the live page
# even when the database was created before facebook and tiktok columns existed.
DEMO_PROFILES = {
    "Nairobi Tech Hub Electronics": ("nairobitechhub", "NairobiTechHubElectronics", "nairobitechhub"),
    "Trendy Clothez Kenya": ("trendyclothez_ke", "TrendyClothezKenya", "trendyclothez_ke"),
    "Mama Boaz Organic Veggies": ("mamaboazveggies", "MamaBoazOrganicVeggies", "mamaboazveggies"),
}
KRA_RE = re.compile(r"^[A-Z]\d{9}[A-Z]$")
BRS_RE = re.compile(r"^(?:PVT|BN|CPR|LLP)[-/A-Z0-9]+$")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_report_columns(db: Session) -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    rows = db.execute(text("PRAGMA table_info(reports)")).fetchall()
    present = {row[1] for row in rows}
    statements = {
        "source": "ALTER TABLE reports ADD COLUMN source VARCHAR(24) DEFAULT 'buyer'",
        "platform": "ALTER TABLE reports ADD COLUMN platform VARCHAR(24)",
        "author_handle": "ALTER TABLE reports ADD COLUMN author_handle VARCHAR(80)",
        "permalink": "ALTER TABLE reports ADD COLUMN permalink VARCHAR(500)",
        "external_id": "ALTER TABLE reports ADD COLUMN external_id VARCHAR(80)",
        "score_eligible": "ALTER TABLE reports ADD COLUMN score_eligible BOOLEAN DEFAULT 1",
        "resolved_by": "ALTER TABLE reports ADD COLUMN resolved_by VARCHAR(80)",
        "resolved_at": "ALTER TABLE reports ADD COLUMN resolved_at DATETIME",
        "receipt_hash": "ALTER TABLE reports ADD COLUMN receipt_hash VARCHAR(64)",
        "ineligible_reason": "ALTER TABLE reports ADD COLUMN ineligible_reason TEXT",
    }
    for name, statement in statements.items():
        if name not in present:
            db.execute(text(statement))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_receipt_hash ON reports (receipt_hash)"))
    db.commit()


def _ensure_vendor_columns(db: Session) -> None:
    """Add vendor columns on a database created before those fields existed."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    rows = db.execute(text("PRAGMA table_info(vendors)")).fetchall()
    if not rows:
        return
    present = {row[1] for row in rows}
    statements = {
        "facebook": "ALTER TABLE vendors ADD COLUMN facebook VARCHAR(80)",
        "tiktok": "ALTER TABLE vendors ADD COLUMN tiktok VARCHAR(80)",
        "whatsapp_phone_number_id": "ALTER TABLE vendors ADD COLUMN whatsapp_phone_number_id VARCHAR(40)",
        "mpesa_till_name": "ALTER TABLE vendors ADD COLUMN mpesa_till_name VARCHAR(200)",
        "mpesa_name_match": "ALTER TABLE vendors ADD COLUMN mpesa_name_match BOOLEAN",
    }
    for name, statement in statements.items():
        if name not in present:
            db.execute(text(statement))
    db.commit()


def _backfill_profiles(db: Session) -> None:
    """Fill demo handles without overwriting a handle a contributor already set."""
    for name, (instagram, facebook, tiktok) in DEMO_PROFILES.items():
        vendor = db.query(Vendor).filter(Vendor.name == name).one_or_none()
        if vendor is None:
            continue
        vendor.instagram = vendor.instagram or instagram
        vendor.facebook = vendor.facebook or facebook
        vendor.tiktok = vendor.tiktok or tiktok
    db.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _ensure_report_columns(db)
        _ensure_vendor_columns(db)
        db.execute(text("UPDATE vendors SET about = REPLACE(about, 'Social-only', 'Social only')"))
        db.commit()
        if db.query(Vendor).count() == 0:
            seed(db)
        _ensure_showcase(db)
        _backfill_profiles(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def normalize_phone(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 10 and digits.startswith("07"):
        return "254" + digits[1:]
    if len(digits) == 12 and digits.startswith("2547"):
        return digits
    if len(digits) == 9 and digits.startswith("7"):
        return "254" + digits
    return None


def phone_tail(value: str | None) -> str | None:
    normalized = normalize_phone(value)
    if normalized:
        return normalized[-9:]
    return None


def handle_of(value: str | None) -> str:
    return (value or "").strip().lstrip("@").lower()


def split_identifier(identifier: str) -> tuple[str, str]:
    raw = " ".join(identifier.strip().split())
    compact = re.sub(r"[\s-]", "", raw)
    pin = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if KRA_RE.fullmatch(pin):
        return "kra_pin", pin
    brs = raw.strip().upper()
    if BRS_RE.fullmatch(brs):
        return "brs", brs
    phone = normalize_phone(raw)
    if phone and re.fullmatch(r"(?:\+?254|0)7\d{8}", compact):
        return "phone", phone
    digits = re.sub(r"\D", "", raw)
    if re.fullmatch(r"\d{5,7}", digits) and phone is None:
        return "paybill", digits
    if " " not in raw and (raw.startswith("@") or "_" in raw):
        return "instagram", handle_of(raw)
    return "name", raw[:160]


def shadow_name(kind: str, value: str, raw: str) -> str:
    if kind == "phone" and value.startswith("254"):
        return f"Unverified number 0{value[3:]}"
    if kind == "paybill":
        return f"Unverified paybill {value}"
    if kind == "instagram":
        return f"Unverified @{value}"
    if kind == "kra_pin":
        return f"Unverified PIN {value}"
    if kind == "brs":
        return f"Unverified registration {value}"
    return raw.strip()[:160]


def _match_vendor(vendor: Vendor, query: str) -> tuple[int, str] | None:
    compact_digits = re.sub(r"\D", "", query)
    phone = normalize_phone(query)
    if vendor.paybill and compact_digits == vendor.paybill and phone is None:
        return 0, "paybill"
    if phone and phone_tail(vendor.phone) and phone_tail(vendor.phone) == phone[-9:]:
        return 1, "phone"
    # A single token can be an Instagram, TikTok, or Facebook handle.
    # Profile links use these fields. The score does not.
    if " " not in query.strip():
        handle = handle_of(query)
        if vendor.instagram and handle == handle_of(vendor.instagram):
            return 2, "instagram"
        if vendor.tiktok and handle == handle_of(vendor.tiktok):
            return 2, "tiktok"
        if vendor.facebook and handle == handle_of(vendor.facebook):
            return 2, "facebook"
    pin = re.sub(r"[^A-Za-z0-9]", "", query).upper()
    if vendor.kra_pin and pin == vendor.kra_pin.upper():
        return 3, "kra_pin"
    if vendor.brs_number and query.strip().upper() == vendor.brs_number.upper():
        return 4, "brs_number"
    needle = query.strip().lower()
    if len(needle) >= 2 and needle in vendor.name.lower():
        priority = 5 if vendor.name.lower().startswith(needle) else 6
        return priority, "name"
    return None


def search_vendors(db: Session, query: str) -> list[tuple[Vendor, str]]:
    vendors = db.query(Vendor).order_by(Vendor.id).all()
    cleaned = query.strip()
    if not cleaned:
        return [(vendor, "directory") for vendor in vendors]

    ranked: list[tuple[int, str, Vendor]] = []
    for vendor in vendors:
        match = _match_vendor(vendor, cleaned)
        if match:
            priority, field = match
            ranked.append((priority, vendor.name.lower(), vendor, field))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [(vendor, field) for _, _, vendor, field in ranked]


class DuplicateShop(Exception):
    """The paybill or phone is already on a shop, so registration must not clone it."""

    def __init__(self, field: str):
        self.field = field
        super().__init__(field)


def create_registered_vendor(
    db: Session,
    *,
    name: str,
    phone: str,
    paybill: str | None = None,
    instagram: str | None = None,
    facebook: str | None = None,
    tiktok: str | None = None,
    category: str = "General",
    location: str = "Kenya",
    about: str = "",
    kra_pin: str | None = None,
    brs_number: str | None = None,
) -> Vendor:
    """A shop filing itself. A matching registry record can be applied by the caller."""
    if paybill and db.query(Vendor).filter(Vendor.paybill == paybill).first():
        raise DuplicateShop("paybill")
    if phone and db.query(Vendor).filter(Vendor.phone == phone).first():
        raise DuplicateShop("phone")
    if kra_pin and db.query(Vendor).filter(Vendor.kra_pin == kra_pin).first():
        raise DuplicateShop("kra_pin")
    if brs_number and db.query(Vendor).filter(Vendor.brs_number == brs_number).first():
        raise DuplicateShop("brs_number")
    vendor = Vendor(
        name=" ".join(name.split())[:160],
        phone=phone,
        paybill=paybill,
        instagram=handle_of(instagram) or None,
        facebook=(facebook or "").strip().strip("/") or None,
        tiktok=handle_of(tiktok) or None,
        category=(category or "General")[:80],
        location=(location or "Kenya")[:120],
        about=(" ".join(about.split()) if about else "Registered by the shop. No legal record is linked yet.")[:1000],
        kra_pin=kra_pin,
        brs_number=brs_number,
        mpesa_verified=False,
        kra_status="unverified",
        brs_status="unverified",
        is_shadow=False,
        created_at=utcnow(),
    )
    db.add(vendor)
    db.flush()
    return vendor


def resolve_identifier(db: Session, identifier: str) -> tuple[Vendor, bool]:
    matches = search_vendors(db, identifier)
    exact = [vendor for vendor, field in matches if field in EXACT_FIELDS]
    if len(exact) == 1:
        return exact[0], False
    if len(exact) > 1:
        raise AmbiguousIdentifier()
    named = [vendor for vendor, field in matches if field == "name"]
    if len(named) == 1:
        return named[0], False
    if len(named) > 1:
        raise AmbiguousIdentifier()
    return create_shadow_vendor(db, identifier), True


def create_shadow_vendor(db: Session, identifier: str) -> Vendor:
    kind, value = split_identifier(identifier)
    vendor = Vendor(
        name=shadow_name(kind, value, identifier),
        category="Unverified listing",
        location="Not on a registry",
        about="Opened from a buyer report. No legal record is linked yet.",
        mpesa_verified=False,
        kra_status="unverified",
        brs_status="unverified",
        is_shadow=True,
        created_at=utcnow(),
    )
    if kind == "phone":
        vendor.phone = value
    elif kind == "paybill":
        vendor.paybill = value
    elif kind == "instagram":
        vendor.instagram = value
    elif kind == "kra_pin":
        vendor.kra_pin = value
    elif kind == "brs":
        vendor.brs_number = value
    db.add(vendor)
    db.flush()
    return vendor


def _add_report(
    db: Session,
    vendor: Vendor,
    *,
    days_ago: int,
    report_type: str,
    description: str,
    phone: str,
    proof: str | None,
    verified_hint: bool,
) -> Report:
    result = classify_report(description, report_type)
    verified = bool(verified_hint and result.category == "POSITIVE" and not result.is_false_report)
    report = Report(
        vendor=vendor,
        report_type=report_type,
        ai_category=result.category,
        ai_confidence=result.confidence,
        ai_reasons=json.dumps(result.reasons),
        sentiment=result.sentiment,
        is_false_report=result.is_false_report,
        description=description,
        proof_url=proof,
        user_phone=normalize_phone(phone) or phone,
        verified=verified,
        resolved=False,
        created_at=utcnow() - timedelta(days=days_ago, hours=4),
    )
    db.add(report)
    return report


def seed(db: Session) -> None:
    db.add_all(
        [
            OfficialRecord(
                kra_pin="P051987654Z",
                brs_number="PVT-9X2K41",
                registered_name="Nairobi Tech Hub Electronics Limited",
                kra_status="active",
                brs_status="registered",
                county="Nairobi",
                entity_type="private_company",
                registered_on="2019-04-12",
            ),
            OfficialRecord(
                kra_pin="A044218903K",
                brs_number="BN-2024-330191",
                registered_name="Mama Boaz Fresh Produce",
                kra_status="pending",
                brs_status="pending",
                county="Nairobi",
                entity_type="business_name",
                registered_on="2024-11-02",
            ),
            OfficialRecord(
                kra_pin="P009112233K",
                brs_number="PVT-88HQ17",
                registered_name="Savanna Hardware Limited",
                kra_status="active",
                brs_status="registered",
                county="Mombasa",
                entity_type="private_company",
                registered_on="2016-08-19",
            ),
        ]
    )

    tech = Vendor(
        name="Nairobi Tech Hub Electronics",
        phone=normalize_phone("0712345678"),
        paybill="400200",
        instagram="nairobitechhub",
        facebook="NairobiTechHubElectronics",
        tiktok="nairobitechhub",
        kra_pin="P051987654Z",
        brs_number="PVT-9X2K41",
        category="Electronics",
        location="Westlands, Nairobi",
        about="Registered retailer of phones, accessories, and small appliances. The M-Pesa paybill is in the company name.",
        mpesa_verified=True,
        kra_status="verified",
        brs_status="verified",
        created_at=utcnow() - timedelta(days=400),
    )
    trendy = Vendor(
        name="Trendy Clothez Kenya",
        phone=normalize_phone("0799887766"),
        paybill="987654",
        instagram="trendyclothez_ke",
        facebook="TrendyClothezKenya",
        tiktok="trendyclothez_ke",
        category="Fashion",
        location="Instagram and WhatsApp only",
        about="Social only clothing seller. No BRS record under this trading name. Buyers report payment without delivery.",
        mpesa_verified=False,
        kra_status="unverified",
        brs_status="unverified",
        created_at=utcnow() - timedelta(days=120),
    )
    mama = Vendor(
        name="Mama Boaz Organic Veggies",
        phone=normalize_phone("0722113344"),
        instagram="mamaboazveggies",
        facebook="MamaBoazOrganicVeggies",
        tiktok="mamaboazveggies",
        kra_pin="A044218903K",
        brs_number="BN-2024-330191",
        category="Fresh produce",
        location="Kayole, Nairobi",
        about="Neighbourhood grocer that regulars pay on delivery. The BRS business name and KRA PIN are still pending.",
        mpesa_verified=False,
        kra_status="pending",
        brs_status="pending",
        created_at=utcnow() - timedelta(days=200),
    )
    db.add_all([tech, trendy, mama])
    db.flush()

    tech_reviews = [
        (
            12,
            "Ordered a Samsung charger and it arrived the next day in Westlands. Genuine item and the receipt matched the paybill. I would buy again.",
            "0711111001",
            "https://example.com/veriduka/tech-1",
        ),
        (
            26,
            "Paid paybill 400200 for a laptop stand. It was well packed and the team answered the phone. Legit shop, fast delivery to the office.",
            "0711111002",
            "https://example.com/veriduka/tech-2",
        ),
        (
            48,
            "Headphones were authentic and well packed. Fast delivery to Rongai. I recommend Nairobi Tech Hub.",
            "0711111003",
            "https://example.com/veriduka/tech-3",
        ),
        (
            80,
            "Customer care called when the courier was an hour behind schedule. The item was genuine. Thank you, I would buy again.",
            "0711111004",
            "https://example.com/veriduka/tech-4",
        ),
    ]
    for days_ago, description, phone, proof in tech_reviews:
        _add_report(
            db,
            tech,
            days_ago=days_ago,
            report_type="POSITIVE",
            description=description,
            phone=phone,
            proof=proof,
            verified_hint=True,
        )

    _add_report(
        db,
        trendy,
        days_ago=45,
        report_type="SCAM",
        description="I sent 4500 to paybill 987654 for a dress. They blocked me on WhatsApp the same evening and nothing was delivered. This is a ghost shop.",
        phone="0722222001",
        proof="https://example.com/veriduka/trendy-mpesa",
        verified_hint=False,
    )
    _add_report(
        db,
        trendy,
        days_ago=55,
        report_type="NON_DELIVERY",
        description="I ordered two blouses and I am still waiting. The rider is on the way was their last update, but the clothes have not arrived in Kisumu.",
        phone="0722222002",
        proof=None,
        verified_hint=False,
    )
    _add_report(
        db,
        trendy,
        days_ago=6,
        report_type="SCAM",
        description="SCAM SCAM SCAM fake fake click http://bit.ly/free-refund and win free airtime now!!!!",
        phone="0722222003",
        proof=None,
        verified_hint=False,
    )
    _add_report(
        db,
        trendy,
        days_ago=9,
        report_type="SCAM",
        description="Worst shop ever scam",
        phone="0722222004",
        proof=None,
        verified_hint=False,
    )

    mama_reviews = [
        (
            8,
            "Fresh sukuma wiki arrived the same afternoon in Umoja. Fair price and the portions were genuine. I recommend Mama Boaz.",
            "0733333001",
        ),
        (
            18,
            "Ordered tomatoes and spinach. Fast delivery, well packed, and the greens were genuine. Thank you.",
            "0733333002",
        ),
        (
            33,
            "This grocer is legit. The avocados were authentic and the rider was polite. I would buy again.",
            "0733333003",
        ),
        (
            60,
            "Managu and onions were fresh. Fair price, fast delivery to Kayole. I recommend them to neighbours.",
            "0733333004",
        ),
        (
            90,
            "They answered the phone when I asked about kale. Genuine produce and well packed. Thank you, I would buy again.",
            "0733333005",
        ),
    ]
    for index, (days_ago, description, phone) in enumerate(mama_reviews, start=1):
        _add_report(
            db,
            mama,
            days_ago=days_ago,
            report_type="POSITIVE",
            description=description,
            phone=phone,
            proof=f"https://example.com/veriduka/mama-{index}",
            verified_hint=True,
        )
    _add_report(
        db,
        mama,
        days_ago=42,
        report_type="NON_DELIVERY",
        description="My vegetable box was six days late. I was still waiting most of the week because the rider delayed the delivery.",
        phone="0733333006",
        proof=None,
        verified_hint=False,
    )


def _shop_already_listed(db: Session, *, name: str, phone: str | None, paybill: str | None, kra_pin: str | None) -> bool:
    if db.query(Vendor).filter(Vendor.name == name).first():
        return True
    if phone and db.query(Vendor).filter(Vendor.phone == phone).first():
        return True
    if paybill and db.query(Vendor).filter(Vendor.paybill == paybill).first():
        return True
    if kra_pin and db.query(Vendor).filter(Vendor.kra_pin == kra_pin).first():
        return True
    return False


def _ensure_showcase(db: Session) -> None:
    """Add the judge directory without cloning a shop that is already on file.

    Runs on every startup, including a database that already holds the first
    three shops. A later start finds the paybill or PIN and skips that row.
    """
    from showcase import SHOWCASE_RECORDS, SHOWCASE_SHOPS

    for pin, brs, registered_name, kra_status, brs_status, county, registered_on in SHOWCASE_RECORDS:
        if db.query(OfficialRecord).filter(OfficialRecord.kra_pin == pin).first():
            continue
        if db.query(OfficialRecord).filter(OfficialRecord.brs_number == brs).first():
            continue
        db.add(
            OfficialRecord(
                kra_pin=pin,
                brs_number=brs,
                registered_name=registered_name,
                kra_status=kra_status,
                brs_status=brs_status,
                county=county,
                entity_type="private_company" if brs.startswith("PVT") else "business_name",
                registered_on=registered_on,
            )
        )
    db.flush()

    for shop in SHOWCASE_SHOPS:
        phone = normalize_phone(shop["phone"])
        if _shop_already_listed(db, name=shop["name"], phone=phone, paybill=shop["paybill"], kra_pin=shop["kra_pin"]):
            continue
        vendor = Vendor(
            name=shop["name"],
            phone=phone,
            paybill=shop["paybill"],
            instagram=shop["instagram"],
            facebook=shop["name"].replace(" ", ""),
            tiktok=shop["instagram"],
            kra_pin=shop["kra_pin"],
            brs_number=shop["brs_number"],
            category=shop["category"],
            location=shop["location"],
            about=shop["about"],
            mpesa_verified=shop["mpesa_verified"],
            mpesa_till_name=shop["mpesa_till_name"],
            mpesa_name_match=shop["mpesa_name_match"],
            kra_status=shop["kra_status"],
            brs_status=shop["brs_status"],
            is_shadow=False,
            created_at=utcnow() - timedelta(days=180),
        )
        db.add(vendor)
        db.flush()
        for report_type, days_ago, description, reporter, proof, reply in shop["reports"]:
            saved = _add_report(
                db,
                vendor,
                days_ago=days_ago,
                report_type=report_type,
                description=description,
                phone=reporter,
                proof=proof,
                verified_hint=report_type == "POSITIVE",
            )
            if reply and saved is not None:
                db.add(
                    ReportReply(
                        report=saved,
                        text=reply,
                        author=vendor.name,
                        created_at=utcnow() - timedelta(days=max(days_ago - 1, 1)),
                    )
                )
    db.commit()
