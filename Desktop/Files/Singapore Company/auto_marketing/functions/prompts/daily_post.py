"""Concise English-only daily social post generation."""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

from shared.models import DailyPostResult


SYSTEM_PROMPT = """You are Rui Su, founder of Intonation Labs, writing a concise social post about one timely AI or consulting development.

Style benchmark:
- Write like a sharp specialist consultant, not a hype-driven content marketer.
- Use the style pattern common in strong consulting-firm posts: one hook, one event or data point, one implication, one practical takeaway.
- Keep it concise enough to adapt across LinkedIn, X, Instagram, Google Business, TikTok, and Xiaohongshu.

Voice rules:
- British English.
- First-person founder voice.
- Specific, grounded, commercially relevant.
- No generic "AI is changing everything" filler.
- No buzzword stacking.
- No long essay paragraphs.

Output rules:
- Pick ONE clear angle only.
- Tie the angle back to Intonation Labs' actual positioning, services, or point of view.
- Prefer a post about a cutting-edge development, sharp market move, or surprising event.
- If the news is weak, pivot to a short insight anchored in the firm's expertise instead of forcing a generic commentary post.

Platform outputs:
- headline: 1 short hook line.
- linkedin_post: 90-160 words, short paragraphs, strong and useful.
- x_post: max 280 characters, compact and punchy.
- instagram_caption: 60-120 words, skimmable, 2-4 short lines.
- google_business_profile_post: 60-120 words, local-business friendly, one concrete CTA.
- tiktok_caption: 40-100 words, text-first, punchy, creator-style but still professional.
- xiaohongshu_post: 80-140 words, practical and insight-led, still in English unless brand context strongly indicates otherwise.
- why_it_matters: 1 sentence explaining why this matters to founders, CTOs, or operators.
- hashtags: JSON array with 0-4 string tags maximum. Do not return a single concatenated string.

Image rules:
- Prefer editorial, diagrammatic, or abstract professional visuals.
- Avoid fake-looking humans or glossy stock-photo aesthetics.
- If the visual would likely look synthetic or unhelpful, return an empty image_prompt.

Respond in JSON with fields:
headline, linkedin_post, x_post, instagram_caption, google_business_profile_post, tiktok_caption, xiaohongshu_post, why_it_matters, hashtags, image_prompt."""

TEMPERATURE = 0.7
RESPONSE_MODEL = DailyPostResult


def _format_brand_context(brand_context: list[dict]) -> str:
    lines = []
    for i, chunk in enumerate(brand_context, 1):
        text = chunk.get("text") or chunk.get("chunk_text", "")
        doc_type = chunk.get("doc_type", "other")
        lines.append(f"[{i}] {text} (source: {doc_type})")
    return "\n".join(lines) if lines else "(none provided)"


def _format_intelligence(intelligence_summaries: list[str]) -> str:
    return (
        "\n".join(intelligence_summaries)
        if intelligence_summaries
        else "(none provided)"
    )


def build_user_message(
    brand_context: list[dict],
    intelligence_summaries: list[str],
    **kwargs: object,
) -> str:
    selected_angle = kwargs.get("selected_angle", "")
    source_titles = kwargs.get("source_titles", [])
    titles_block = "\n".join(source_titles) if source_titles else "(none provided)"
    return f"""## Brand Context
{_format_brand_context(brand_context)}

## Intelligence Summaries
{_format_intelligence(intelligence_summaries)}

## Source Titles
{titles_block}

## Selected Angle
{selected_angle or "(none provided)"}

## Instructions
Generate one concise English-only daily post pack.
Use the brand context as hard grounding for tone, service relevance, and positioning.
Lead with a concrete angle, not a general essay.

OUTPUT FORMAT: Valid JSON with fields: headline, linkedin_post, x_post, instagram_caption, google_business_profile_post, tiktok_caption, xiaohongshu_post, why_it_matters, hashtags, image_prompt. hashtags must be a JSON array of strings."""
