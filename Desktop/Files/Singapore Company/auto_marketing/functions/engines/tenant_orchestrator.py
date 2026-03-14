"""Orchestrate daily pipeline runs across all active tenants."""

from __future__ import annotations

import traceback

from shared.entitlements import resolve_access
from shared.firestore_client import query_docs
from shared.logger import get_logger
from shared.models import TenantProfile

logger = get_logger("tenant_orchestrator")


async def run_all_active_tenants() -> dict:
    """Run the daily pipeline for every tenant with starter or pro access.

    Tenants are processed sequentially to avoid Vertex AI rate limits.
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
    failures: list[dict] = []

    for doc in eligible_tenants:
        tenant_id = doc.get("tenant_id") or doc.get("id", "")
        if not tenant_id:
            continue

        logger.info("orchestrator.tenant_start", extra={"tenant_id": tenant_id})
        try:
            result = await _run_pipeline(tenant_id=tenant_id)
            processed += 1
            logger.info(
                "orchestrator.tenant_done",
                extra={"tenant_id": tenant_id, **result},
            )
        except Exception as exc:
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
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )

    summary = {
        "tenants_processed": processed,
        "tenants_failed": failed,
        "failures": failures,
    }
    logger.info("orchestrator.done", extra=summary)
    return summary
