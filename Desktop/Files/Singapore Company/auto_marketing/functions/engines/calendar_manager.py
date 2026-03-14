"""Engine for managing content calendar and scheduling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.firestore_client import query_docs, add_doc, update_doc
from shared.logger import get_logger
from shared.models import CalendarEvent, DailyPostResult, NewsletterDraft

logger = get_logger("engine.calendar_manager")


def _coerce_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "to_datetime"):
        converted = value.to_datetime()
        return converted if converted.tzinfo else converted.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            converted = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (
                converted
                if converted.tzinfo
                else converted.replace(tzinfo=timezone.utc)
            )
        except ValueError:
            return None
    return None


async def manage_calendar() -> dict:
    """Ensure a consistent posting cadence by scheduling drafts and newsletters."""

    tenant_docs = query_docs("tenants")

    processed = 0
    scheduled = 0

    for tenant_doc in tenant_docs:
        tenant_id = tenant_doc.get("id") or tenant_doc.get("tenant_id")
        if not tenant_id:
            continue

        # Query unscheduled drafts (DailyPostResult)
        drafts = query_docs(
            "drafts", filters=[("status", "==", "draft")], tenant_id=tenant_id
        )

        # Query unscheduled newsletters (NewsletterDraft)
        newsletters = query_docs(
            "newsletters", filters=[("status", "==", "draft")], tenant_id=tenant_id
        )

        if not drafts and not newsletters:
            continue

        # Query existing calendar events to avoid overlaps
        now = datetime.now(timezone.utc)
        events = query_docs(
            "calendar_events",
            filters=[("scheduled_for", ">=", now)],
            order_by="scheduled_for",
            tenant_id=tenant_id,
        )

        # Determine next available slot (e.g., tomorrow at 9 AM)
        next_slot = now + timedelta(days=1)
        next_slot = next_slot.replace(hour=9, minute=0, second=0, microsecond=0)

        if events:
            last_event_time = _coerce_datetime(events[-1].get("scheduled_for"))
            if last_event_time is not None:
                next_slot = last_event_time + timedelta(days=1)
                next_slot = next_slot.replace(hour=9, minute=0, second=0, microsecond=0)

        for draft_data in drafts:
            try:
                # Validate it's a DailyPostResult or compatible draft
                _ = DailyPostResult.model_validate(
                    draft_data.get("post_data", draft_data)
                )
            except Exception as exc:
                logger.warning(
                    "calendar.invalid_draft",
                    extra={"error": str(exc), "draft_id": draft_data.get("id")},
                )
                continue

            # Create CalendarEvent
            event = CalendarEvent(
                event_type="social_post",
                scheduled_for=next_slot,
                reference_id=draft_data.get("id", ""),
                status="scheduled",
            )

            add_doc("calendar_events", event.model_dump(), tenant_id=tenant_id)

            # Update draft status
            update_doc(
                "drafts",
                draft_data.get("id", ""),
                {"status": "scheduled", "scheduled_for": next_slot},
                tenant_id=tenant_id,
            )

            next_slot += timedelta(days=1)
            scheduled += 1

        for newsletter_data in newsletters:
            try:
                _ = NewsletterDraft.model_validate(newsletter_data)
            except Exception as exc:
                logger.warning(
                    "calendar.invalid_newsletter",
                    extra={
                        "error": str(exc),
                        "newsletter_id": newsletter_data.get("id"),
                    },
                )
                continue

            # Create CalendarEvent
            event = CalendarEvent(
                event_type="newsletter",
                scheduled_for=next_slot,
                reference_id=newsletter_data.get("id", ""),
                status="scheduled",
            )

            add_doc("calendar_events", event.model_dump(), tenant_id=tenant_id)

            # Update newsletter status
            update_doc(
                "newsletters",
                newsletter_data.get("id", ""),
                {"status": "scheduled", "scheduled_for": next_slot},
                tenant_id=tenant_id,
            )

            next_slot += timedelta(days=1)
            scheduled += 1

        processed += 1

    return {"tenants_processed": processed, "events_scheduled": scheduled}
