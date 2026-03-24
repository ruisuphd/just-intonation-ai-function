"""Marketing AI chatbot route — powered by Gemini Flash Lite via Vertex AI."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError, field_validator

from fastapi.responses import JSONResponse, StreamingResponse

from api.middleware.legal import require_legal_acceptance_verified
from shared.chat_schema import ChatStructuredReply
from shared.errors import RATE_LIMITED, build_error_body
from shared.usage_limits import check_limit, increment_usage
from shared.firestore_client import update_tenant
from shared.gemini_client import GeminiClient, _capture_healing_event, _extract_json
from shared.logger import get_logger
from shared.models import TenantProfile
from shared.redis_client import cache_delete_pattern

logger = get_logger("api.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])

_gemini = GeminiClient()

_MAX_CHAT_MESSAGES = 40
_MAX_CHAT_PAYLOAD_CHARS = 32000

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

_SYSTEM_PROMPT_TEMPLATE = """You are the IntoMarketing Assistant — a helpful AI that helps users configure their marketing workspace and improve their brand settings.

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

    @field_validator("messages")
    @classmethod
    def _limit_payload(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if len(v) > _MAX_CHAT_MESSAGES:
            raise ValueError(f"Too many messages (max {_MAX_CHAT_MESSAGES})")
        total = sum(len(m.content) for m in v)
        if total > _MAX_CHAT_PAYLOAD_CHARS:
            raise ValueError(
                "Conversation too long; shorten your message and try again."
            )
        return v


class ChatResponse(BaseModel):
    reply: str
    settings_updated: dict = {}
    suggested_questions: list[str] = []


async def _parse_stream_chat_json(text: str, tier: str) -> ChatStructuredReply:
    stripped = text.strip()
    if not stripped:
        return ChatStructuredReply()
    try:
        parsed = _extract_json(stripped)
        return ChatStructuredReply.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as exc:
        repaired = await _gemini._repair_structured_output(
            stripped,
            str(exc),
            ChatStructuredReply,
            tier,
        )
        if repaired is not None:
            return repaired
        logger.warning(
            "chat.stream_parse_failed",
            extra={"error": str(exc), "snippet": stripped[:200]},
        )
        _capture_healing_event(
            "chat.parse_repair_failed",
            task_name="marketing_chat_stream",
        )
        return ChatStructuredReply(
            reply="Something didn't format quite right on our side. Please try again, or rephrase your question.",
            settings_to_update={},
            suggested_questions=[
                "Tell me about my company profile",
                "What can you help me with?",
            ],
        )


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    tenant: TenantProfile = Depends(require_legal_acceptance_verified),
):
    if not body.messages:
        return ChatResponse(
            reply="Hi! I'm your Marketing Assistant. How can I help you today?"
        )

    tier = getattr(request.state, "tenant_tier", "starter")
    allowed, _, limit = check_limit(
        tenant.tenant_id, tier, "chat_messages_per_day", tenant.timezone
    )
    if not allowed:
        trace_id = getattr(request.state, "trace_id", None)
        body = build_error_body(
            error_code=RATE_LIMITED,
            detail="Daily chat limit reached",
            trace_id=trace_id,
            status_code=429,
            extras={
                "limit": limit,
                "tier": tier,
                "upgrade_url": "/billing",
            },
        )
        return JSONResponse(status_code=429, content=body)

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
        structured = await _gemini.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.6,
            max_tokens=512,
            task_name="marketing_chat",
            tier=tenant.subscription_tier or "starter",
            response_model=ChatStructuredReply,
        )

        reply = structured.reply
        settings_to_update = structured.settings_to_update
        suggested_questions = structured.suggested_questions

        # Apply allowed settings updates
        applied: dict = {}
        if settings_to_update:
            safe_updates = {
                k: v for k, v in settings_to_update.items() if k in _UPDATABLE_FIELDS
            }
            if safe_updates:
                update_tenant(tenant.tenant_id, safe_updates)
                # Bust the tenant cache so dashboard reflects changes immediately
                cache_delete_pattern(f"tenant:uid:{tenant.owner_uid}*")
                applied = safe_updates
                logger.info(
                    "chat.settings_updated",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "fields": list(safe_updates.keys()),
                    },
                )

        increment_usage(tenant.tenant_id, "chat_messages_per_day", tenant.timezone)
        return ChatResponse(
            reply=reply,
            settings_updated=applied,
            suggested_questions=suggested_questions[:3],
        )

    except Exception as exc:
        trace_id = getattr(request.state, "trace_id", None)
        logger.error(
            "chat.error",
            extra={
                "tenant_id": tenant.tenant_id,
                "error": str(exc),
                "exc_type": type(exc).__name__,
                "trace_id": trace_id,
            },
            exc_info=True,
        )
        try:
            import sentry_sdk

            if trace_id:
                sentry_sdk.set_tag("trace_id", trace_id)
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass
        return ChatResponse(
            reply="I'm having trouble right now. Please try again in a moment.",
            suggested_questions=[
                "Tell me about my company profile",
                "What can you help me with?",
            ],
        )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    tenant: TenantProfile = Depends(require_legal_acceptance_verified),
):
    """Same as POST /api/chat but streams model output as SSE (delta + final JSON)."""
    if not body.messages:

        async def empty():
            yield _sse(
                {
                    "done": True,
                    "reply": "Hi! I'm your Marketing Assistant. How can I help you today?",
                    "settings_updated": {},
                    "suggested_questions": [],
                }
            )

        return StreamingResponse(
            empty(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    tier = getattr(request.state, "tenant_tier", "starter")
    allowed, _, limit = check_limit(
        tenant.tenant_id, tier, "chat_messages_per_day", tenant.timezone
    )
    if not allowed:
        trace_id = getattr(request.state, "trace_id", None)
        body = build_error_body(
            error_code=RATE_LIMITED,
            detail="Daily chat limit reached",
            trace_id=trace_id,
            status_code=429,
            extras={
                "limit": limit,
                "tier": tier,
                "upgrade_url": "/billing",
            },
        )
        return JSONResponse(status_code=429, content=body)

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

    history_parts = []
    for msg in body.messages[:-1]:
        prefix = "User" if msg.role == "user" else "Assistant"
        history_parts.append(f"{prefix}: {msg.content}")

    last_message = body.messages[-1].content
    if history_parts:
        user_message = "\n".join(history_parts) + f"\nUser: {last_message}"
    else:
        user_message = last_message

    async def event_gen():
        buf: list[str] = []
        try:
            async for piece in _gemini.generate_stream_text(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.6,
                max_tokens=512,
                task_name="marketing_chat",
                tier=tenant.subscription_tier or "starter",
                response_mime_json=True,
            ):
                buf.append(piece)
                yield _sse({"delta": piece})

            text = "".join(buf)
            parsed = await _parse_stream_chat_json(
                text,
                tenant.subscription_tier or "starter",
            )
            reply = parsed.reply
            settings_to_update = parsed.settings_to_update
            suggested_questions = parsed.suggested_questions

            applied: dict = {}
            if settings_to_update:
                safe_updates = {
                    k: v
                    for k, v in settings_to_update.items()
                    if k in _UPDATABLE_FIELDS
                }
                if safe_updates:
                    update_tenant(tenant.tenant_id, safe_updates)
                    cache_delete_pattern(f"tenant:uid:{tenant.owner_uid}*")
                    applied = safe_updates
                    logger.info(
                        "chat.settings_updated",
                        extra={
                            "tenant_id": tenant.tenant_id,
                            "fields": list(safe_updates.keys()),
                        },
                    )

            increment_usage(tenant.tenant_id, "chat_messages_per_day", tenant.timezone)
            yield _sse(
                {
                    "done": True,
                    "reply": reply,
                    "settings_updated": applied,
                    "suggested_questions": suggested_questions[:3],
                }
            )
        except Exception as exc:
            trace_id = getattr(request.state, "trace_id", None)
            logger.error(
                "chat.stream_error",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(exc),
                    "exc_type": type(exc).__name__,
                    "trace_id": trace_id,
                },
                exc_info=True,
            )
            try:
                import sentry_sdk

                if trace_id:
                    sentry_sdk.set_tag("trace_id", trace_id)
                sentry_sdk.capture_exception(exc)
            except Exception:
                pass
            yield _sse(
                {
                    "done": True,
                    "reply": "I'm having trouble right now. Please try again in a moment.",
                    "settings_updated": {},
                    "suggested_questions": [
                        "Tell me about my company profile",
                        "What can you help me with?",
                    ],
                    "error": True,
                }
            )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
