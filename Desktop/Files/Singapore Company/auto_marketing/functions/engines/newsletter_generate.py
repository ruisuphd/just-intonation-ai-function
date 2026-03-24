"""Email newsletter generation engine -- runs weekly, produces a digest from the week's top intel."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prompts.email_newsletter import (
    SYSTEM_PROMPT,
    TEMPERATURE,
    RESPONSE_MODEL,
    build_user_message,
)
from shared.datetime_utils import coerce_datetime
from shared.firestore_client import add_doc, query_docs
from shared.gemini_client import GeminiClient
from shared.logger import get_logger
from shared.retriever import Retriever

logger = get_logger("engine.newsletter_generate")


async def generate_newsletter(
    tenant_id: str,
    company_name: str = "",
) -> dict:
    """Generate a weekly newsletter from the past 7 days of intelligence."""

    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    cutoff = now - timedelta(days=7)

    # ── Dedup: skip if a newsletter already exists for this week_start ─────
    existing = query_docs(
        "newsletters",
        filters=[("week_start", "==", week_start)],
        limit=1,
        tenant_id=tenant_id,
    )
    if existing:
        logger.info(
            "newsletter.duplicate_skipped",
            extra={"tenant_id": tenant_id, "week_start": week_start},
        )
        return {
            "status": "skipped",
            "reason": f"A newsletter for the week of {week_start} already exists.",
        }

    try:
        weekly_items = query_docs(
            "intelligence_items",
            filters=[("gathered_at", ">=", cutoff)],
            order_by="-relevance_score",
            limit=10,
            tenant_id=tenant_id,
        )
    except Exception:
        weekly_items = query_docs(
            "intelligence_items",
            order_by="-relevance_score",
            limit=50,
            tenant_id=tenant_id,
        )
        weekly_items = [
            item
            for item in weekly_items
            if (dt := coerce_datetime(item.get("gathered_at"))) and dt >= cutoff
        ][:10]

    if not weekly_items:
        logger.info("newsletter.no_intel", extra={"tenant_id": tenant_id})
        return {"status": "skipped", "reason": "no intelligence items this week"}

    retriever = Retriever(top_k=4, tenant_id=tenant_id)
    query = " ".join(item.get("title", "") for item in weekly_items[:3])
    chunks, _ = retriever.retrieve(query, language="en")
    brand_context = [
        {"text": c.get("text", ""), "doc_type": c.get("doc_type", "other")}
        for c in chunks
    ]

    user_message = build_user_message(
        brand_context=brand_context,
        weekly_intel=weekly_items,
        company_name=company_name,
    )

    client = GeminiClient()
    result = await client.generate(
        SYSTEM_PROMPT,
        user_message,
        temperature=TEMPERATURE,
        response_model=RESPONSE_MODEL,
        task_name="email_newsletter",
    )

    newsletter_data = {
        "week_start": week_start,
        "subject": result.subject,
        "preview_text": result.preview_text,
        "html_body": result.html_body,
        "plain_body": result.plain_body,
        "intel_count": len(weekly_items),
        "status": "draft",
        "created_at": now,
    }
    doc_id = add_doc("newsletters", newsletter_data, tenant_id=tenant_id)

    logger.info(
        "newsletter.generated",
        extra={
            "tenant_id": tenant_id,
            "doc_id": doc_id,
            "intel_count": len(weekly_items),
        },
    )
    return {"status": "generated", "newsletter_id": doc_id, **newsletter_data}
