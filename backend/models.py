"""SQLAlchemy models for shops, buyer reports, the mock registry, and SMS logs.

The trust score reads Vendor legal status plus Report rows. Instagram, Facebook,
and TikTok handles are public links for a buyer to open. They are stored here
so the dossier can point at the live page, and they are not score inputs.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    paybill: Mapped[str | None] = mapped_column(String(20), index=True)
    instagram: Mapped[str | None] = mapped_column(String(80), index=True)
    # Public page handles. The prototype links out. It does not import comments.
    facebook: Mapped[str | None] = mapped_column(String(80), index=True)
    tiktok: Mapped[str | None] = mapped_column(String(80), index=True)
    kra_pin: Mapped[str | None] = mapped_column(String(20), index=True)
    brs_number: Mapped[str | None] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(80), default="General")
    location: Mapped[str] = mapped_column(String(120), default="Kenya")
    about: Mapped[str] = mapped_column(Text, default="")
    mpesa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # verified | pending | unverified
    kra_status: Mapped[str] = mapped_column(String(20), default="unverified")
    brs_status: Mapped[str] = mapped_column(String(20), default="unverified")
    is_shadow: Mapped[bool] = mapped_column(Boolean, default=False)
    # Meta WhatsApp Business phone_number_id. Set only when the shop connects its own number.
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    reports: Mapped[list["Report"]] = relationship(
        back_populates="vendor",
        cascade="all, delete-orphan",
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(32))
    ai_category: Mapped[str] = mapped_column(String(32), default="")
    ai_confidence: Mapped[float] = mapped_column(Float, default=0)
    ai_reasons: Mapped[str] = mapped_column(Text, default="[]")
    sentiment: Mapped[str] = mapped_column(String(16), default="neutral")
    is_false_report: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text)
    proof_url: Mapped[str | None] = mapped_column(String(500))
    reporter_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    reporter_phone_masked: Mapped[str] = mapped_column(String(16), default="hidden")
    source: Mapped[str] = mapped_column(String(24), default="buyer")
    platform: Mapped[str | None] = mapped_column(String(24))
    author_handle: Mapped[str | None] = mapped_column(String(80))
    permalink: Mapped[str | None] = mapped_column(String(500))
    external_id: Mapped[str | None] = mapped_column(String(80), index=True)
    score_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    # SHA-256 of an M-Pesa confirmation code pasted into the report. The raw code is not stored here.
    receipt_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    # Why a saved report was kept out of the score. Empty when the report can still count.
    ineligible_reason: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[str | None] = mapped_column(String(80))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    vendor: Mapped[Vendor] = relationship(back_populates="reports")
    replies: Mapped[list["ReportReply"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportReply.created_at",
    )

    @property
    def user_phone(self) -> str:
        return ""

    @user_phone.setter
    def user_phone(self, _value: str) -> None:
        pass


class ReportReply(Base):
    """A public answer to a report. A reply never changes the score by itself."""

    __tablename__ = "report_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    report: Mapped[Report] = relationship(back_populates="replies")


class OfficialRecord(Base):
    """Mock row from the Business Registration Service and KRA PIN registries."""

    __tablename__ = "official_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kra_pin: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    brs_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    registered_name: Mapped[str] = mapped_column(String(200))
    kra_status: Mapped[str] = mapped_column(String(20))  # active | pending | inactive
    brs_status: Mapped[str] = mapped_column(String(20))  # registered | pending | struck_off
    county: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    registered_on: Mapped[str] = mapped_column(String(20))


class SmsCursor(Base):
    """Where a feature phone left off while reading reviews. Not a score input."""

    __tablename__ = "sms_cursors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    msisdn: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    vendor_id: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)


class SmsLog(Base):
    __tablename__ = "sms_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    msisdn: Mapped[str] = mapped_column(String(20), default="")
    inbound_text: Mapped[str] = mapped_column(Text)
    reply_text: Mapped[str] = mapped_column(Text)
    vendor_id: Mapped[int | None] = mapped_column(Integer)
    provider_ref: Mapped[str] = mapped_column(String(40), default="")
    dispatch_status: Mapped[str] = mapped_column(String(20), default="mocked")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
