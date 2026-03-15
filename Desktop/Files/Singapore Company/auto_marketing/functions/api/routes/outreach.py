"""Outreach drafts API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.middleware.auth import require_subscription
from shared.firestore_client import query_docs
from shared.models import TenantProfile

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


@router.get("")
async def list_outreach(
    limit: int = 20,
    tenant: TenantProfile = Depends(require_subscription("pro")),
):
    docs = query_docs(
        "outreach_drafts",
        order_by="-generated_at",
        limit=min(limit, 50),
        tenant_id=tenant.tenant_id,
    )
    return {"drafts": docs}
