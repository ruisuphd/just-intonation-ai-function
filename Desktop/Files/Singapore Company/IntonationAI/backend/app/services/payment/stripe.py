import asyncio
import logging
from datetime import datetime, timezone

import stripe

from app.core.config import settings

logger = logging.getLogger(__name__)


class StripeService:
    def __init__(self) -> None:
        stripe.api_key = settings.STRIPE_SECRET_KEY

    async def create_customer(self, email: str, name: str) -> str:
        def _create() -> str:
            customer = stripe.Customer.create(email=email, name=name)
            return customer.id

        try:
            return await asyncio.to_thread(_create)
        except stripe.StripeError as e:
            logger.exception("Stripe create_customer failed: %s", e)
            raise

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        def _create() -> str:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
            )
            return session.url or ""

        try:
            return await asyncio.to_thread(_create)
        except stripe.StripeError as e:
            logger.exception("Stripe create_checkout_session failed: %s", e)
            raise

    async def handle_webhook(self, payload: bytes, sig: str) -> dict:
        def _verify_and_parse() -> dict:
            event = stripe.Webhook.construct_event(
                payload,
                sig,
                settings.STRIPE_WEBHOOK_SECRET or "",
            )
            event_type = event["type"]
            data = event.get("data", {}).get("object", {})

            result: dict = {"type": event_type, "object_id": data.get("id")}

            if event_type in (
                "customer.subscription.created",
                "customer.subscription.updated",
            ):
                result["subscription_id"] = data.get("id")
                result["customer_id"] = data.get("customer")
                result["status"] = data.get("status")
                ts = data.get("current_period_end")
                result["current_period_end"] = (
                    datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
                )
                items = data.get("items", {}).get("data", [])
                if items:
                    price = items[0].get("price")
                    result["price_id"] = (
                        price if isinstance(price, str) else
                        (price.get("id") if isinstance(price, dict) else None)
                    )
            elif event_type == "customer.subscription.deleted":
                result["subscription_id"] = data.get("id")
                result["customer_id"] = data.get("customer")

            return result

        try:
            return await asyncio.to_thread(_verify_and_parse)
        except stripe.SignatureVerificationError as e:
            logger.warning("Stripe webhook signature verification failed: %s", e)
            raise ValueError("Invalid webhook signature")
        except stripe.StripeError as e:
            logger.exception("Stripe webhook processing failed: %s", e)
            raise


stripe_service = StripeService()
