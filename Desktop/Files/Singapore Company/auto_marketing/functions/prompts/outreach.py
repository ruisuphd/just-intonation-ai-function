"""LinkedIn DM and cold email outreach generation."""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

from shared.models import ColdEmailResult, LinkedInDMResult

LINKEDIN_DM_SYSTEM_PROMPT = """You are drafting a concise, professional LinkedIn DM for an AI consulting founder. Reference the specific signal that triggered outreach. Sound useful and observant, not salesy. Soft CTA only. Max 300 characters."""

COLD_EMAIL_SYSTEM_PROMPT = """You are drafting a concise cold outreach email for an AI consulting founder. Three short paragraphs only: hook (reference the signal), practical relevance, soft CTA. Make it feel specific and useful, not like a marketing blast. CAN-SPAM compliant. Include physical_address and unsubscribe_note as provided."""

LINKEDIN_DM_TEMPERATURE = 0.6
COLD_EMAIL_TEMPERATURE = 0.5

LINKEDIN_DM_RESPONSE_MODEL = LinkedInDMResult
COLD_EMAIL_RESPONSE_MODEL = ColdEmailResult


def build_linkedin_dm_message(
    brand_context: list[dict],
    intelligence_summaries: list[str],
    signal_summary: str,
    prospect_name: str | None = None,
    company_name: str | None = None,
    **kwargs,
) -> str:
    bc_lines = []
    for i, chunk in enumerate(brand_context, 1):
        text = chunk.get("text") or chunk.get("chunk_text", "")
        doc_type = chunk.get("doc_type", "other")
        bc_lines.append(f"[{i}] {text} (source: {doc_type})")

    intel_block = (
        "\n".join(intelligence_summaries) if intelligence_summaries else "(none)"
    )
    bc_block = "\n".join(bc_lines) if bc_lines else "(none)"

    prospect_info = []
    if prospect_name:
        prospect_info.append(f"Prospect: {prospect_name}")
    if company_name:
        prospect_info.append(f"Company: {company_name}")
    prospect_block = "\n".join(prospect_info) if prospect_info else "(not provided)"

    return f"""## Brand Context
{bc_block}

## Intelligence
{intel_block}

## Signal That Triggered Outreach
{signal_summary}

## Prospect
{prospect_block}

## Instructions
Generate a LinkedIn DM. Max 300 characters. Reference the signal, keep it specific, and avoid hype.

OUTPUT FORMAT: Valid JSON with field: message."""


def build_cold_email_message(
    brand_context: list[dict],
    intelligence_summaries: list[str],
    signal_summary: str,
    physical_address: str,
    unsubscribe_note: str,
    prospect_name: str | None = None,
    company_name: str | None = None,
    **kwargs,
) -> str:
    bc_lines = []
    for i, chunk in enumerate(brand_context, 1):
        text = chunk.get("text") or chunk.get("chunk_text", "")
        doc_type = chunk.get("doc_type", "other")
        bc_lines.append(f"[{i}] {text} (source: {doc_type})")

    intel_block = (
        "\n".join(intelligence_summaries) if intelligence_summaries else "(none)"
    )
    bc_block = "\n".join(bc_lines) if bc_lines else "(none)"

    prospect_info = []
    if prospect_name:
        prospect_info.append(f"Prospect: {prospect_name}")
    if company_name:
        prospect_info.append(f"Company: {company_name}")
    prospect_block = "\n".join(prospect_info) if prospect_info else "(not provided)"

    return f"""## Brand Context
{bc_block}

## Intelligence
{intel_block}

## Signal That Triggered Outreach
{signal_summary}

## Prospect
{prospect_block}

## CAN-SPAM Required
physical_address: {physical_address}
unsubscribe_note: {unsubscribe_note}

## Instructions
Generate a cold email. Three short paragraphs: hook (reference signal), value proposition, soft CTA.
Include physical_address and unsubscribe_note in the body as required for CAN-SPAM.

OUTPUT FORMAT: Valid JSON with fields: subject, body, physical_address, unsubscribe_note."""
