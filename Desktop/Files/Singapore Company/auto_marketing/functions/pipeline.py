"""Daily marketing pipeline — single Cloud Function entry point.

Runs sequentially each morning:
  1. Fetch & score news (company mentions, competitors, market signals)
  2. Generate concise English-first social post + optional image
  3. Detect buying signals → qualify leads → draft outreach messages
  4. Send HTML email with all outputs to founder

Triggered daily by Cloud Scheduler at 07:00 SGT.
"""

from __future__ import annotations

import asyncio
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import functions_framework
from flask import Request, jsonify

from shared.firestore_client import create_doc_if_absent, get_doc, update_doc
from shared.logger import clear_trace_id, get_logger, set_trace_id
from shared.models import GenerationConfig

logger = get_logger("pipeline")

_DEFAULT_DIGEST_TIMEZONE = "Asia/Singapore"
_DEFAULT_TOP_K_INTELLIGENCE = 5
_DAILY_DIGEST_COLLECTION = "daily_digest_sends"

# ── Source Configuration ───────────────────────────────────────────────────────
#
# Inline config — no Firestore lookup needed for sources.
# Edit this list to add/remove/toggle RSS feeds.
#
# Categories:
#   "industry_news" → intelligence engine (marketing content)
#   "competitor"    → intelligence engine + signals engine
#   "funding"       → signals engine (lead detection)
#   "community"     → signals engine (pain points, discussion)
#
SOURCES_CONFIG: list[dict] = [
    {
        "id": "self_intonation_labs",
        "name": "Intonation Labs Mentions",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=%22Intonation+Labs%22+AI+OR+%22Rui+Su%22&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "industry_news",
    },
    {
        "id": "global_enterprise_ai",
        "name": "Global Enterprise AI",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=enterprise+AI+deployment+OR+agentic+AI+OR+RAG+OR+LLM+integration&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "industry_news",
    },
    {
        "id": "global_consulting_ai",
        "name": "Global AI Consulting Strategy",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=AI+consulting+digital+transformation+enterprise+strategy&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "industry_news",
    },
    {
        "id": "us_ai_news",
        "name": "US AI News",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=AI+infrastructure+enterprise+software+funding&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "industry_news",
    },
    {
        "id": "europe_ai_news",
        "name": "Europe AI News",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=Europe+AI+enterprise+consulting+funding&hl=en-GB&gl=GB&ceid=GB:en",
        "enabled": True,
        "category": "industry_news",
    },
    {
        "id": "global_ai_policy",
        "name": "AI Policy And Regulation",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=AI+policy+regulation+enterprise+deployments&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "industry_news",
    },
    {
        "id": "venturebeat_ai",
        "name": "VentureBeat AI",
        "type": "rss",
        "url": "https://venturebeat.com/ai/feed/",
        "enabled": True,
        "category": "industry_news",
    },
    {
        "id": "mit_ai",
        "name": "MIT Technology Review AI",
        "type": "rss",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
        "enabled": True,
        "category": "industry_news",
    },
    {
        "id": "accenture_ai",
        "name": "Accenture AI",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=Accenture+AI+consulting+enterprise&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "competitor",
    },
    {
        "id": "mckinsey_ai",
        "name": "McKinsey AI",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=McKinsey+AI+consulting+enterprise&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "competitor",
    },
    {
        "id": "bcg_ai",
        "name": "BCG AI",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=BCG+AI+consulting+enterprise&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "competitor",
    },
    {
        "id": "deloitte_ai",
        "name": "Deloitte AI",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=Deloitte+AI+consulting+enterprise&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "competitor",
    },
    {
        "id": "techcrunch_startups",
        "name": "TechCrunch Startups",
        "type": "rss",
        "url": "https://techcrunch.com/category/startups/feed/",
        "enabled": True,
        "category": "funding",
    },
    {
        "id": "crunchbase_news",
        "name": "Crunchbase News",
        "type": "rss",
        "url": "https://news.crunchbase.com/feed/",
        "enabled": True,
        "category": "funding",
    },
    {
        "id": "global_ai_funding",
        "name": "Global AI Startup Funding",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=AI+startup+funding+Series+A+Series+B+enterprise&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "funding",
    },
    {
        "id": "enterprise_ai_hiring",
        "name": "Enterprise AI Hiring",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=enterprise+hiring+AI+machine+learning+head+of+AI&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "community",
    },
    {
        "id": "enterprise_ai_transformation",
        "name": "Enterprise AI Transformation",
        "type": "google_news_rss",
        "url": "https://news.google.com/rss/search?q=CIO+AI+transformation+enterprise+modernization&hl=en-US&gl=US&ceid=US:en",
        "enabled": True,
        "category": "community",
    },
]


@dataclass(frozen=True)
class DigestConfig:
    enabled: bool
    recipient_email: str | None
    timezone_name: str
    top_k_intelligence: int


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_timezone(timezone_name: str | None) -> ZoneInfo:
    candidate = (timezone_name or _DEFAULT_DIGEST_TIMEZONE).strip() or _DEFAULT_DIGEST_TIMEZONE
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        logger.warning(
            "pipeline.invalid_timezone",
            extra={"timezone": candidate, "fallback": _DEFAULT_DIGEST_TIMEZONE},
        )
        return ZoneInfo(_DEFAULT_DIGEST_TIMEZONE)


def _load_digest_config() -> DigestConfig:
    raw_config = get_doc("system_config", "generation_config") or {}
    validated = GenerationConfig.model_validate(raw_config)

    digest_enabled = validated.daily_digest_enabled if "daily_digest_enabled" in raw_config else True
    recipient_email = (raw_config.get("daily_digest_email") or "").strip() or None
    top_k_intelligence = (
        validated.top_k_intelligence
        if "top_k_intelligence" in raw_config
        else _DEFAULT_TOP_K_INTELLIGENCE
    )
    digest_tz = _resolve_timezone(raw_config.get("timezone") or validated.timezone)

    return DigestConfig(
        enabled=digest_enabled,
        recipient_email=recipient_email,
        timezone_name=digest_tz.key,
        top_k_intelligence=max(1, top_k_intelligence),
    )


def _request_force_send(request: Request) -> bool:
    body = request.get_json(silent=True) or {}
    force_value = None
    if hasattr(request, "args"):
        force_value = request.args.get("force_send") or request.args.get("force")
    if force_value is None and isinstance(body, dict):
        force_value = body.get("force_send", body.get("force"))
    return _as_bool(force_value)


def _daily_digest_doc_id(day_key: str, timezone_name: str) -> str:
    safe_tz = timezone_name.replace("/", "_").replace(" ", "_")
    return f"{day_key}__{safe_tz}"


def _claim_daily_digest_send(
    *,
    day_key: str,
    timezone_name: str,
    recipient_email: str | None,
    trace_id: str,
) -> bool:
    return create_doc_if_absent(
        _DAILY_DIGEST_COLLECTION,
        _daily_digest_doc_id(day_key, timezone_name),
        {
            "day_key": day_key,
            "timezone": timezone_name,
            "recipient_email": recipient_email or "",
            "status": "claimed",
            "claimed_at": datetime.now(timezone.utc),
            "trace_id": trace_id,
        },
    )


def _update_daily_digest_send(
    *,
    day_key: str,
    timezone_name: str,
    trace_id: str,
    status: str,
    error: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
        "last_trace_id": trace_id,
    }
    if status == "sent":
        payload["sent_at"] = datetime.now(timezone.utc)
    if error:
        payload["error"] = error
    try:
        update_doc(
            _DAILY_DIGEST_COLLECTION,
            _daily_digest_doc_id(day_key, timezone_name),
            payload,
        )
    except Exception as exc:
        logger.warning(
            "pipeline.send_ledger_update_failed",
            extra={
                "day_key": day_key,
                "timezone": timezone_name,
                "status": status,
                "error": str(exc),
            },
        )


def _select_content_items(intel_items: list[dict]) -> list[dict]:
    ranked = sorted(
        intel_items,
        key=lambda item: (
            item.get("postability_score") or 0.0,
            item.get("relevance_score") or 0.0,
        ),
        reverse=True,
    )
    return ranked[:2]


def _recommend_watchlist_action(signal: dict) -> tuple[str, str]:
    signal_type = signal.get("signal_type") or ""
    if signal_type in {"funding_received", "hiring_ai_role"}:
        return (
            "Email",
            "Reference the expansion trigger and suggest a short discovery conversation.",
        )
    if signal_type in {"pain_point_expressed", "digital_transformation_signal"}:
        return (
            "LinkedIn",
            "Start with a low-pressure note tied to the visible pain point or transformation signal.",
        )
    return (
        "LinkedIn",
        "Warm the relationship first, then move to a short diagnostic conversation.",
    )


def _build_best_effort_item(
    signal: dict,
    lead_data: dict | None = None,
    outreach: dict | None = None,
) -> dict:
    lead_data = lead_data or {}
    outreach = outreach or {}
    channel, suggestion = _recommend_watchlist_action(signal)

    return {
        "company_name": signal.get("company_name", "Unknown"),
        "signal_summary": signal.get("summary") or signal.get("title", ""),
        "icp_fit": lead_data.get("icp_fit", "low"),
        "icp_fit_score": lead_data.get("icp_fit_score", 0.0),
        "fit_reasoning": lead_data.get("icp_reasoning", ""),
        "approach_suggestion": lead_data.get("suggested_outreach_angle") or suggestion,
        "recommended_channel": outreach.get("recommended_channel") or channel,
        "channel_reason": outreach.get("channel_reason", ""),
        "linkedin_dm": outreach.get("linkedin_dm", ""),
        "cold_email": outreach.get("cold_email", {}),
    }


# ── Cloud Function entry point ────────────────────────────────────────────────

@functions_framework.http
def run_daily_pipeline(request: Request):
    """HTTP-triggered Cloud Function. Runs the full daily marketing pipeline."""
    trace_id = f"pipeline-{uuid.uuid4().hex[:12]}"
    force_send = _request_force_send(request)
    set_trace_id(trace_id)
    t0 = time.monotonic()
    logger.info("pipeline.start", extra={"force_send": force_send})

    try:
        result = asyncio.run(_run_pipeline(force_send=force_send, trace_id=trace_id))
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.info("pipeline.done", extra={"elapsed_ms": elapsed_ms, **result})
        return jsonify({"ok": True, **result}), 200
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.error(
            "pipeline.error",
            extra={
                "elapsed_ms": elapsed_ms,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        clear_trace_id()


# ── Pipeline orchestration ────────────────────────────────────────────────────

async def _run_pipeline(*, force_send: bool = False, trace_id: str = "") -> dict:
    from engines import image_generate
    from engines import email_builder
    from engines.intelligence import run_and_return_items
    from engines.post_generate import generate_daily_post
    from engines.qualification import qualify_inline
    from engines.outreach_generate import generate_outreach_inline
    from engines.signals import run_and_classify
    from shared.retriever import Retriever

    digest_config = _load_digest_config()
    digest_tz = _resolve_timezone(digest_config.timezone_name)
    local_today = datetime.now(digest_tz).strftime("%Y-%m-%d")

    # ── Step 1: Fetch & score news ────────────────────────────────────────────
    logger.info("pipeline.step1.intelligence_start")
    intel_items: list[dict] = []
    try:
        intel_items = await run_and_return_items(sources=SOURCES_CONFIG)
        logger.info("pipeline.step1.intelligence_done", extra={"items": len(intel_items)})
    except Exception as exc:
        logger.error("pipeline.step1.intelligence_failed", extra={"error": str(exc)})

    top_intel = intel_items[:digest_config.top_k_intelligence]
    content_intel = _select_content_items(intel_items)

    # ── Step 2: Generate daily post + image ───────────────────────────────────
    logger.info("pipeline.step2.content_start")
    post_draft = None
    image_bytes = None
    post_status = "no_candidates"

    if content_intel:
        post_status = "failed"
        try:
            intelligence_summaries = [
                item.get("summary") or item.get("title", "") for item in content_intel
            ]
            query = " ".join(item.get("title", "") for item in content_intel)
            retriever = Retriever(top_k=6)
            chunks, _ = retriever.retrieve(query, language="en")
            brand_context = [
                {"text": c.get("text", ""), "doc_type": c.get("doc_type", "other")}
                for c in chunks
            ]
            post_draft = await generate_daily_post(
                intelligence_summaries=intelligence_summaries,
                intelligence_items=content_intel,
                brand_context=brand_context or None,
            )
            post_status = "ready"
            logger.info("pipeline.step2.post_generated")
        except Exception as exc:
            logger.error("pipeline.step2.post_failed", extra={"error": str(exc)})
    else:
        logger.info("pipeline.step2.no_content_candidates")

    if post_draft and post_draft.image_prompt:
        try:
            image_bytes = await image_generate.generate(post_draft.image_prompt)
            logger.info("pipeline.step2.image_generated", extra={"bytes": len(image_bytes)})
        except Exception as exc:
            logger.warning("pipeline.step2.image_failed", extra={"error": str(exc)})

    # ── Step 3: Detect leads ──────────────────────────────────────────────────
    logger.info("pipeline.step3.leads_start")
    lead_items: list[dict] = []
    prospect_items: list[dict] = []

    try:
        classified_signals = await run_and_classify(sources=SOURCES_CONFIG, max_signals=8)
        logger.info("pipeline.step3.signals_detected", extra={"count": len(classified_signals)})

        for signal in classified_signals:
            if len(lead_items) >= 3 and len(prospect_items) >= 3:
                break
            try:
                lead_data = await qualify_inline(signal)
                is_qualified = lead_data.get("icp_fit") in ("high", "medium")
                outreach: dict = {}

                try:
                    if is_qualified or len(prospect_items) < 3:
                        outreach = await generate_outreach_inline(lead_data, signal)
                except Exception as exc:
                    logger.warning(
                        "pipeline.step3.outreach_generation_failed",
                        extra={"company": signal.get("company_name"), "error": str(exc)},
                    )

                if is_qualified:
                    if len(lead_items) < 3:
                        lead_items.append({
                            "company_name": signal.get("company_name", "Unknown"),
                            "signal_summary": signal.get("summary") or signal.get("title", ""),
                            "icp_fit": lead_data.get("icp_fit"),
                            "icp_fit_score": lead_data.get("icp_fit_score", 0.0),
                            "approach_suggestion": lead_data.get("suggested_outreach_angle", ""),
                            "recommended_channel": outreach.get("recommended_channel", ""),
                            "channel_reason": outreach.get("channel_reason", ""),
                            "linkedin_dm": outreach.get("linkedin_dm", ""),
                            "cold_email": outreach.get("cold_email", {}),
                        })
                    continue

                if len(prospect_items) < 3:
                    prospect_items.append(
                        _build_best_effort_item(signal, lead_data=lead_data, outreach=outreach)
                    )
            except Exception as exc:
                if len(prospect_items) < 3:
                    fallback_outreach: dict = {}
                    try:
                        fallback_outreach = await generate_outreach_inline(
                            {
                                "company_name": signal.get("company_name", "Unknown"),
                                "suggested_outreach_angle": "",
                            },
                            signal,
                        )
                    except Exception as outreach_exc:
                        logger.warning(
                            "pipeline.step3.best_effort_outreach_failed",
                            extra={
                                "company": signal.get("company_name"),
                                "error": str(outreach_exc),
                            },
                        )
                    prospect_items.append(
                        _build_best_effort_item(signal, outreach=fallback_outreach)
                    )
                logger.warning(
                    "pipeline.step3.lead_processing_failed",
                    extra={"company": signal.get("company_name"), "error": str(exc)},
                )

        logger.info(
            "pipeline.step3.leads_done",
            extra={"leads": len(lead_items), "prospects": len(prospect_items)},
        )
    except Exception as exc:
        logger.error("pipeline.step3.leads_failed", extra={"error": str(exc)})

    # ── Step 4: Send email ────────────────────────────────────────────────────
    logger.info("pipeline.step4.email_start")
    email_status = "skipped_disabled"
    if not digest_config.enabled and not force_send:
        logger.info("pipeline.step4.email_disabled")
    elif not force_send and not _claim_daily_digest_send(
        day_key=local_today,
        timezone_name=digest_config.timezone_name,
        recipient_email=digest_config.recipient_email,
        trace_id=trace_id,
    ):
        email_status = "skipped_duplicate"
        logger.info(
            "pipeline.step4.email_duplicate_skipped",
            extra={"day_key": local_today, "timezone": digest_config.timezone_name},
        )
    else:
        try:
            email_builder.send_daily_brief(
                today=local_today,
                post_draft=post_draft,
                post_status=post_status,
                image_bytes=image_bytes,
                intel_items=top_intel,
                lead_items=lead_items,
                prospect_items=prospect_items,
                generated_at=datetime.now(digest_tz),
                timezone_name=digest_config.timezone_name,
                recipient_email=digest_config.recipient_email,
            )
            if not force_send:
                _update_daily_digest_send(
                    day_key=local_today,
                    timezone_name=digest_config.timezone_name,
                    trace_id=trace_id,
                    status="sent",
                )
            email_status = "sent"
            logger.info("pipeline.step4.email_sent", extra={"force_send": force_send})
        except Exception as exc:
            if not force_send:
                _update_daily_digest_send(
                    day_key=local_today,
                    timezone_name=digest_config.timezone_name,
                    trace_id=trace_id,
                    status="failed",
                    error=str(exc),
                )
            logger.error("pipeline.step4.email_failed", extra={"error": str(exc)})
            raise

    return {
        "date": local_today,
        "timezone": digest_config.timezone_name,
        "intel_items": len(top_intel),
        "post_generated": post_draft is not None,
        "image_generated": image_bytes is not None,
        "leads_found": len(lead_items),
        "prospects_found": len(prospect_items),
        "email_status": email_status,
        "force_send": force_send,
    }
