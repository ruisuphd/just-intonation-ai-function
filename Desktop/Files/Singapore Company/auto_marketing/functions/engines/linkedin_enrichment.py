from shared.enrichment_providers import (
    enrich_from_linkedin_url,
    _apollo_experience_to_list,
)
from shared.firestore_client import get_doc, update_doc
from shared.logger import get_logger

logger = get_logger("engine.linkedin_enrichment")


async def enrich_lead(tenant_id: str, lead_id: str):
    """Enrich lead from LinkedIn URL using Apollo (or mock when not configured)."""
    logger.info(
        "linkedin_enrichment.enrich_lead.start",
        extra={"tenant_id": tenant_id, "lead_id": lead_id},
    )

    lead = get_doc("qualified_leads", lead_id, tenant_id=tenant_id)
    if not lead:
        logger.warning(
            "linkedin_enrichment.enrich_lead.not_found",
            extra={"tenant_id": tenant_id, "lead_id": lead_id},
        )
        return

    linkedin_url = lead.get("contact_linkedin_url")
    if not linkedin_url:
        logger.warning(
            "linkedin_enrichment.enrich_lead.no_url",
            extra={"tenant_id": tenant_id, "lead_id": lead_id},
        )
        update_doc(
            "qualified_leads",
            lead_id,
            {"enrichment_status": "failed"},
            tenant_id=tenant_id,
        )
        return

    person = await enrich_from_linkedin_url(linkedin_url)
    if person:
        headline = person.get("headline") or ""
        experiences = (
            person.get("employment_history") or person.get("experiences") or []
        )
        about = headline
        if person.get("bio"):
            about = f"{headline}\n\n{person.get('bio', '')}".strip()
        updates = {
            "linkedin_about": about or "No summary available.",
            "recent_experience": _apollo_experience_to_list(experiences),
            "recent_posts": person.get("recent_posts") or [],
            "enrichment_status": "completed",
        }
        if person.get("email"):
            updates["contact_email"] = person.get("email")
    else:
        mock_about = "Enrichment provider not configured or unavailable."
        mock_experience = [
            {
                "title": "—",
                "company": lead.get("company_name", "Unknown"),
                "duration": "",
            },
        ]
        updates = {
            "linkedin_about": mock_about,
            "recent_experience": mock_experience,
            "recent_posts": [],
            "enrichment_status": "completed",
        }

    update_doc("qualified_leads", lead_id, updates, tenant_id=tenant_id)
    logger.info(
        "linkedin_enrichment.enrich_lead.done",
        extra={"tenant_id": tenant_id, "lead_id": lead_id},
    )
