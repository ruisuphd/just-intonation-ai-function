from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from shared.models import TenantProfile

STARTER_TIER = "starter"
PRO_TIER = "pro"
STARTER_ACCESS_DAYS = 7  # Keep for backward compat but unused

_DEFAULT_INTERNAL_EMAILS = {"yoryouyoi@gmail.com"}


@dataclass(frozen=True)
class AccessSnapshot:
    effective_tier: str
    access_source: str
    starter_access_expires_at: datetime | None
    starter_access_active: bool
    has_paid_subscription: bool
    can_manage_billing: bool
    can_start_checkout: bool


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalize_subscription_tier(raw: str | None) -> str:
    raw = (raw or "").strip().lower()
    if raw == "pro":
        return PRO_TIER
    return STARTER_TIER  # "free", "growth", "starter", empty, anything else → starter


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        try:
            return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def default_starter_access_expires_at(now: datetime | None = None) -> datetime:
    current = _as_utc(now or datetime.now(timezone.utc))
    return current + timedelta(days=STARTER_ACCESS_DAYS)


def internal_test_emails() -> set[str]:
    configured = {
        normalize_email(raw)
        for raw in os.getenv("INTERNAL_TEST_EMAILS", "").split(",")
        if normalize_email(raw)
    }
    return _DEFAULT_INTERNAL_EMAILS | configured


def is_internal_test_email(email: str | None) -> bool:
    return normalize_email(email) in internal_test_emails()


def derive_starter_access_expires_at(profile: TenantProfile) -> datetime | None:
    explicit = parse_datetime(profile.starter_access_expires_at)
    if explicit:
        return explicit

    # Preserve legacy starter trials that existed before the explicit free tier.
    if (
        normalize_subscription_tier(profile.subscription_tier) == STARTER_TIER
        and profile.subscription_status == "trialing"
        and not profile.is_internal
        and not (profile.stripe_subscription_id or profile.stripe_customer_id)
    ):
        return default_starter_access_expires_at(profile.created_at)

    return None


def has_paid_subscription(profile: TenantProfile) -> bool:
    normalized_tier = normalize_subscription_tier(profile.subscription_tier)
    if normalized_tier not in {STARTER_TIER, PRO_TIER}:
        return False
    if profile.subscription_status == "active":
        return True
    if profile.subscription_status == "trialing" and (
        profile.stripe_subscription_id or profile.stripe_customer_id
    ):
        return True
    return False


def resolve_access(
    profile: TenantProfile,
    *,
    now: datetime | None = None,
) -> AccessSnapshot:
    paid_subscription = has_paid_subscription(profile)

    if profile.is_internal:
        return AccessSnapshot(
            effective_tier=PRO_TIER,
            access_source="internal",
            starter_access_expires_at=None,
            starter_access_active=False,
            has_paid_subscription=False,
            can_manage_billing=False,
            can_start_checkout=False,
        )

    if paid_subscription and profile.stripe_subscription_id:
        return AccessSnapshot(
            effective_tier=normalize_subscription_tier(profile.subscription_tier),
            access_source="paid_subscription",
            starter_access_expires_at=None,
            starter_access_active=False,
            has_paid_subscription=True,
            can_manage_billing=bool(profile.stripe_customer_id),
            can_start_checkout=False,
        )

    return AccessSnapshot(
        effective_tier=STARTER_TIER,
        access_source="starter",
        starter_access_expires_at=None,
        starter_access_active=False,
        has_paid_subscription=False,
        can_manage_billing=bool(profile.stripe_customer_id),
        can_start_checkout=True,
    )
