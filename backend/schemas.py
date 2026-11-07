"""Pydantic request and response models for the public API."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


PHONE_RE = re.compile(r"^(?:\+?254|0)?7\d{8}$")
URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def canonical_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        return "254" + digits[1:]
    if len(digits) == 9 and digits.startswith("7"):
        return "254" + digits
    raise ValueError("Use a Kenyan mobile number, for example 0712345678.")


class ScoreOut(BaseModel):
    formula: str
    score: int
    raw: int
    band: str
    label: str
    advice: str
    base: int
    legal_points: int
    positive_points: int
    scam_points: int
    service_points: int
    positive_count: int
    scam_count: int
    service_count: int
    false_count: int
    notes: list[str]
    service_rating: dict


class ReplyOut(BaseModel):
    id: int
    text: str
    author: str
    created_at: str


class ReplyIn(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    author: str = Field(min_length=2, max_length=80, description="Who is replying, for example the shop name.")

    @field_validator("text", "author")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Enter at least 2 characters.")
        return value


class ResolveIn(BaseModel):
    reviewer: str = Field(min_length=2, max_length=80, description="Who reviewed and accepted the resolution.")


class ReportOut(BaseModel):
    id: int
    report_type: str
    ai_category: str
    ai_label: str
    ai_confidence: float
    sentiment: str
    is_false_report: bool
    reasons: list[str]
    description: str
    proof_url: str | None
    user_phone_masked: str
    verified: bool
    resolved: bool
    resolved_by: str | None = None
    resolved_at: str | None = None
    replies: list[ReplyOut] = []
    created_at: str
    impact: dict
    source: str = "buyer"
    platform: str | None = None
    author_handle: str | None = None
    permalink: str | None = None


class OfficialOut(BaseModel):
    registered_name: str
    kra_pin: str
    brs_number: str
    kra_status: str
    brs_status: str
    county: str
    entity_type: str
    registered_on: str


class ProfileLink(BaseModel):
    """A public page the buyer opens. The URL is not fed into the trust score."""

    handle: str
    url: str


class VendorCard(BaseModel):
    id: int
    name: str
    category: str
    location: str
    about: str
    phone: str | None
    paybill: str | None
    instagram: str | None
    facebook: str | None = None
    tiktok: str | None = None
    profiles: dict[str, ProfileLink] = Field(default_factory=dict)
    kra_pin: str | None
    brs_number: str | None
    kra_status: str
    brs_status: str
    mpesa_verified: bool
    mpesa_till_name: str | None
    mpesa_name_match: bool | None
    is_shadow: bool
    match_field: str
    score: int
    band: str
    label: str
    advice: str


class VendorDetail(VendorCard):
    badges: dict
    legal_state: str
    score_detail: ScoreOut
    official: OfficialOut | None
    reports: list[ReportOut]


class SearchOut(BaseModel):
    query: str
    count: int
    results: list[VendorCard]


class ReportIn(BaseModel):
    vendor_id: int | None = None
    identifier: str | None = Field(default=None, max_length=80)
    report_type: str
    description: str = Field(min_length=10, max_length=2000)
    proof_url: str | None = None
    user_phone: str

    @field_validator("report_type")
    @classmethod
    def known_type(cls, value: str) -> str:
        allowed = {"SCAM", "POOR_SERVICE", "NON_DELIVERY", "POSITIVE"}
        cleaned = value.strip().upper()
        if cleaned not in allowed:
            raise ValueError("report_type must be SCAM, POOR_SERVICE, NON_DELIVERY, or POSITIVE.")
        return cleaned

    @field_validator("identifier")
    @classmethod
    def clean_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.strip().split())
        return cleaned or None

    @field_validator("proof_url")
    @classmethod
    def clean_proof(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        if not URL_RE.match(cleaned):
            raise ValueError("Proof link must start with http:// or https://")
        if len(cleaned) > 500:
            raise ValueError("Proof link is too long.")
        return cleaned

    @field_validator("user_phone")
    @classmethod
    def clean_phone(cls, value: str) -> str:
        if not PHONE_RE.match(re.sub(r"\s+", "", value.strip())):
            raise ValueError("Use a Kenyan mobile number, for example 0712345678.")
        return canonical_phone(value)


class ClassifyIn(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    report_type: str | None = None

    @field_validator("report_type")
    @classmethod
    def known_type(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip().upper()
        allowed = {"SCAM", "POOR_SERVICE", "NON_DELIVERY", "POSITIVE"}
        if cleaned not in allowed:
            raise ValueError("report_type must be SCAM, POOR_SERVICE, NON_DELIVERY, or POSITIVE.")
        return cleaned


class ClassifyOut(BaseModel):
    category: str
    label: str
    confidence: float
    sentiment: str
    is_false_report: bool
    reasons: list[str]
    summary: str


class ReportCreated(BaseModel):
    id: int
    vendor_id: int
    vendor_name: str
    created_shadow: bool
    classification: ClassifyOut
    verified: bool
    score: int
    band: str
    label: str


class LegalIn(BaseModel):
    vendor_id: int | None = None
    business_name: str | None = Field(default=None, max_length=200)
    kra_pin: str | None = Field(default=None, max_length=20)
    brs_number: str | None = Field(default=None, max_length=40)

    @field_validator("business_name", "kra_pin", "brs_number")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.strip().split())
        return cleaned or None


class LegalOut(BaseModel):
    found: bool
    kra_match: bool
    brs_match: bool
    name_match: bool
    bonus_eligible: bool
    official_name: str | None
    kra_pin: str | None
    brs_number: str | None
    kra_status: str | None
    brs_status: str | None
    county: str | None
    entity_type: str | None
    registered_on: str | None
    message: str
    vendor_updated: bool


class VendorRegisterIn(BaseModel):
    """A shop putting itself on file. This does not grant a legal bonus."""

    name: str = Field(min_length=3, max_length=160)
    phone: str
    paybill: str | None = None
    instagram: str | None = Field(default=None, max_length=80)
    facebook: str | None = Field(default=None, max_length=80)
    tiktok: str | None = Field(default=None, max_length=80)
    category: str = Field(default="General", max_length=80)
    location: str = Field(default="Kenya", max_length=120)
    about: str = Field(default="", max_length=1000)

    @field_validator("name", "category", "location", "about")
    @classmethod
    def tidy(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, value: str) -> str:
        if not PHONE_RE.match(re.sub(r"\s+", "", value.strip())):
            raise ValueError("Use a Kenyan mobile number, for example 0712345678.")
        return canonical_phone(value)

    @field_validator("paybill")
    @classmethod
    def clean_paybill(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        digits = re.sub(r"\D", "", value)
        if not re.fullmatch(r"\d{5,7}", digits):
            raise ValueError("Paybill must be 5 to 7 digits.")
        return digits

    @field_validator("instagram", "facebook", "tiktok")
    @classmethod
    def clean_handle(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip().lstrip("@")[:80]


class ReadingOut(BaseModel):
    """Comments in reading order. The list is not classified and does not move the score."""

    vendor_id: int
    vendor_name: str
    count: int
    lines: list[str]


class SmsOut(BaseModel):
    command: str
    query: str | None
    reply: str
    vendor_id: int | None
    score: int | None
    band: str | None
    dispatch: dict


class SocialCommentIn(BaseModel):
    text: str = Field(min_length=8, max_length=2000)
    author_handle: str | None = Field(default=None, max_length=80)
    permalink: str | None = Field(default=None, max_length=500)

    @field_validator("permalink")
    @classmethod
    def clean_link(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        if not URL_RE.match(cleaned):
            raise ValueError("Post link must start with http:// or https://")
        return cleaned


class SocialImportIn(BaseModel):
    vendor_id: int | None = None
    identifier: str | None = Field(default=None, max_length=80)
    platform: str
    permalink: str | None = None
    comments: list[SocialCommentIn] = Field(min_length=1, max_length=30)

    @field_validator("platform")
    @classmethod
    def known_platform(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"instagram", "facebook", "tiktok", "x", "whatsapp"}
        if cleaned not in allowed:
            raise ValueError("platform must be instagram, facebook, tiktok, x, or whatsapp.")
        return cleaned

    @field_validator("permalink")
    @classmethod
    def clean_shared_link(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        if not URL_RE.match(cleaned):
            raise ValueError("Post link must start with http:// or https://")
        return cleaned


class SocialImportOut(BaseModel):
    vendor_id: int
    vendor_name: str
    imported: int
    counted: int
    held: int
    score: int
    band: str
    label: str


class SocialSyncOut(BaseModel):
    configured: bool
    imported: int
    message: str
    vendor_id: int | None = None
    username: str | None = None


class WhatsAppConnectIn(BaseModel):
    vendor_id: int
    phone_number_id: str = Field(min_length=5, max_length=40, description="Meta phone_number_id of the shop's own WhatsApp Business number.")

    @field_validator("phone_number_id")
    @classmethod
    def digits_only(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise ValueError("phone_number_id is the numeric id from Meta, not the phone number.")
        return cleaned


class WhatsAppConnectOut(BaseModel):
    vendor_id: int
    vendor_name: str
    phone_number_id: str


class WhatsAppWebhookOut(BaseModel):
    received: int
    imported: int
    ignored: int


class TikTokLookupIn(BaseModel):
    query: str = Field(min_length=2, max_length=200, description="A TikTok link, @handle, or the name of a shop already in VeriDuka.")
    videos: int = Field(default=3, ge=1, le=5)
    comments_per_video: int = Field(default=5, ge=1, le=10)
    save: bool = Field(default=False, description="Also save the shop and its comments. Off by default: a lookup only reads.")


class TikTokLookupOut(BaseModel):
    handle: str
    profile: dict
    videos: list[dict]
    comments: list[dict]
    summary: dict
    ai: dict | None = None
    vendor_id: int | None = None
    saved: int = 0
    note: str = ""
