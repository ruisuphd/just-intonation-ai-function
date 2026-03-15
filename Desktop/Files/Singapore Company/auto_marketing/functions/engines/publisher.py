"""Engine for publishing scheduled posts to social platforms."""

from __future__ import annotations

import os
from datetime import datetime, timezone
import traceback

from shared.firestore_client import (
    get_doc,
    get_tenant,
    query_collection_group,
    query_docs,
    update_doc,
)
from shared.logger import get_logger
from shared.models import PublishingRecord, TenantProfile

logger = get_logger("engine.publisher")

REAL_PUBLISHING_ENABLED = os.getenv("REAL_PUBLISHING_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)

PLATFORM_FIELDS = {
    "linkedin": "linkedin_post",
    "x_twitter": "x_post",
    "instagram": "instagram_caption",
    "google_business_profile": "google_business_profile_post",
    "tiktok": "tiktok_caption",
    "xiaohongshu": "xiaohongshu_post",
}


def _draft_text_for_platform(draft_doc: dict, platform: str) -> str:
    content_by_platform = draft_doc.get("content_by_platform") or {}
    text = content_by_platform.get(platform, "")
    if text:
        return text.strip()
    field_name = PLATFORM_FIELDS.get(platform, "")
    if field_name:
        return str(draft_doc.get(field_name, "")).strip()
    return str(draft_doc.get("text", "")).strip()


def _sync_parent_draft_status(
    *, tenant_id: str, post_id: str, published_at: datetime
) -> None:
    sibling_records = query_docs(
        "publishing_records",
        filters=[("post_id", "==", post_id)],
        tenant_id=tenant_id,
    )
    if sibling_records and all(
        record.get("status") == "published" for record in sibling_records
    ):
        update_doc(
            "drafts",
            post_id,
            {
                "status": "published",
                "published_at": published_at,
                "updated_at": published_at,
            },
            tenant_id=tenant_id,
        )
        if get_doc("calendar_events", f"social_post_{post_id}", tenant_id=tenant_id):
            update_doc(
                "calendar_events",
                f"social_post_{post_id}",
                {
                    "status": "published",
                    "published_at": published_at,
                },
                tenant_id=tenant_id,
            )


async def run_publisher() -> dict:
    """Find and publish all scheduled posts that are due.

    Uses a collection group query to find all scheduled publishing records
    across all tenants, avoiding the need to scan every tenant document.
    """
    now = datetime.now(timezone.utc)

    # Query scheduled records across all tenants directly
    due_records = query_collection_group(
        "publishing_records",
        filters=[
            ("status", "==", "scheduled"),
            ("scheduled_for", "<=", now),
        ],
        limit=200,
    )

    processed = 0
    published = 0
    failed = 0

    # Cache tenant profiles to avoid repeated lookups
    tenant_cache: dict[str, TenantProfile | None] = {}

    for record_data in due_records:
        tenant_id = record_data.get("tenant_id", "")
        if not tenant_id:
            logger.warning(
                "publisher.missing_tenant_id",
                extra={"record_id": record_data.get("id")},
            )
            continue

        # Load and cache tenant profile
        if tenant_id not in tenant_cache:
            tenant_doc = get_tenant(tenant_id)
            if tenant_doc:
                try:
                    tenant_cache[tenant_id] = TenantProfile.model_validate(tenant_doc)
                except Exception as exc:
                    logger.warning(
                        "publisher.invalid_tenant",
                        extra={"tenant_id": tenant_id, "error": str(exc)},
                    )
                    tenant_cache[tenant_id] = None
            else:
                tenant_cache[tenant_id] = None

        profile = tenant_cache.get(tenant_id)
        if not profile:
            continue

        try:
            record = PublishingRecord.model_validate(record_data)
            processed += 1

            platform = record.platform.lower()
            credentials = profile.platform_credentials.get(platform)

            if not credentials:
                raise ValueError(f"No credentials found for platform: {platform}")

            draft_doc = get_doc("drafts", record.post_id, tenant_id=tenant_id)
            if not draft_doc:
                raise ValueError(f"Draft not found for post_id={record.post_id}")

            content_text = _draft_text_for_platform(draft_doc, platform)
            if not content_text:
                raise ValueError(f"No draft content found for platform: {platform}")

            external_id: str | None = None
            provider = "mock"

            if REAL_PUBLISHING_ENABLED and platform in ("linkedin", "x_twitter"):
                from shared.platform_clients import publish_linkedin, publish_x

                access_token = credentials.access_token
                if platform == "linkedin":
                    author_urn = credentials.platform_id or "urn:li:person:unknown"
                    ext_id, err = await publish_linkedin(
                        access_token=access_token,
                        author_urn=author_urn,
                        text=content_text,
                    )
                    if err:
                        raise ValueError(err)
                    external_id = ext_id
                    provider = "linkedin"
                elif platform == "x_twitter":
                    ext_id, err = await publish_x(
                        access_token=access_token, text=content_text
                    )
                    if err:
                        raise ValueError(err)
                    external_id = ext_id
                    provider = "x"

            if external_id is None:
                external_id = f"mock_{platform}_{record.post_id}"

            logger.info(
                "publisher.published",
                extra={
                    "tenant_id": tenant_id,
                    "post_id": record.post_id,
                    "platform": platform,
                    "provider": provider,
                },
            )

            if "id" in record_data:
                published_at = datetime.now(timezone.utc)
                update_doc(
                    "publishing_records",
                    record_data["id"],
                    {
                        "status": "published",
                        "external_id": external_id,
                        "published_at": published_at,
                        "content_length": len(content_text),
                        "provider": provider,
                    },
                    tenant_id=tenant_id,
                )
                _sync_parent_draft_status(
                    tenant_id=tenant_id,
                    post_id=record.post_id,
                    published_at=published_at,
                )
            published += 1

        except Exception as exc:
            failed += 1
            logger.error(
                "publisher.record_failed",
                extra={
                    "tenant_id": tenant_id,
                    "record_id": record_data.get("id"),
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )

            # Update record to failed
            if "id" in record_data:
                update_doc(
                    "publishing_records",
                    record_data["id"],
                    {"status": "failed", "error_message": str(exc)},
                    tenant_id=tenant_id,
                )

    return {"processed": processed, "published": published, "failed": failed}
