from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformConfig:
    id: str
    label: str
    short_label: str
    result_field: str


PLATFORMS: tuple[PlatformConfig, ...] = (
    PlatformConfig("linkedin", "LinkedIn", "LinkedIn", "linkedin_post"),
    PlatformConfig("x_twitter", "X", "X", "x_post"),
    PlatformConfig("instagram", "Instagram", "Instagram", "instagram_caption"),
    PlatformConfig(
        "google_business_profile",
        "Google Business",
        "GBP",
        "google_business_profile_post",
    ),
    PlatformConfig("tiktok", "TikTok", "TikTok", "tiktok_caption"),
    PlatformConfig("xiaohongshu", "Xiaohongshu", "XHS", "xiaohongshu_post"),
)

DEFAULT_ENABLED_PLATFORMS: tuple[str, ...] = (
    "linkedin",
    "x_twitter",
    "instagram",
    "google_business_profile",
)

PLATFORM_IDS: tuple[str, ...] = tuple(platform.id for platform in PLATFORMS)
PLATFORM_MAP: dict[str, PlatformConfig] = {
    platform.id: platform for platform in PLATFORMS
}


def normalize_platforms(
    values: Iterable[str] | None,
    *,
    fallback: Iterable[str] | None = None,
) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for raw in values or fallback or DEFAULT_ENABLED_PLATFORMS:
        platform_id = str(raw or "").strip()
        if platform_id in PLATFORM_MAP and platform_id not in seen:
            normalized.append(platform_id)
            seen.add(platform_id)

    return normalized or list(DEFAULT_ENABLED_PLATFORMS)


def result_field_for_platform(platform_id: str) -> str:
    platform = PLATFORM_MAP.get(platform_id)
    if platform:
        return platform.result_field
    return PLATFORM_MAP["linkedin"].result_field
