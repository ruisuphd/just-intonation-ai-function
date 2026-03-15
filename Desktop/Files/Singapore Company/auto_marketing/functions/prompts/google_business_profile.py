"""Google Business Profile post generation (max 1500 chars)."""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

from pydantic import BaseModel


class GBPPostResult(BaseModel):
    title: str = ""
    body: str = ""
    call_to_action: str = ""
    image_prompt: str = ""

    model_config = {"extra": "allow"}


SYSTEM_PROMPT = """You are writing a Google Business Profile (GBP) post for a business owner.

GBP posts appear on Google Maps and local search results. They should be:
- Short and scannable (max 1500 characters total, including title)
- Focused on a single local-relevant angle: an event, update, offer, or industry insight
- Written in the first person company voice
- Include a clear call-to-action (e.g. "Book a free consultation", "Visit us today")

Respond in JSON with fields: title, body, call_to_action, image_prompt.
If no good image prompt comes to mind, return image_prompt as an empty string."""

TEMPERATURE = 0.7
RESPONSE_MODEL = GBPPostResult


def build_user_message(
    brand_context: list[dict],
    intelligence_summaries: list[str],
    **kwargs,
) -> str:
    bc_lines = []
    for i, chunk in enumerate(brand_context, 1):
        text = chunk.get("text") or chunk.get("chunk_text", "")
        doc_type = chunk.get("doc_type", "other")
        bc_lines.append(f"[{i}] {text} (source: {doc_type})")
    bc_block = "\n".join(bc_lines) if bc_lines else "(none)"
    intel_block = (
        "\n".join(intelligence_summaries) if intelligence_summaries else "(none)"
    )

    return f"""## Brand Context
{bc_block}

## Recent Intelligence
{intel_block}

## Instructions
Write a Google Business Profile post. Keep total length under 1500 characters.
Focus on a concrete, locally relevant angle drawn from the intelligence or brand context.
Include a clear call-to-action.

OUTPUT FORMAT: Valid JSON with fields: title, body, call_to_action, image_prompt."""
