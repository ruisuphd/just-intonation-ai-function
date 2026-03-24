"""Newsletter API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.middleware.auth import require_subscription
from api.middleware.legal import (
    require_subscription_with_legal,
    require_subscription_with_legal_verified,
)
from shared.firestore_client import add_doc, get_doc, query_docs_paginated
from shared.models import TenantProfile

router = APIRouter(prefix="/api/newsletters", tags=["newsletters"])


@router.get("")
async def list_newsletters(
    limit: int = 10,
    cursor: str | None = None,
    tenant: TenantProfile = Depends(require_subscription("pro")),
):
    page_limit = min(limit, 20)
    docs, next_cursor = query_docs_paginated(
        "newsletters",
        order_by="-created_at",
        limit=page_limit,
        tenant_id=tenant.tenant_id,
        start_after_id=cursor,
    )
    out: dict = {"newsletters": docs}
    if next_cursor:
        out["next_cursor"] = next_cursor
    return out


@router.post("/generate")
async def generate_newsletter_endpoint(
    tenant: TenantProfile = Depends(require_subscription_with_legal_verified("pro")),
):
    from engines.newsletter_generate import generate_newsletter

    result = await generate_newsletter(
        tenant_id=tenant.tenant_id,
        company_name=tenant.company_name,
    )
    return result


class ScheduleNewsletterRequest(BaseModel):
    newsletter_id: str
    scheduled_at: str
    platform: str = "ghost"


@router.post("/schedule")
async def schedule_newsletter_endpoint(
    body: ScheduleNewsletterRequest,
    tenant: TenantProfile = Depends(require_subscription_with_legal("pro")),
):
    newsletter_id = body.newsletter_id
    scheduled_at = body.scheduled_at
    platform = body.platform
    doc = get_doc("newsletters", newsletter_id, tenant_id=tenant.tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Newsletter not found")
    try:
        dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scheduled_at format")
    campaign_data = {
        "newsletter_id": newsletter_id,
        "subject": doc.get("subject", ""),
        "html_body": doc.get("html_body", doc.get("plain_body", "")),
        "platform": platform,
        "status": "scheduled",
        "scheduled_at": dt,
        "tenant_id": tenant.tenant_id,
    }
    campaign_id = add_doc(
        "newsletter_campaigns",
        campaign_data,
        tenant_id=tenant.tenant_id,
    )
    return {"ok": True, "campaign_id": campaign_id}
