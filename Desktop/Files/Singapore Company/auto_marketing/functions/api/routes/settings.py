"""Tenant settings API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from api.middleware.auth import require_tenant
from shared.entitlements import normalize_subscription_tier
from shared.platforms import normalize_platforms
from shared.settings_limits import (
    COMPETITOR_LIMIT,
    DESCRIPTION_MAX_CHARS,
    INDUSTRY_KEYWORDS_LIMIT,
    TARGET_AUDIENCE_MAX_CHARS,
)
from shared.firestore_client import update_tenant
from shared.models import TenantProfile
from shared.redis_client import cache_delete_pattern

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(tenant: TenantProfile = Depends(require_tenant)):
    return {
        "tenant_id": tenant.tenant_id,
        "company_name": tenant.company_name,
        "industry": tenant.industry,
        "description": tenant.description,
        "target_audience": tenant.target_audience,
        "tone": tenant.tone,
        "language": tenant.language,
        "timezone": tenant.timezone,
        "competitor_names": tenant.competitor_names,
        "industry_keywords": tenant.industry_keywords,
        "platforms_enabled": tenant.platforms_enabled,
        "daily_digest_enabled": tenant.daily_digest_enabled,
        "daily_digest_email": tenant.daily_digest_email,
        "notification_time": tenant.notification_time,
        "subscription_tier": normalize_subscription_tier(tenant.subscription_tier),
        "subscription_status": tenant.subscription_status,
        "starter_access_expires_at": tenant.starter_access_expires_at,
        "is_internal": tenant.is_internal,
        "onboarding_completed": tenant.onboarding_completed,
        "tone_formal_casual": getattr(tenant, "tone_formal_casual", 50),
        "tone_technical_accessible": getattr(tenant, "tone_technical_accessible", 50),
    }


class SettingsUpdate(BaseModel):
    company_name: str | None = None
    industry: str | None = None
    description: str | None = None
    target_audience: str | None = None
    tone: str | None = None
    language: str | None = None
    timezone: str | None = None
    competitor_names: list[str] | None = None
    industry_keywords: list[str] | None = None
    platforms_enabled: list[str] | None = None
    daily_digest_enabled: bool | None = None
    daily_digest_email: str | None = None
    notification_time: str | None = None
    tone_formal_casual: int | None = None
    tone_technical_accessible: int | None = None

    @field_validator("description")
    @classmethod
    def clamp_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()[:DESCRIPTION_MAX_CHARS]

    @field_validator("target_audience")
    @classmethod
    def clamp_target_audience(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()[:TARGET_AUDIENCE_MAX_CHARS]

    @field_validator("industry")
    @classmethod
    def normalize_industry(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("competitor_names")
    @classmethod
    def normalize_competitors(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        return cleaned[:COMPETITOR_LIMIT]

    @field_validator("industry_keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        return cleaned[:INDUSTRY_KEYWORDS_LIMIT]

    @field_validator("platforms_enabled")
    @classmethod
    def normalize_enabled_platforms(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return normalize_platforms(value)

    @field_validator("tone_formal_casual", "tone_technical_accessible")
    @classmethod
    def clamp_slider_values(cls, value: int | None) -> int | None:
        if value is None:
            return None
        return max(0, min(100, int(value)))


@router.put("")
async def update_settings(
    body: SettingsUpdate,
    tenant: TenantProfile = Depends(require_tenant),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    if updates:
        update_tenant(tenant.tenant_id, updates)
        cache_delete_pattern(f"tenant:uid:{tenant.owner_uid}*")

    return {"ok": True, "updated_fields": list(updates.keys())}
