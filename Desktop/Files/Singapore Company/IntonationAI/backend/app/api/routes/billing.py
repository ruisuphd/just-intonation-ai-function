import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_app_check_if_enforced
from app.core.config import settings
from app.db.base import get_db
from app.http_errors import AppHTTPException
from app.models import StripeEvent, Subscription, User
from app.services.payment.stripe import stripe_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

_CHECKOUT_RETURN_PATHS = frozenset({"/pricing", "/settings", "/dashboard"})


def _validate_checkout_return_path(raw: str | None, default: str) -> str:
    p = (raw if raw is not None else default).strip()
    if not p.startswith("/") or "//" in p or ".." in p or "\n" in p or "\r" in p:
        raise HTTPException(400, "Invalid success_path or cancel_path")
    path_only = p.split("?", 1)[0]
    if path_only not in _CHECKOUT_RETURN_PATHS:
        raise HTTPException(400, "Invalid success_path or cancel_path")
    return path_only


def _checkout_redirect_urls(body: dict) -> tuple[str, str]:
    base = (settings.FRONTEND_URL or "").rstrip("/")
    if not base:
        raise HTTPException(500, "FRONTEND_URL is not configured")
    success_path = _validate_checkout_return_path(body.get("success_path"), "/settings")
    cancel_path = _validate_checkout_return_path(body.get("cancel_path"), "/settings")
    success_url = f"{base}{success_path}?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base}{cancel_path}?payment=cancelled"
    return success_url, cancel_url


def _configured_price_ids() -> set[str]:
    s = settings
    raw = [
        s.STRIPE_PRICE_ID_MONTHLY,
        s.STRIPE_PRICE_ID_YEARLY,
        s.STRIPE_PRICE_ID_PRO_MONTHLY,
        s.STRIPE_PRICE_ID_PRO_YEARLY,
    ]
    return {x for x in raw if x}


def _price_id_to_plan(price_id: str | None) -> str:
    if not price_id:
        return "free"
    s = settings
    if price_id in (s.STRIPE_PRICE_ID_PRO_MONTHLY, s.STRIPE_PRICE_ID_PRO_YEARLY):
        return "pro"
    if price_id in (
        getattr(s, "STRIPE_PRICE_ID_MONTHLY", None),
        getattr(s, "STRIPE_PRICE_ID_YEARLY", None),
    ):
        return "pro"
    return "free"


async def _persist_subscription_webhook(db: AsyncSession, result: dict) -> None:
    customer_id = result.get("customer_id")
    if not customer_id:
        return
    result_select = await db.execute(
        select(Subscription).where(Subscription.stripe_customer_id == customer_id)
    )
    sub_row = result_select.scalar_one_or_none()
    if not sub_row:
        return

    event_created = int(result.get("event_created") or 0)
    prev_ts = sub_row.last_stripe_event_created or 0
    etype = result.get("type", "")

    if etype == "customer.subscription.deleted":
        sub_row.stripe_sub_id = None
        sub_row.plan = "free"
        sub_row.status = "cancelled"
        sub_row.current_period_end = None
        sub_row.last_stripe_event_created = max(prev_ts, event_created)
        return

    if event_created < prev_ts:
        return

    sub_id = result.get("subscription_id")
    if not sub_id:
        return

    live = await stripe_service.fetch_subscription_sync_payload(sub_id)
    if not live:
        sub_row.stripe_sub_id = None
        sub_row.plan = "free"
        sub_row.status = "cancelled"
        sub_row.current_period_end = None
        sub_row.last_stripe_event_created = max(prev_ts, event_created)
        return

    sub_row.stripe_sub_id = live.get("subscription_id")
    sub_row.status = live.get("status") or "active"
    sub_row.current_period_end = live.get("current_period_end")
    st = (live.get("status") or "").lower()
    if st == "active":
        sub_row.plan = _price_id_to_plan(live.get("price_id"))
    else:
        sub_row.plan = "free"
    sub_row.last_stripe_event_created = max(prev_ts, event_created)


@router.get("/entitlements")
async def get_entitlements(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    timezone_name: str | None = Query(None, alias="timezone"),
):
    from app.services.entitlement import entitlement_service

    is_pro = await entitlement_service.is_pro(db, user.id)
    remaining = await entitlement_service.remaining_free_sessions(
        db, user.id, timezone_name=timezone_name
    )
    result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    sub = result.scalar_one_or_none()
    plan = "pro" if is_pro else ((sub.plan or "free") if sub else "free")
    return {
        "plan": plan,
        "is_pro": is_pro,
        "remaining_free_sessions": remaining,
        "current_period_end": (
            sub.current_period_end.isoformat() if sub and sub.current_period_end else None
        ),
    }


@router.post("/checkout")
async def create_checkout(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _app_check: None = Depends(require_app_check_if_enforced),
):
    result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    sub = result.scalar_one_or_none()

    if not sub:
        try:
            new_customer_id = await stripe_service.create_customer(
                user.email or "", user.display_name or ""
            )
        except stripe.StripeError as e:
            logger.exception("Stripe create_customer failed: %s", e)
            raise AppHTTPException(
                status_code=502,
                code="stripe_error",
                message="Payment service is temporarily unavailable. Please try again.",
            ) from e
        await db.execute(
            insert(Subscription)
            .values(
                user_id=user.id,
                stripe_customer_id=new_customer_id,
            )
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await db.flush()
        result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
        sub = result.scalar_one_or_none()
        if not sub:
            await stripe_service.delete_customer(new_customer_id)
            raise HTTPException(500, "Subscription provisioning failed; please try again.")
        if sub.stripe_customer_id != new_customer_id:
            await stripe_service.delete_customer(new_customer_id)
        await db.commit()
        await db.refresh(sub)

    allowed = _configured_price_ids()
    price_id = body.get("price_id")
    if price_id:
        if not allowed:
            raise HTTPException(
                400,
                "Stripe price IDs are not configured on the server",
            )
        if price_id not in allowed:
            raise HTTPException(400, "Invalid price_id")
    if not price_id:
        interval = body.get("interval", "monthly")
        if interval == "yearly":
            price_id = settings.STRIPE_PRICE_ID_PRO_YEARLY or settings.STRIPE_PRICE_ID_YEARLY
        else:
            price_id = settings.STRIPE_PRICE_ID_PRO_MONTHLY or settings.STRIPE_PRICE_ID_MONTHLY
    if not price_id:
        raise HTTPException(
            400,
            "price_id or interval (monthly|yearly) required; configure STRIPE_PRICE_ID_PRO_*",
        )

    trial_days = body.get("trial_days")
    if trial_days is None and getattr(settings, "STRIPE_TRIAL_DAYS", None):
        trial_days = settings.STRIPE_TRIAL_DAYS

    success_url, cancel_url = _checkout_redirect_urls(body)
    meta = {"user_id": str(user.id)}

    try:
        url = await stripe_service.create_checkout_session(
            customer_id=sub.stripe_customer_id,
            price_id=price_id,
            success_url=success_url,
            cancel_url=cancel_url,
            trial_period_days=int(trial_days) if trial_days else None,
            metadata=meta,
        )
    except stripe.StripeError as e:
        logger.exception("Stripe checkout failed: %s", e)
        raise AppHTTPException(
            status_code=502,
            code="stripe_error",
            message="Payment service is temporarily unavailable. Please try again.",
        ) from e
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        result = await stripe_service.handle_webhook(payload, sig)
        event_id = result.get("event_id")
        if not event_id:
            raise ValueError("missing event id")
        ev_created = int(result.get("event_created") or 0)
        ins = await db.execute(
            insert(StripeEvent)
            .values(id=event_id, event_created=ev_created)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(StripeEvent.id)
        )
        if ins.scalar_one_or_none() is None:
            await db.commit()
            return {"received": True, "duplicate": True}
        if result.get("type", "").startswith("customer.subscription"):
            await _persist_subscription_webhook(db, result)
        await db.commit()
        return {"received": True}
    except ValueError:
        raise HTTPException(400, "Invalid webhook payload")
