"""Lead enrichment providers (Apollo, etc.)."""

from __future__ import annotations


import httpx

from shared.logger import get_logger
from shared.secrets import get_secret_or_env

logger = get_logger("enrichment_providers")

APOLLO_API = "https://api.apollo.io/api/v1"


async def enrich_from_linkedin_url(linkedin_url: str) -> dict | None:
    """Enrich using Apollo People API with LinkedIn URL. Returns person data or None."""
    api_key = get_secret_or_env(secret_id="apollo-api-key", env_var="APOLLO_API_KEY")
    if not api_key:
        logger.warning("enrichment_providers.apollo_not_configured")
        return None

    url = f"{APOLLO_API}/people/match"
    params = {"linkedin_url": linkedin_url}
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, params=params, headers=headers)
        if resp.status_code != 200:
            logger.warning(
                "enrichment_providers.apollo_failed", extra={"status": resp.status_code}
            )
            return None
        data = resp.json()
        person = data.get("person")
        if not person:
            return None
        return person
    except Exception as exc:
        logger.warning("enrichment_providers.apollo_error", extra={"error": str(exc)})
        return None


def _apollo_experience_to_list(experiences: list | None) -> list[dict]:
    if not experiences:
        return []
    out = []
    for exp in experiences[:5]:
        if not isinstance(exp, dict):
            continue
        org = exp.get("organization") or {}
        company = (
            org.get("name", "")
            if isinstance(org, dict)
            else str(exp.get("company_name", ""))
        )
        start = exp.get("start_date") or {}
        end = exp.get("end_date") or {}
        if isinstance(start, dict) and isinstance(end, dict):
            duration = f"{start.get('month', '')}/{start.get('year', '')} - {end.get('month', '')}/{end.get('year', '')}".strip(
                " -/"
            )
        else:
            duration = ""
        out.append(
            {
                "title": str(exp.get("title") or ""),
                "company": str(company),
                "duration": duration,
            }
        )
    return out
