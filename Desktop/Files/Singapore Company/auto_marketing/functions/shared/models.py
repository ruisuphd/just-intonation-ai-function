from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from shared.platforms import DEFAULT_ENABLED_PLATFORMS


class _Base(BaseModel):
    model_config = {"extra": "allow"}


# ── Tenant ───────────────────────────────────────────────────────────────────


class OnboardingState(_Base):
    website_scraped: bool = False
    competitors_identified: bool = False
    brand_voice_analyzed: bool = False
    platforms_connected: list[str] = Field(default_factory=list)


class AgencyProfile(_Base):
    agency_id: str
    name: str
    owner_uid: str


class UserRole(_Base):
    uid: str
    role: Literal["agency_admin", "tenant_admin", "viewer"]
    accessible_tenant_ids: list[str] = Field(default_factory=list)


class PlatformCredentials(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    platform_id: str


class CompetitorProfile(_Base):
    name: str
    website: str
    linkedin_url: str
    x_url: str


class TenantProfile(_Base):
    tenant_id: str
    owner_uid: str = ""
    owner_email: str = ""
    company_name: str
    industry: str
    description: str
    target_audience: str = ""
    tone: Literal["professional", "friendly", "authoritative", "casual"] = (
        "professional"
    )
    language: Literal["en", "zh", "bilingual"] = "en"
    timezone: str = "Asia/Singapore"
    subscription_tier: Literal["starter", "pro"] = "starter"
    competitor_names: list[str] = Field(default_factory=list)
    industry_keywords: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_internal: bool = False
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    starter_access_expires_at: datetime | None = None
    subscription_status: Literal["active", "trialing", "past_due", "canceled"] = "active"
    platforms_enabled: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ENABLED_PLATFORMS)
    )
    platform_credentials: dict[str, PlatformCredentials] = Field(default_factory=dict)
    daily_digest_enabled: bool = True
    daily_digest_email: str = ""
    notification_time: str = "07:00"
    onboarding_completed: bool = False
    onboarding_state: Optional[OnboardingState] = None
    agency_id: Optional[str] = None


class TenantSourceConfig(_Base):
    tenant_id: str
    sources: list[dict] = Field(default_factory=list)
    last_generated_at: datetime | None = None


# ── Intelligence ──────────────────────────────────────────────────────────────

SourceType = Literal[
    "google_news_rss", "reddit", "rss_competitor", "crunchbase_rss", "techcrunch_rss"
]


class IntelligenceItem(_Base):
    tenant_id: str = ""
    source_url: str
    source_type: SourceType
    source_name: str
    title: str
    raw_content: str
    summary: Optional[str] = None
    relevance_score: Optional[float] = None
    relevance_reasoning: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    postability_score: float = 0.0
    suggested_angle: str = ""
    why_now: str = ""
    batch_date: str
    gathered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dedup_window_expires: Optional[datetime] = None
    is_used_for_content: bool = False
    expires_at: Optional[datetime] = None
    competitor_id: Optional[str] = None


# ── Brand Documents ───────────────────────────────────────────────────────────

DocType = Literal[
    "brand_voice",
    "service_description",
    "case_study",
    "icp_definition",
    "outreach_guide",
    "other",
]


class BrandDocument(_Base):
    filename: str
    storage_path: str
    file_type: Literal["pdf", "docx", "md"]
    file_size_bytes: int
    doc_type: DocType = "other"
    language: Literal["en", "zh"] = "en"
    status: Literal["uploaded", "processing", "indexed", "error"] = "uploaded"
    chunk_count: int = 0
    uploaded_by: str = ""
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class BrandChunk(_Base):
    document_id: str
    chunk_index: int
    text: str
    token_count: int
    embedding: list[float] = Field(default_factory=list)
    language: Literal["en", "zh"] = "en"
    doc_type: str = "other"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BrandGuidelines(_Base):
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    vocabulary: list[str] = Field(default_factory=list)
    formatting_rules: str = ""
    tone_formality: int = 5
    tone_technicality: int = 5


# ── Daily Post Draft ──────────────────────────────────────────────────────────


class DailyPostResult(_Base):
    """English-only daily post pack with platform-ready variants."""

    headline: str = ""
    linkedin_post: str = ""
    x_post: str = ""
    instagram_caption: str = ""
    google_business_profile_post: str = ""
    tiktok_caption: str = ""
    xiaohongshu_post: str = ""
    why_it_matters: str = ""
    hashtags: list[str] = Field(default_factory=list)
    image_prompt: str = ""

    @field_validator("hashtags", mode="before")
    @classmethod
    def normalize_hashtags(cls, value):
        if value is None:
            return []

        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()][:4]

        text = str(value).strip()
        if not text:
            return []

        hashtag_matches = re.findall(r"#[-\w]+", text.replace("\n", " "))
        if hashtag_matches:
            return hashtag_matches[:4]

        parts = [
            part.strip() for part in re.split(r"[,|\n]+", text) if part and part.strip()
        ]
        if len(parts) == 1 and " " in parts[0]:
            parts = [part.strip() for part in parts[0].split() if part.strip()]
        return parts[:4]


# ── Prospect Signals ──────────────────────────────────────────────────────────

SignalType = Literal[
    "hiring_ai_role",
    "funding_received",
    "pain_point_expressed",
    "competitor_move",
    "digital_transformation_signal",
]


class ProspectSignal(_Base):
    tenant_id: str = ""
    source_url: str
    source_type: SourceType
    source_name: str
    title: str
    raw_content: str
    summary: str = ""
    is_buying_signal: bool = False
    signal_type: Optional[SignalType] = None
    strength_score: int = 0
    company_name: str = ""
    reasoning: str = ""
    status: Literal["new", "qualified", "dismissed", "converted"] = "new"
    batch_date: str = ""
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


# ── Qualified Leads ───────────────────────────────────────────────────────────

ICPFit = Literal["high", "medium", "low"]


class QualifiedLead(_Base):
    tenant_id: str = ""
    signal_id: str
    company_name: str
    company_location: Optional[str] = None
    icp_fit: Optional[ICPFit] = None
    icp_fit_score: float = 0.0
    icp_reasoning: Optional[str] = None
    matching_services: list[str] = Field(default_factory=list)
    suggested_outreach_angle: Optional[str] = None
    brand_chunk_ids: list[str] = Field(default_factory=list)
    # PII fields
    contact_name: Optional[str] = Field(default=None, json_schema_extra={"pii": True})
    contact_title: Optional[str] = Field(default=None, json_schema_extra={"pii": True})
    contact_email: Optional[str] = Field(default=None, json_schema_extra={"pii": True})
    contact_linkedin_url: Optional[str] = Field(
        default=None, json_schema_extra={"pii": True}
    )
    linkedin_about: Optional[str] = None
    recent_experience: Optional[list[dict]] = None
    recent_posts: Optional[list[str]] = None
    enrichment_status: Literal["pending", "completed", "failed"] = "pending"
    status: Literal[
        "new", "contacted", "meeting_booked", "negotiation", "closed_won", "closed_lost"
    ] = "new"
    deal_value: Optional[float] = None
    last_contacted_at: Optional[datetime] = None
    is_pinned: bool = False
    qualified_at: Optional[datetime] = None
    qualified_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


class CRMActivity(_Base):
    lead_id: str
    activity_type: Literal["email_sent", "reply_received", "note_added"]
    content: str
    timestamp: datetime


# ── Outreach ──────────────────────────────────────────────────────────────────


class ComplianceFlags(_Base):
    can_spam_ok: bool = False
    casl_warning: bool = False
    gdpr_applicable: bool = False
    suppress_list_checked: bool = False
    human_reviewed: bool = False


class OutreachContent(_Base):
    message: Optional[str] = None  # linkedin_dm (max 300 chars)
    subject: Optional[str] = None  # cold_email
    body: Optional[str] = None  # cold_email (3 paragraphs)
    physical_address: Optional[str] = None  # cold_email CAN-SPAM required
    unsubscribe_note: Optional[str] = None  # cold_email CAN-SPAM required


class OutreachDraft(_Base):
    tenant_id: str = ""
    lead_id: str
    company_name: str = ""
    draft_type: Literal["linkedin_dm", "cold_email"]
    content: OutreachContent = Field(default_factory=OutreachContent)
    compliance_flags: ComplianceFlags = Field(default_factory=ComplianceFlags)
    status: Literal["pending_human_review", "approved", "sent", "archived"] = (
        "pending_human_review"
    )
    sent_at: Optional[datetime] = None
    sent_by: Optional[str] = None
    compliance_checklist_completed: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    brand_chunk_ids: list[str] = Field(default_factory=list)


# ── Suppress List ─────────────────────────────────────────────────────────────


class SuppressListEntry(_Base):
    type: Literal["email", "domain"]
    value: str
    reason: Literal["opt_out", "deletion_request", "manual"] = "manual"
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    added_by: str = ""


# ── System Config ─────────────────────────────────────────────────────────────


class IntelligenceSource(_Base):
    id: str
    name: str
    type: Literal[
        "google_news_rss", "reddit", "rss", "crunchbase_rss", "techcrunch_rss"
    ]
    url: Optional[str] = None
    subreddit: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    enabled: bool = True
    category: Literal["industry_news", "competitor", "funding", "community"] = (
        "industry_news"
    )


class GenerationConfig(_Base):
    intelligence_gather_cron: str = "0 7 * * *"
    content_generate_cron: str = "30 7 * * *"
    signal_detect_cron: str = "0 8 * * *"
    retention_cleanup_cron: str = "0 4 * * *"
    auto_package: bool = False
    timezone: str = "Asia/Singapore"
    top_k_intelligence: int = 3
    default_language: str = "en"
    daily_digest_enabled: bool = False
    daily_digest_email: str = ""


class ComplianceConfig(_Base):
    physical_address: str = ""
    unsubscribe_email: str = ""
    privacy_policy_url: str = ""
    data_retention_days_signals: int = 180
    data_retention_days_leads: int = 365
    firm_name: str = "Intonation Labs Pte. Ltd."


# ── LLM response schemas (used in prompt templates) ──────────────────────────


class IntelligenceScoreResult(_Base):
    summary: str = ""
    relevance_score: float = 0.0
    relevance_reasoning: str = ""
    tags: list[str] = Field(default_factory=list)
    postability_score: float = 0.0
    suggested_angle: str = ""
    why_now: str = ""


class SignalClassificationResult(_Base):
    is_buying_signal: bool = False
    signal_type: str | None = None
    strength_score: int = 0
    company_name: str = ""
    reasoning: str = ""
    summary: str = ""


class ICPQualificationResult(_Base):
    icp_fit: ICPFit = "low"
    icp_fit_score: float = 0.0
    reasoning: str = ""
    matching_services: list[str] = Field(default_factory=list)
    suggested_outreach_angle: str = ""


class LinkedInDMResult(_Base):
    message: str = ""


class ColdEmailResult(_Base):
    subject: str = ""
    body: str = ""
    physical_address: str = ""
    unsubscribe_note: str = ""


class NewsletterDraft(_Base):
    tenant_id: str = ""
    week_start: str = ""
    subject: str = ""
    preview_text: str = ""
    html_body: str = ""
    plain_body: str = ""
    intel_count: int = 0
    status: Literal["draft", "scheduled", "sent", "archived"] = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_for: Optional[datetime] = None


class NewsletterCampaign(_Base):
    subject: str
    html_body: str
    platform: Literal["mailchimp", "beehiiv", "substack", "ghost"]
    status: Literal["draft", "scheduled", "sent"]
    scheduled_at: datetime
    tenant_id: Optional[str] = None


# ── Publishing & Scheduling ───────────────────────────────────────────────────


class PublishingRecord(_Base):
    post_id: str
    platform: str
    status: Literal["scheduled", "published", "failed"]
    external_id: Optional[str] = None
    error_message: Optional[str] = None
    scheduled_for: datetime


class CalendarEvent(_Base):
    event_type: Literal["social_post", "newsletter", "outreach_campaign"]
    scheduled_for: datetime
    reference_id: str
    status: str


# ── Analytics ─────────────────────────────────────────────────────────────────


class PostMetrics(_Base):
    post_id: str
    impressions: int
    clicks: int
    likes: int
    comments: int
    shares: int
    measured_at: datetime


class OutreachMetrics(_Base):
    campaign_id: str
    open_rate: float
    click_rate: float
    reply_rate: float
    measured_at: datetime
