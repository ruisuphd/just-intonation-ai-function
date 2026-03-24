"""Billing API: Stripe webhooks, portal, subscription status."""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.middleware.auth import require_tenant, require_tenant_verified
from shared.entitlements import (
    normalize_email,
    normalize_subscription_tier,
    resolve_access,
)
from shared.firestore_client import query_docs, update_tenant
from shared.redis_client import cache_delete_pattern, cache_get, cache_set
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


def _subscription_first_price_id(subscription_id: str) -> str | None:
    """First recurring price on a subscription (for Pricing Table checkouts without metadata)."""
    import stripe

    _ensure_stripe_api_key()
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        if not getattr(sub, "items", None) or not sub.items.data:
            return None
        price = sub.items.data[0].price
        return price.id if price else None
    except Exception as exc:
        logger.warning(
            "billing.subscription_price_lookup_failed",
            extra={"subscription_id": subscription_id, "error": str(exc)},
        )
        return None


def _cached_pro_price_snapshot() -> dict | None:
    """Stripe Price fields for displaying Pro on the billing page. Cached to limit API calls."""
    price_id = os.getenv("STRIPE_PRO_PRICE_ID", "")
    if not price_id:
        return None
    cache_key = f"stripe:pro_price:{price_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    import stripe

    _ensure_stripe_api_key()
    try:
        p = stripe.Price.retrieve(price_id)
        recurring = getattr(p, "recurring", None)
        interval = getattr(recurring, "interval", None) if recurring else None
        snap = {
            "pro_unit_amount": getattr(p, "unit_amount", None),
            "pro_currency": (getattr(p, "currency", None) or "usd").lower(),
            "pro_interval": interval or "month",
        }
        cache_set(cache_key, snap, ttl_seconds=300)
        return snap
    except Exception as exc:
        logger.warning("billing.pro_price_fetch_failed", extra={"error": str(exc)})
        return None


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

    event_id = event.get("id") or ""
    dedupe_key = f"stripe_webhook_evt:{event_id}" if event_id else ""
    if dedupe_key and cache_get(dedupe_key):
        logger.info("billing.webhook_duplicate", extra={"event_id": event_id})
        return {"received": True}

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

    if dedupe_key:
        cache_set(dedupe_key, {"processed": True}, ttl_seconds=86400 * 3)

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
    meta = session.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = dict(meta) if hasattr(meta, "items") else {}
    sub_details = session.get("subscription_details") or {}
    if not isinstance(sub_details, dict):
        sub_details = {}
    sub_details_meta = sub_details.get("metadata") or {}
    if not isinstance(sub_details_meta, dict):
        sub_details_meta = {}

    cref = str(session.get("client_reference_id") or "").strip()
    tenant_id = (
        meta.get("tenant_id") or sub_details_meta.get("tenant_id") or cref or ""
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
    requested_tier = normalize_subscription_tier(meta.get("target_tier"))
    if requested_tier == "pro":
        updates["subscription_tier"] = requested_tier
    elif session.get("subscription"):
        price_id = _subscription_first_price_id(session["subscription"])
        inferred = _tier_from_price_id(price_id or "")
        if inferred:
            updates["subscription_tier"] = inferred
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
    tenant: TenantProfile = Depends(require_tenant_verified),
):
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
        success_url=f"{app_url}/billing?checkout=success",
        cancel_url=f"{app_url}/billing?checkout=canceled",
        metadata={"tenant_id": tenant.tenant_id, "target_tier": tier},
        subscription_data={
            "metadata": {"tenant_id": tenant.tenant_id, "target_tier": tier}
        },
    )
    return {"url": session.url}


@router.get("/portal")
async def billing_portal(
    tenant: TenantProfile = Depends(require_tenant_verified),
):
    import stripe

    _ensure_stripe_api_key()

    if not tenant.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer linked")

    return_url = f"{_app_url()}/billing"
    session = stripe.billing_portal.Session.create(
        customer=tenant.stripe_customer_id,
        return_url=return_url,
    )
    return {"url": session.url}


@router.get("/invoices")
async def get_invoices(
    tenant: TenantProfile = Depends(require_tenant_verified),
    starting_after: str | None = None,
):
    """Return Stripe invoices for the tenant's customer. Supports pagination via starting_after."""
    import stripe

    _ensure_stripe_api_key()

    if not tenant.stripe_customer_id:
        return {"invoices": [], "has_more": False}

    try:
        list_params = {
            "customer": tenant.stripe_customer_id,
            "limit": 12,
            "status": "paid",
        }
        if starting_after:
            list_params["starting_after"] = starting_after
        invoices = stripe.Invoice.list(**list_params)
        return {
            "invoices": [
                {
                    "id": inv.id,
                    "number": inv.number,
                    "amount_paid": inv.amount_paid,
                    "currency": inv.currency,
                    "status": inv.status,
                    "created": inv.created,
                    "invoice_pdf": inv.invoice_pdf,
                }
                for inv in invoices.data
            ],
            "has_more": invoices.has_more,
        }
    except Exception as exc:
        logger.warning("billing.invoices_failed", extra={"error": str(exc)})
        return {"invoices": [], "has_more": False}


@router.get("/subscription")
async def get_subscription(
    tenant: TenantProfile = Depends(require_tenant),
):
    access = resolve_access(tenant)
    price_snap = _cached_pro_price_snapshot()
    payload: dict = {
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
    }
    if price_snap:
        payload.update(price_snap)
    return payload
