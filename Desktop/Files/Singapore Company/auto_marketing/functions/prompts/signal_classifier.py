"""B2B buying signal classification."""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

from shared.models import SignalClassificationResult

SYSTEM_PROMPT = """You are a B2B sales intelligence analyst identifying buying signals for an AI consulting firm. Be precise about company attribution. Only classify as a buying signal if there is a concrete, actionable indicator."""

TEMPERATURE = 0.2
RESPONSE_MODEL = SignalClassificationResult


def build_user_message(
    raw_title: str,
    raw_content: str,
    signal_types: list[str],
    target_industries: list[str],
    **kwargs,
) -> str:
    signal_types_text = "\n".join(f"- {s}" for s in signal_types)
    target_industries_text = "\n".join(f"- {i}" for i in target_industries)
    return f"""## Title
{raw_title}

## Content
{raw_content}

## Signal Types
{signal_types_text}

## Target Industries
{target_industries_text}

## Instructions
Classify this item: is it a buying signal? If yes, assign signal_type, strength_score (1-5), company_name, and reasoning.
Only mark is_buying_signal=true when there is a concrete, actionable indicator.
If is_buying_signal=false, set signal_type to null, strength_score to 0, company_name to an empty string, and still provide a short summary.

OUTPUT FORMAT: Valid JSON with fields: is_buying_signal, signal_type, strength_score, company_name, reasoning, summary."""
