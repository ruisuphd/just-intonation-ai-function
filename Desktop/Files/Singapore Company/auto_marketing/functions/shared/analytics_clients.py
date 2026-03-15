"""Platform analytics clients for fetching post metrics."""

from __future__ import annotations

import urllib.parse

import httpx

from shared.logger import get_logger

logger = get_logger("analytics_clients")

LINKEDIN_API = "https://api.linkedin.com"
X_API = "https://api.x.com"
LINKEDIN_VERSION = "202402"


async def fetch_linkedin_share_metrics(
    access_token: str,
    organization_urn: str,
    share_urns: list[str],
    timeout: float = 30.0,
) -> dict[str, dict[str, int]]:
    """Fetch LinkedIn metrics for given shares. Returns {share_urn: {impressions, likes, ...}}."""
    if not share_urns:
        return {}
    org_encoded = urllib.parse.quote(organization_urn, safe="")
    params: list[tuple[str, str]] = [
        ("q", "organizationalEntity"),
        ("organizationalEntity", org_encoded),
    ]
    for i, urn in enumerate(share_urns[:20]):
        params.append((f"shares[{i}]", urn))
    query = urllib.parse.urlencode(params)
    url = f"{LINKEDIN_API}/rest/organizationalEntityShareStatistics?{query}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": LINKEDIN_VERSION,
        "Accept": "application/json",
    }
    results: dict[str, dict[str, int]] = {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning(
                "analytics_clients.linkedin_failed", extra={"status": resp.status_code}
            )
            return {}
        data = resp.json()
        elements = data.get("elements", [])
        for el in elements:
            share = el.get("share") or el.get("organizationalEntity") or ""
            if not share:
                continue
            total = el.get("totalShareStatistics") or {}
            if isinstance(total, dict):
                results[share] = {
                    "impressions": int(total.get("impressionCount", 0) or 0),
                    "clicks": int(total.get("clickCount", 0) or 0),
                    "likes": int(total.get("likeCount", 0) or 0),
                    "comments": int(total.get("commentCount", 0) or 0),
                    "shares": int(total.get("shareCount", 0) or 0),
                }
    except Exception as exc:
        logger.warning("analytics_clients.linkedin_error", extra={"error": str(exc)})
    return results


async def fetch_x_tweet_metrics(
    access_token: str,
    tweet_ids: list[str],
    timeout: float = 30.0,
) -> dict[str, dict[str, int]]:
    """Fetch X public metrics for tweets. Returns {tweet_id: {impressions, likes, ...}}."""
    if not tweet_ids or len(tweet_ids) > 100:
        return {}
    ids_param = ",".join(tweet_ids[:100])
    url = f"{X_API}/2/tweets?ids={ids_param}&tweet.fields=public_metrics"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    results: dict[str, dict[str, int]] = {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning(
                "analytics_clients.x_failed", extra={"status": resp.status_code}
            )
            return {}
        data = resp.json()
        for t in data.get("data", []) or []:
            tid = t.get("id")
            if not tid:
                continue
            pm = t.get("public_metrics") or {}
            results[tid] = {
                "impressions": pm.get("impression_count", 0) or 0,
                "clicks": 0,
                "likes": pm.get("like_count", 0) or 0,
                "comments": pm.get("reply_count", 0) or 0,
                "shares": (pm.get("retweet_count", 0) or 0)
                + (pm.get("quote_count", 0) or 0),
            }
    except Exception as exc:
        logger.warning("analytics_clients.x_error", extra={"error": str(exc)})
    return results
