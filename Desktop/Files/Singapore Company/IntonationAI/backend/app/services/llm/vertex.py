import asyncio
import logging

from anthropic import AnthropicVertex

from app.core.config import settings

logger = logging.getLogger(__name__)


class VertexClient:
    def __init__(self) -> None:
        project_id = settings.gcp_project
        if not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT or FIREBASE_PROJECT_ID must be set")
        self._client = AnthropicVertex(
            project_id=project_id,
            region=settings.VERTEX_AI_LOCATION,
        )
        self._model = settings.VERTEX_AI_MODEL

    def _format_messages(self, messages: list[dict]) -> list[dict]:
        formatted: list[dict] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            formatted.append({"role": role, "content": content})
        return formatted

    async def invoke(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> str:
        formatted = self._format_messages(messages)

        def _invoke() -> str:
            response = self._client.messages.create(
                model=self._model,
                system=system_prompt,
                messages=formatted,
                max_tokens=max_tokens,
            )
            text_parts: list[str] = []
            for block in response.content:
                if getattr(block, "text", None):
                    text_parts.append(block.text)
            return "".join(text_parts)

        try:
            return await asyncio.to_thread(_invoke)
        except Exception as e:
            logger.exception("Vertex invoke failed: %s", e)
            raise


vertex_client = VertexClient()
