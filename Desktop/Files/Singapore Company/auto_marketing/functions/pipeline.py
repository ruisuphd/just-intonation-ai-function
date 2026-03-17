"""Daily marketing pipeline -- single Cloud Function entry point.

Runs sequentially each morning per tenant:
  1. Fetch & score news (company mentions, competitors, market signals)
  2. Generate concise English-first social post + optional image
  3. Detect buying signals -> qualify leads -> draft outreach messages
  4. Send HTML email with all outputs to founder

Triggered daily by Cloud Scheduler at 07:00 SGT.
"""

from __future__ import annotations

import asyncio
import time
import traceback
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import functions_framework
from flask import Request, jsonify

from shared.draft_utils import best_effort_post_topic, build_draft_payload
from shared.firestore_client import (
    add_doc,
    create_doc_if_absent,
    get_doc,
    get_tenant,
    update_doc,
)
from shared.logger import clear_trace_id, get_logger, set_trace_id
from shared.models import GenerationConfig, TenantProfile

logger = get_logger("pipeline")

_DEFAULT_DIGEST_TIMEZONE = "Asia/Singapore"
_DEFAULT_TOP_K_INTELLIGENCE = 5
_DAILY_DIGEST_COLLECTION = "daily_digest_sends"
_MAX_DYNAMIC_SOURCES = 12

# ── Legacy source config (used when tenant_id is None for backward compat) ────
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


def _build_sources_config(tenant: TenantProfile) -> list[dict]:
    """Dynamically generate RSS source config from a tenant's profile."""
    sources: list[dict] = []

    company_name = tenant.company_name.strip()
    if company_name:
        company_q = urllib.parse.quote_plus(f'"{company_name}"')
        sources.append(
            {
                "id": "self_mentions",
                "name": f"{company_name} Mentions",
                "type": "google_news_rss",
                "url": f"https://news.google.com/rss/search?q={company_q}&hl=en-US&gl=US&ceid=US:en",
                "enabled": True,
                "category": "industry_news",
            }
        )

    keyword_terms = [kw.strip() for kw in tenant.industry_keywords if kw.strip()]
    industry = tenant.industry.strip()
    if not keyword_terms and industry and industry.lower() != "other":
        keyword_terms.extend(
            [
                f"{industry} trends",
                f"{industry} strategy",
            ]
        )
    if not keyword_terms:
        keyword_terms.extend(
            [
                "enterprise AI consulting",
                "AI transformation",
            ]
        )

    for kw in keyword_terms:
        if len(sources) >= _MAX_DYNAMIC_SOURCES:
            break
        kw_q = urllib.parse.quote_plus(kw)
        slug = kw.lower().replace(" ", "_")[:30]
        sources.append(
            {
                "id": f"keyword_{slug}",
                "name": f"{kw} News",
                "type": "google_news_rss",
                "url": f"https://news.google.com/rss/search?q={kw_q}&hl=en-US&gl=US&ceid=US:en",
                "enabled": True,
                "category": "industry_news",
            }
        )

    for comp in tenant.competitor_names:
        if len(sources) >= _MAX_DYNAMIC_SOURCES:
            break
        comp_q = urllib.parse.quote_plus(comp)
        slug = comp.lower().replace(" ", "_")[:30]
        sources.append(
            {
                "id": f"competitor_{slug}",
                "name": f"{comp} News",
                "type": "google_news_rss",
                "url": f"https://news.google.com/rss/search?q={comp_q}&hl=en-US&gl=US&ceid=US:en",
                "enabled": True,
                "category": "competitor",
            }
        )

    return sources[:_MAX_DYNAMIC_SOURCES]


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
    candidate = (
        timezone_name or _DEFAULT_DIGEST_TIMEZONE
    ).strip() or _DEFAULT_DIGEST_TIMEZONE
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        logger.warning(
            "pipeline.invalid_timezone",
            extra={"timezone": candidate, "fallback": _DEFAULT_DIGEST_TIMEZONE},
        )
        return ZoneInfo(_DEFAULT_DIGEST_TIMEZONE)


def _load_digest_config(tenant_id: str | None = None) -> DigestConfig:
    if tenant_id:
        tenant_doc = get_tenant(tenant_id)
        if tenant_doc:
            return DigestConfig(
                enabled=tenant_doc.get("daily_digest_enabled", True),
                recipient_email=tenant_doc.get("daily_digest_email") or None,
                timezone_name=tenant_doc.get("timezone", _DEFAULT_DIGEST_TIMEZONE),
                top_k_intelligence=_DEFAULT_TOP_K_INTELLIGENCE,
            )

    raw_config = get_doc("system_config", "generation_config") or {}
    validated = GenerationConfig.model_validate(raw_config)

    digest_enabled = (
        validated.daily_digest_enabled if "daily_digest_enabled" in raw_config else True
    )
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


def _daily_digest_doc_id(
    day_key: str, timezone_name: str, tenant_id: str | None = None
) -> str:
    safe_tz = timezone_name.replace("/", "_").replace(" ", "_")
    prefix = f"{tenant_id}_" if tenant_id else ""
    return f"{prefix}{day_key}__{safe_tz}"


def _claim_daily_digest_send(
    *,
    day_key: str,
    timezone_name: str,
    recipient_email: str | None,
    trace_id: str,
    tenant_id: str | None = None,
) -> bool:
    return create_doc_if_absent(
        _DAILY_DIGEST_COLLECTION,
        _daily_digest_doc_id(day_key, timezone_name, tenant_id),
        {
            "day_key": day_key,
            "timezone": timezone_name,
            "recipient_email": recipient_email or "",
            "status": "claimed",
            "claimed_at": datetime.now(timezone.utc),
            "trace_id": trace_id,
            "tenant_id": tenant_id or "",
        },
        tenant_id=tenant_id,
    )


def _update_daily_digest_send(
    *,
    day_key: str,
    timezone_name: str,
    trace_id: str,
    status: str,
    error: str | None = None,
    tenant_id: str | None = None,
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
            _daily_digest_doc_id(day_key, timezone_name, tenant_id),
            payload,
            tenant_id=tenant_id,
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
    body = request.get_json(silent=True) or {}
    tenant_id = body.get("tenant_id") if isinstance(body, dict) else None
    trace_id = f"pipeline-{uuid.uuid4().hex[:12]}"
    force_send = _request_force_send(request)
    set_trace_id(trace_id)
    t0 = time.monotonic()
    logger.info(
        "pipeline.start",
        extra={"force_send": force_send, "tenant_id": tenant_id or "legacy"},
    )

    try:
        result = asyncio.run(
            _run_pipeline(force_send=force_send, trace_id=trace_id, tenant_id=tenant_id)
        )
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
                "tenant_id": tenant_id or "legacy",
            },
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        clear_trace_id()


# ── Pipeline orchestration ────────────────────────────────────────────────────


async def _run_pipeline(
    *,
    force_send: bool = False,
    trace_id: str = "",
    tenant_id: str | None = None,
) -> dict:
    from engines import image_generate
    from engines import email_builder
    from engines.intelligence import run_and_return_items
    from engines.post_generate import generate_daily_post
    from engines.qualification import qualify_inline
    from engines.outreach_generate import generate_outreach_inline
    from engines.signals import run_and_classify
    from shared.retriever import Retriever

    # Resolve sources: tenant-specific or legacy hardcoded
    tenant: TenantProfile | None = None
    if tenant_id:
        tenant_doc = get_tenant(tenant_id)
        if not tenant_doc:
            raise ValueError(f"Tenant {tenant_id} not found")
        tenant = TenantProfile.model_validate(tenant_doc)
        sources = _build_sources_config(tenant)
    else:
        sources = SOURCES_CONFIG

    digest_config = (
        _load_digest_config(tenant_id) if tenant_id else _load_digest_config()
    )
    digest_tz = _resolve_timezone(digest_config.timezone_name)
    local_today = datetime.now(digest_tz).strftime("%Y-%m-%d")

    from shared.usage_limits import get_limits_for_tier, is_pipeline_day
    from shared.entitlements import resolve_access

    # Resolve tier for limit enforcement
    effective_tier = "starter"
    if tenant is not None:
        access = resolve_access(tenant)
        effective_tier = access.effective_tier

    tier_limits = get_limits_for_tier(effective_tier)

    # Check if today is a pipeline day for this tier
    if tenant_id and not is_pipeline_day(effective_tier, digest_config.timezone_name):
        logger.info("pipeline.skipped_not_pipeline_day", extra={
            "tenant_id": tenant_id, "tier": effective_tier,
        })
        return {
            "tenant_id": tenant_id,
            "date": local_today,
            "timezone": digest_config.timezone_name,
            "email_status": "skipped_not_pipeline_day",
            "intel_items": 0, "post_generated": False,
            "image_generated": False, "leads_found": 0,
            "prospects_found": 0, "force_send": force_send,
        }

    # ── Step 1: Fetch & score news ────────────────────────────────────────────
    logger.info(
        "pipeline.step1.intelligence_start", extra={"tenant_id": tenant_id or "legacy"}
    )
    intel_items: list[dict] = []
    try:
        intel_items = await run_and_return_items(sources=sources, tenant_id=tenant_id)
        logger.info(
            "pipeline.step1.intelligence_done", extra={"items": len(intel_items)}
        )
    except Exception as exc:
        logger.error("pipeline.step1.intelligence_failed", extra={"error": str(exc)})

    # Cap intelligence items per tier
    max_intel = tier_limits.get("intelligence_items_per_run", 100)
    intel_items = intel_items[:max_intel]

    top_intel = intel_items[: digest_config.top_k_intelligence]
    content_intel = _select_content_items(intel_items)

    # ── Step 2: Generate daily post + image ───────────────────────────────────
    logger.info("pipeline.step2.content_start")
    post_draft = None
    image_bytes = None
    post_status = "no_candidates"
    content_summaries: list[str] = []
    content_query = ""

    if content_intel:
        content_summaries = [
            item.get("summary") or item.get("title", "") for item in content_intel
        ]
        content_query = " ".join(
            item.get("title") or item.get("summary", "") for item in content_intel
        )
    elif tenant is not None:
        fallback_topic = best_effort_post_topic(tenant)
        content_summaries = [fallback_topic]
        content_query = fallback_topic

    if content_summaries:
        post_status = "failed"
        try:
            retriever = Retriever(top_k=6, tenant_id=tenant_id)
            chunks, _ = retriever.retrieve(
                content_query or content_summaries[0], language="en"
            )
            brand_context = [
                {"text": c.get("text", ""), "doc_type": c.get("doc_type", "other")}
                for c in chunks
            ]
            post_draft = await generate_daily_post(
                intelligence_summaries=content_summaries,
                intelligence_items=content_intel or None,
                brand_context=brand_context or None,
                tenant_id=tenant_id,
                tier=effective_tier,
            )
            post_status = "ready" if content_intel else "best_effort"

            if tenant is not None:
                draft_payload = build_draft_payload(
                    post_draft,
                    tenant=tenant,
                    origin="pipeline",
                    topic=content_summaries[0],
                    batch_date=local_today,
                    platforms_enabled=tenant.platforms_enabled,
                )
                add_doc(
                    "drafts",
                    draft_payload,
                    doc_id=f"{local_today}__pipeline_post",
                    tenant_id=tenant_id,
                )
            logger.info("pipeline.step2.post_generated", extra={"status": post_status})
        except Exception as exc:
            logger.error("pipeline.step2.post_failed", extra={"error": str(exc)})
    else:
        logger.info("pipeline.step2.no_content_candidates")

    if post_draft and post_draft.image_prompt:
        try:
            image_bytes = await image_generate.generate(post_draft.image_prompt)
            logger.info(
                "pipeline.step2.image_generated", extra={"bytes": len(image_bytes)}
            )
            if tenant_id and image_bytes:
                import os

                from shared.firestore_client import update_doc
                from shared.storage_client import upload_bytes, generate_signed_url

                bucket = os.getenv("BRAND_DOCS_BUCKET", "")
                if bucket:
                    draft_id = f"{local_today}__pipeline_post"
                    blob_path = f"drafts/{draft_id}/image.png"
                    upload_bytes(
                        bucket,
                        blob_path,
                        image_bytes,
                        content_type="image/png",
                        tenant_id=tenant_id,
                    )
                    image_url = generate_signed_url(
                        bucket,
                        blob_path,
                        expiry_hours=168,
                        tenant_id=tenant_id,
                    )
                    update_doc(
                        "drafts",
                        draft_id,
                        {"image_url": image_url},
                        tenant_id=tenant_id,
                    )
        except Exception as exc:
            logger.warning("pipeline.step2.image_failed", extra={"error": str(exc)})

    # ── Step 3: Detect leads ──────────────────────────────────────────────────
    logger.info("pipeline.step3.leads_start")
    lead_items: list[dict] = []
    prospect_items: list[dict] = []

    try:
        max_leads = tier_limits.get("leads_per_run", 8)
        classified_signals = await run_and_classify(
            sources=sources,
            max_signals=8,
            tenant_id=tenant_id,
            tier=effective_tier,
        )
        logger.info(
            "pipeline.step3.signals_detected", extra={"count": len(classified_signals)}
        )

        for signal in classified_signals:
            if len(lead_items) >= max_leads and len(prospect_items) >= max_leads:
                break
            try:
                lead_data = await qualify_inline(signal, tenant_id=tenant_id, tier=effective_tier)
                is_qualified = lead_data.get("icp_fit") in ("high", "medium")
                outreach: dict = {}

                try:
                    if is_qualified or len(prospect_items) < max_leads:
                        outreach = await generate_outreach_inline(
                            lead_data,
                            signal,
                            tenant_id=tenant_id,
                            tier=effective_tier,
                        )
                except Exception as exc:
                    logger.warning(
                        "pipeline.step3.outreach_generation_failed",
                        extra={
                            "company": signal.get("company_name"),
                            "error": str(exc),
                        },
                    )

                if is_qualified:
                    if len(lead_items) < max_leads:
                        lead_items.append(
                            {
                                "company_name": signal.get("company_name", "Unknown"),
                                "signal_summary": signal.get("summary")
                                or signal.get("title", ""),
                                "icp_fit": lead_data.get("icp_fit"),
                                "icp_fit_score": lead_data.get("icp_fit_score", 0.0),
                                "approach_suggestion": lead_data.get(
                                    "suggested_outreach_angle", ""
                                ),
                                "recommended_channel": outreach.get(
                                    "recommended_channel", ""
                                ),
                                "channel_reason": outreach.get("channel_reason", ""),
                                "linkedin_dm": outreach.get("linkedin_dm", ""),
                                "cold_email": outreach.get("cold_email", {}),
                            }
                        )
                    continue

                if len(prospect_items) < max_leads:
                    prospect_items.append(
                        _build_best_effort_item(
                            signal, lead_data=lead_data, outreach=outreach
                        )
                    )
            except Exception as exc:
                if len(prospect_items) < max_leads:
                    fallback_outreach: dict = {}
                    try:
                        fallback_outreach = await generate_outreach_inline(
                            {
                                "company_name": signal.get("company_name", "Unknown"),
                                "suggested_outreach_angle": "",
                            },
                            signal,
                            tenant_id=tenant_id,
                            tier=effective_tier,
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
        tenant_id=tenant_id,
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
                company_name=tenant.company_name if tenant else "",
            )
            if not force_send:
                _update_daily_digest_send(
                    day_key=local_today,
                    timezone_name=digest_config.timezone_name,
                    trace_id=trace_id,
                    status="sent",
                    tenant_id=tenant_id,
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
                    tenant_id=tenant_id,
                )
            email_status = "failed"
            logger.error(
                "pipeline.step4.email_failed",
                extra={"error": str(exc), "traceback": traceback.format_exc()},
            )

    return {
        "tenant_id": tenant_id or "legacy",
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
