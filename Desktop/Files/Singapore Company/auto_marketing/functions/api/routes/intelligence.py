"""Intelligence (Market Intel) API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.middleware.auth import require_access
from shared.firestore_client import query_docs_paginated
from shared.models import TenantProfile

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("")
async def list_intelligence(
    date: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
    tenant: TenantProfile = Depends(require_access("starter", "pro")),
):
    filters: list[tuple] = []
    if date:
        filters.append(("batch_date", "==", date))
    page_limit = min(limit, 50)
    docs, next_cursor = query_docs_paginated(
        "intelligence_items",
        filters=filters or None,
        order_by="-relevance_score",
        limit=page_limit,
        tenant_id=tenant.tenant_id,
        start_after_id=cursor,
    )
    out: dict = {"items": docs}
    if next_cursor:
        out["next_cursor"] = next_cursor
    return out
