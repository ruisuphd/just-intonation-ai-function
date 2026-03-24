"""Onboarding API: tenant creation, setup completion, document upload."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from api.middleware.auth import get_current_user, require_access
from api.middleware.legal import ensure_legal_acceptance, require_legal_acceptance
from shared.entitlements import normalize_email
from shared.firestore_client import update_tenant
from shared.logger import get_logger
from shared.platforms import normalize_platforms
from shared.upload_validation import validate_upload

logger = get_logger("api.onboarding")

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class TenantCreateRequest(BaseModel):
    company_name: str
    industry: str
    description: str
    website_url: str = ""
    target_audience: str = ""
    tone: str = "professional"
    language: str = "en"
    timezone: str = "Asia/Singapore"
    competitor_names: list[str] = []
    industry_keywords: list[str] = []
    platforms_enabled: list[str] = []
    daily_digest_enabled: bool = True
    daily_digest_email: str = ""
    notification_time: str = "07:00"
    tone_formal_casual: int = 50
    tone_technical_accessible: int = 50


class TenantCreateResponse(BaseModel):
    tenant_id: str
    stripe_client_secret: str | None = None
    checkout_url: str | None = None
    checkout_session_id: str | None = None


@router.post("/create-tenant", response_model=TenantCreateResponse)
async def create_tenant_endpoint(
    body: TenantCreateRequest,
    tenant=Depends(require_legal_acceptance),
    user: dict = Depends(get_current_user),
):
    email = user.get("email", "")
    updates = {
        "company_name": body.company_name,
        "industry": body.industry,
        "description": body.description,
        "website_url": body.website_url,
        "target_audience": body.target_audience,
        "tone": body.tone,
        "language": body.language,
        "timezone": body.timezone or "Asia/Singapore",
        "competitor_names": body.competitor_names[:5],
        "industry_keywords": body.industry_keywords[:10],
        "platforms_enabled": normalize_platforms(body.platforms_enabled),
        "daily_digest_enabled": body.daily_digest_enabled,
        "daily_digest_email": normalize_email(body.daily_digest_email or email),
        "notification_time": body.notification_time,
        "tone_formal_casual": max(0, min(100, body.tone_formal_casual)),
        "tone_technical_accessible": max(0, min(100, body.tone_technical_accessible)),
        "owner_email": normalize_email(email),
    }

    update_tenant(tenant.tenant_id, updates)
    logger.info(
        "onboarding.tenant_profile_updated", extra={"tenant_id": tenant.tenant_id}
    )

    return TenantCreateResponse(
        tenant_id=tenant.tenant_id,
    )


@router.post("/complete")
async def complete_onboarding(
    tenant=Depends(require_access("starter", "pro")),
):
    ensure_legal_acceptance(tenant)
    update_tenant(tenant.tenant_id, {"onboarding_completed": True})

    from shared.pipeline_runs import run_tenant_pipeline_with_record

    async def _first_pipeline() -> None:
        try:
            await run_tenant_pipeline_with_record(
                tenant.tenant_id,
                ignore_pipeline_schedule=True,
                force_send=False,
            )
        except Exception as exc:
            logger.error(
                "onboarding.pipeline_failed",
                extra={"tenant_id": tenant.tenant_id, "error": str(exc)},
            )

    asyncio.create_task(_first_pipeline())

    return {"ok": True, "tenant_id": tenant.tenant_id}


@router.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    tenant=Depends(require_access("starter", "pro")),
):
    ensure_legal_acceptance(tenant)
    content = await file.read()
    validated = validate_upload(file, len(content))

    from shared.storage_client import upload_bytes

    bucket = os.getenv("BRAND_DOCS_BUCKET", "")
    if not bucket:
        raise HTTPException(status_code=500, detail="Storage not configured")

    blob_path = f"documents/{validated.filename}"
    gs_path = upload_bytes(
        bucket,
        blob_path,
        content,
        content_type=validated.content_type,
        tenant_id=tenant.tenant_id,
    )

    from shared.firestore_client import add_doc

    doc_data = {
        "filename": validated.filename,
        "storage_path": gs_path,
        "file_type": validated.file_type,
        "file_size_bytes": len(content),
        "status": "uploaded",
        "uploaded_at": datetime.now(timezone.utc),
    }
    doc_id = add_doc("documents", doc_data, tenant_id=tenant.tenant_id)

    return {"ok": True, "document_id": doc_id, "storage_path": gs_path}
