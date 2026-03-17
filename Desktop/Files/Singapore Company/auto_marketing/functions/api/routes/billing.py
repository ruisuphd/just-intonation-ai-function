"""Billing API: Stripe webhooks, portal, subscription status."""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.middleware.auth import require_tenant
from shared.entitlements import (
    normalize_email,
    normalize_subscription_tier,
    resolve_access,
)
from shared.firestore_client import query_docs, update_tenant
from shared.redis_client import cache_delete_pattern
from shared.logger import get_logger
from shared.models import TenantProfile
from shared.secrets import get_secret_or_env

logger = get_logger("api.billing")

router = APIRouter(prefix="/billing", tags=["billing"])


def _ensure_stripe_api_key() -> None:
    """Set the Stripe API key if not already set. Safe to call multiple times."""
    import stripe

    if not stripe.api_key:
        stripe.api_key = get_secret_or_env(
            secret_id="stripe-api-key",
            env_var="STRIPE_API_KEY",
        )


class BillingCheckoutRequest(BaseModel):
    tier: Literal["pro"]  # Only Pro is purchasable; Starter is free


def _app_url() -> str:
    return (os.getenv("APP_URL") or "http://localhost:3000").rstrip("/")


def _tier_from_price_id(price_id: str) -> str | None:
    pro_price = os.getenv("STRIPE_PRO_PRICE_ID", "")
    if pro_price and price_id == pro_price:
        return "pro"
    return None


def _price_id_for_tier(tier: str) -> str:
    if tier == "pro":
        return os.getenv("STRIPE_PRO_PRICE_ID", "")
    return ""


@router.post("/webhook")
async def stripe_webhook(request: Request):
    import stripe

    _ensure_stripe_api_key()

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    webhook_secret = get_secret_or_env(
        secret_id="stripe-webhook-secret",
        env_var="STRIPE_WEBHOOK_SECRET",
    )

    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]
    logger.info("billing.webhook", extra={"type": event_type})

    if event_type == "customer.subscription.updated":
        _handle_subscription_updated(data)
    elif event_type == "customer.subscription.created":
        _handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(data)
    elif event_type == "checkout.session.completed":
        _handle_checkout_completed(data)

    return {"received": True}


def _find_tenant_by_stripe_customer(customer_id: str) -> dict | None:
    docs = query_docs(
        "tenants", filters=[("stripe_customer_id", "==", customer_id)], limit=1
    )
    return docs[0] if docs else None


def _handle_subscription_updated(sub: dict):
    customer_id = sub.get("customer", "")
    tenant = _find_tenant_by_stripe_customer(customer_id)
    if not tenant:
        logger.warning("billing.tenant_not_found", extra={"customer": customer_id})
        return

    status = sub.get("status", "")
    status_map = {
        "active": "active",
        "trialing": "trialing",
        "past_due": "past_due",
        "canceled": "canceled",
        "incomplete": "past_due",
        "incomplete_expired": "canceled",
        "unpaid": "past_due",
    }
    mapped = status_map.get(status, "past_due")

    updates: dict = {"subscription_status": mapped}
    if sub.get("id"):
        updates["stripe_subscription_id"] = sub["id"]

    items = sub.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        tier = _tier_from_price_id(price_id)
        if tier:
            updates["subscription_tier"] = tier

    tenant_id = tenant.get("tenant_id") or tenant.get("id", "")
    update_tenant(tenant_id, updates)
    owner_uid = tenant.get("owner_uid", "")
    if owner_uid:
        cache_delete_pattern(f"tenant:uid:{owner_uid}*")
    logger.info(
        "billing.subscription_updated", extra={"tenant_id": tenant_id, **updates}
    )


def _handle_checkout_completed(session: dict):
    customer_id = session.get("customer", "")
    tenant_id = (
        session.get("metadata", {}).get("tenant_id")
        or session.get("subscription_details", {}).get("metadata", {}).get("tenant_id")
        or ""
    )
    if not tenant_id and customer_id:
        tenant = _find_tenant_by_stripe_customer(customer_id)
        tenant_id = tenant.get("tenant_id") if tenant else ""
    if not tenant_id:
        logger.warning(
            "billing.checkout_missing_tenant", extra={"customer": customer_id}
        )
        return

    updates: dict = {}
    if customer_id:
        updates["stripe_customer_id"] = customer_id
    if session.get("subscription"):
        updates["stripe_subscription_id"] = session["subscription"]
    requested_tier = normalize_subscription_tier(
        session.get("metadata", {}).get("target_tier")
    )
    if requested_tier == "pro":
        updates["subscription_tier"] = requested_tier
    updates["subscription_status"] = "trialing"
    update_tenant(tenant_id, updates)
    logger.info("billing.checkout_completed", extra={"tenant_id": tenant_id, **updates})


def _handle_subscription_deleted(sub: dict):
    customer_id = sub.get("customer", "")
    tenant = _find_tenant_by_stripe_customer(customer_id)
    if not tenant:
        return
    tenant_id = tenant.get("tenant_id") or tenant.get("id", "")
    update_tenant(
        tenant_id,
        {
            "subscription_status": "canceled",
            "subscription_tier": "starter",
            "stripe_subscription_id": None,
        },
    )
    logger.info("billing.subscription_deleted", extra={"tenant_id": tenant_id})


def _handle_payment_failed(invoice: dict):
    customer_id = invoice.get("customer", "")
    tenant = _find_tenant_by_stripe_customer(customer_id)
    if not tenant:
        return
    tenant_id = tenant.get("tenant_id") or tenant.get("id", "")
    update_tenant(tenant_id, {"subscription_status": "past_due"})
    logger.info("billing.payment_failed", extra={"tenant_id": tenant_id})


def _ensure_customer(tenant: TenantProfile, owner_email: str, company_name: str) -> str:
    import stripe

    if tenant.stripe_customer_id:
        return tenant.stripe_customer_id

    customer = stripe.Customer.create(
        email=normalize_email(owner_email) or None,
        name=company_name or None,
        metadata={"tenant_id": tenant.tenant_id},
    )
    update_tenant(tenant.tenant_id, {"stripe_customer_id": customer.id})
    return customer.id


@router.post("/checkout")
async def create_checkout_session(
    body: BillingCheckoutRequest,
    request: Request,
    tenant: TenantProfile = Depends(require_tenant),
):
    if request.state.bypass_billing:
        raise HTTPException(
            status_code=400, detail="Internal accounts do not have billing"
        )

    access = resolve_access(tenant)
    if access.has_paid_subscription and tenant.stripe_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="Paid subscriptions should be managed from the billing portal.",
        )

    tier = normalize_subscription_tier(body.tier)
    price_id = _price_id_for_tier(tier)
    if not price_id:
        raise HTTPException(
            status_code=500, detail=f"Stripe price not configured for {tier}"
        )

    import stripe

    _ensure_stripe_api_key()

    customer_id = _ensure_customer(
        tenant,
        owner_email=getattr(request.state, "email", ""),
        company_name=tenant.company_name,
    )

    app_url = _app_url()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        billing_address_collection="auto",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{app_url}/settings?tab=billing&checkout=success",
        cancel_url=f"{app_url}/settings?tab=billing&checkout=canceled",
        metadata={"tenant_id": tenant.tenant_id, "target_tier": tier},
        subscription_data={
            "metadata": {"tenant_id": tenant.tenant_id, "target_tier": tier}
        },
    )
    return {"url": session.url}


@router.get("/portal")
async def billing_portal(
    request: Request,
    tenant: TenantProfile = Depends(require_tenant),
):
    if request.state.bypass_billing:
        raise HTTPException(
            status_code=400, detail="Internal accounts do not have billing"
        )

    import stripe

    _ensure_stripe_api_key()

    if not tenant.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer linked")

    return_url = f"{_app_url()}/settings?tab=billing"
    session = stripe.billing_portal.Session.create(
        customer=tenant.stripe_customer_id,
        return_url=return_url,
    )
    return {"url": session.url}


@router.get("/subscription")
async def get_subscription(
    tenant: TenantProfile = Depends(require_tenant),
):
    access = resolve_access(tenant)
    return {
        "tenant_id": tenant.tenant_id,
        "subscription_tier": normalize_subscription_tier(tenant.subscription_tier),
        "subscription_status": tenant.subscription_status,
        "effective_tier": access.effective_tier,
        "access_source": access.access_source,
        "starter_access_expires_at": access.starter_access_expires_at,
        "starter_access_active": access.starter_access_active,
        "has_paid_subscription": access.has_paid_subscription,
        "can_manage_billing": access.can_manage_billing,
        "can_start_checkout": access.can_start_checkout,
        "stripe_customer_linked": bool(tenant.stripe_customer_id),
        "is_internal": tenant.is_internal,
    }
