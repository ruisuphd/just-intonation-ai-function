"""Intelligence relevance scoring for AI consulting firm news items."""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

from shared.models import IntelligenceScoreResult


SYSTEM_PROMPT = """You are an AI industry analyst selecting news that is both commercially relevant and worth turning into a strong consulting social post.

The firm specialises in production ML, GenAI/RAG systems, agentic AI, and real-time AI systems.

Score each item on two dimensions:
- relevance_score: how relevant this is to the firm's services and clients
- postability_score: how strong this is as a sharp social post angle

Prefer:
- major consulting or enterprise AI moves
- meaningful funding or strategic bets
- policy, platform, or operating-model shifts with business consequences
- concrete events over vague trend talk

Respond in JSON with fields:
summary, relevance_score, relevance_reasoning, tags, postability_score, suggested_angle, why_now."""

TEMPERATURE = 0.2
RESPONSE_MODEL = IntelligenceScoreResult


def build_user_message(
    raw_title: str,
    raw_content: str,
    firm_services: list[str],
    target_verticals: list[str],
    **kwargs: object,
) -> str:
    firm_services_text = "\n".join(f"- {s}" for s in firm_services)
    target_verticals_text = "\n".join(f"- {v}" for v in target_verticals)
    return f"""## Title
{raw_title}

## Content
{raw_content}

## Firm Services
{firm_services_text}

## Target Verticals
{target_verticals_text}

## Instructions
Summarise the item, score both relevance and postability (0.0-1.0), explain why it matters, and suggest a sharp posting angle.

OUTPUT FORMAT: Valid JSON with fields: summary, relevance_score, relevance_reasoning, tags, postability_score, suggested_angle, why_now."""
