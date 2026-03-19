import asyncio
import logging

import vertexai
from vertexai.generative_models import Content, GenerativeModel, Part

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self) -> None:
        vertexai.init(
            project=settings.gcp_project,
            location=settings.VERTEX_AI_LOCATION,
        )

    async def invoke(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
        audio_bytes: bytes | None = None,
    ) -> str:
        model = GenerativeModel(
            settings.GEMINI_MODEL,
            system_instruction=system_prompt,
        )

        contents: list[Content] = []
        for i, msg in enumerate(messages):
            role = "user" if msg.get("role") == "user" else "model"
            text = msg.get("content", "")
            parts: list[Part] = [Part.from_text(text)]

            # Augment the last user message with audio if provided
            is_last = i == len(messages) - 1
            if audio_bytes and is_last and msg.get("role") == "user":
                parts.append(Part.from_data(audio_bytes, "audio/wav"))

            contents.append(Content(role=role, parts=parts))

        generation_config = {"max_output_tokens": max_tokens}

        def _generate() -> str:
            response = model.generate_content(
                contents,
                generation_config=generation_config,
            )
            return response.text

        try:
            return await asyncio.to_thread(_generate)
        except Exception as e:
            logger.exception("Gemini invoke failed: %s", e)
            raise


gemini_client = GeminiClient()
