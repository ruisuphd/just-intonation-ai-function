"""Orchestrate daily pipeline runs across all active tenants."""

from __future__ import annotations

import asyncio
import time
import traceback

from shared.entitlements import resolve_access
from shared.firestore_client import query_docs
from shared.logger import get_logger
from shared.models import TenantProfile

logger = get_logger("tenant_orchestrator")

# Maximum seconds a single tenant pipeline may run before being cancelled.
# Cloud Scheduler gives the function 600s total — this budget leaves headroom
# for multiple tenants and avoids a single slow tenant causing a 504.
_PER_TENANT_TIMEOUT_S = 240


async def run_all_active_tenants() -> dict:
    """Run the daily pipeline for every tenant with starter or pro access.

    Tenants are processed sequentially to avoid Vertex AI rate limits.
    Each tenant is given a time budget so one slow tenant cannot 504 the
    entire function.
    """
    from pipeline import _run_pipeline

    tenant_docs = query_docs("tenants")
    eligible_tenants: list[dict] = []
    for doc in tenant_docs:
        try:
            profile = TenantProfile.model_validate(doc)
        except Exception as exc:
            logger.warning(
                "orchestrator.invalid_tenant",
                extra={"error": str(exc), "tenant": doc.get("tenant_id", "")},
            )
            continue
        access = resolve_access(profile)
        if access.effective_tier in {"starter", "pro"}:
            eligible_tenants.append(doc)

    logger.info(
        "orchestrator.start",
        extra={"active_tenants": len(eligible_tenants)},
    )

    processed = 0
    failed = 0
    timed_out = 0
    failures: list[dict] = []

    for doc in eligible_tenants:
        tenant_id = doc.get("tenant_id") or doc.get("id", "")
        if not tenant_id:
            continue

        logger.info("orchestrator.tenant_start", extra={"tenant_id": tenant_id})
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(
                _run_pipeline(tenant_id=tenant_id),
                timeout=_PER_TENANT_TIMEOUT_S,
            )
            elapsed_s = round(time.monotonic() - t0, 1)
            processed += 1
            logger.info(
                "orchestrator.tenant_done",
                extra={"tenant_id": tenant_id, "elapsed_s": elapsed_s, **result},
            )
        except asyncio.TimeoutError:
            elapsed_s = round(time.monotonic() - t0, 1)
            timed_out += 1
            failed += 1
            failures.append(
                {
                    "tenant_id": tenant_id,
                    "error": f"Timed out after {_PER_TENANT_TIMEOUT_S}s",
                }
            )
            logger.error(
                "orchestrator.tenant_timeout",
                extra={
                    "tenant_id": tenant_id,
                    "timeout_s": _PER_TENANT_TIMEOUT_S,
                    "elapsed_s": elapsed_s,
                },
            )
        except Exception as exc:
            elapsed_s = round(time.monotonic() - t0, 1)
            failed += 1
            failures.append(
                {
                    "tenant_id": tenant_id,
                    "error": str(exc),
                }
            )
            logger.error(
                "orchestrator.tenant_failed",
                extra={
                    "tenant_id": tenant_id,
                    "elapsed_s": elapsed_s,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )

    summary = {
        "tenants_processed": processed,
        "tenants_failed": failed,
        "tenants_timed_out": timed_out,
        "failures": failures,
    }
    logger.info("orchestrator.done", extra=summary)
    return summary
