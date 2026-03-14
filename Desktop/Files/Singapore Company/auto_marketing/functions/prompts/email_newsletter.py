"""Email newsletter draft generation (weekly digest format)."""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

from pydantic import BaseModel


class NewsletterResult(BaseModel):
    subject: str = ""
    preview_text: str = ""
    html_body: str = ""
    plain_body: str = ""

    model_config = {"extra": "allow"}


SYSTEM_PROMPT = """You are writing a weekly email newsletter for a business.

The newsletter should:
- Recap the most interesting market developments from this week
- Tie insights back to the company's services and positioning
- Be concise (3-5 short sections)
- Have a clear, compelling subject line and preview text
- Include both HTML and plain-text versions

HTML should use simple, inline-styled tags. No external CSS.
Use headings, short paragraphs, and bold for emphasis.

Respond in JSON with fields: subject, preview_text, html_body, plain_body."""

TEMPERATURE = 0.6
RESPONSE_MODEL = NewsletterResult


def build_user_message(
    brand_context: list[dict],
    weekly_intel: list[dict],
    company_name: str = "",
    **kwargs,
) -> str:
    bc_lines = []
    for i, chunk in enumerate(brand_context, 1):
        text = chunk.get("text") or chunk.get("chunk_text", "")
        bc_lines.append(f"[{i}] {text}")
    bc_block = "\n".join(bc_lines) if bc_lines else "(none)"

    intel_lines = []
    for item in weekly_intel[:10]:
        title = item.get("title", "")
        summary = item.get("summary", "")
        intel_lines.append(f"- {title}: {summary}")
    intel_block = "\n".join(intel_lines) if intel_lines else "(none)"

    return f"""## Company: {company_name}

## Brand Context
{bc_block}

## This Week's Top Intelligence
{intel_block}

## Instructions
Write a weekly newsletter email recapping the most noteworthy items above.
Tie insights back to the company's positioning and services.
Keep it tight: 3-5 sections, each 2-3 sentences max.

OUTPUT FORMAT: Valid JSON with fields: subject, preview_text, html_body, plain_body."""
