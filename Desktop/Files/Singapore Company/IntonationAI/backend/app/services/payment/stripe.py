import asyncio
import logging
from datetime import UTC, datetime

import stripe

from app.core.config import settings

logger = logging.getLogger(__name__)

stripe.default_http_client = stripe.new_default_http_client(
    timeout=int(settings.STRIPE_HTTP_TIMEOUT_SEC),
)


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

    async def delete_customer(self, customer_id: str) -> None:
        def _delete() -> None:
            stripe.Customer.delete(customer_id)

        try:
            await asyncio.to_thread(_delete)
        except stripe.StripeError as e:
            logger.warning("Stripe delete_customer failed for %s: %s", customer_id, e)

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        trial_period_days: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        def _create() -> str:
            meta = {k: str(v)[:500] for k, v in (metadata or {}).items() if v is not None}
            kwargs: dict = {
                "customer": customer_id,
                "line_items": [{"price": price_id, "quantity": 1}],
                "mode": "subscription",
                "success_url": success_url,
                "cancel_url": cancel_url,
            }
            if meta:
                kwargs["metadata"] = meta
            sub_data: dict = {}
            if trial_period_days and trial_period_days > 0:
                sub_data["trial_period_days"] = trial_period_days
            if meta:
                sub_data["metadata"] = dict(meta)
            if sub_data:
                kwargs["subscription_data"] = sub_data
            session = stripe.checkout.Session.create(**kwargs)
            return session.url or ""

        try:
            return await asyncio.to_thread(_create)
        except stripe.StripeError as e:
            logger.exception("Stripe create_checkout_session failed: %s", e)
            raise

    def _subscription_dict_from_stripe_object(self, data: dict) -> dict:
        customer = data.get("customer")
        if isinstance(customer, dict):
            customer = customer.get("id")
        ts = data.get("current_period_end")
        cpe = datetime.fromtimestamp(ts, tz=UTC) if ts else None
        items = data.get("items", {}).get("data", [])
        price_id = None
        if items:
            price = items[0].get("price")
            price_id = (
                price
                if isinstance(price, str)
                else (price.get("id") if isinstance(price, dict) else None)
            )
        return {
            "subscription_id": data.get("id"),
            "customer_id": customer,
            "status": data.get("status"),
            "current_period_end": cpe,
            "price_id": price_id,
        }

    async def fetch_subscription_sync_payload(self, subscription_id: str) -> dict | None:
        def _get() -> dict | None:
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                return sub.to_dict()
            except stripe.InvalidRequestError:
                return None

        try:
            raw = await asyncio.to_thread(_get)
        except stripe.StripeError as e:
            logger.warning("Stripe retrieve subscription failed: %s", e)
            return None
        if not raw:
            return None
        return self._subscription_dict_from_stripe_object(raw)

    async def handle_webhook(self, payload: bytes, sig: str) -> dict:
        def _verify_and_parse() -> dict:
            event = stripe.Webhook.construct_event(
                payload,
                sig,
                settings.STRIPE_WEBHOOK_SECRET or "",
            )
            event_type = event["type"]
            data = event.get("data", {}).get("object", {})

            result: dict = {
                "type": event_type,
                "object_id": data.get("id"),
                "event_id": event.get("id"),
                "event_created": int(event.get("created") or 0),
            }

            if event_type in (
                "customer.subscription.created",
                "customer.subscription.updated",
            ):
                result.update(self._subscription_dict_from_stripe_object(data))
            elif event_type == "customer.subscription.deleted":
                result["subscription_id"] = data.get("id")
                cust = data.get("customer")
                result["customer_id"] = cust if isinstance(cust, str) else (cust or {}).get("id")

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
