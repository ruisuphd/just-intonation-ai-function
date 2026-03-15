from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import numpy as np

from prompts.intelligence_scorer import SYSTEM_PROMPT as SCORER_PROMPT
from prompts.intelligence_scorer import build_user_message
from shared.gemini_client import GeminiClient
from shared.embedder import Embedder
from shared.firestore_client import add_doc, query_docs
from shared.logger import get_logger
from shared.models import (
    IntelligenceItem,
    IntelligenceScoreResult,
    IntelligenceSource,
    ProspectSignal,
)
from shared.source_adapters.base import RawItem, SourceAdapter
from shared.source_adapters.rss import RSSAdapter

logger = get_logger("engine.intelligence")

# IntelligenceSource.type "rss" -> IntelligenceItem.source_type "rss_competitor"
_SOURCE_TYPE_MAP: dict[str, str] = {"rss": "rss_competitor"}
_DEDUP_SCAN_LIMIT = max(1, int(os.getenv("INTELLIGENCE_DEDUP_SCAN_LIMIT", "1000")))
_MAX_ITEMS_TO_SCORE = max(1, int(os.getenv("INTELLIGENCE_MAX_ITEMS_TO_SCORE", "120")))
_SEMANTIC_DEDUP_MAX = max(1, int(os.getenv("INTELLIGENCE_SEMANTIC_DEDUP_MAX", "120")))
_DEFAULT_FIRM_SERVICES = [
    "Production ML deployment",
    "GenAI and RAG systems",
    "Agentic AI workflows",
    "Real-time AI systems",
    "AI strategy and feasibility assessment",
    "AI workshops and technical training",
]
_DEFAULT_TARGET_VERTICALS = [
    "startups",
    "SMEs",
    "fintech",
    "SaaS",
    "music-tech",
    "product and engineering teams adopting AI",
]


def _build_adapters(
    sources: list[dict],
) -> list[tuple[SourceAdapter, str]]:
    """Return (adapter, mapped_source_type) pairs."""
    adapters: list[tuple[SourceAdapter, str]] = []

    for src in sources:
        cfg = IntelligenceSource.model_validate(src)
        if not cfg.enabled:
            continue

        if cfg.type in ("google_news_rss", "rss", "crunchbase_rss", "techcrunch_rss"):
            if cfg.url:
                mapped = _SOURCE_TYPE_MAP.get(cfg.type, cfg.type)
                adapters.append(
                    (RSSAdapter(feed_url=cfg.url, source_name=cfg.name), mapped)
                )
        elif cfg.type == "reddit":
            logger.info(
                "intelligence.skip_removed_source",
                extra={"source_name": cfg.name, "type": cfg.type},
            )
        else:
            logger.warning(
                "intelligence.skip_source",
                extra={"name": cfg.name, "type": cfg.type},
            )

    return adapters


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


async def run_and_return_items(
    sources: list[dict],
    *,
    tenant_id: str | None = None,
) -> list[dict]:
    """Fetch, score, dedup, store intelligence items. Returns scored items sorted by relevance.

    Args:
        sources: List of IntelligenceSource dicts (inline config — no Firestore lookup needed).

    Returns:
        List of stored intelligence item dicts, sorted by relevance_score descending.
    """
    logger.info(
        "intelligence.run_and_return_items.start",
        extra={"tenant_id": tenant_id or "root"},
    )

    adapters = _build_adapters(sources)

    # ── 2-3. Fetch items from every adapter ──────────────────────────────────
    all_raw: list[tuple[RawItem, str]] = []
    for adapter, source_type in adapters:
        try:
            items = await adapter.fetch_items()
            all_raw.extend((item, source_type) for item in items)
        except Exception as exc:
            logger.error(
                "intelligence.fetch_error",
                extra={"adapter": type(adapter).__name__, "error": str(exc)},
            )

    items_fetched = len(all_raw)
    if not all_raw:
        return []

    # ── 4. URL dedup against existing items within 48 h window ───────────────
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)
    existing_docs = query_docs(
        "intelligence_items",
        filters=[("gathered_at", ">=", cutoff)],
        order_by="-gathered_at",
        limit=_DEDUP_SCAN_LIMIT,
        tenant_id=tenant_id,
    )
    existing_urls: set[str] = {d.get("source_url") for d in existing_docs}

    new_raw = [
        (item, st) for item, st in all_raw if item.source_url not in existing_urls
    ]
    new_raw.sort(
        key=lambda pair: pair[0].published_at
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    if len(new_raw) > _MAX_ITEMS_TO_SCORE:
        logger.info(
            "intelligence.score_window_capped",
            extra={"before": len(new_raw), "max_items": _MAX_ITEMS_TO_SCORE},
        )
        new_raw = new_raw[:_MAX_ITEMS_TO_SCORE]
    logger.info(
        "intelligence.url_dedup",
        extra={"before": items_fetched, "after": len(new_raw)},
    )
    if not new_raw:
        return []

    # ── 5. Score each new item with Claude ───────────────────────────────────
    client = GeminiClient()
    scored: list[dict] = []

    for raw, source_type in new_raw:
        try:
            user_msg = build_user_message(
                raw_title=raw.title,
                raw_content=raw.raw_content[:3000],
                firm_services=_DEFAULT_FIRM_SERVICES,
                target_verticals=_DEFAULT_TARGET_VERTICALS,
            )
            result: IntelligenceScoreResult = await client.generate(
                system_prompt=SCORER_PROMPT,
                user_message=user_msg,
                temperature=0.2,
                response_model=IntelligenceScoreResult,
                task_name="intelligence_scorer",
            )
            scored.append(
                {
                    "raw": raw,
                    "result": result,
                    "source_type": source_type,
                }
            )
        except Exception as exc:
            logger.error(
                "intelligence.score_error",
                extra={"title": raw.title[:80], "error": str(exc)},
            )

    items_scored = len(scored)
    if not scored:
        return []

    # ── 6. Semantic dedup (in-memory, embeddings never persisted) ────────────
    scored.sort(
        key=lambda item: (
            item["result"].postability_score,
            item["result"].relevance_score,
        ),
        reverse=True,
    )
    semantic_candidates = scored[:_SEMANTIC_DEDUP_MAX]
    overflow_candidates = scored[_SEMANTIC_DEDUP_MAX:]
    if overflow_candidates:
        logger.info(
            "intelligence.semantic_window_capped",
            extra={
                "window": _SEMANTIC_DEDUP_MAX,
                "overflow_items": len(overflow_candidates),
            },
        )

    embedder = Embedder()
    titles = [s["raw"].title for s in semantic_candidates]
    embeddings = np.array(embedder.embed_texts(titles, task_type="SEMANTIC_SIMILARITY"))

    discard: set[int] = set()
    n = len(semantic_candidates)
    for i in range(n):
        if i in discard:
            continue
        for j in range(i + 1, n):
            if j in discard:
                continue
            if _cosine_sim(embeddings[i], embeddings[j]) > 0.85:
                si = semantic_candidates[i]["result"].relevance_score
                sj = semantic_candidates[j]["result"].relevance_score
                discard.add(j if si >= sj else i)

    surviving = [s for idx, s in enumerate(semantic_candidates) if idx not in discard]
    surviving.extend(overflow_candidates)
    items_deduped = len(semantic_candidates) - len(
        [s for idx, s in enumerate(semantic_candidates) if idx not in discard]
    )
    logger.info(
        "intelligence.semantic_dedup",
        extra={"discarded": items_deduped, "surviving": len(surviving)},
    )

    # ── 7. Write surviving items to Firestore ────────────────────────────────
    today = now.strftime("%Y-%m-%d")
    stored_items: list[dict] = []

    for s in surviving:
        raw: RawItem = s["raw"]
        res: IntelligenceScoreResult = s["result"]
        item = IntelligenceItem(
            tenant_id=tenant_id or "",
            source_url=raw.source_url,
            source_type=s["source_type"],
            source_name=raw.source_name,
            title=raw.title,
            raw_content=raw.raw_content,
            summary=res.summary,
            relevance_score=res.relevance_score,
            relevance_reasoning=res.relevance_reasoning,
            tags=res.tags,
            postability_score=res.postability_score,
            suggested_angle=res.suggested_angle,
            why_now=res.why_now,
            batch_date=today,
            gathered_at=now,
            dedup_window_expires=now + timedelta(hours=48),
            expires_at=now + timedelta(days=180),
        )
        try:
            add_doc("intelligence_items", item.model_dump(), tenant_id=tenant_id)
            stored_items.append(item.model_dump())
        except Exception as exc:
            logger.error(
                "intelligence.store_error",
                extra={"title": raw.title[:80], "error": str(exc)},
            )

    # Sort by posting strength first, then relevance.
    stored_items.sort(
        key=lambda x: (
            x.get("postability_score") or 0.0,
            x.get("relevance_score") or 0.0,
        ),
        reverse=True,
    )

    logger.info(
        "intelligence.run_and_return_items.done",
        extra={
            "items_fetched": items_fetched,
            "items_scored": items_scored,
            "items_deduped": items_deduped,
            "items_stored": len(stored_items),
            "tenant_id": tenant_id or "root",
        },
    )
    return stored_items


async def run(*, request=None, cloud_event=None) -> dict | None:
    """Legacy HTTP-trigger wrapper kept for backwards compatibility."""
    from shared.firestore_client import get_doc as _get_doc

    config_doc = _get_doc("system_config", "intelligence_sources")
    if not config_doc:
        logger.warning("intelligence.no_sources_configured")
        return {
            "items_fetched": 0,
            "items_scored": 0,
            "items_deduped": 0,
            "items_stored": 0,
        }
    items = await run_and_return_items(config_doc.get("sources", []))
    return {"items_stored": len(items)}


async def monitor_competitors(tenant_id: str):
    """Query competitors subcollection, mock scraping websites, and generate ProspectSignals and IntelligenceItems."""
    logger.info(
        "intelligence.monitor_competitors.start", extra={"tenant_id": tenant_id}
    )

    # Query competitors
    competitors = query_docs("competitors", tenant_id=tenant_id)
    if not competitors:
        logger.info(
            "intelligence.monitor_competitors.no_competitors",
            extra={"tenant_id": tenant_id},
        )
        return

    for comp in competitors:
        comp_id = comp.get("id")
        comp_name = comp.get("name", "Unknown Competitor")
        website = comp.get("website", "")

        logger.info(
            "intelligence.monitor_competitors.mock_scrape",
            extra={"tenant_id": tenant_id, "competitor": comp_name},
        )

        now = datetime.now(timezone.utc)

        # Mock IntelligenceItem
        intel_item = IntelligenceItem(
            tenant_id=tenant_id,
            source_url=website or f"https://{comp_name.lower().replace(' ', '')}.com",
            source_type="rss_competitor",
            source_name=comp_name,
            title=f"{comp_name} announced new feature",
            raw_content=f"Mock scraped content from {website} about {comp_name} new feature.",
            summary=f"{comp_name} released a new feature that competes with our core offering.",
            relevance_score=8.5,
            relevance_reasoning="Direct competitor feature launch",
            postability_score=7.0,
            suggested_angle="Highlight our superior alternative",
            why_now="Recent competitor announcement",
            batch_date=now.strftime("%Y-%m-%d"),
            gathered_at=now,
            competitor_id=comp_id,
        )
        add_doc("intelligence_items", intel_item.model_dump(), tenant_id=tenant_id)

        # Mock ProspectSignal
        signal = ProspectSignal(
            tenant_id=tenant_id,
            source_url=website or f"https://{comp_name.lower().replace(' ', '')}.com",
            source_type="rss_competitor",
            source_name=comp_name,
            title=f"{comp_name} changing pricing",
            raw_content=f"Mock scraped content from {website} about {comp_name} pricing changes.",
            summary=f"{comp_name} is increasing their prices, creating an opportunity for counter-positioning.",
            is_buying_signal=True,
            signal_type="competitor_move",
            strength_score=8,
            company_name=comp_name,
            reasoning="Competitor price increase is a strong signal to target their unhappy customers.",
            status="new",
            batch_date=now.strftime("%Y-%m-%d"),
            detected_at=now,
        )
        add_doc("signals", signal.model_dump(), tenant_id=tenant_id)

    logger.info("intelligence.monitor_competitors.done", extra={"tenant_id": tenant_id})
