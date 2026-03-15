"""Platform publishing clients for LinkedIn and X."""

from __future__ import annotations


import httpx

from shared.logger import get_logger

logger = get_logger("platform_clients")

LINKEDIN_API = "https://api.linkedin.com"
X_API = "https://api.x.com"
LINKEDIN_VERSION = "202402"


async def publish_linkedin(
    *,
    access_token: str,
    author_urn: str,
    text: str,
    timeout: float = 30.0,
) -> tuple[str | None, str | None]:
    """Publish a text post to LinkedIn. Returns (external_id, error_message)."""
    url = f"{LINKEDIN_API}/rest/posts"
    payload = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 201:
                post_id = resp.headers.get("x-restli-id")
                if post_id:
                    logger.info(
                        "platform_clients.linkedin_published",
                        extra={"post_id": post_id[:50]},
                    )
                    return (post_id, None)
                return ("linkedin_unknown", None)
            body = resp.text
            logger.warning(
                "platform_clients.linkedin_failed",
                extra={"status": resp.status_code, "body": body[:200]},
            )
            return (None, f"LinkedIn API {resp.status_code}: {body[:200]}")
    except httpx.TimeoutException:
        logger.warning("platform_clients.linkedin_timeout")
        return (None, "LinkedIn request timed out")
    except Exception as exc:
        logger.error(
            "platform_clients.linkedin_error",
            extra={"error": str(exc)},
        )
        return (None, str(exc))


async def publish_x(
    *,
    access_token: str,
    text: str,
    timeout: float = 30.0,
) -> tuple[str | None, str | None]:
    """Publish a tweet to X. Text truncated to 280 chars. Returns (external_id, error_message)."""
    truncated = text[:280] if len(text) > 280 else text
    url = f"{X_API}/2/tweets"
    payload = {"text": truncated}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                tweet_id = (
                    data.get("data", {}).get("id") if isinstance(data, dict) else None
                )
                if tweet_id:
                    logger.info(
                        "platform_clients.x_published",
                        extra={"tweet_id": tweet_id},
                    )
                    return (tweet_id, None)
                return ("x_unknown", None)
            body = resp.text
            logger.warning(
                "platform_clients.x_failed",
                extra={"status": resp.status_code, "body": body[:200]},
            )
            return (None, f"X API {resp.status_code}: {body[:200]}")
    except httpx.TimeoutException:
        logger.warning("platform_clients.x_timeout")
        return (None, "X request timed out")
    except Exception as exc:
        logger.error(
            "platform_clients.x_error",
            extra={"error": str(exc)},
        )
        return (None, str(exc))
