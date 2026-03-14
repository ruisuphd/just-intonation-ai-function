from __future__ import annotations

from datetime import datetime, timezone

from shared.models import DailyPostResult, TenantProfile
from shared.platforms import PLATFORM_MAP, normalize_platforms


def _clean_text(value: str | None) -> str:
    return (value or "").strip()


def best_effort_post_topic(tenant: TenantProfile) -> str:
    parts: list[str] = []

    if tenant.company_name.strip():
        parts.append(tenant.company_name.strip())
    if tenant.industry.strip() and tenant.industry.strip().lower() != "other":
        parts.append(tenant.industry.strip())
    if tenant.target_audience.strip():
        parts.append(f"Audience: {tenant.target_audience.strip()}")
    if tenant.description.strip():
        parts.append(tenant.description.strip()[:280])

    if parts:
        return " | ".join(parts)
    return "Share a grounded founder update about the company's expertise, customer problems, and market perspective."


def platform_content_from_result(result: DailyPostResult) -> dict[str, str]:
    return {
        platform_id: _clean_text(getattr(result, config.result_field, ""))
        for platform_id, config in PLATFORM_MAP.items()
    }


def build_draft_payload(
    result: DailyPostResult,
    *,
    tenant: TenantProfile,
    origin: str,
    primary_platform: str | None = None,
    topic: str = "",
    batch_date: str | None = None,
    platforms_enabled: list[str] | None = None,
    created_at: datetime | None = None,
) -> dict:
    generated_at = created_at or datetime.now(timezone.utc)
    enabled_platforms = normalize_platforms(platforms_enabled)
    content_by_platform = platform_content_from_result(result)
    generated_platforms = [
        platform_id
        for platform_id in enabled_platforms
        if content_by_platform.get(platform_id)
    ]

    if not generated_platforms:
        generated_platforms = [
            platform_id for platform_id, text in content_by_platform.items() if text
        ]

    resolved_platform = primary_platform if primary_platform in PLATFORM_MAP else None
    if not resolved_platform:
        resolved_platform = (
            generated_platforms[0] if generated_platforms else "linkedin"
        )

    primary_text = content_by_platform.get(resolved_platform, "")
    if not primary_text:
        for platform_id in generated_platforms:
            primary_text = content_by_platform.get(platform_id, "")
            if primary_text:
                resolved_platform = platform_id
                break

    return {
        "tenant_id": tenant.tenant_id,
        "company_name": tenant.company_name,
        "headline": _clean_text(result.headline),
        "platform": resolved_platform,
        "text": primary_text,
        "topic": topic.strip(),
        "origin": origin,
        "status": "draft",
        "batch_date": batch_date or generated_at.date().isoformat(),
        "created_at": generated_at,
        "updated_at": generated_at,
        "hashtags": [tag.strip() for tag in result.hashtags if tag and tag.strip()],
        "why_it_matters": _clean_text(result.why_it_matters),
        "image_prompt": _clean_text(result.image_prompt),
        "platforms_generated": generated_platforms,
        "content_by_platform": content_by_platform,
        "linkedin_post": content_by_platform.get("linkedin", ""),
        "x_post": content_by_platform.get("x_twitter", ""),
        "instagram_caption": content_by_platform.get("instagram", ""),
        "google_business_profile_post": content_by_platform.get(
            "google_business_profile", ""
        ),
        "tiktok_caption": content_by_platform.get("tiktok", ""),
        "xiaohongshu_post": content_by_platform.get("xiaohongshu", ""),
    }
