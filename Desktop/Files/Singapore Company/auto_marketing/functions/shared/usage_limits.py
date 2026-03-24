"""Tier-based usage limits and Redis-backed daily counters."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

from shared.logger import get_logger
from shared.redis_client import counter_get, counter_increment

logger = get_logger("usage_limits")

TIER_LIMITS: dict[str, dict] = {
    "starter": {
        "intelligence_items_per_run": 25,
        "post_generations_per_day": 1,
        "leads_per_run": 2,
        "chat_messages_per_day": 10,
        "brand_documents_total": 3,
        "pipeline_days_per_week": [0, 2, 4],  # Mon, Wed, Fri
        "newsletter_enabled": False,
        "max_platform_connections": 1,
    },
    "pro": {
        "intelligence_items_per_run": 100,
        "post_generations_per_day": 5,
        "leads_per_run": 8,
        "chat_messages_per_day": 100,
        "brand_documents_total": 50,
        "pipeline_days_per_week": [0, 1, 2, 3, 4, 5, 6],
        "newsletter_enabled": True,
        "max_platform_connections": 10,
    },
}


def get_limits_for_tier(tier: str) -> dict:
    """Return limits dict for a tier. Unknown tiers get starter limits."""
    return TIER_LIMITS.get(tier, TIER_LIMITS["starter"])


def _usage_key(tenant_id: str, action: str, date_str: str) -> str:
    return f"usage:{tenant_id}:{action}:{date_str}"


def _today_str(timezone_name: str = "UTC") -> str:
    try:
        tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).strftime("%Y-%m-%d")


def check_limit(
    tenant_id: str,
    tier: str,
    action: str,
    timezone_name: str = "UTC",
) -> tuple[bool, int, int]:
    """Check if a daily action is within limits.

    Returns (allowed, current_count, limit).
    """
    limits = get_limits_for_tier(tier)
    limit = limits.get(action)
    if limit is None:
        return (True, 0, 0)

    date_str = _today_str(timezone_name)
    key = _usage_key(tenant_id, action, date_str)
    current = counter_get(key)
    return (current < limit, current, limit)


def increment_usage(
    tenant_id: str,
    action: str,
    timezone_name: str = "UTC",
) -> int:
    """Increment a daily usage counter. Returns new count."""
    date_str = _today_str(timezone_name)
    key = _usage_key(tenant_id, action, date_str)
    return counter_increment(key, ttl_seconds=172800)  # 48h


def is_pipeline_day(tier: str, timezone_name: str = "UTC") -> bool:
    """Check if today is a pipeline day for this tier."""
    limits = get_limits_for_tier(tier)
    allowed_days = limits.get("pipeline_days_per_week", [])
    try:
        tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo("UTC")
    today_weekday = datetime.now(tz).weekday()
    return today_weekday in allowed_days


def get_usage_summary(
    tenant_id: str,
    tier: str,
    timezone_name: str = "UTC",
) -> dict[str, dict]:
    """Return usage summary for all daily-tracked actions."""
    limits = get_limits_for_tier(tier)
    date_str = _today_str(timezone_name)
    daily_actions = ["post_generations_per_day", "chat_messages_per_day"]

    summary: dict[str, dict] = {}
    for action in daily_actions:
        limit = limits.get(action, 0)
        key = _usage_key(tenant_id, action, date_str)
        used = counter_get(key)
        summary[action] = {
            "used": used,
            "limit": limit,
            "percentage": round(used / limit * 100, 1) if limit > 0 else 0,
        }

    # Add non-daily limits for display
    summary["intelligence_items_per_run"] = {
        "limit": limits["intelligence_items_per_run"]
    }
    summary["leads_per_run"] = {"limit": limits["leads_per_run"]}
    summary["brand_documents_total"] = {"limit": limits["brand_documents_total"]}
    summary["newsletter_enabled"] = {"enabled": limits["newsletter_enabled"]}
    summary["max_platform_connections"] = {"limit": limits["max_platform_connections"]}
    summary["pipeline_days_per_week"] = {"days": limits["pipeline_days_per_week"]}

    return summary


def require_usage_limit(
    tenant_id: str,
    tier: str,
    action: str,
    timezone_name: str = "UTC",
) -> None:
    """Raise 429 if limit is exceeded. Call before the action."""
    allowed, current, limit = check_limit(tenant_id, tier, action, timezone_name)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit reached: {current}/{limit} {action.replace('_', ' ')}. "
            f"Upgrade to Pro for higher limits.",
        )
