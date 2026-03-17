"""Concise daily social post generation engine."""

from __future__ import annotations

from prompts.daily_post import (
    SYSTEM_PROMPT,
    TEMPERATURE,
    RESPONSE_MODEL,
    build_user_message,
)
from shared.gemini_client import GeminiClient
from shared.firestore_client import query_docs
from shared.logger import get_logger
from shared.models import DailyPostResult
from shared.retriever import Retriever

logger = get_logger("engine.post_generate")


async def generate_daily_post(
    intelligence_summaries: list[str],
    intelligence_items: list[dict] | None = None,
    brand_context: list[dict] | None = None,
    tenant_id: str | None = None,
    tier: str = "starter",
) -> DailyPostResult:
    """Generate the daily English-only post pack.

    Args:
        intelligence_summaries: Summaries from top intelligence items.
        intelligence_items: Rich intelligence items used to select a stronger post angle.
        brand_context: Pre-fetched brand chunks. If None, retrieval is performed internally.

    Returns:
        DailyPostResult with platform-ready variants and an optional image prompt.
    """
    intelligence_items = intelligence_items or []

    if brand_context is None:
        query = (
            " ".join(intelligence_summaries[:2])
            if intelligence_summaries
            else "AI consulting"
        )
        retriever = Retriever(top_k=6, tenant_id=tenant_id)
        semantic_chunks, _ = retriever.retrieve(query, language="en")
        direct_chunks = query_docs(
            "brand_chunks",
            filters=[("doc_type", "in", ["brand_voice", "service_description"])],
            limit=6,
            tenant_id=tenant_id,
        )
        seen: set[tuple[object, object]] = set()
        merged_chunks: list[dict] = []
        for chunk in direct_chunks + semantic_chunks:
            key = (chunk.get("document_id"), chunk.get("chunk_index"))
            if key in seen:
                continue
            seen.add(key)
            merged_chunks.append(chunk)
        brand_context = [
            {"text": c.get("text", ""), "doc_type": c.get("doc_type", "other")}
            for c in merged_chunks
        ]

    from shared.firestore_client import get_doc

    guidelines_doc = get_doc("brand_guidelines", "current", tenant_id=tenant_id)
    system_prompt_to_use = SYSTEM_PROMPT
    if guidelines_doc:
        guidelines_text = (
            f"\n\n## Brand Guidelines\n"
            f"Dos: {', '.join(guidelines_doc.get('dos', []))}\n"
            f"Don'ts: {', '.join(guidelines_doc.get('donts', []))}\n"
            f"Vocabulary: {', '.join(guidelines_doc.get('vocabulary', []))}\n"
            f"Formatting Rules: {guidelines_doc.get('formatting_rules', '')}\n"
            f"Tone Formality (1-10): {guidelines_doc.get('tone_formality', 5)}\n"
            f"Tone Technicality (1-10): {guidelines_doc.get('tone_technicality', 5)}\n"
        )
        system_prompt_to_use += guidelines_text

    ranked_items = sorted(
        intelligence_items,
        key=lambda item: (
            item.get("postability_score") or 0.0,
            item.get("relevance_score") or 0.0,
        ),
        reverse=True,
    )
    selected_angle = ""
    source_titles = [
        item.get("title", "") for item in ranked_items[:2] if item.get("title")
    ]
    if ranked_items:
        best = ranked_items[0]
        selected_angle = (
            best.get("suggested_angle")
            or best.get("why_now")
            or best.get("summary")
            or best.get("title", "")
        )

    user_message = build_user_message(
        brand_context=brand_context,
        intelligence_summaries=intelligence_summaries,
        selected_angle=selected_angle,
        source_titles=source_titles,
    )

    client = GeminiClient()
    result: DailyPostResult = await client.generate(
        system_prompt=system_prompt_to_use,
        user_message=user_message,
        temperature=TEMPERATURE,
        response_model=RESPONSE_MODEL,
        task_name="linkedin",
        tier=tier,
    )

    logger.info(
        "post_generate.done",
        extra={
            "linkedin_chars": len(result.linkedin_post),
            "x_chars": len(result.x_post),
            "has_image_prompt": bool(result.image_prompt),
        },
    )
    return result


async def repurpose_post(
    source_text: str,
    target_platform: str,
    brand_context: list[dict] | None = None,
    tenant_id: str | None = None,
) -> str:
    """Repurpose a source post (e.g., LinkedIn) into a format for another platform (e.g., X thread)."""
    client = GeminiClient()

    brand_info = ""
    if brand_context:
        brand_info = "\n".join([c.get("text", "") for c in brand_context])

    from shared.firestore_client import get_doc

    guidelines_doc = get_doc("brand_guidelines", "current", tenant_id=tenant_id)
    guidelines_text = ""
    if guidelines_doc:
        guidelines_text = (
            f"\n\n## Brand Guidelines\n"
            f"Dos: {', '.join(guidelines_doc.get('dos', []))}\n"
            f"Don'ts: {', '.join(guidelines_doc.get('donts', []))}\n"
            f"Vocabulary: {', '.join(guidelines_doc.get('vocabulary', []))}\n"
            f"Formatting Rules: {guidelines_doc.get('formatting_rules', '')}\n"
            f"Tone Formality (1-10): {guidelines_doc.get('tone_formality', 5)}\n"
            f"Tone Technicality (1-10): {guidelines_doc.get('tone_technicality', 5)}\n"
        )

    system_prompt = (
        f"You are an expert social media manager. Your task is to repurpose the provided source text "
        f"into a highly engaging post optimized for {target_platform}.\n"
        f"Maintain the core message and value proposition, but adapt the tone, formatting, and structure "
        f"to fit {target_platform}'s best practices.\n"
        f"Brand Context:\n{brand_info}{guidelines_text}"
    )

    user_message = (
        f"Source Text:\n{source_text}\n\nPlease adapt this for {target_platform}."
    )

    from pydantic import BaseModel

    class RepurposeResult(BaseModel):
        content: str

    result = await client.generate(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.7,
        response_model=RepurposeResult,
        task_name=f"repurpose_{target_platform.lower()}",
    )

    return result.content
