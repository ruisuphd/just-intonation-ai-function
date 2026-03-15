"""Newsletter publishing providers (Ghost, etc.)."""

from __future__ import annotations

import time

import httpx
import jwt

from shared.logger import get_logger

logger = get_logger("newsletter_providers")


def _ghost_token(admin_key: str) -> str:
    """Generate JWT for Ghost Admin API from id:secret key."""
    parts = admin_key.split(":")
    if len(parts) != 2:
        raise ValueError("Ghost API key must be in format id:secret")
    kid, secret = parts[0].strip(), parts[1].strip()
    now = int(time.time())
    payload = {"iat": now, "exp": now + 300, "aud": "/admin/"}
    headers = {"alg": "HS256", "typ": "JWT", "kid": kid}
    return jwt.encode(
        payload,
        bytes.fromhex(secret),
        algorithm="HS256",
        headers=headers,
    )


async def publish_to_ghost(
    admin_url: str,
    admin_key: str,
    title: str,
    html_body: str,
    status: str = "published",
    timeout: float = 30.0,
) -> tuple[str | None, str | None]:
    """Publish a post to Ghost. Returns (external_id, error_message)."""
    base = admin_url.rstrip("/").replace("/ghost", "").rstrip("/")
    url = f"{base}/ghost/api/admin/posts/?source=html"
    try:
        token = _ghost_token(admin_key)
    except Exception as exc:
        return (None, f"Ghost token: {exc}")
    payload = {
        "posts": [
            {
                "title": title,
                "html": html_body,
                "status": status,
            }
        ],
    }
    headers = {
        "Authorization": f"Ghost {token}",
        "Content-Type": "application/json",
        "Accept-Version": "v5.0",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code in (200, 201):
            data = resp.json()
            posts = data.get("posts") or []
            if posts and isinstance(posts[0], dict):
                post_id = posts[0].get("id")
                if post_id:
                    logger.info(
                        "newsletter_providers.ghost_published",
                        extra={"post_id": post_id},
                    )
                    return (post_id, None)
            return ("ghost_unknown", None)
        body = resp.text[:200]
        logger.warning(
            "newsletter_providers.ghost_failed", extra={"status": resp.status_code}
        )
        return (None, f"Ghost API {resp.status_code}: {body}")
    except Exception as exc:
        logger.warning("newsletter_providers.ghost_error", extra={"error": str(exc)})
        return (None, str(exc))
