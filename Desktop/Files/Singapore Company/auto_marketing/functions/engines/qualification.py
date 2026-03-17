from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prompts.icp_qualifier import (
    SYSTEM_PROMPT,
    TEMPERATURE,
    build_user_message,
)
from shared.gemini_client import GeminiClient
from shared.firestore_client import add_doc, get_doc, query_docs, update_doc
from shared.logger import get_logger
from shared.models import ICPQualificationResult, QualifiedLead
from shared.retriever import Retriever

logger = get_logger("engine.qualification")

_DEFAULT_SERVICES = [
    "AI strategy consulting",
    "Custom ML model development",
    "Data pipeline engineering",
    "AI integration & deployment",
    "AI training & workshops",
]


async def qualify_inline(signal_data: dict, *, tenant_id: str | None = None, tier: str = "starter") -> dict:
    """Qualify a prospect signal inline without Firestore lead storage.

    Used by the pipeline to qualify signals immediately after detection.
    The result is included directly in the daily email — no lead document created.

    Args:
        signal_data: ProspectSignal dict as returned by signals.run_and_classify().

    Returns:
        Dict with icp_fit, icp_fit_score, company_name, suggested_outreach_angle, etc.
    """
    logger.info(
        "qualification.qualify_inline.start",
        extra={"company": signal_data.get("company_name", "unknown")},
    )

    tenant_scope = tenant_id or signal_data.get("tenant_id") or None
    query_text = signal_data.get("summary") or signal_data.get("title", "")

    icp_chunks = query_docs(
        "brand_chunks",
        filters=[("doc_type", "==", "icp_definition")],
        limit=5,
        tenant_id=tenant_scope,
    )
    case_study_chunks = query_docs(
        "brand_chunks",
        filters=[("doc_type", "==", "case_study")],
        limit=3,
        tenant_id=tenant_scope,
    )

    retriever = Retriever(tenant_id=tenant_scope)
    rag_chunks, _ = retriever.retrieve(query_text)
    rag_icp = [c for c in rag_chunks if c.get("doc_type") == "icp_definition"]
    rag_case = [c for c in rag_chunks if c.get("doc_type") == "case_study"]

    seen_ids: set[str] = set()
    merged_icp: list[dict] = []
    for c in icp_chunks + rag_icp:
        cid = c.get("id", "")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            merged_icp.append(c)
    merged_case: list[dict] = []
    for c in case_study_chunks + rag_case:
        cid = c.get("id", "")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            merged_case.append(c)

    icp_texts = [c.get("text", "") for c in merged_icp if c.get("text")]
    case_texts = [c.get("text", "") for c in merged_case if c.get("text")]

    svc_chunks = query_docs(
        "brand_chunks",
        filters=[("doc_type", "==", "service_description")],
        limit=10,
        tenant_id=tenant_scope,
    )
    firm_services = [
        c.get("text", "") for c in svc_chunks if c.get("text")
    ] or _DEFAULT_SERVICES

    user_msg = build_user_message(
        signal_summary=query_text,
        icp_chunks=icp_texts,
        case_study_chunks=case_texts,
        firm_services=firm_services,
    )

    client = GeminiClient()
    result: ICPQualificationResult = await client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        temperature=TEMPERATURE,
        response_model=ICPQualificationResult,
        task_name="icp_qualifier",
        tier=tier,
    )

    logger.info(
        "qualification.qualify_inline.done",
        extra={"icp_fit": result.icp_fit, "score": result.icp_fit_score},
    )
    return {
        "company_name": signal_data.get("company_name", ""),
        "company_location": signal_data.get("company_location"),
        "icp_fit": result.icp_fit,
        "icp_fit_score": result.icp_fit_score,
        "icp_reasoning": result.reasoning,
        "matching_services": result.matching_services,
        "suggested_outreach_angle": result.suggested_outreach_angle,
    }


async def run_qualify(
    signal_id: str,
    contact_data: dict | None = None,
    user_uid: str = "",
    tenant_id: str | None = None,
) -> dict:
    logger.info("qualification.run_qualify.start", extra={"signal_id": signal_id})

    signal = get_doc("prospect_signals", signal_id, tenant_id=tenant_id)
    if not signal and tenant_id is None:
        signal = get_doc("prospect_signals", signal_id)
    if not signal:
        raise ValueError(f"Signal {signal_id} not found")

    tenant_scope = tenant_id or signal.get("tenant_id") or None

    if signal.get("status") != "new":
        raise ValueError(
            f"Signal {signal_id} has status '{signal.get('status')}', expected 'new'"
        )

    query_text = signal.get("summary") or signal.get("title", "")

    # --- RAG: type-specific Firestore queries ---
    icp_chunks = query_docs(
        "brand_chunks",
        filters=[("doc_type", "==", "icp_definition")],
        limit=5,
        tenant_id=tenant_scope,
    )
    case_study_chunks = query_docs(
        "brand_chunks",
        filters=[("doc_type", "==", "case_study")],
        limit=3,
        tenant_id=tenant_scope,
    )

    # --- RAG: semantic retrieval, then merge & deduplicate ---
    retriever = Retriever(tenant_id=tenant_scope)
    rag_chunks, _ = retriever.retrieve(query_text)
    rag_icp = [c for c in rag_chunks if c.get("doc_type") == "icp_definition"]
    rag_case = [c for c in rag_chunks if c.get("doc_type") == "case_study"]

    seen_ids: set[str] = set()

    merged_icp: list[dict] = []
    for c in icp_chunks + rag_icp:
        cid = c.get("id", "")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            merged_icp.append(c)

    merged_case: list[dict] = []
    for c in case_study_chunks + rag_case:
        cid = c.get("id", "")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            merged_case.append(c)

    icp_texts = [c.get("text", "") for c in merged_icp if c.get("text")]
    case_texts = [c.get("text", "") for c in merged_case if c.get("text")]
    chunk_ids = [c.get("id", "") for c in merged_icp + merged_case if c.get("id")]

    # --- Firm services from service_description chunks, fallback to config ---
    svc_chunks = query_docs(
        "brand_chunks",
        filters=[("doc_type", "==", "service_description")],
        limit=10,
        tenant_id=tenant_scope,
    )
    firm_services = [c.get("text", "") for c in svc_chunks if c.get("text")]
    if not firm_services:
        config_doc = get_doc("system_config", "generation_config")
        firm_services = (config_doc or {}).get("firm_services", _DEFAULT_SERVICES)

    user_msg = build_user_message(
        signal_summary=query_text,
        icp_chunks=icp_texts,
        case_study_chunks=case_texts,
        firm_services=firm_services,
    )

    client = GeminiClient()
    result: ICPQualificationResult = await client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        temperature=TEMPERATURE,
        response_model=ICPQualificationResult,
        task_name="icp_qualifier",
    )

    now = datetime.now(timezone.utc)
    cd = contact_data or {}

    lead = QualifiedLead(
        tenant_id=tenant_scope or "",
        signal_id=signal_id,
        company_name=signal.get("company_name", ""),
        company_location=signal.get("company_location"),
        icp_fit=result.icp_fit,
        icp_fit_score=result.icp_fit_score,
        icp_reasoning=result.reasoning,
        matching_services=result.matching_services,
        suggested_outreach_angle=result.suggested_outreach_angle,
        brand_chunk_ids=chunk_ids,
        contact_name=cd.get("contact_name"),
        contact_title=cd.get("contact_title"),
        contact_email=cd.get("contact_email"),
        contact_linkedin_url=cd.get("contact_linkedin_url"),
        status="qualified",
        is_pinned=False,
        qualified_at=now,
        qualified_by=user_uid,
        created_at=now,
        expires_at=now + timedelta(days=365),
    )

    lead_id = add_doc("qualified_leads", lead.model_dump(), tenant_id=tenant_scope)

    try:
        update_doc(
            "prospect_signals",
            signal_id,
            {"status": "qualified"},
            tenant_id=tenant_scope,
        )
    except Exception as exc:
        logger.warning(
            "qualification.signal_update_error",
            extra={"signal_id": signal_id, "error": str(exc)},
        )

    lead_data = lead.model_dump()
    lead_data["lead_id"] = lead_id

    logger.info(
        "qualification.run_qualify.done",
        extra={
            "lead_id": lead_id,
            "icp_fit": result.icp_fit,
            "icp_fit_score": result.icp_fit_score,
        },
    )
    return lead_data


async def run(*, request=None, cloud_event=None) -> dict | None:
    """HTTP-trigger wrapper. Parses request body and delegates to run_qualify."""
    logger.info("qualification.run.start")

    if request is None:
        logger.error("qualification.no_request")
        return {"error": "qualification requires an HTTP request"}

    body = request.get_json(silent=True) or {}
    signal_id = body.get("signal_id")
    tenant_id = body.get("tenant_id")
    if not signal_id:
        logger.error("qualification.missing_signal_id")
        return {"error": "signal_id is required"}

    contact_data = {
        "contact_name": body.get("contact_name"),
        "contact_title": body.get("contact_title"),
        "contact_email": body.get("contact_email"),
        "contact_linkedin_url": body.get("contact_linkedin_url"),
    }

    user_uid = ""
    if hasattr(request, "headers"):
        user_uid = request.headers.get("X-User-Email") or ""

    try:
        lead_data = await run_qualify(
            signal_id, contact_data, user_uid, tenant_id=tenant_id
        )
        return {
            "lead_id": lead_data["lead_id"],
            "icp_fit": lead_data.get("icp_fit"),
            "icp_fit_score": lead_data.get("icp_fit_score"),
        }
    except ValueError as exc:
        logger.error("qualification.validation_error", extra={"error": str(exc)})
        return {"error": str(exc)}
    except Exception as exc:
        logger.error("qualification.error", extra={"error": str(exc)})
        return {"error": f"Qualification failed: {exc}"}
