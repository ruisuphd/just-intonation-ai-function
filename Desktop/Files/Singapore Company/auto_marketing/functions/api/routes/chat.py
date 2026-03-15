"""Marketing AI chatbot route — powered by Gemini Flash Lite via Vertex AI."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.middleware.auth import require_tenant
from shared.firestore_client import get_tenant, update_tenant
from shared.gemini_client import GeminiClient
from shared.logger import get_logger
from shared.models import TenantProfile
from shared.redis_client import cache_delete_pattern

logger = get_logger("api.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])

_gemini = GeminiClient()

# Fields the bot is allowed to update
_UPDATABLE_FIELDS = {
    "company_name": "Company name",
    "industry": "Industry / sector",
    "description": "Company description (max 500 chars)",
    "target_audience": "Target audience description (max 500 chars)",
    "competitor_names": "List of competitor names (max 5)",
    "industry_keywords": "List of industry keywords (max 10)",
    "tone": "Tone: one of professional | friendly | authoritative | casual",
    "tone_formal_casual": "Formal-to-casual tone scale (0=very formal, 100=very casual)",
    "tone_technical_accessible": "Technical-to-accessible scale (0=very technical, 100=very accessible)",
    "language": "Content language: en | zh | bilingual",
    "daily_digest_enabled": "Whether daily email digest is enabled (true/false)",
    "daily_digest_email": "Email address for daily digest",
    "notification_time": "Notification time in HH:MM format (e.g. 08:00)",
    "timezone": "IANA timezone name (e.g. Asia/Singapore)",
}

_SYSTEM_PROMPT_TEMPLATE = """You are the AutoMark Marketing Assistant — a helpful AI that helps users configure their marketing workspace and improve their brand settings.

## Current workspace profile:
{profile_json}

## Your capabilities:
You can have a natural conversation AND optionally update the user's workspace settings.

When the user wants to update their profile, extract the changes and include them in `settings_to_update`.

## Updatable fields:
{fields_doc}

## Response format:
Always respond with valid JSON in this exact shape:
{{
  "reply": "Your conversational reply here (friendly, concise, 1-3 sentences)",
  "settings_to_update": {{}},
  "suggested_questions": ["Question 1?", "Question 2?", "Question 3?"]
}}

Rules:
- `settings_to_update` should only contain fields that the user explicitly wants to change. Leave it empty {{}} if no changes.
- For list fields (competitor_names, industry_keywords), always return the complete new list.
- `suggested_questions` should be 2-3 relevant follow-up questions based on the conversation.
- Be encouraging and friendly. Use first-person ("I've updated...").
- Keep replies concise (1-3 sentences max).
- Never mention JSON or technical internals to the user.
- If asked something outside marketing/settings, gently redirect to your purpose.
"""


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    reply: str
    settings_updated: dict = {}
    suggested_questions: list[str] = []


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    tenant: TenantProfile = Depends(require_tenant),
):
    if not body.messages:
        return ChatResponse(reply="Hi! I'm your Marketing Assistant. How can I help you today?")

    # Build profile summary for the system prompt
    profile = {
        "company_name": tenant.company_name,
        "industry": tenant.industry,
        "description": tenant.description,
        "target_audience": tenant.target_audience,
        "competitor_names": tenant.competitor_names or [],
        "industry_keywords": tenant.industry_keywords or [],
        "tone": tenant.tone,
        "tone_formal_casual": tenant.tone_formal_casual,
        "tone_technical_accessible": tenant.tone_technical_accessible,
        "language": tenant.language,
        "platforms_enabled": tenant.platforms_enabled or [],
        "daily_digest_enabled": tenant.daily_digest_enabled,
        "notification_time": getattr(tenant, "notification_time", "07:00"),
        "timezone": getattr(tenant, "timezone", "Asia/Singapore"),
    }
    fields_doc = "\n".join(f"- `{k}`: {v}" for k, v in _UPDATABLE_FIELDS.items())
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        profile_json=json.dumps(profile, indent=2),
        fields_doc=fields_doc,
    )

    # Build the conversation as a single user message for Gemini
    # (Gemini Flash Lite does not support multi-turn via generate_content easily,
    #  so we format the history as a single prompt)
    history_parts = []
    for msg in body.messages[:-1]:  # all but last
        prefix = "User" if msg.role == "user" else "Assistant"
        history_parts.append(f"{prefix}: {msg.content}")

    last_message = body.messages[-1].content
    if history_parts:
        user_message = "\n".join(history_parts) + f"\nUser: {last_message}"
    else:
        user_message = last_message

    try:
        raw = await _gemini.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.6,
            max_tokens=512,
            task_name="marketing_chat",
            tier=tenant.subscription_tier or "starter",
        )

        # Parse structured response
        try:
            data = json.loads(raw) if isinstance(raw, str) else {}
        except Exception:
            data = {}

        reply = data.get("reply", str(raw))
        settings_to_update = data.get("settings_to_update", {})
        suggested_questions = data.get("suggested_questions", [])

        # Apply allowed settings updates
        applied: dict = {}
        if settings_to_update:
            safe_updates = {k: v for k, v in settings_to_update.items() if k in _UPDATABLE_FIELDS}
            if safe_updates:
                update_tenant(tenant.tenant_id, safe_updates)
                # Bust the tenant cache so dashboard reflects changes immediately
                cache_delete_pattern(f"tenant:uid:{tenant.owner_uid}*")
                applied = safe_updates
                logger.info(
                    "chat.settings_updated",
                    extra={"tenant_id": tenant.tenant_id, "fields": list(safe_updates.keys())},
                )

        return ChatResponse(
            reply=reply,
            settings_updated=applied,
            suggested_questions=suggested_questions[:3],
        )

    except Exception as exc:
        logger.error("chat.error", extra={"tenant_id": tenant.tenant_id, "error": str(exc)})
        return ChatResponse(
            reply="I'm having trouble right now. Please try again in a moment.",
            suggested_questions=["Tell me about my company profile", "What can you help me with?"],
        )
