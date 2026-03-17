"""Usage tracking API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.middleware.auth import require_tenant
from shared.models import TenantProfile
from shared.usage_limits import get_usage_summary

router = APIRouter(prefix="/api/usage", tags=["usage"])


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
    return {"tier": tier, "usage": summary}
