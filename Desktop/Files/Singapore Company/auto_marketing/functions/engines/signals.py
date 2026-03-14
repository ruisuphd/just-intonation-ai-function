from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from prompts.signal_classifier import (
    SYSTEM_PROMPT,
    TEMPERATURE,
    build_user_message,
)
from shared.gemini_client import GeminiClient
from shared.firestore_client import add_doc, query_docs
from shared.logger import get_logger
from shared.models import IntelligenceSource, ProspectSignal, SignalClassificationResult
from shared.source_adapters.base import RawItem, SourceAdapter
from shared.source_adapters.rss import RSSAdapter

logger = get_logger("engine.signals")

_SIGNAL_CATEGORIES = {"funding", "competitor", "community"}
_SOURCE_TYPE_MAP: dict[str, str] = {"rss": "rss_competitor"}

_SIGNAL_TYPES = [
    "hiring_ai_role",
    "funding_received",
    "pain_point_expressed",
    "competitor_move",
    "digital_transformation_signal",
]
_TARGET_INDUSTRIES = [
    "fintech",
    "saas",
    "e-commerce",
    "healthcare",
    "education",
    "logistics",
]
_DEDUP_SCAN_LIMIT = max(1, int(os.getenv("SIGNALS_DEDUP_SCAN_LIMIT", "1000")))
_MAX_ITEMS_TO_CLASSIFY = max(1, int(os.getenv("SIGNALS_MAX_ITEMS_TO_CLASSIFY", "120")))


def _build_adapters(sources: list[dict]) -> list[tuple[SourceAdapter, str]]:
    adapters: list[tuple[SourceAdapter, str]] = []

    for src in sources:
        cfg = IntelligenceSource.model_validate(src)
        if not cfg.enabled:
            continue
        if cfg.category not in _SIGNAL_CATEGORIES:
            continue

        if cfg.type in ("google_news_rss", "rss", "crunchbase_rss", "techcrunch_rss"):
            if cfg.url:
                mapped = _SOURCE_TYPE_MAP.get(cfg.type, cfg.type)
                adapters.append(
                    (RSSAdapter(feed_url=cfg.url, source_name=cfg.name), mapped)
                )
        elif cfg.type == "reddit":
            logger.info(
                "signals.skip_removed_source",
                extra={"source_name": cfg.name, "type": cfg.type},
            )
        else:
            logger.warning(
                "signals.skip_source", extra={"name": cfg.name, "type": cfg.type}
            )

    return adapters


async def run_and_classify(
    sources: list[dict],
    max_signals: int = 10,
    *,
    tenant_id: str | None = None,
) -> list[dict]:
    """Fetch items, classify for buying signals, store confirmed signals, return them.

    Args:
        sources: List of IntelligenceSource dicts (inline config — no Firestore lookup).
        max_signals: Maximum number of buying signals to return (sorted by strength_score).

    Returns:
        List of ProspectSignal dicts for confirmed buying signals, sorted by strength_score desc.
    """
    logger.info(
        "signals.run_and_classify.start", extra={"tenant_id": tenant_id or "root"}
    )

    adapters = _build_adapters(sources)
    if not adapters:
        logger.info("signals.no_signal_adapters")
        return []

    all_raw: list[tuple[RawItem, str]] = []
    for adapter, source_type in adapters:
        try:
            items = await adapter.fetch_items()
            all_raw.extend((item, source_type) for item in items)
        except Exception as exc:
            logger.error(
                "signals.fetch_error",
                extra={"adapter": type(adapter).__name__, "error": str(exc)},
            )

    items_fetched = len(all_raw)
    if not all_raw:
        return []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)
    existing_docs = query_docs(
        "prospect_signals",
        filters=[("detected_at", ">=", cutoff)],
        order_by="-detected_at",
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
    if len(new_raw) > _MAX_ITEMS_TO_CLASSIFY:
        new_raw = new_raw[:_MAX_ITEMS_TO_CLASSIFY]
    logger.info(
        "signals.url_dedup",
        extra={"before": items_fetched, "after": len(new_raw)},
    )
    if not new_raw:
        return []

    client = GeminiClient()
    today = now.strftime("%Y-%m-%d")
    detected_signals: list[dict] = []

    for raw, source_type in new_raw:
        try:
            user_msg = build_user_message(
                raw_title=raw.title,
                raw_content=raw.raw_content[:3000],
                signal_types=_SIGNAL_TYPES,
                target_industries=_TARGET_INDUSTRIES,
            )
            result: SignalClassificationResult = await client.generate(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_msg,
                temperature=TEMPERATURE,
                response_model=SignalClassificationResult,
                task_name="signal_classifier",
            )

            if not result.is_buying_signal:
                continue

            signal = ProspectSignal(
                tenant_id=tenant_id or "",
                source_url=raw.source_url,
                source_type=source_type,
                source_name=raw.source_name,
                title=raw.title,
                raw_content=raw.raw_content,
                summary=result.summary,
                is_buying_signal=True,
                signal_type=result.signal_type,
                strength_score=result.strength_score,
                company_name=result.company_name,
                reasoning=result.reasoning,
                status="new",
                batch_date=today,
                detected_at=now,
                expires_at=now + timedelta(days=180),
            )
            add_doc("prospect_signals", signal.model_dump(), tenant_id=tenant_id)
            detected_signals.append(signal.model_dump())

        except Exception as exc:
            logger.error(
                "signals.classify_error",
                extra={"title": raw.title[:80], "error": str(exc)},
            )

    detected_signals.sort(key=lambda s: s.get("strength_score") or 0, reverse=True)
    result_signals = detected_signals[:max_signals]

    logger.info(
        "signals.run_and_classify.done",
        extra={
            "items_fetched": items_fetched,
            "signals_detected": len(detected_signals),
            "tenant_id": tenant_id or "root",
        },
    )
    return result_signals


async def run(*, request=None, cloud_event=None) -> dict | None:
    """Legacy HTTP-trigger wrapper kept for backwards compatibility."""
    from shared.firestore_client import get_doc as _get_doc

    config_doc = _get_doc("system_config", "intelligence_sources")
    if not config_doc:
        logger.warning("signals.no_sources_configured")
        return {"signals_detected": 0}
    signals = await run_and_classify(config_doc.get("sources", []))
    return {"signals_detected": len(signals)}
