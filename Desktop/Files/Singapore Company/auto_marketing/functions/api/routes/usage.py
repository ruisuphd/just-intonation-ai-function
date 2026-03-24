"""Usage tracking API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.middleware.auth import require_tenant
from shared.firestore_client import query_docs
from shared.models import TenantProfile
from shared.usage_limits import get_usage_summary

router = APIRouter(prefix="/api/usage", tags=["usage"])

USAGE_LABELS: dict[str, str] = {
    "post_generations_per_day": "Posts generated today",
    "chat_messages_per_day": "AI chat messages",
    "intelligence_items_per_run": "Intelligence signals",
    "leads_per_run": "Leads qualified",
    "brand_documents_total": "Brand documents",
}


@router.get("")
async def get_usage(
    request: Request,
    tenant: TenantProfile = Depends(require_tenant),
):
    tier = getattr(request.state, "tenant_tier", "starter")
    summary = get_usage_summary(
        tenant_id=tenant.tenant_id,
        tier=tier,
        timezone_name=tenant.timezone,
    )
    doc_count = len(query_docs("documents", tenant_id=tenant.tenant_id))
    summary["brand_documents_total"] = {
        **summary.get("brand_documents_total", {}),
        "used": doc_count,
        "limit": summary.get("brand_documents_total", {}).get("limit", 3),
    }
    return {"tier": tier, "usage": summary, "labels": USAGE_LABELS}
