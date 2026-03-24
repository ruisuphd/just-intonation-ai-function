import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.i18n.locale_maps import tts_voice_for_ui_locale
from app.services.coach.audio_prompt import build_user_content_with_audio
from app.services.coach.base import BaseCoach
from app.services.coach.welcome_i18n import build_coach_welcome
from app.services.llm.gemini import gemini_client
from app.services.llm.prompts import (
    COACH_METRICS_TRUST_NOTE,
    GUITAR_COACH_PROMPT,
    GUITAR_COACH_RAG_SECTION,
    SESSION_MODE_PERFORMANCE_ADDON,
    SESSION_MODE_PRACTICE_ADDON,
    coach_output_language_addon,
    coach_universal_addons,
)
from app.services.rag.retriever import retriever
from app.services.storage import storage_service
from app.services.tts.polly import polly_client

logger = logging.getLogger(__name__)


class GuitarCoach(BaseCoach):
    coach_type = "guitar"

    async def _build_system_prompt(self, user_text: str, use_rag: bool = True) -> str:
        query = f"guitar technique {user_text}" if user_text else "guitar pedagogy"
        context = await retriever.retrieve_context(query, top_k=3) if use_rag else ""
        rag_block = GUITAR_COACH_RAG_SECTION.format(context=context) if context else ""
        return GUITAR_COACH_PROMPT.format(rag_context=rag_block)

    async def _prepare_llm_turn(
        self,
        user_text: str,
        audio_analysis: dict | None,
        session_history: list[dict],
        *,
        use_rag: bool,
        learner_context: str,
        command_hint: str,
        session_stage_hint: str,
        practice_mode: bool,
        tts_in_prompt: bool,
        locale: str,
    ) -> tuple[list[dict], str]:
        messages: list[dict] = []
        for entry in session_history:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            messages.append({"role": role, "content": content})

        user_content = build_user_content_with_audio(user_text, audio_analysis)
        messages.append({"role": "user", "content": user_content})

        system_prompt = await self._build_system_prompt(user_text, use_rag=use_rag)
        system_prompt += COACH_METRICS_TRUST_NOTE
        system_prompt += coach_output_language_addon(locale)
        system_prompt += (
            SESSION_MODE_PRACTICE_ADDON if practice_mode else SESSION_MODE_PERFORMANCE_ADDON
        )
        system_prompt += coach_universal_addons(use_tts=tts_in_prompt)
        if learner_context:
            system_prompt += f"\n\nStudent context (from prior sessions): {learner_context}"
        hint_parts = [x for x in (command_hint, session_stage_hint) if x]
        if hint_parts:
            system_prompt += "\n\n" + "\n\n".join(hint_parts)
        return messages, system_prompt

    async def stream_message(
        self,
        user_text: str,
        audio_analysis: dict | None,
        session_history: list[dict],
        *,
        use_rag: bool = True,
        audio_bytes: bytes | None = None,
        learner_context: str = "",
        command_hint: str = "",
        session_stage_hint: str = "",
        practice_mode: bool = True,
        locale: str = "en",
    ) -> AsyncIterator[str]:
        messages, system_prompt = await self._prepare_llm_turn(
            user_text,
            audio_analysis,
            session_history,
            use_rag=use_rag,
            learner_context=learner_context,
            command_hint=command_hint,
            session_stage_hint=session_stage_hint,
            practice_mode=practice_mode,
            tts_in_prompt=False,
            locale=locale,
        )
        async for part in gemini_client.invoke_stream(
            system_prompt=system_prompt,
            messages=messages,
            audio_bytes=audio_bytes,
        ):
            yield part

    async def process_message(
        self,
        user_text: str,
        audio_analysis: dict | None,
        session_history: list[dict],
        *,
        use_rag: bool = True,
        audio_bytes: bytes | None = None,
        learner_context: str = "",
        command_hint: str = "",
        session_stage_hint: str = "",
        use_tts: bool = False,
        practice_mode: bool = True,
        locale: str = "en",
    ) -> dict:
        messages, system_prompt = await self._prepare_llm_turn(
            user_text,
            audio_analysis,
            session_history,
            use_rag=use_rag,
            learner_context=learner_context,
            command_hint=command_hint,
            session_stage_hint=session_stage_hint,
            practice_mode=practice_mode,
            tts_in_prompt=use_tts,
            locale=locale,
        )

        reply = await gemini_client.invoke(
            system_prompt=system_prompt,
            messages=messages,
            audio_bytes=audio_bytes,
        )

        audio_url = None
        if use_tts:
            try:
                lang, voice = tts_voice_for_ui_locale(locale)
                tts_bytes = await polly_client.synthesize(
                    reply, language_code=lang, voice_name=voice
                )
                key = f"tts/{uuid.uuid4()}.mp3"
                audio_url = await storage_service.upload(tts_bytes, key, "audio/mpeg")
            except Exception:
                logger.debug("TTS generation skipped", exc_info=True)

        return {
            "reply": reply,
            "audio_url": audio_url,
            "analysis": audio_analysis,
        }

    async def get_welcome_message(
        self,
        skill_profile: dict[str, Any] | None = None,
        *,
        locale: str = "en",
    ) -> str:
        return build_coach_welcome(self.coach_type, skill_profile, locale)
