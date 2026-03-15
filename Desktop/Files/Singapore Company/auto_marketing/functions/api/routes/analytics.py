"""Analytics API."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import fmean

from fastapi import APIRouter, Depends

from api.middleware.auth import require_access
from shared.datetime_utils import coerce_datetime
from shared.firestore_client import query_docs
from shared.models import TenantProfile

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@router.get("")
async def get_analytics(
    days: int = 14,
    tenant: TenantProfile = Depends(require_access("starter", "pro")),
):
    window = max(7, min(days, 90))
    snapshot_docs = query_docs(
        "analytics_snapshots",
        order_by="-measured_at",
        limit=window,
        tenant_id=tenant.tenant_id,
    )

    series: list[dict] = []
    total_impressions = 0
    avg_open_rate_values: list[float] = []

    for snapshot in reversed(snapshot_docs):
        post_metrics = snapshot.get("post_metrics") or []
        outreach_metrics = snapshot.get("outreach_metrics") or []
        measured_at = (
            coerce_datetime(snapshot.get("measured_at"))
            or coerce_datetime(snapshot.get("id"))
            or datetime.now(timezone.utc)
        )

        impressions = sum(_safe_int(item.get("impressions")) for item in post_metrics)
        engagements = sum(
            _safe_int(item.get("likes"))
            + _safe_int(item.get("comments"))
            + _safe_int(item.get("shares"))
            for item in post_metrics
        )
        open_rates = [
            _safe_float(item.get("open_rate"))
            for item in outreach_metrics
            if item.get("open_rate") is not None
        ]
        avg_open_rate = fmean(open_rates) if open_rates else 0.0

        total_impressions += impressions
        if open_rates:
            avg_open_rate_values.extend(open_rates)

        series.append(
            {
                "date": measured_at.date().isoformat(),
                "label": measured_at.strftime("%b %d"),
                "impressions": impressions,
                "engagements": engagements,
                "avg_open_rate": round(avg_open_rate, 4),
            }
        )

    published_posts = query_docs(
        "publishing_records",
        filters=[("status", "==", "published")],
        tenant_id=tenant.tenant_id,
        limit=500,
    )
    signals = query_docs("prospect_signals", tenant_id=tenant.tenant_id, limit=500)
    leads = query_docs("qualified_leads", tenant_id=tenant.tenant_id, limit=500)
    outreach = query_docs("outreach_drafts", tenant_id=tenant.tenant_id, limit=500)

    reply_statuses = {"meeting_booked", "negotiation", "closed_won", "closed_lost"}
    reply_count = sum(1 for lead in leads if lead.get("status") in reply_statuses)
    outreach_sent_count = sum(
        1
        for draft in outreach
        if draft.get("status") in {"approved", "sent", "archived"}
    )
    live_metrics_available = any(
        snapshot.get("metrics_source") == "platform_api" for snapshot in snapshot_docs
    )

    return {
        "summary": {
            "total_impressions": total_impressions,
            "avg_open_rate": round(fmean(avg_open_rate_values), 4)
            if avg_open_rate_values
            else 0.0,
            "qualified_leads": len(leads),
            "published_posts": len(published_posts),
            "signals_detected": len(signals),
            "outreach_sent": outreach_sent_count,
            "reply_received": reply_count,
        },
        "series": series,
        "live_metrics_available": live_metrics_available,
    }
