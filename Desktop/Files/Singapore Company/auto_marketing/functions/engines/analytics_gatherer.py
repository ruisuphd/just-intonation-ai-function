"""Engine for gathering daily analytics snapshots for active tenants."""

from __future__ import annotations

from datetime import datetime, timezone

from shared.analytics_clients import fetch_linkedin_share_metrics, fetch_x_tweet_metrics
from shared.firestore_client import query_docs, set_doc
from shared.logger import get_logger
from shared.models import OutreachMetrics, PostMetrics

logger = get_logger("analytics_gatherer")


async def _fetch_platform_metrics(
    tenant_doc: dict, published_posts: list[dict]
) -> tuple[dict[str, dict], str]:
    """Fetch metrics from LinkedIn/X when credentials and external_ids exist. Returns (metrics_by_post_id, source)."""
    results: dict[str, dict] = {}
    source = "placeholder_until_platform_apis"
    creds = tenant_doc.get("platform_credentials") or {}

    linkedin_creds = creds.get("linkedin", {})
    linkedin_token = (
        linkedin_creds.get("access_token") if isinstance(linkedin_creds, dict) else None
    )
    linkedin_org = (
        linkedin_creds.get("platform_id", "")
        if isinstance(linkedin_creds, dict)
        else ""
    )
    if linkedin_token and linkedin_org and "organization" in linkedin_org:
        share_urns = [
            str(p.get("external_id", ""))
            for p in published_posts
            if p.get("platform", "").lower() == "linkedin"
            and p.get("external_id")
            and str(p.get("external_id", "")).startswith("urn:")
        ]
        if share_urns:
            link_metrics = await fetch_linkedin_share_metrics(
                linkedin_token, linkedin_org, share_urns
            )
            if link_metrics:
                source = "linkedin_api"
            for post in published_posts:
                ext_id = str(post.get("external_id", ""))
                post_id = post.get("post_id") or post.get("id")
                if ext_id and post_id and ext_id in link_metrics:
                    results[post_id] = link_metrics[ext_id]

    x_creds = creds.get("x_twitter", {})
    x_token = x_creds.get("access_token") if isinstance(x_creds, dict) else None
    if x_token and (not results or source == "placeholder_until_platform_apis"):
        tweet_ids = [
            str(p.get("external_id", ""))
            for p in published_posts
            if p.get("platform", "").lower() in ("x_twitter", "x")
            and p.get("external_id")
            and str(p.get("external_id", "")).isdigit()
        ]
        if tweet_ids:
            x_metrics = await fetch_x_tweet_metrics(x_token, tweet_ids)
            if x_metrics:
                source = (
                    "x_api" if source == "placeholder_until_platform_apis" else source
                )
            for post in published_posts:
                ext_id = str(post.get("external_id", ""))
                post_id = post.get("post_id") or post.get("id")
                if ext_id and post_id and ext_id in x_metrics:
                    results[post_id] = x_metrics[ext_id]

    return results, source


async def gather_daily_analytics() -> dict:
    """Iterate over tenants and store conservative analytics snapshots.

    Until platform analytics APIs are integrated, this worker records honest
    placeholder engagement metrics and relies on live funnel counts elsewhere in
    the product. It does not fabricate likes, reach, or open rates.
    """
    tenant_docs = query_docs("tenants")
    processed_tenants = 0
    total_snapshots = 0

    for doc in tenant_docs:
        tenant_id = doc.get("tenant_id") or doc.get("id")
        if not tenant_id:
            continue

        now = datetime.now(timezone.utc)
        snapshot_id = now.strftime("%Y-%m-%d")

        published_posts = query_docs(
            "publishing_records",
            filters=[("status", "==", "published")],
            tenant_id=tenant_id,
        )
        platform_metrics, metrics_source = await _fetch_platform_metrics(
            doc, published_posts
        )
        post_metrics_list = []
        for post in published_posts:
            post_id = post.get("post_id") or post.get("id")
            if not post_id:
                continue
            pm = platform_metrics.get(post_id) or {}
            metrics = PostMetrics(
                post_id=post_id,
                impressions=pm.get("impressions", 0) or 0,
                clicks=pm.get("clicks", 0) or 0,
                likes=pm.get("likes", 0) or 0,
                comments=pm.get("comments", 0) or 0,
                shares=pm.get("shares", 0) or 0,
                measured_at=now,
            )
            post_metrics_list.append(metrics.model_dump(mode="json"))

        # Mock fetching email/outreach campaign metrics.
        outreach_drafts = query_docs("outreach_drafts", tenant_id=tenant_id)
        outreach_metrics_list = []
        for draft in outreach_drafts:
            draft_id = draft.get("id") or draft.get("lead_id")
            if not draft_id:
                continue

            metrics = OutreachMetrics(
                campaign_id=draft_id,
                open_rate=0.0,
                click_rate=0.0,
                reply_rate=0.0,
                measured_at=now,
            )
            outreach_metrics_list.append(metrics.model_dump(mode="json"))

        snapshot_data = {
            "id": snapshot_id,
            "measured_at": now.isoformat(),
            "post_metrics": post_metrics_list,
            "outreach_metrics": outreach_metrics_list,
            "metrics_source": metrics_source,
        }

        set_doc("analytics_snapshots", snapshot_id, snapshot_data, tenant_id=tenant_id)
        processed_tenants += 1
        total_snapshots += len(post_metrics_list) + len(outreach_metrics_list)

        logger.info(
            "analytics.tenant_processed",
            extra={
                "tenant_id": tenant_id,
                "posts": len(post_metrics_list),
                "outreach": len(outreach_metrics_list),
            },
        )

    return {
        "tenants_processed": processed_tenants,
        "total_metrics_gathered": total_snapshots,
    }
