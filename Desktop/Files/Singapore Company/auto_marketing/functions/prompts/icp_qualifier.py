"""ICP (Ideal Customer Profile) qualification."""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

from shared.models import ICPQualificationResult

SYSTEM_PROMPT = """You are a B2B sales strategist evaluating prospect-firm fit for Intonation Labs.

The firm is strongest when the work is close to production ML, GenAI/RAG systems, agentic AI, real-time AI systems, or practical AI strategy for startups and SMEs.

Be honest. A low score is more useful than a flattering one. Do not invent fit where it does not exist."""

TEMPERATURE = 0.3
RESPONSE_MODEL = ICPQualificationResult


def build_user_message(
    signal_summary: str,
    icp_chunks: list[str],
    case_study_chunks: list[str],
    firm_services: list[str],
    **kwargs,
) -> str:
    icp_block = "\n".join(icp_chunks) if icp_chunks else "(none)"
    case_block = "\n".join(case_study_chunks) if case_study_chunks else "(none)"
    services_block = "\n".join(f"- {s}" for s in firm_services)
    return f"""## Signal Summary
{signal_summary}

## ICP Definition
{icp_block}

## Case Studies
{case_block}

## Firm Services
{services_block}

## Instructions
Score this prospect against the ICP. Use icp_fit: "high" | "medium" | "low" and icp_fit_score 0.0-1.0.
Be honest -- low score is better than false high.
Favour practical consulting fit over broad AI interest.

OUTPUT FORMAT: Valid JSON with fields: icp_fit, icp_fit_score, reasoning, matching_services, suggested_outreach_angle."""
