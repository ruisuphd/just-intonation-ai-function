"""Calendar events API: unified view of scheduled drafts and newsletters."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.middleware.auth import require_access
from shared.datetime_utils import coerce_datetime
from shared.firestore_client import query_docs
from shared.models import TenantProfile

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/events")
async def list_calendar_events(
    tenant: TenantProfile = Depends(require_access("starter", "pro")),
):
    """Return scheduled drafts and newsletter campaigns for the calendar view."""
    drafts = query_docs(
        "drafts",
        filters=[("status", "==", "scheduled")],
        tenant_id=tenant.tenant_id,
        limit=100,
    )
    newsletter_campaigns = query_docs(
        "newsletter_campaigns",
        filters=[("status", "==", "scheduled")],
        tenant_id=tenant.tenant_id,
        limit=50,
    )
    campaigns_by_date: dict[str, list[dict]] = {}
    for c in newsletter_campaigns:
        dt = coerce_datetime(c.get("scheduled_at"))
        if dt:
            date_str = dt.strftime("%Y-%m-%d")
            if date_str not in campaigns_by_date:
                campaigns_by_date[date_str] = []
            campaigns_by_date[date_str].append(
                {"id": c.get("id"), "type": "newsletter", "subject": c.get("subject", "")}
            )
    return {
        "drafts": drafts,
        "newsletters_by_date": campaigns_by_date,
    }
