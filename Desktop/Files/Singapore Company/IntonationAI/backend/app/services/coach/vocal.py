import logging
import uuid

from app.services.coach.base import BaseCoach
from app.services.llm.gemini import gemini_client
from app.services.llm.prompts import VOCAL_COACH_PROMPT, VOCAL_COACH_RAG_SECTION
from app.services.tts.polly import polly_client
from app.services.storage import storage_service
from app.services.rag.retriever import retriever

logger = logging.getLogger(__name__)


class VocalCoach(BaseCoach):
    coach_type = "vocal"

    async def _build_system_prompt(
        self, user_text: str, use_rag: bool = True
    ) -> str:
        context = (
            await retriever.retrieve_context(user_text, top_k=3)
            if use_rag
            else ""
        )
        if context:
            rag_block = VOCAL_COACH_RAG_SECTION.format(context=context)
        else:
            rag_block = ""
        return VOCAL_COACH_PROMPT.format(rag_context=rag_block)

    async def process_message(
        self,
        user_text: str,
        audio_analysis: dict | None,
        session_history: list[dict],
        *,
        use_rag: bool = True,
        audio_bytes: bytes | None = None,
    ) -> dict:
        messages: list[dict] = []
        for entry in session_history:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            messages.append({"role": role, "content": content})

        user_content = user_text
        if audio_analysis:
            user_content += f"\n\n[Audio metrics]: {audio_analysis}"
        messages.append({"role": "user", "content": user_content})

        system_prompt = await self._build_system_prompt(user_text, use_rag=use_rag)

        reply = await gemini_client.invoke(
            system_prompt=system_prompt,
            messages=messages,
            audio_bytes=audio_bytes,
        )

        audio_url = None
        try:
            tts_bytes = await polly_client.synthesize(reply)
            key = f"tts/{uuid.uuid4()}.mp3"
            audio_url = await storage_service.upload(tts_bytes, key, "audio/mpeg")
        except Exception:
            logger.debug("TTS generation skipped", exc_info=True)

        return {
            "reply": reply,
            "audio_url": audio_url,
            "analysis": audio_analysis,
        }

    async def get_welcome_message(self) -> str:
        return (
            "Hi! I'm your AI vocal coach. Sing or speak into the mic, and I'll analyse "
            "your pitch, rhythm, and technique to give you specific, actionable feedback. "
            "Let's get started!"
        )
