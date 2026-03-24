"""Draft content API: list, get, update status, quick-generate."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator, model_validator

from api.middleware.auth import require_access
from api.middleware.legal import require_access_with_legal, require_access_with_legal_verified
from shared.usage_limits import require_usage_limit, increment_usage
from shared.datetime_utils import coerce_datetime
from shared.draft_utils import best_effort_post_topic, build_draft_payload
from shared.firestore_client import (
    add_doc,
    count_docs,
    delete_doc,
    get_doc,
    query_docs,
    query_docs_paginated,
    set_doc,
    update_doc,
)
from shared.logger import get_logger
from shared.models import CalendarEvent, PublishingRecord, TenantProfile
from shared.platforms import PLATFORM_MAP, normalize_platforms

logger = get_logger("api.drafts")

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


def _default_scheduled_for(
    batch_date: str, previous: datetime | None = None
) -> datetime:
    target_day = date.fromisoformat(batch_date)
    hour = previous.hour if previous is not None else 9
    minute = previous.minute if previous is not None else 0
    return datetime.combine(
        target_day,
        time(hour=hour, minute=minute, tzinfo=timezone.utc),
    )


def _draft_platforms(draft_doc: dict) -> list[str]:
    raw_platforms = draft_doc.get("platforms_generated") or []
    if not raw_platforms and draft_doc.get("platform"):
        raw_platforms = [draft_doc["platform"]]
    if not raw_platforms:
        return []
    return normalize_platforms(raw_platforms)


def _draft_sort_key(draft_doc: dict) -> datetime:
    return (
        coerce_datetime(draft_doc.get("created_at"))
        or coerce_datetime(draft_doc.get("updated_at"))
        or _default_scheduled_for(draft_doc.get("batch_date") or "1970-01-01")
    )


def _list_drafts_fallback(
    *,
    tenant_id: str,
    date: str | None,
    platform: str | None,
    status: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict], str | None]:
    docs = query_docs("drafts", limit=500, tenant_id=tenant_id)
    filtered = []
    for doc in docs:
        if date and doc.get("batch_date") != date:
            continue
        if status and doc.get("status") != status:
            continue
        if platform and platform not in _draft_platforms(doc):
            continue
        filtered.append(doc)

    filtered.sort(key=_draft_sort_key, reverse=True)

    start_index = 0
    if cursor:
        for index, doc in enumerate(filtered):
            if doc.get("id") == cursor:
                start_index = index + 1
                break

    page = filtered[start_index : start_index + limit]
    next_cursor = (
        page[-1]["id"] if start_index + limit < len(filtered) and page else None
    )
    return page, next_cursor


def _sync_scheduled_records(
    *,
    tenant_id: str,
    draft_id: str,
    draft_doc: dict,
    batch_date: str,
    scheduled_for: datetime,
) -> None:
    event = CalendarEvent(
        event_type="social_post",
        scheduled_for=scheduled_for,
        reference_id=draft_id,
        status="scheduled",
    )
    set_doc(
        "calendar_events",
        f"social_post_{draft_id}",
        {
            **event.model_dump(mode="json"),
            "batch_date": batch_date,
            "headline": draft_doc.get("headline", ""),
            "platforms": _draft_platforms(draft_doc),
        },
        tenant_id=tenant_id,
    )

    for platform in _draft_platforms(draft_doc):
        record_doc_id = f"{draft_id}:{platform}"
        existing_record = (
            get_doc("publishing_records", record_doc_id, tenant_id=tenant_id) or {}
        )
        if existing_record.get("status") == "published":
            continue
        record = PublishingRecord(
            post_id=draft_id,
            platform=platform,
            status="scheduled",
            external_id=existing_record.get("external_id"),
            error_message=None,
            scheduled_for=scheduled_for,
        )
        set_doc(
            "publishing_records",
            record_doc_id,
            {
                **record.model_dump(mode="json"),
                "headline": draft_doc.get("headline", ""),
                "batch_date": batch_date,
            },
            tenant_id=tenant_id,
        )


@router.get("")
async def list_drafts(
    date: str | None = None,
    platform: str | None = None,
    status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    tenant: TenantProfile = Depends(require_access("starter", "pro")),
):
    filters: list[tuple] = []
    if date:
        filters.append(("batch_date", "==", date))
    if status:
        filters.append(("status", "==", status))
    if platform:
        filters.append(("platforms_generated", "array_contains", platform))
    page_limit = min(limit, 100)
    try:
        docs, next_cursor = query_docs_paginated(
            "drafts",
            filters=filters or None,
            order_by="-created_at",
            limit=page_limit,
            tenant_id=tenant.tenant_id,
            start_after_id=cursor,
        )
    except Exception as exc:
        logger.warning(
            "drafts.list_fallback",
            extra={
                "tenant_id": tenant.tenant_id,
                "status": status,
                "date": date,
                "platform": platform,
                "cursor": cursor,
                "error": str(exc),
            },
        )
        docs, next_cursor = _list_drafts_fallback(
            tenant_id=tenant.tenant_id,
            date=date,
            platform=platform,
            status=status,
            limit=page_limit,
            cursor=cursor,
        )
    out: dict = {"drafts": docs}
    if next_cursor:
        out["next_cursor"] = next_cursor
    return out


@router.get("/count")
async def count_drafts(
    status: str | None = None,
    tenant: TenantProfile = Depends(require_access("starter", "pro")),
):
    filters: list[tuple] = []
    if status:
        filters.append(("status", "==", status))
    n = await asyncio.to_thread(
        count_docs,
        "drafts",
        filters if filters else None,
        tenant_id=tenant.tenant_id,
    )
    return {"count": n}


@router.get("/{draft_id}")
async def get_draft(
    draft_id: str,
    tenant: TenantProfile = Depends(require_access("starter", "pro")),
):
    doc = get_doc("drafts", draft_id, tenant_id=tenant.tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Draft not found")
    return doc


class DraftStatusUpdate(BaseModel):
    status: str | None = None
    batch_date: str | None = None

    @field_validator("batch_date")
    @classmethod
    def validate_batch_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def ensure_update_present(self):
        if self.status is None and self.batch_date is None:
            raise ValueError("status or batch_date is required")
        return self


@router.patch("/{draft_id}/status")
async def update_draft_status(
    draft_id: str,
    body: DraftStatusUpdate,
    tenant: TenantProfile = Depends(require_access_with_legal("starter", "pro")),
):
    existing_doc = get_doc("drafts", draft_id, tenant_id=tenant.tenant_id)
    if not existing_doc:
        raise HTTPException(status_code=404, detail="Draft not found")

    updates: dict[str, object] = {"updated_at": datetime.now(timezone.utc)}
    if body.status is not None:
        updates["status"] = body.status
    if body.batch_date is not None:
        updates["batch_date"] = body.batch_date

    effective_status = body.status or existing_doc.get("status")
    effective_batch_date = (
        body.batch_date
        or existing_doc.get("batch_date")
        or datetime.now(timezone.utc).date().isoformat()
    )

    if effective_status == "scheduled":
        scheduled_for = _default_scheduled_for(
            effective_batch_date,
            previous=coerce_datetime(existing_doc.get("scheduled_for")),
        )
        updates["status"] = "scheduled"
        updates["batch_date"] = effective_batch_date
        updates["scheduled_for"] = scheduled_for

    update_doc(
        "drafts",
        draft_id,
        updates,
        tenant_id=tenant.tenant_id,
    )
    updated_doc = {**existing_doc, **updates, "id": draft_id}

    if updated_doc.get("status") == "scheduled" and updated_doc.get("batch_date"):
        _sync_scheduled_records(
            tenant_id=tenant.tenant_id,
            draft_id=draft_id,
            draft_doc=updated_doc,
            batch_date=updated_doc["batch_date"],
            scheduled_for=updated_doc["scheduled_for"],
        )

    return {"ok": True, "draft": updated_doc}


def _cleanup_scheduled_draft(*, tenant_id: str, draft_id: str, draft_doc: dict) -> None:
    """Remove calendar_events and publishing_records for a scheduled draft."""
    platforms = _draft_platforms(draft_doc)
    ops: list[dict] = [
        {
            "action": "delete",
            "collection": "calendar_events",
            "doc_id": f"social_post_{draft_id}",
            "tenant_id": tenant_id,
        },
    ]
    for platform in platforms:
        record_id = f"{draft_id}:{platform}"
        rec = get_doc("publishing_records", record_id, tenant_id=tenant_id) or {}
        if rec.get("status") != "published":
            ops.append(
                {
                    "action": "delete",
                    "collection": "publishing_records",
                    "doc_id": record_id,
                    "tenant_id": tenant_id,
                },
            )
    from shared.firestore_client import batch_write

    batch_write(ops)


@router.delete("/{draft_id}")
async def delete_draft(
    draft_id: str,
    tenant: TenantProfile = Depends(require_access_with_legal("starter", "pro")),
):
    existing_doc = get_doc("drafts", draft_id, tenant_id=tenant.tenant_id)
    if not existing_doc:
        raise HTTPException(status_code=404, detail="Draft not found")
    if existing_doc.get("status") == "scheduled":
        _cleanup_scheduled_draft(
            tenant_id=tenant.tenant_id,
            draft_id=draft_id,
            draft_doc=existing_doc,
        )
    delete_doc("drafts", draft_id, tenant_id=tenant.tenant_id)
    return {"ok": True}


class DraftContentUpdate(BaseModel):
    headline: str | None = None
    text: str | None = None
    content_by_platform: dict[str, str] | None = None
    hashtags: list[str] | None = None
    why_it_matters: str | None = None

    @field_validator("hashtags")
    @classmethod
    def validate_hashtags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [str(t).strip() for t in value if str(t).strip()][:10]


@router.patch("/{draft_id}")
async def update_draft_content(
    draft_id: str,
    body: DraftContentUpdate,
    tenant: TenantProfile = Depends(require_access_with_legal("starter", "pro")),
):
    existing_doc = get_doc("drafts", draft_id, tenant_id=tenant.tenant_id)
    if not existing_doc:
        raise HTTPException(status_code=404, detail="Draft not found")
    updates: dict[str, object] = {"updated_at": datetime.now(timezone.utc)}
    if body.headline is not None:
        updates["headline"] = (body.headline or "").strip()
    if body.text is not None:
        updates["text"] = (body.text or "").strip()
    if body.content_by_platform is not None:
        valid = {
            k: (v or "").strip()
            for k, v in body.content_by_platform.items()
            if k in PLATFORM_MAP
        }
        merged = dict(existing_doc.get("content_by_platform") or {})
        merged.update(valid)
        updates["content_by_platform"] = merged
        platforms_generated = [
            k for k in merged if k in PLATFORM_MAP and (merged.get(k) or "").strip()
        ]
        updates["platforms_generated"] = platforms_generated
    if body.hashtags is not None:
        updates["hashtags"] = body.hashtags
    if body.why_it_matters is not None:
        updates["why_it_matters"] = (body.why_it_matters or "").strip()
    if len(updates) <= 1:
        raise HTTPException(status_code=400, detail="No content fields to update")
    update_doc("drafts", draft_id, updates, tenant_id=tenant.tenant_id)
    updated_doc = {**existing_doc, **updates, "id": draft_id}
    return {"ok": True, "draft": updated_doc}


class QuickGenerateRequest(BaseModel):
    platform: str
    topic: str | None = None

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        platform = (value or "").strip()
        if platform not in PLATFORM_MAP:
            raise ValueError(f"Unsupported platform: {value}")
        return platform


@router.post("/quick-generate")
async def quick_generate(
    body: QuickGenerateRequest,
    request: Request,
    tenant: TenantProfile = Depends(require_access_with_legal_verified("starter", "pro")),
):
    tier = getattr(request.state, "tenant_tier", "starter")
    require_usage_limit(
        tenant.tenant_id, tier, "post_generations_per_day", tenant.timezone
    )

    from engines.post_generate import generate_daily_post
    from shared.retriever import Retriever

    topic = (body.topic or "").strip()
    if not topic:
        intel_docs = query_docs(
            "intelligence_items",
            order_by="-postability_score",
            limit=1,
            tenant_id=tenant.tenant_id,
        )
        if intel_docs:
            topic = intel_docs[0].get("summary") or intel_docs[0].get("title", "")

    if not topic:
        topic = best_effort_post_topic(tenant)

    retriever = Retriever(top_k=4, tenant_id=tenant.tenant_id)
    chunks, _ = retriever.retrieve(topic, language="en")
    brand_context = [
        {"text": c.get("text", ""), "doc_type": c.get("doc_type", "other")}
        for c in chunks
    ]

    result = await generate_daily_post(
        intelligence_summaries=[topic],
        brand_context=brand_context or None,
        tenant_id=tenant.tenant_id,
    )

    draft_payload = build_draft_payload(
        result,
        tenant=tenant,
        origin="quick_generate",
        primary_platform=body.platform,
        topic=topic,
        platforms_enabled=tenant.platforms_enabled,
    )
    draft_id = add_doc("drafts", draft_payload, tenant_id=tenant.tenant_id)
    increment_usage(tenant.tenant_id, "post_generations_per_day", tenant.timezone)
    return {"id": draft_id, **draft_payload}


@router.post("/{draft_id}/regenerate")
async def regenerate_draft(
    draft_id: str,
    request: Request,
    tenant: TenantProfile = Depends(require_access_with_legal_verified("starter", "pro")),
):
    existing_doc = get_doc("drafts", draft_id, tenant_id=tenant.tenant_id)
    if not existing_doc:
        raise HTTPException(status_code=404, detail="Draft not found")

    tier = getattr(request.state, "tenant_tier", "starter")
    require_usage_limit(
        tenant.tenant_id, tier, "post_generations_per_day", tenant.timezone
    )

    from engines.post_generate import generate_daily_post
    from shared.retriever import Retriever

    topic = (
        existing_doc.get("headline")
        or existing_doc.get("why_it_matters")
        or existing_doc.get("topic")
        or ""
    ).strip()
    platforms = _draft_platforms(existing_doc)
    primary_platform = platforms[0] if platforms else "linkedin"

    if not topic:
        intel_docs = query_docs(
            "intelligence_items",
            order_by="-postability_score",
            limit=1,
            tenant_id=tenant.tenant_id,
        )
        if intel_docs:
            topic = intel_docs[0].get("summary") or intel_docs[0].get("title", "")
    if not topic:
        topic = best_effort_post_topic(tenant)

    retriever = Retriever(top_k=4, tenant_id=tenant.tenant_id)
    chunks, _ = retriever.retrieve(topic, language="en")
    brand_context = [
        {"text": c.get("text", ""), "doc_type": c.get("doc_type", "other")}
        for c in chunks
    ]

    result = await generate_daily_post(
        intelligence_summaries=[topic],
        brand_context=brand_context or None,
        tenant_id=tenant.tenant_id,
    )

    draft_payload = build_draft_payload(
        result,
        tenant=tenant,
        origin="regenerate",
        primary_platform=primary_platform,
        topic=topic,
        platforms_enabled=tenant.platforms_enabled or platforms,
    )
    version = existing_doc.get("version", 0) + 1
    updates = {
        **draft_payload,
        "updated_at": datetime.now(timezone.utc),
        "version": version,
        "created_at": existing_doc.get("created_at") or draft_payload.get("created_at"),
    }
    update_doc("drafts", draft_id, updates, tenant_id=tenant.tenant_id)
    increment_usage(tenant.tenant_id, "post_generations_per_day", tenant.timezone)
    updated_doc = {**existing_doc, **updates, "id": draft_id}
    return updated_doc


class DraftFeedbackRequest(BaseModel):
    thumbs: str
    reason: str | None = None

    @field_validator("thumbs")
    @classmethod
    def validate_thumbs(cls, value: str) -> str:
        v = (value or "").strip().lower()
        if v not in ("up", "down"):
            raise ValueError("thumbs must be 'up' or 'down'")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        s = value.strip()
        if len(s) > 500:
            raise ValueError("reason must be at most 500 characters")
        return s or None


@router.post("/{draft_id}/feedback")
async def draft_feedback(
    draft_id: str,
    body: DraftFeedbackRequest,
    tenant: TenantProfile = Depends(require_access_with_legal("starter", "pro")),
):
    existing_doc = get_doc("drafts", draft_id, tenant_id=tenant.tenant_id)
    if not existing_doc:
        raise HTTPException(status_code=404, detail="Draft not found")
    now = datetime.now(timezone.utc)
    updates: dict = {
        "feedback_thumbs": body.thumbs,
        "feedback_at": now,
        "updated_at": now,
    }
    if body.reason is not None:
        updates["feedback_reason"] = body.reason
    update_doc(
        "drafts",
        draft_id,
        updates,
        tenant_id=tenant.tenant_id,
    )
    return {"ok": True, "thumbs": body.thumbs}
