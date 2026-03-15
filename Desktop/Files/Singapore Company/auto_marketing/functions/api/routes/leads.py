"""Leads API: list, get, delete, enrich."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.middleware.auth import require_subscription
from engines.linkedin_enrichment import enrich_lead
from shared.firestore_client import (
    delete_doc,
    get_doc,
    query_docs,
    query_docs_paginated,
    update_doc,
)
from shared.logger import get_logger
from shared.models import TenantProfile
from shared.storage_client import delete_blob

logger = get_logger("api.leads")

router = APIRouter(prefix="/api/leads", tags=["leads"])


def _draft_body(draft_doc: dict) -> str:
    content = draft_doc.get("content") or {}
    return (content.get("body") or content.get("message") or "").strip()


def _draft_subject(draft_doc: dict) -> str:
    content = draft_doc.get("content") or {}
    return (content.get("subject") or "").strip()


class LeadUpdate(BaseModel):
    status: str | None = None
    last_contacted_at: datetime | None = None


@router.get("")
async def list_leads(
    limit: int = 20,
    cursor: str | None = None,
    tenant: TenantProfile = Depends(require_subscription("pro")),
):
    page_limit = min(limit, 50)
    docs, next_cursor = query_docs_paginated(
        "qualified_leads",
        order_by="-created_at",
        limit=page_limit,
        tenant_id=tenant.tenant_id,
        start_after_id=cursor,
    )
    if not docs:
        return {"leads": []}

    outreach_docs = query_docs(
        "outreach_drafts",
        order_by="-generated_at",
        limit=max(page_limit * 3, 50),
        tenant_id=tenant.tenant_id,
    )
    latest_outreach_by_lead: dict[str, dict] = {}
    for draft in outreach_docs:
        lead_id = draft.get("lead_id")
        if lead_id and lead_id not in latest_outreach_by_lead:
            latest_outreach_by_lead[lead_id] = draft

    enriched_docs = []
    for doc in docs:
        outreach_doc = latest_outreach_by_lead.get(doc.get("id"))
        if outreach_doc:
            doc = {
                **doc,
                "draft_content": _draft_body(outreach_doc),
                "draft_subject": _draft_subject(outreach_doc),
                "draft_type": outreach_doc.get("draft_type", ""),
                "outreach_status": outreach_doc.get("status", ""),
            }
        enriched_docs.append(doc)
    out: dict = {"leads": enriched_docs}
    if next_cursor:
        out["next_cursor"] = next_cursor
    return out


@router.get("/{lead_id}")
async def get_lead(
    lead_id: str,
    tenant: TenantProfile = Depends(require_subscription("pro")),
):
    doc = get_doc("qualified_leads", lead_id, tenant_id=tenant.tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Lead not found")
    return doc


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: str,
    update_data: LeadUpdate,
    tenant: TenantProfile = Depends(require_subscription("pro")),
):
    doc = get_doc("qualified_leads", lead_id, tenant_id=tenant.tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Lead not found")

    updates = {
        key: value
        for key, value in update_data.model_dump(exclude_none=True).items()
        if key in {"status", "last_contacted_at"}
    }

    if updates:
        if updates.get("status") == "contacted" and "last_contacted_at" not in updates:
            updates["last_contacted_at"] = datetime.now(timezone.utc)
        update_doc("qualified_leads", lead_id, updates, tenant_id=tenant.tenant_id)
        doc.update(updates)
        logger.info(
            "leads.updated",
            extra={
                "lead_id": lead_id,
                "tenant_id": tenant.tenant_id,
                "updates": updates,
            },
        )

    return doc


@router.post("/{lead_id}/enrich")
async def enrich_lead_endpoint(
    lead_id: str,
    tenant: TenantProfile = Depends(require_subscription("pro")),
):
    doc = get_doc("qualified_leads", lead_id, tenant_id=tenant.tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not doc.get("contact_linkedin_url"):
        raise HTTPException(
            status_code=400, detail="Lead has no LinkedIn URL to enrich"
        )
    await enrich_lead(tenant.tenant_id, lead_id)
    updated = get_doc("qualified_leads", lead_id, tenant_id=tenant.tenant_id)
    return updated


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    tenant: TenantProfile = Depends(require_subscription("pro")),
):
    doc = get_doc("qualified_leads", lead_id, tenant_id=tenant.tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Lead not found")

    delete_doc("qualified_leads", lead_id, tenant_id=tenant.tenant_id)

    bucket = os.getenv("BRAND_DOCS_BUCKET", "")
    for chunk_id in doc.get("brand_chunk_ids", []):
        try:
            if bucket:
                delete_blob(
                    bucket, f"leads/{lead_id}/{chunk_id}", tenant_id=tenant.tenant_id
                )
        except Exception:
            pass

    logger.info(
        "leads.deleted", extra={"lead_id": lead_id, "tenant_id": tenant.tenant_id}
    )
    return {"ok": True}
