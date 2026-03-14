"""Cloud Function entry points.

- run_daily_pipeline: single-tenant pipeline (manual testing or legacy scheduler)
- run_tenant_pipelines: multi-tenant orchestrator (production scheduler)
- sync_brand_context: brand document ingestion
"""

from __future__ import annotations

import asyncio
import time
import traceback
import uuid

import functions_framework
from flask import Request, jsonify

from shared.logger import clear_trace_id, get_logger, set_trace_id

logger = get_logger("main")

# Re-export existing entry points for backward compatibility
from pipeline import run_daily_pipeline  # noqa: F401
from brand_context_runtime import sync_brand_context  # noqa: F401


@functions_framework.http
def run_tenant_pipelines(request: Request):
    """Run the daily pipeline for all active tenants. Called by Cloud Scheduler."""
    trace_id = f"orchestrator-{uuid.uuid4().hex[:12]}"
    set_trace_id(trace_id)
    t0 = time.monotonic()
    logger.info("tenant_pipelines.start")

    try:
        from engines.tenant_orchestrator import run_all_active_tenants

        result = asyncio.run(run_all_active_tenants())
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.info("tenant_pipelines.done", extra={"elapsed_ms": elapsed_ms, **result})
        return jsonify({"ok": True, **result}), 200
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.error(
            "tenant_pipelines.error",
            extra={
                "elapsed_ms": elapsed_ms,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        clear_trace_id()


@functions_framework.http
def run_scheduled_publisher(request: Request):
    """Publish due social posts created from approved draft records."""
    trace_id = f"publisher-{uuid.uuid4().hex[:12]}"
    set_trace_id(trace_id)
    t0 = time.monotonic()
    logger.info("scheduled_publisher.start")

    try:
        from engines.publisher import run_publisher
        from engines.newsletter_publisher import publish_newsletters

        async def _run_all():
            result = await run_publisher()
            try:
                await publish_newsletters()
            except Exception as nl_exc:
                logger.warning(
                    "scheduled_publisher.newsletter_failed",
                    extra={"error": str(nl_exc)},
                )
            return result

        result = asyncio.run(_run_all())
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.info(
            "scheduled_publisher.done", extra={"elapsed_ms": elapsed_ms, **result}
        )
        return jsonify({"ok": True, **result}), 200
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.error(
            "scheduled_publisher.error",
            extra={
                "elapsed_ms": elapsed_ms,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        clear_trace_id()


@functions_framework.http
def run_analytics_sync(request: Request):
    """Collect daily analytics snapshots for dashboard reporting."""
    trace_id = f"analytics-{uuid.uuid4().hex[:12]}"
    set_trace_id(trace_id)
    t0 = time.monotonic()
    logger.info("analytics_sync.start")

    try:
        from engines.analytics_gatherer import gather_daily_analytics

        result = asyncio.run(gather_daily_analytics())
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.info("analytics_sync.done", extra={"elapsed_ms": elapsed_ms, **result})
        return jsonify({"ok": True, **result}), 200
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.error(
            "analytics_sync.error",
            extra={
                "elapsed_ms": elapsed_ms,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        clear_trace_id()
