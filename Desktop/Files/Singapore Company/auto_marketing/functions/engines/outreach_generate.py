from __future__ import annotations

from datetime import datetime, timezone

from prompts.outreach import (
    COLD_EMAIL_RESPONSE_MODEL,
    COLD_EMAIL_SYSTEM_PROMPT,
    COLD_EMAIL_TEMPERATURE,
    LINKEDIN_DM_RESPONSE_MODEL,
    LINKEDIN_DM_SYSTEM_PROMPT,
    LINKEDIN_DM_TEMPERATURE,
    build_cold_email_message,
    build_linkedin_dm_message,
)
from shared.gemini_client import GeminiClient
from shared.firestore_client import add_doc, get_doc, query_docs, update_doc
from shared.logger import get_logger
from shared.retriever import Retriever

logger = get_logger("engine.outreach_generate")

_EU_EEA_COUNTRIES = frozenset(
    [
        "austria",
        "belgium",
        "bulgaria",
        "croatia",
        "cyprus",
        "czech",
        "denmark",
        "estonia",
        "finland",
        "france",
        "germany",
        "greece",
        "hungary",
        "ireland",
        "italy",
        "latvia",
        "lithuania",
        "luxembourg",
        "malta",
        "netherlands",
        "poland",
        "portugal",
        "romania",
        "slovakia",
        "slovenia",
        "spain",
        "sweden",
        "iceland",
        "norway",
        "liechtenstein",
        "uk",
        "united kingdom",
    ]
)


def _extract_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.strip().split("@")[-1].lower()


def _check_suppress_list(email: str | None, *, tenant_id: str | None = None) -> bool:
    """Return True if email or its domain appears on the suppress list."""
    if not email:
        return False
    email_lower = email.strip().lower()
    domain = _extract_domain(email)

    email_hits = query_docs(
        "suppress_list",
        filters=[("type", "==", "email"), ("value", "==", email_lower)],
        limit=1,
        tenant_id=tenant_id,
    )
    if email_hits:
        return True

    if domain:
        domain_hits = query_docs(
            "suppress_list",
            filters=[("type", "==", "domain"), ("value", "==", domain)],
            limit=1,
            tenant_id=tenant_id,
        )
        if domain_hits:
            return True

    return False


def _gdpr_applicable(location: str) -> bool:
    if not location:
        return False
    loc_lower = location.lower()
    return any(country in loc_lower for country in _EU_EEA_COUNTRIES)


def _recommend_channel(signal_data: dict) -> tuple[str, str]:
    signal_type = signal_data.get("signal_type") or ""
    if signal_type in {"funding_received", "hiring_ai_role"}:
        return (
            "Email",
            "A direct email is stronger when the signal is tied to expansion, hiring, or a formal business trigger.",
        )
    if signal_type in {"pain_point_expressed", "digital_transformation_signal"}:
        return (
            "LinkedIn",
            "A lighter LinkedIn approach fits better when the signal is exploratory or based on a visible operational pain point.",
        )
    return (
        "LinkedIn",
        "Start with a lower-friction conversation before moving into a more formal outreach sequence.",
    )


async def generate_outreach_inline(
    lead_data: dict,
    signal_data: dict,
    *,
    tenant_id: str | None = None,
    tier: str = "starter",
) -> dict:
    """Generate LinkedIn DM and cold email without Firestore storage.

    Used by the pipeline to draft outreach immediately after qualification.
    Results are included directly in the daily email.

    Args:
        lead_data: Dict from qualify_inline() with icp_fit, company_name, etc.
        signal_data: ProspectSignal dict with summary, title, etc.

    Returns:
        Dict with linkedin_dm (str) and cold_email (dict with subject, body).
    """
    logger.info(
        "outreach_generate.generate_outreach_inline.start",
        extra={"company": lead_data.get("company_name", "unknown")},
    )

    tenant_scope = (
        tenant_id or lead_data.get("tenant_id") or signal_data.get("tenant_id") or None
    )
    signal_summary = signal_data.get("summary") or signal_data.get("title") or ""
    query = (
        f"{lead_data.get('company_name', '')} "
        f"{lead_data.get('suggested_outreach_angle', '')} "
        f"{signal_summary}"
    ).strip()

    retriever = Retriever(top_k=6, tenant_id=tenant_scope)
    chunks, _ = retriever.retrieve(query, language="en")
    direct_chunks = query_docs(
        "brand_chunks",
        filters=[
            ("doc_type", "in", ["brand_voice", "service_description", "outreach_guide"])
        ],
        limit=8,
        tenant_id=tenant_scope,
    )
    seen: set[tuple[object, object]] = set()
    merged_chunks: list[dict] = []
    for chunk in direct_chunks + chunks:
        key = (chunk.get("document_id"), chunk.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        merged_chunks.append(chunk)
    brand_context = [
        {"text": c.get("text", ""), "doc_type": c.get("doc_type", "other")}
        for c in merged_chunks
    ]

    comp = get_doc("system_config", "compliance") or {}
    physical_address = comp.get("physical_address") or ""
    unsubscribe_email = comp.get("unsubscribe_email") or ""
    unsubscribe_note = (
        f"To unsubscribe, reply UNSUBSCRIBE or email {unsubscribe_email}."
        if unsubscribe_email
        else ""
    )

    client = GeminiClient()
    recommended_channel, channel_reason = _recommend_channel(signal_data)

    linkedin_msg = build_linkedin_dm_message(
        brand_context=brand_context,
        intelligence_summaries=[],
        signal_summary=signal_summary,
        company_name=lead_data.get("company_name"),
    )
    linkedin_result = await client.generate(
        LINKEDIN_DM_SYSTEM_PROMPT,
        linkedin_msg,
        temperature=LINKEDIN_DM_TEMPERATURE,
        response_model=LINKEDIN_DM_RESPONSE_MODEL,
        task_name="outreach",
        tier=tier,
    )

    cold_email_msg = build_cold_email_message(
        brand_context=brand_context,
        intelligence_summaries=[],
        signal_summary=signal_summary,
        physical_address=physical_address,
        unsubscribe_note=unsubscribe_note,
        company_name=lead_data.get("company_name"),
    )
    cold_result = await client.generate(
        COLD_EMAIL_SYSTEM_PROMPT,
        cold_email_msg,
        temperature=COLD_EMAIL_TEMPERATURE,
        response_model=COLD_EMAIL_RESPONSE_MODEL,
        task_name="outreach",
        tier=tier,
    )

    logger.info(
        "outreach_generate.generate_outreach_inline.done",
        extra={"company": lead_data.get("company_name", "unknown")},
    )
    return {
        "recommended_channel": recommended_channel,
        "channel_reason": channel_reason,
        "linkedin_dm": linkedin_result.message,
        "cold_email": {
            "subject": cold_result.subject,
            "body": cold_result.body,
            "physical_address": cold_result.physical_address or physical_address,
            "unsubscribe_note": cold_result.unsubscribe_note or unsubscribe_note,
        },
    }


async def run_generate(lead_id: str, *, tenant_id: str | None = None) -> dict:
    logger.info("outreach_generate.run_generate.start", extra={"lead_id": lead_id})

    # --- 1. Fetch lead ---
    lead = get_doc("qualified_leads", lead_id, tenant_id=tenant_id)
    if not lead and tenant_id is None:
        lead = get_doc("qualified_leads", lead_id)
    if not lead:
        raise ValueError(f"Lead {lead_id} not found")

    tenant_scope = tenant_id or lead.get("tenant_id") or None

    # --- 2. Validate at least one contact method ---
    has_email = bool(lead.get("contact_email"))
    has_linkedin = bool(lead.get("contact_linkedin_url"))
    if not has_email and not has_linkedin:
        raise ValueError("Lead must have contact_email or contact_linkedin_url")

    # --- 3. Suppress list check ---
    if has_email and _check_suppress_list(
        lead["contact_email"], tenant_id=tenant_scope
    ):
        raise ValueError("Contact or domain is on suppress list")

    # --- 4. Fetch linked signal ---
    signal = None
    if lead.get("signal_id"):
        signal = get_doc("prospect_signals", lead["signal_id"], tenant_id=tenant_scope)
        if not signal and tenant_scope is None:
            signal = get_doc("prospect_signals", lead["signal_id"])
    signal_summary = ""
    if signal:
        signal_summary = signal.get("summary") or signal.get("title") or ""

    # --- 5. RAG retrieval ---
    query = (
        f"{lead.get('company_name', '')} "
        f"{lead.get('suggested_outreach_angle', '')} "
        f"{signal_summary}"
    ).strip()
    retriever = Retriever(top_k=8, tenant_id=tenant_scope)
    chunks, _ = retriever.retrieve(query, language="en")
    direct_chunks = query_docs(
        "brand_chunks",
        filters=[
            ("doc_type", "in", ["brand_voice", "service_description", "outreach_guide"])
        ],
        limit=8,
        tenant_id=tenant_scope,
    )
    seen: set[tuple[object, object]] = set()
    merged_chunks: list[dict] = []
    for chunk in direct_chunks + chunks:
        key = (chunk.get("document_id"), chunk.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        merged_chunks.append(chunk)
    brand_context = [
        {"text": c.get("text", ""), "doc_type": c.get("doc_type", "other")}
        for c in merged_chunks
    ]
    brand_chunk_ids = [c.get("id", "") for c in merged_chunks if c.get("id")]

    # --- 6. Compliance config ---
    comp = get_doc("system_config", "compliance") or {}
    physical_address = comp.get("physical_address") or ""
    unsubscribe_email = comp.get("unsubscribe_email") or ""
    unsubscribe_note = (
        f"To unsubscribe, reply with UNSUBSCRIBE or email {unsubscribe_email}."
        if unsubscribe_email
        else ""
    )

    # --- 7. Compliance flags ---
    company_location = lead.get("company_location") or ""
    casl_warning = "canada" in company_location.lower()
    gdpr_applicable = _gdpr_applicable(company_location)

    client = GeminiClient()
    now = datetime.now(timezone.utc)

    linkedin_msg = build_linkedin_dm_message(
        brand_context=brand_context,
        intelligence_summaries=[],
        signal_summary=signal_summary,
        prospect_name=lead.get("contact_name"),
        company_name=lead.get("company_name"),
    )
    linkedin_result = await client.generate(
        LINKEDIN_DM_SYSTEM_PROMPT,
        linkedin_msg,
        temperature=LINKEDIN_DM_TEMPERATURE,
        response_model=LINKEDIN_DM_RESPONSE_MODEL,
        task_name="outreach",
    )

    cold_email_msg = build_cold_email_message(
        brand_context=brand_context,
        intelligence_summaries=[],
        signal_summary=signal_summary,
        physical_address=physical_address,
        unsubscribe_note=unsubscribe_note,
        prospect_name=lead.get("contact_name"),
        company_name=lead.get("company_name"),
    )
    cold_result = await client.generate(
        COLD_EMAIL_SYSTEM_PROMPT,
        cold_email_msg,
        temperature=COLD_EMAIL_TEMPERATURE,
        response_model=COLD_EMAIL_RESPONSE_MODEL,
        task_name="outreach",
    )

    final_address = cold_result.physical_address or physical_address
    final_unsub = cold_result.unsubscribe_note or unsubscribe_note
    can_spam_ok = bool(final_address.strip() and final_unsub.strip())

    # --- 10. Store drafts with compliance flags ---
    shared_flags = {
        "casl_warning": casl_warning,
        "gdpr_applicable": gdpr_applicable,
        "suppress_list_checked": True,
        "human_reviewed": False,
    }

    linkedin_dm_data = {
        "tenant_id": tenant_scope or "",
        "lead_id": lead_id,
        "company_name": lead.get("company_name", ""),
        "draft_type": "linkedin_dm",
        "content": {"message": linkedin_result.message},
        "compliance_flags": {**shared_flags, "can_spam_ok": True},
        "status": "pending_human_review",
        "compliance_checklist_completed": False,
        "generated_at": now,
        "brand_chunk_ids": brand_chunk_ids,
    }
    linkedin_dm_id = add_doc(
        "outreach_drafts", linkedin_dm_data, tenant_id=tenant_scope
    )

    cold_email_data = {
        "tenant_id": tenant_scope or "",
        "lead_id": lead_id,
        "company_name": lead.get("company_name", ""),
        "draft_type": "cold_email",
        "content": {
            "subject": cold_result.subject,
            "body": cold_result.body,
            "physical_address": final_address,
            "unsubscribe_note": final_unsub,
        },
        "compliance_flags": {**shared_flags, "can_spam_ok": can_spam_ok},
        "status": "pending_human_review",
        "compliance_checklist_completed": False,
        "generated_at": now,
        "brand_chunk_ids": brand_chunk_ids,
    }
    cold_email_id = add_doc("outreach_drafts", cold_email_data, tenant_id=tenant_scope)

    # --- 11. Update lead status ---
    update_doc(
        "qualified_leads",
        lead_id,
        {"status": "outreach_drafted"},
        tenant_id=tenant_scope,
    )

    # --- 12. Return ---
    compliance_flags = {**shared_flags, "can_spam_ok": can_spam_ok}
    result = {
        "linkedin_dm_id": linkedin_dm_id,
        "cold_email_id": cold_email_id,
        "compliance_flags": compliance_flags,
    }
    logger.info(
        "outreach_generate.run_generate.done",
        extra={
            "lead_id": lead_id,
            "linkedin_dm_id": linkedin_dm_id,
            "cold_email_id": cold_email_id,
        },
    )
    return result


async def run(
    *,
    lead_id: str = "",
    tenant_id: str | None = None,
    request=None,
    cloud_event=None,
) -> dict | None:
    """Backward-compatible wrapper. Delegates to run_generate."""
    if not lead_id and request:
        body = request.get_json(silent=True) or {}
        lead_id = body.get("lead_id", "")
        tenant_id = tenant_id or body.get("tenant_id")

    if not lead_id:
        logger.error("outreach_generate.missing_lead_id")
        return None

    try:
        return await run_generate(lead_id, tenant_id=tenant_id)
    except ValueError as exc:
        msg = str(exc)
        logger.warning("outreach_generate.validation_error", extra={"error": msg})
        if "suppress list" in msg.lower():
            return {"suppressed": True, "reason": msg}
        return None
