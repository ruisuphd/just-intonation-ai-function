from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.middleware.auth import _build_default_tenant
from api.routes import billing
from shared.entitlements import resolve_access
from shared.models import TenantProfile


def _tenant(**overrides) -> TenantProfile:
    base = {
        "tenant_id": "tenant-1",
        "owner_uid": "uid-1",
        "owner_email": "owner@example.com",
        "company_name": "Example Co",
        "industry": "AI",
        "description": "Example description",
        "subscription_tier": "free",
        "subscription_status": "free",
        "created_at": datetime(2026, 3, 13, tzinfo=timezone.utc),
        "daily_digest_email": "owner@example.com",
    }
    base.update(overrides)
    return TenantProfile.model_validate(base)


def test_build_default_tenant_starts_with_free_and_starter_access():
    tenant = _build_default_tenant("uid-123", "yoryouyoi@gmail.com")

    assert tenant["subscription_tier"] == "free"
    assert tenant["subscription_status"] == "free"
    assert tenant["is_internal"] is True
    assert tenant["starter_access_expires_at"] > datetime.now(timezone.utc)


def test_resolve_access_uses_starter_window_before_free():
    profile = _tenant(
        starter_access_expires_at=datetime.now(timezone.utc) + timedelta(days=3),
    )

    access = resolve_access(profile)

    assert access.effective_tier == "starter"
    assert access.access_source == "starter_access"
    assert access.starter_access_active is True


def test_resolve_access_falls_back_to_free_after_starter_window():
    profile = _tenant(
        starter_access_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    access = resolve_access(profile)

    assert access.effective_tier == "free"
    assert access.access_source == "free"


def test_resolve_access_internal_account_bypasses_billing():
    profile = _tenant(is_internal=True)

    access = resolve_access(profile)

    assert access.effective_tier == "pro"
    assert access.access_source == "internal"
    assert access.can_manage_billing is False


def test_resolve_access_treats_paid_subscription_as_authoritative():
    profile = _tenant(
        subscription_tier="pro",
        subscription_status="active",
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
    )

    access = resolve_access(profile)

    assert access.effective_tier == "pro"
    assert access.access_source == "paid_subscription"
    assert access.has_paid_subscription is True
    assert access.can_start_checkout is False


def test_handle_subscription_updated_maps_price_to_starter(monkeypatch):
    updates: list[tuple[str, dict]] = []

    monkeypatch.setenv("STRIPE_STARTER_PRICE_ID", "price_starter")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro")
    monkeypatch.setattr(
        billing,
        "query_docs",
        lambda *args, **kwargs: [
            {"tenant_id": "tenant-1", "stripe_customer_id": "cus_123"}
        ],
    )
    monkeypatch.setattr(
        billing,
        "update_tenant",
        lambda tenant_id, payload: updates.append((tenant_id, payload)),
    )

    billing._handle_subscription_updated(
        {
            "customer": "cus_123",
            "status": "active",
            "id": "sub_123",
            "items": {"data": [{"price": {"id": "price_starter"}}]},
        }
    )

    assert updates == [
        (
            "tenant-1",
            {
                "subscription_status": "active",
                "stripe_subscription_id": "sub_123",
                "subscription_tier": "starter",
            },
        )
    ]


def test_handle_checkout_completed_sets_trialing_for_selected_tier(monkeypatch):
    updates: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        billing,
        "update_tenant",
        lambda tenant_id, payload: updates.append((tenant_id, payload)),
    )

    billing._handle_checkout_completed(
        {
            "customer": "cus_123",
            "subscription": "sub_123",
            "metadata": {
                "tenant_id": "tenant-1",
                "target_tier": "pro",
            },
        }
    )

    assert updates == [
        (
            "tenant-1",
            {
                "stripe_customer_id": "cus_123",
                "stripe_subscription_id": "sub_123",
                "subscription_tier": "pro",
                "subscription_status": "trialing",
            },
        )
    ]


def test_handle_subscription_deleted_resets_to_free(monkeypatch):
    updates: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        billing,
        "query_docs",
        lambda *args, **kwargs: [
            {"tenant_id": "tenant-1", "stripe_customer_id": "cus_123"}
        ],
    )
    monkeypatch.setattr(
        billing,
        "update_tenant",
        lambda tenant_id, payload: updates.append((tenant_id, payload)),
    )

    billing._handle_subscription_deleted({"customer": "cus_123"})

    assert updates == [
        (
            "tenant-1",
            {
                "subscription_status": "canceled",
                "subscription_tier": "free",
                "stripe_subscription_id": None,
            },
        )
    ]
