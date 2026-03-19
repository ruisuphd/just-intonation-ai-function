from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.models import User, Subscription
from app.core.config import settings
from app.services.payment.stripe import stripe_service

router = APIRouter(prefix="/billing", tags=["billing"])


def _price_id_to_plan(price_id: str | None) -> str:
    if not price_id:
        return "essential"
    s = settings
    if price_id in (s.STRIPE_PRICE_ID_PRO_MONTHLY, s.STRIPE_PRICE_ID_PRO_YEARLY):
        return "pro"
    return "essential"


async def _persist_subscription_webhook(
    db: AsyncSession, result: dict
) -> None:
    customer_id = result.get("customer_id")
    if not customer_id:
        return
    result_select = await db.execute(
        select(Subscription).where(
            Subscription.stripe_customer_id == customer_id
        )
    )
    sub_row = result_select.scalar_one_or_none()
    if not sub_row:
        return
    if result["type"] in (
        "customer.subscription.created",
        "customer.subscription.updated",
    ):
        sub_row.stripe_sub_id = result.get("subscription_id")
        sub_row.status = result.get("status", "active")
        sub_row.current_period_end = result.get("current_period_end")
        if result.get("status") == "active":
            sub_row.plan = _price_id_to_plan(result.get("price_id"))
        else:
            sub_row.plan = "free"
    elif result["type"] == "customer.subscription.deleted":
        sub_row.stripe_sub_id = None
        sub_row.plan = "free"
        sub_row.status = "cancelled"
        sub_row.current_period_end = None


@router.get("/entitlements")
async def get_entitlements(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.entitlement import entitlement_service

    is_essential = await entitlement_service.is_essential(db, user.id)
    is_pro = await entitlement_service.is_pro(db, user.id)
    remaining = await entitlement_service.remaining_free_sessions(db, user.id)
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()
    return {
        "plan": (sub.plan or "free") if sub else "free",
        "is_essential": is_essential,
        "is_pro": is_pro,
        "remaining_free_sessions": remaining,
        "current_period_end": (
            sub.current_period_end.isoformat()
            if sub and sub.current_period_end
            else None
        ),
    }


@router.post("/checkout")
async def create_checkout(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()

    if not sub:
        customer_id = await stripe_service.create_customer(
            user.email or "", user.display_name or ""
        )
        sub = Subscription(
            user_id=user.id,
            stripe_customer_id=customer_id,
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)

    price_id = body.get("price_id")
    if not price_id:
        plan = body.get("plan")
        interval = body.get("interval", "monthly")
        if plan == "essential":
            price_id = (
                settings.STRIPE_PRICE_ID_ESSENTIAL_YEARLY
                if interval == "yearly"
                else settings.STRIPE_PRICE_ID_ESSENTIAL_MONTHLY
            )
        elif plan == "pro":
            price_id = (
                settings.STRIPE_PRICE_ID_PRO_YEARLY
                if interval == "yearly"
                else settings.STRIPE_PRICE_ID_PRO_MONTHLY
            )
        elif plan == "monthly":
            price_id = settings.STRIPE_PRICE_ID_ESSENTIAL_MONTHLY or settings.STRIPE_PRICE_ID_MONTHLY
        elif plan == "yearly":
            price_id = settings.STRIPE_PRICE_ID_ESSENTIAL_YEARLY or settings.STRIPE_PRICE_ID_YEARLY
    if not price_id:
        raise HTTPException(
            400,
            "price_id or plan (essential|pro) with interval (monthly|yearly) required"
        )

    url = await stripe_service.create_checkout_session(
        customer_id=sub.stripe_customer_id,
        price_id=price_id,
        success_url=f"{settings.FRONTEND_URL}/settings?payment=success",
        cancel_url=f"{settings.FRONTEND_URL}/settings?payment=cancelled",
    )
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        result = await stripe_service.handle_webhook(payload, sig)
        if result.get("type", "").startswith("customer.subscription"):
            await _persist_subscription_webhook(db, result)
        return {"received": True, "event": result}
    except ValueError:
        raise HTTPException(400, "Invalid webhook payload")
